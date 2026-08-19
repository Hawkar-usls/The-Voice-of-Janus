#!/usr/bin/env python3
"""Semantic recitation v2 using the shared 117-121 Hz Pyramid Language operator."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pyramid_anchor_filter import Pyramid117121Filter, write_mono_pcm16
from semantic_recitation import (
    load_json,
    load_pcm16_mono,
    read_semantic_text,
    require_mapping,
    run_espeak,
    sha256_bytes,
)

VERSION = "0.2"


def build_filter(activation: dict, sample_rate_hz: int) -> Pyramid117121Filter:
    anchor = require_mapping(activation.get("anchor"), "activation.anchor")
    room = require_mapping(activation.get("room_tail"), "activation.room_tail")
    band = anchor.get("band_hz", [117.0, 121.0])
    geometry = room.get("geometry_m", [10.45, 5.20, 5.80])
    if not isinstance(band, list) or len(band) != 2:
        raise ValueError("activation.anchor.band_hz must contain two values")
    if not isinstance(geometry, list) or len(geometry) != 3:
        raise ValueError("activation.room_tail.geometry_m must contain three values")
    return Pyramid117121Filter(
        sample_rate_hz,
        anchor_low_hz=float(band[0]),
        anchor_high_hz=float(band[1]),
        anchor_gain_db=float(anchor.get("gain_db", 11.5)),
        anchor_decay_s=float(anchor.get("decay_s", 1.65)),
        room_decay=float(room.get("room_decay", 0.78)),
        wet=float(room.get("wet", 0.72)),
        dry=float(room.get("dry", 0.62)),
        speed_of_sound_m_s=float(room.get("speed_of_sound_m_s", 343.0)),
        geometry_m=tuple(float(value) for value in geometry),
    )


def render(config_path: Path, output_override: Path | None, receipt_override: Path | None) -> dict:
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

    activation_path = Path(str(language_cfg.get("activation")))
    activation, activation_raw = load_json(activation_path)
    output_path = output_override or Path(str(output_cfg.get("default_path")))
    receipt_path = receipt_override or Path(str(output_cfg.get("default_receipt")))

    with tempfile.TemporaryDirectory(prefix="janus_recitation_v2_") as tmp_dir:
        dry_path = Path(tmp_dir) / "dry.wav"
        larynx_meta = run_espeak(text, larynx_cfg, dry_path)
        dry_raw = dry_path.read_bytes()
        sample_rate_hz, dry_samples = load_pcm16_mono(dry_path)
        acoustic = build_filter(activation, sample_rate_hz)
        rendered = acoustic.process_block(dry_samples)
        rendered.extend(
            acoustic.process_sample(0.0) for _ in range(int(sample_rate_hz * 2.0))
        )

    output_meta = write_mono_pcm16(output_path, sample_rate_hz, rendered)
    receipt = {
        "receipt_type": "JANUS_OSIRIS_SEMANTIC_RECITATION_RECEIPT_V2",
        "runner_version": VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "config": {"path": str(config_path), "sha256": sha256_bytes(config_raw)},
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
            "implementation": "src/pyramid_anchor_filter.py::Pyramid117121Filter",
            "activation": str(activation_path),
            "activation_sha256": sha256_bytes(activation_raw),
            "anchor_band_hz": list(acoustic.anchor_band_hz),
            "anchor_center_hz": acoustic.anchor_center_hz,
            "anchor_q": acoustic.anchor_q,
        },
        "output": {"path": str(output_path), **output_meta, "automatic_playback": False},
        "claim_boundary": config.get("claim_boundary", {}),
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recite semantic JSON through JANUS 117-121 Hz Pyramid Language")
    parser.add_argument("config", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--receipt", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    receipt = render(args.config, args.out, args.receipt)
    print("JANUS semantic recitation v2 PASS")
    print(f"WAV: {receipt['output']['path']}")
    print(f"SHA-256: {receipt['output']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
