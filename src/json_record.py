#!/usr/bin/env python3
"""Deterministic JSON -> Pyramid Language audio record.

v0.2 is sonification, not a proven reversible audio codec. Canonical UTF-8 JSON
bytes are mapped to a 16-tone alphabet derived from the chamber modal bank and
then passed through the same model-based acoustic operator used by Voice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

from pyramid_dsp import ModalAcousticFilter, derive_acoustic_modes, load_preset


SCHEMA = "janus.voice.json_record_receipt.v1"
PREAMBLE = (15, 0, 15, 0, 10, 5)


def canonical_json_bytes(value: Any) -> bytes:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def bytes_to_nibbles(payload: bytes) -> list[int]:
    symbols: list[int] = list(PREAMBLE)
    for byte in payload:
        symbols.append((byte >> 4) & 0x0F)
        symbols.append(byte & 0x0F)
    return symbols


def carrier_bank(preset: dict[str, Any]) -> tuple[list[float], list[dict[str, Any]]]:
    modes = derive_acoustic_modes(
        preset,
        count=16,
        minimum_hz=180.0,
        maximum_hz=2400.0,
    )
    if len(modes) < 16:
        raise ValueError("preset did not yield 16 distinct carrier modes")
    frequencies = [mode.render_hz for mode in modes[:16]]
    metadata = [
        {
            "symbol": index,
            "physical_hz": mode.physical_hz,
            "carrier_hz": mode.render_hz,
            "octave_multiplier": mode.octave_multiplier,
        }
        for index, mode in enumerate(modes[:16])
    ]
    return frequencies, metadata


def render_json_record(
    value: Any,
    preset: dict[str, Any],
    out_path: Path,
    *,
    sample_rate_hz: int = 44100,
    tone_ms: float = 18.0,
    gap_ms: float = 2.0,
    max_payload_bytes: int = 1_000_000,
) -> dict[str, Any]:
    payload = canonical_json_bytes(value)
    if len(payload) > max_payload_bytes:
        raise ValueError(f"canonical JSON exceeds max_payload_bytes={max_payload_bytes}")
    if tone_ms <= 0 or gap_ms < 0:
        raise ValueError("tone_ms must be > 0 and gap_ms must be >= 0")

    carriers, carrier_meta = carrier_bank(preset)
    symbols = bytes_to_nibbles(payload)
    tone_frames = max(1, int(round(sample_rate_hz * tone_ms / 1000.0)))
    gap_frames = max(0, int(round(sample_rate_hz * gap_ms / 1000.0)))
    ramp_frames = max(1, min(tone_frames // 4, int(round(sample_rate_hz * 0.0015))))

    acoustic = ModalAcousticFilter(
        [item["carrier_hz"] for item in carrier_meta[:8]],
        sample_rate_hz=sample_rate_hz,
        decay_s=0.16,
        wet=0.36,
        dry=0.82,
        output_gain=0.82,
    )

    pcm = bytearray()
    phase = 0.0
    for symbol in symbols:
        freq = carriers[symbol]
        step = 2.0 * math.pi * freq / sample_rate_hz
        raw_block: list[float] = []
        for index in range(tone_frames):
            envelope = 1.0
            if index < ramp_frames:
                envelope = index / ramp_frames
            elif index >= tone_frames - ramp_frames:
                envelope = max(0.0, (tone_frames - 1 - index) / ramp_frames)
            raw_block.append(math.sin(phase) * envelope * 0.72)
            phase = (phase + step) % (2.0 * math.pi)
        if gap_frames:
            raw_block.extend([0.0] * gap_frames)
        for sample in acoustic.process_block(raw_block):
            sample = max(-1.0, min(1.0, sample))
            pcm.extend(struct.pack("<h", int(round(sample * 32767.0))))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate_hz)
        wav.writeframes(bytes(pcm))

    audio = out_path.read_bytes()
    return {
        "schema": SCHEMA,
        "status": "SONIFIED_NOT_DECODE_PROVEN",
        "canonical_json_sha256": sha256_bytes(payload),
        "canonical_json_bytes": len(payload),
        "symbol_count": len(symbols),
        "preamble_symbols": list(PREAMBLE),
        "sample_rate_hz": sample_rate_hz,
        "tone_ms": tone_ms,
        "gap_ms": gap_ms,
        "carrier_bank": carrier_meta,
        "audio": {
            "path": str(out_path),
            "sha256": sha256_bytes(audio),
            "bytes": len(audio),
        },
        "claim_boundary": {
            "deterministic_sonification": True,
            "reversible_decode_established": False,
            "measured_historical_pyramid_response": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert JSON into a deterministic Pyramid Language audio record")
    parser.add_argument("json_file", type=Path)
    parser.add_argument("--preset", type=Path, default=Path("presets/great_pyramid_kings_chamber.example.json"))
    parser.add_argument("--out", type=Path, default=Path("outputs/json_record.wav"))
    parser.add_argument("--receipt", type=Path, default=Path("receipts/json_record.json"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    value = json.loads(args.json_file.read_text(encoding="utf-8"))
    preset = load_preset(args.preset)
    receipt = render_json_record(value, preset, args.out)
    receipt["input"] = {
        "path": str(args.json_file),
        "preset": str(args.preset),
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
