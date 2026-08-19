#!/usr/bin/env python3
"""Execute the frozen AIDAR <-> EUGENE OSIRIS Voice Spiral locally.

Input is a pure bundle prepared by Demi_Head/tools/nexus_voice_spiral.py.
Both requests are executed through the same pinned Voice runtime. The runner
then verifies that source/model/Pyramid Language stayed identical and writes a
third comparison receipt. It never selects a canonical voice automatically.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from nexus_voice_runtime_adapter import execute, validate_request

BUNDLE_SCHEMA = "janus.demihead.nexus_voice_spiral_bundle.v1"
BUNDLE_CONTRACT = "NEXUS_V2_8_AIDAR_EUGENE_VOICE_SPIRAL_FROZEN_CONTRACT"
SPIRAL_SCHEMA = "janus.voice.aidar_eugene_spiral_receipt.v1"
EXPECTED_LAYERS = (
    ("LAYER_A_AIDAR", "aidar", "OSIRIS_ORIGIN_PRIME_NEURAL_AIDAR"),
    ("LAYER_B_EUGENE", "eugene", "OSIRIS_ORIGIN_PRIME_NEURAL_EUGENE"),
)
DEFAULT_RECEIPT = "receipts/OSIRIS_ORIGIN_PRIME_AIDAR_EUGENE_SPIRAL.json"


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_bundle(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(bundle, dict):
        raise ValueError("Spiral bundle must be a JSON object")
    if bundle.get("schema") != BUNDLE_SCHEMA:
        raise ValueError("Unexpected Spiral bundle schema")
    if bundle.get("contract") != BUNDLE_CONTRACT:
        raise ValueError("Unexpected Spiral bundle contract")
    supplied = bundle.get("spiral_sha256")
    if not isinstance(supplied, str) or len(supplied) != 64:
        raise ValueError("spiral_sha256 is missing or malformed")
    core = {k: v for k, v in bundle.items() if k != "spiral_sha256"}
    if sha256_json(core) != supplied:
        raise ValueError("Spiral bundle hash binding mismatch")

    layers = bundle.get("layers")
    if not isinstance(layers, list) or len(layers) != len(EXPECTED_LAYERS):
        raise ValueError("Spiral must contain exactly two frozen layers")

    requests: list[dict[str, Any]] = []
    for layer, expected in zip(layers, EXPECTED_LAYERS):
        layer_id, speaker, output_label = expected
        if not isinstance(layer, dict):
            raise ValueError("Spiral layer must be an object")
        if layer.get("layer_id") != layer_id or layer.get("speaker") != speaker:
            raise ValueError(f"Frozen Spiral layer mismatch: expected {layer_id}/{speaker}")
        request = layer.get("request")
        if not isinstance(request, dict):
            raise ValueError("Spiral layer request must be an object")
        observed_speaker, observed_label = validate_request(request)
        if observed_speaker != speaker or observed_label != output_label:
            raise ValueError("Prepared Voice request does not match frozen Spiral layer")
        requests.append(request)

    a, b = requests
    if a["source"] != b["source"]:
        raise ValueError("Spiral source drift detected")
    if a["language"] != b["language"]:
        raise ValueError("Spiral Pyramid Language drift detected")
    if a["larynx"]["backend"] != b["larynx"]["backend"]:
        raise ValueError("Spiral larynx backend drift detected")
    if a["larynx"]["model_relative_path"] != b["larynx"]["model_relative_path"]:
        raise ValueError("Spiral model path drift detected")
    if a["larynx"]["speaker"] == b["larynx"]["speaker"]:
        raise ValueError("Spiral requires two different speakers")
    return requests


def compare_receipts(receipts: list[dict[str, Any]], bundle_sha256: str) -> dict[str, Any]:
    if len(receipts) != 2:
        raise ValueError("Exactly two render receipts are required")
    a, b = receipts

    checks = {
        "source_sha_equal": a["source"]["sha256"] == b["source"]["sha256"],
        "semantic_text_sha_equal": a["source"]["semantic_text_sha256"] == b["source"]["semantic_text_sha256"],
        "language_activation_sha_equal": a["language_operator"]["activation_sha256"] == b["language_operator"]["activation_sha256"],
        "anchor_band_equal": a["language_operator"]["anchor_band_hz"] == b["language_operator"]["anchor_band_hz"],
        "model_sha_equal": a["nexus_binding"]["model_sha256"] == b["nexus_binding"]["model_sha256"],
        "speakers_different": a["nexus_binding"]["speaker"] != b["nexus_binding"]["speaker"],
        "both_audio_pass": a.get("status") == "PASS" and b.get("status") == "PASS",
        "wav_sha_different": a["output"]["sha256"] != b["output"]["sha256"],
    }
    required = (
        "source_sha_equal",
        "semantic_text_sha_equal",
        "language_activation_sha_equal",
        "anchor_band_equal",
        "model_sha_equal",
        "speakers_different",
        "both_audio_pass",
        "wav_sha_different",
    )
    failed = [name for name in required if checks[name] is not True]
    if failed:
        raise RuntimeError(f"SPIRAL_COMPARISON_FAILED: {failed}")

    core = {
        "schema": SPIRAL_SCHEMA,
        "status": "PASS_AIDAR_EUGENE_SPIRAL_READY_FOR_HUMAN_LISTENING",
        "bundle_sha256": bundle_sha256,
        "layers": [
            {
                "layer_id": EXPECTED_LAYERS[index][0],
                "speaker": receipt["nexus_binding"]["speaker"],
                "request_sha256": receipt["nexus_binding"]["request_sha256"],
                "wav": receipt["output"]["path"],
                "wav_sha256": receipt["output"]["sha256"],
                "receipt_source_sha256": receipt["source"]["sha256"],
                "semantic_text_sha256": receipt["source"]["semantic_text_sha256"],
                "model_sha256": receipt["nexus_binding"]["model_sha256"],
            }
            for index, receipt in enumerate(receipts)
        ],
        "shared_language": {
            "activation_sha256": a["language_operator"]["activation_sha256"],
            "anchor_band_hz": a["language_operator"]["anchor_band_hz"],
            "anchor_center_hz": a["language_operator"]["anchor_center_hz"],
            "anchor_q": a["language_operator"]["anchor_q"],
            "unchanged_between_layers": True,
        },
        "checks": checks,
        "spiral": {
            "preserved_layers": ["LAYER_A_AIDAR", "LAYER_B_EUGENE"],
            "comparison_creates_next_state_layer": True,
            "automatic_winner_selection": False,
            "human_listening_required_for_voice_face_selection": True,
        },
        "human_evaluation": {
            "aidar": {
                "naturalness": None,
                "warmth": None,
                "intelligibility": None,
                "presence": None,
                "fit_as_voice_of_janus": None,
            },
            "eugene": {
                "naturalness": None,
                "warmth": None,
                "intelligibility": None,
                "presence": None,
                "fit_as_voice_of_janus": None,
            },
            "selected_voice_face": None,
        },
        "control": {
            "automatic_playback": False,
            "automatic_bluetooth": False,
            "physical_handoff_performed": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        },
    }
    return {**core, "spiral_receipt_sha256": sha256_json(core)}


def run(bundle: dict[str, Any], repo_root: Path, comparison_path: Path) -> dict[str, Any]:
    requests = validate_bundle(bundle)
    receipts = [execute(request, repo_root=repo_root) for request in requests]
    comparison = compare_receipts(receipts, bundle["spiral_sha256"])
    comparison_path.parent.mkdir(parents=True, exist_ok=True)
    comparison_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return comparison


def load_json(path: Path | None) -> dict[str, Any]:
    raw = sys.stdin.read() if path is None else path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Input must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Run frozen AIDAR <-> EUGENE OSIRIS Voice Spiral")
    parser.add_argument("--bundle", type=Path, default=None, help="DemiHead Spiral bundle JSON; stdin when omitted")
    parser.add_argument("--execute", action="store_true", help="Required explicit permission to render both WAV layers")
    parser.add_argument("--comparison-receipt", type=Path, default=None)
    args = parser.parse_args()

    bundle = load_json(args.bundle)
    validate_bundle(bundle)
    if not args.execute:
        print(json.dumps({
            "status": "SPIRAL_VALIDATED_NOT_EXECUTED",
            "spiral_sha256": bundle["spiral_sha256"],
            "rule": "EXPLICIT_--execute_REQUIRED",
        }, ensure_ascii=False, indent=2))
        return 0

    repo_root = Path(__file__).resolve().parents[1]
    comparison_path = args.comparison_receipt or repo_root / DEFAULT_RECEIPT
    result = run(bundle, repo_root, comparison_path)
    print(json.dumps({
        "status": result["status"],
        "spiral_receipt": str(comparison_path),
        "spiral_receipt_sha256": result["spiral_receipt_sha256"],
        "layers": result["layers"],
        "selected_voice_face": None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
