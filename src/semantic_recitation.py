#!/usr/bin/env python3
"""Recite a semantic projection through the JANUS Pyramid Language tract.

Pipeline:
  JSON semantic field -> local dry TTS -> model-based Pyramid Language DSP -> WAV + receipt

The TTS backend supplies articulation only. Acoustic identity is applied by
``pyramid_dsp.ModalAcousticFilter``. No network access or automatic playback is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pyramid_dsp import build_filter_from_preset, derive_acoustic_modes, load_preset

VERSION = "0.1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return parsed, raw


def require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return value


def read_semantic_text(source_json: dict[str, Any], field: str) -> str:
    value = source_json.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"source field {field!r} must be a non-empty string")
    return value


def run_espeak(text: str, config: dict[str, Any], dry_path: Path) -> dict[str, Any]:
    backend = str(config.get("backend", ""))
    if backend != "espeak":
        raise ValueError("only allowlisted local backend 'espeak' is implemented")
    executable = shutil.which("espeak")
    if executable is None:
        raise RuntimeError("espeak executable was not found")

    voice = str(config.get("voice", "ru"))
    speed = int(config.get("speed_wpm", 145))
    pitch = int(config.get("pitch", 42))
    amplitude = int(config.get("amplitude", 175))
    if not 80 <= speed <= 450:
        raise ValueError("larynx.speed_wpm must be within 80..450")
    if not 0 <= pitch <= 99:
        raise ValueError("larynx.pitch must be within 0..99")
    if not 0 <= amplitude <= 200:
        raise ValueError("larynx.amplitude must be within 0..200")

    dry_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
        tmp.write(text)
        text_path = Path(tmp.name)
    try:
        completed = subprocess.run(
            [
                executable,
                "-v", voice,
                "-s", str(speed),
                "-p", str(pitch),
                "-a", str(amplitude),
                "-f", str(text_path),
                "-w", str(dry_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    finally:
        text_path.unlink(missing_ok=True)

    return {
        "backend": backend,
        "voice": voice,
        "speed_wpm": speed,
        "pitch": pitch,
        "amplitude": amplitude,
        "stderr": completed.stderr.strip(),
    }


def load_pcm16_mono(path: Path) -> tuple[int, list[float]]:
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frame_count = wav.getnframes()
        raw = wav.readframes(frame_count)
    if channels != 1:
        raise ValueError("dry TTS WAV must be mono")
    if width != 2:
        raise ValueError("dry TTS WAV must be PCM16")
    values = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    return sample_rate, [value / 32768.0 for value in values]


def write_pcm16_mono(path: Path, sample_rate: int, samples: list[float]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = bytearray()
    peak = 0.0
    for sample in samples:
        value = max(-1.0, min(1.0, float(sample)))
        peak = max(peak, abs(value))
        pcm.extend(struct.pack("<h", int(round(value * 32767.0))))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(pcm))
    raw = path.read_bytes()
    return {
        "sample_rate_hz": sample_rate,
        "channels": 1,
        "sample_width_bits": 16,
        "frames": len(samples),
        "duration_s": len(samples) / sample_rate,
        "peak": peak,
        "bytes": len(raw),
        "sha256": sha256_bytes(raw),
    }


def render(config_path: Path, output_override: Path | None, receipt_override: Path | None) -> dict[str, Any]:
    config, config_raw = load_json(config_path)
    source_cfg = require_mapping(config.get("source"), "source")
    larynx_cfg = require_mapping(config.get("larynx"), "larynx")
    language_cfg = require_mapping(config.get("language_operator"), "language_operator")
    output_cfg = require_mapping(config.get("output"), "output")

    source_path = Path(str(source_cfg.get("path")))
    source, source_raw = load_json(source_path)
    field = str(source_cfg.get("field", "semantic_projection_ru"))
    text = read_semantic_text(source, field)
    required_formula = str(source_cfg.get("required_formula", ""))
    if required_formula and required_formula not in text:
        raise ValueError("required canonical formula is missing from semantic projection")

    preset_path = Path(str(language_cfg.get("preset")))
    preset = load_preset(preset_path)
    mode_count = int(language_cfg.get("mode_count", 8))
    minimum_hz = float(language_cfg.get("minimum_hz", 35.0))
    maximum_hz = float(language_cfg.get("maximum_hz", 900.0))
    modes = derive_acoustic_modes(
        preset,
        count=mode_count,
        minimum_hz=minimum_hz,
        maximum_hz=maximum_hz,
    )

    output_path = output_override or Path(str(output_cfg.get("default_path")))
    receipt_path = receipt_override or Path(str(output_cfg.get("default_receipt")))

    with tempfile.TemporaryDirectory(prefix="janus_recitation_") as tmp_dir:
        dry_path = Path(tmp_dir) / "dry.wav"
        larynx_meta = run_espeak(text, larynx_cfg, dry_path)
        dry_raw = dry_path.read_bytes()
        sample_rate, dry_samples = load_pcm16_mono(dry_path)

        filter_, rebuilt_modes = build_filter_from_preset(
            preset,
            sample_rate_hz=sample_rate,
            mode_count=mode_count,
            decay_s=float(language_cfg.get("decay_s", 0.32)),
            wet=float(language_cfg.get("wet", 0.72)),
            dry=float(language_cfg.get("dry", 0.62)),
            output_gain=float(language_cfg.get("output_gain", 0.85)),
        )
        if [round(m.render_hz, 9) for m in rebuilt_modes] != [round(m.render_hz, 9) for m in modes]:
            raise RuntimeError("mode derivation mismatch")
        rendered = filter_.process_block(dry_samples)

    output_meta = write_pcm16_mono(output_path, sample_rate, rendered)
    receipt = {
        "receipt_type": "JANUS_OSIRIS_SEMANTIC_RECITATION_RECEIPT",
        "runner_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "config": {
            "path": str(config_path),
            "id": config.get("id"),
            "sha256": sha256_bytes(config_raw),
        },
        "source": {
            "path": str(source_path),
            "artifact_id": source.get("artifact_id"),
            "field": field,
            "sha256": sha256_bytes(source_raw),
            "semantic_text_sha256": sha256_bytes(text.encode("utf-8")),
            "required_formula": required_formula,
        },
        "larynx": {
            **larynx_meta,
            "dry_wav_sha256": sha256_bytes(dry_raw),
            "network_io": False,
            "shell_execution": False,
        },
        "language_operator": {
            "implementation": "src/pyramid_dsp.py",
            "preset": str(preset_path),
            "preset_id": preset.get("id"),
            "mode_count": len(modes),
            "modes": [asdict(mode) for mode in modes],
            "decay_s": float(language_cfg.get("decay_s", 0.32)),
            "wet": float(language_cfg.get("wet", 0.72)),
            "dry": float(language_cfg.get("dry", 0.62)),
            "output_gain": float(language_cfg.get("output_gain", 0.85)),
        },
        "output": {
            "path": str(output_path),
            **output_meta,
            "automatic_playback": False,
        },
        "claim_boundary": config.get("claim_boundary", {}),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recite a semantic JSON field through JANUS Pyramid Language")
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = render(args.config, args.out, args.receipt)
    print("JANUS semantic recitation PASS")
    print(f"WAV: {receipt['output']['path']}")
    print(f"SHA-256: {receipt['output']['sha256']}")
    if receipt["larynx"].get("stderr"):
        print(f"TTS warning: {receipt['larynx']['stderr']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
