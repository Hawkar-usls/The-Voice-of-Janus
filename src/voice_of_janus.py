#!/usr/bin/env python3
"""The Voice of Janus v0.1.

Reads a JSON chamber preset, calculates rectangular-room acoustic modes,
renders a deterministic modal WAV, and writes a JSON provenance receipt.

Standard-library only by design.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import wave
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION = "0.1"


@dataclass(frozen=True)
class Mode:
    p: int
    q: int
    r: int
    physical_hz: float
    mode_class: str
    render_hz: float
    octave_multiplier: int


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), raw


def require_positive_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and > 0")
    return number


def classify_mode(p: int, q: int, r: int) -> str:
    nonzero = sum(v != 0 for v in (p, q, r))
    if nonzero == 1:
        return "axial"
    if nonzero == 2:
        return "tangential"
    if nonzero == 3:
        return "oblique"
    raise ValueError("mode indices cannot all be zero")


def octave_translate(freq: float, minimum_hz: float) -> tuple[float, int]:
    render_hz = freq
    multiplier = 1
    while render_hz < minimum_hz:
        render_hz *= 2.0
        multiplier *= 2
    return render_hz, multiplier


def calculate_modes(config: dict[str, Any]) -> list[Mode]:
    geometry = config.get("geometry_m", {})
    lx = require_positive_number(geometry.get("Lx"), "geometry_m.Lx")
    ly = require_positive_number(geometry.get("Ly"), "geometry_m.Ly")
    lz = require_positive_number(geometry.get("Lz"), "geometry_m.Lz")

    environment = config.get("environment", {})
    c = require_positive_number(
        environment.get("speed_of_sound_m_s", 343.0),
        "environment.speed_of_sound_m_s",
    )

    solver = config.get("solver", {})
    max_index = int(solver.get("max_index", 5))
    if max_index < 1:
        raise ValueError("solver.max_index must be >= 1")
    frequency_limit = require_positive_number(
        solver.get("frequency_limit_hz", 240.0),
        "solver.frequency_limit_hz",
    )

    creative = config.get("creative_translation", {})
    creative_enabled = bool(creative.get("enabled", False))
    minimum_audible = require_positive_number(
        creative.get("minimum_audible_hz", 20.0),
        "creative_translation.minimum_audible_hz",
    )

    modes: list[Mode] = []
    for p in range(max_index + 1):
        for q in range(max_index + 1):
            for r in range(max_index + 1):
                if p == q == r == 0:
                    continue
                freq = (c / 2.0) * math.sqrt(
                    (p / lx) ** 2 + (q / ly) ** 2 + (r / lz) ** 2
                )
                if freq > frequency_limit:
                    continue

                render_hz = freq
                multiplier = 1
                if creative_enabled:
                    render_hz, multiplier = octave_translate(freq, minimum_audible)

                modes.append(
                    Mode(
                        p=p,
                        q=q,
                        r=r,
                        physical_hz=round(freq, 9),
                        mode_class=classify_mode(p, q, r),
                        render_hz=round(render_hz, 9),
                        octave_multiplier=multiplier,
                    )
                )

    modes.sort(key=lambda m: (m.physical_hz, m.p, m.q, m.r))
    if not modes:
        raise ValueError("zero usable modes: check geometry and frequency limit")
    return modes


def select_render_modes(config: dict[str, Any], modes: list[Mode]) -> list[Mode]:
    render = config.get("render", {})
    minimum = require_positive_number(render.get("min_render_hz", 20.0), "render.min_render_hz")
    maximum = require_positive_number(render.get("max_render_hz", 220.0), "render.max_render_hz")
    if maximum <= minimum:
        raise ValueError("render.max_render_hz must be > render.min_render_hz")

    max_modes = int(render.get("max_render_modes", 12))
    if max_modes < 1:
        raise ValueError("render.max_render_modes must be >= 1")

    selected = [m for m in modes if minimum <= m.render_hz <= maximum][:max_modes]
    if not selected:
        raise ValueError("zero renderable modes in configured render band")
    return selected


def render_wav(config: dict[str, Any], modes: list[Mode], out_path: Path) -> dict[str, Any]:
    render = config.get("render", {})
    sample_rate = int(render.get("sample_rate_hz", 44100))
    if sample_rate < 8000 or sample_rate > 384000:
        raise ValueError("render.sample_rate_hz must be between 8000 and 384000")

    duration = require_positive_number(render.get("duration_s", 8.0), "render.duration_s")
    master_gain = float(render.get("master_gain", 0.85))
    if not 0.0 < master_gain <= 1.0:
        raise ValueError("render.master_gain must be > 0 and <= 1")

    fade_s = float(render.get("fade_s", 0.08))
    if fade_s < 0.0 or fade_s * 2.0 >= duration:
        raise ValueError("render.fade_s must be >= 0 and less than half the duration")

    frame_count = int(round(duration * sample_rate))
    fade_frames = int(round(fade_s * sample_rate))
    nyquist = sample_rate / 2.0
    for mode in modes:
        if mode.render_hz >= nyquist:
            raise ValueError(f"render frequency {mode.render_hz} Hz exceeds Nyquist")

    # Equal-energy weighting with a gentle preference for lower physical modes.
    weights = [1.0 / math.sqrt(index + 1.0) for index in range(len(modes))]
    weight_sum = sum(weights)

    pcm = bytearray()
    peak = 0.0
    samples: list[float] = []

    for n in range(frame_count):
        t = n / sample_rate
        sample = 0.0
        for weight, mode in zip(weights, modes):
            sample += weight * math.sin(2.0 * math.pi * mode.render_hz * t)
        sample /= weight_sum

        envelope = 1.0
        if fade_frames > 0:
            if n < fade_frames:
                envelope = n / fade_frames
            elif n >= frame_count - fade_frames:
                envelope = (frame_count - 1 - n) / fade_frames
                envelope = max(0.0, envelope)
        sample *= envelope
        samples.append(sample)
        peak = max(peak, abs(sample))

    normalization = master_gain / peak if peak > 0 else 0.0
    for sample in samples:
        value = max(-1.0, min(1.0, sample * normalization))
        pcm.extend(struct.pack("<h", int(round(value * 32767.0))))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))

    wav_bytes = out_path.read_bytes()
    return {
        "sample_rate_hz": sample_rate,
        "duration_s": duration,
        "channels": 1,
        "sample_width_bits": 16,
        "frames": frame_count,
        "normalization_gain": normalization,
        "sha256": sha256_bytes(wav_bytes),
        "bytes": len(wav_bytes),
    }


def write_receipt(
    config_path: Path,
    config_raw: bytes,
    config: dict[str, Any],
    modes: list[Mode],
    selected_modes: list[Mode],
    wav_path: Path,
    wav_meta: dict[str, Any],
    receipt_path: Path,
) -> None:
    receipt = {
        "receipt_type": "JANUS_VOICE_RENDER_RECEIPT",
        "engine_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": {
            "path": str(config_path),
            "id": config.get("id"),
            "schema_version": config.get("schema_version"),
            "status": config.get("status"),
            "claim_boundary": config.get("claim_boundary"),
            "sha256": sha256_bytes(config_raw),
        },
        "equation": "f_pqr = (c/2)*sqrt((p/Lx)^2 + (q/Ly)^2 + (r/Lz)^2)",
        "calculated_mode_count": len(modes),
        "calculated_modes": [asdict(mode) for mode in modes],
        "rendered_mode_count": len(selected_modes),
        "rendered_modes": [asdict(mode) for mode in selected_modes],
        "output": {
            "path": str(wav_path),
            **wav_meta,
        },
        "epistemic_boundary": {
            "predicted_modes_are_measurements": False,
            "intentional_ancient_tuning_established": False,
            "creative_translation_enabled": bool(
                config.get("creative_translation", {}).get("enabled", False)
            ),
        },
    }

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JANUS geometry-to-resonance audio renderer")
    parser.add_argument("preset", type=Path, help="Input JSON preset")
    parser.add_argument("--out", type=Path, default=Path("voice_of_janus.wav"), help="Output WAV path")
    parser.add_argument(
        "--receipt",
        type=Path,
        default=Path("receipts/last_render.json"),
        help="Output JSON provenance receipt",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config, raw = load_json(args.preset)
    modes = calculate_modes(config)
    selected = select_render_modes(config, modes)
    wav_meta = render_wav(config, selected, args.out)
    write_receipt(args.preset, raw, config, modes, selected, args.out, wav_meta, args.receipt)

    print(f"JANUS Voice v{VERSION}")
    print(f"Calculated modes: {len(modes)}")
    print(f"Rendered modes:   {len(selected)}")
    print(f"WAV:              {args.out}")
    print(f"Receipt:          {args.receipt}")
    print("Rendered frequencies (Hz):")
    print(", ".join(f"{mode.render_hz:.3f}" for mode in selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
