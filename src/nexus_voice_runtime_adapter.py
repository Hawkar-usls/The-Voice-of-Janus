#!/usr/bin/env python3
"""Explicit executor for Nexus v2.7 neural Voice render requests.

The Nexus handler in Demi_Head is intentionally pure. This adapter is the
separate local execution boundary. It accepts only the frozen canonical OSIRIS
request, verifies pinned Voice blobs, requires a local Silero model, and then
renders through semantic_recitation_v4 -> Pyramid117121Filter.

No model download, network I/O, shell command, autoplay, Bluetooth connection,
or firmware flashing is performed here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from semantic_recitation_v4 import render

CONTRACT = "NEXUS_V2_7_LOCAL_NEURAL_VOICE_RUNTIME_FROZEN_CONTRACT"
REQUEST_SCHEMA = "janus.demihead.nexus_voice_render_request.v1"
TASK = "RENDER_OSIRIS_ORIGIN_PRIME_NEURAL_PYRAMID"
SOURCE_ARTIFACT_ID = "OSIRIS-SEMANTIC-TEXT-CORE-FOR-THE-VOICE-OF-JANUS-2026-08-19-v1.1"
SEMANTIC_FIELD = "semantic_projection_ru"
REQUIRED_FORMULA = "ORIGIN → EXPERIENCE → RETURN → ORIGIN_PRIME"
LANGUAGE_PROFILE = "PYRAMID_LANGUAGE_117_121_ANCHORED_SPACE_v0.3"
ACTIVATION = "configs/pyramid_117_121_space.activation.json"
ACTIVATION_BLOB_SHA = "70016b9b1ad0ce2b20efd980f14859d66af0a7bd"
VOICE_CONFIG = "configs/osiris_origin_prime_recitation.v4_neural_human.json"
VOICE_CONFIG_BLOB_SHA = "8d18ed86e65e036200f7afa14d62b27fe7c4a0a4"
VOICE_RUNNER = "src/semantic_recitation_v4.py"
VOICE_RUNNER_BLOB_SHA = "85b30261ee7a071655ac6c42cfbb85fc4ae5eed4"
MODEL_PATH = "models/v5_5_ru.pt"
ALLOWED_SPEAKERS = {"aidar", "eugene", "baya", "kseniya", "xenia"}
OUTPUT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def git_blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    payload = f"blob {len(raw)}\0".encode("ascii") + raw
    return hashlib.sha1(payload).hexdigest()


def _expect(mapping: dict[str, Any], key: str, expected: Any, context: str) -> None:
    if mapping.get(key) != expected:
        raise ValueError(f"{context}.{key} mismatch")


def validate_request(request: dict[str, Any]) -> tuple[str, str]:
    if not isinstance(request, dict):
        raise ValueError("Nexus Voice request must be an object")
    _expect(request, "schema", REQUEST_SCHEMA, "request")
    _expect(request, "contract", CONTRACT, "request")
    _expect(request, "task", TASK, "request")
    _expect(request, "target_head", "VOICE_RUNTIME", "request")

    supplied_hash = request.get("request_sha256")
    if not isinstance(supplied_hash, str) or len(supplied_hash) != 64:
        raise ValueError("request_sha256 is missing or malformed")
    core = {k: v for k, v in request.items() if k != "request_sha256"}
    if sha256(core) != supplied_hash:
        raise ValueError("request_sha256 binding mismatch")

    source = request.get("source")
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    _expect(source, "artifact_id", SOURCE_ARTIFACT_ID, "source")
    _expect(source, "semantic_field", SEMANTIC_FIELD, "source")
    _expect(source, "required_formula", REQUIRED_FORMULA, "source")

    larynx = request.get("larynx")
    if not isinstance(larynx, dict):
        raise ValueError("larynx must be an object")
    _expect(larynx, "backend", "silero_v5_5_ru", "larynx")
    _expect(larynx, "model_relative_path", MODEL_PATH, "larynx")
    _expect(larynx, "model_download_permitted", False, "larynx")
    speaker = larynx.get("speaker")
    if speaker not in ALLOWED_SPEAKERS:
        raise ValueError("Speaker is not allowlisted")

    language = request.get("language")
    if not isinstance(language, dict):
        raise ValueError("language must be an object")
    _expect(language, "profile_id", LANGUAGE_PROFILE, "language")
    _expect(language, "activation", ACTIVATION, "language")
    _expect(language, "activation_blob_sha", ACTIVATION_BLOB_SHA, "language")
    _expect(language, "anchor_band_hz", [117.0, 121.0], "language")
    _expect(language, "semantic_content_preserved", True, "language")

    runtime = request.get("voice_runtime")
    if not isinstance(runtime, dict):
        raise ValueError("voice_runtime must be an object")
    _expect(runtime, "config", VOICE_CONFIG, "voice_runtime")
    _expect(runtime, "config_blob_sha", VOICE_CONFIG_BLOB_SHA, "voice_runtime")
    _expect(runtime, "runner", VOICE_RUNNER, "voice_runtime")
    _expect(runtime, "runner_blob_sha", VOICE_RUNNER_BLOB_SHA, "voice_runtime")
    output_label = runtime.get("output_label")
    if not isinstance(output_label, str) or not OUTPUT_RE.fullmatch(output_label):
        raise ValueError("Unsafe output_label")

    control = request.get("control")
    if not isinstance(control, dict):
        raise ValueError("control must be an object")
    for key in (
        "audio_rendered",
        "filesystem_io_performed",
        "network_io_performed",
        "automatic_playback",
        "automatic_bluetooth",
        "firmware_flash",
        "external_effect_permitted",
    ):
        if control.get(key) is not False:
            raise ValueError(f"Prepared request requires control.{key}=false")
    if control.get("explicit_voice_execute_required") is not True:
        raise ValueError("Prepared request must require explicit Voice execution")
    if control.get("authority_delta") != 0 or control.get("mass_effect_budget_delta") != 0:
        raise ValueError("Prepared request cannot alter authority or mass-effect budget")
    return str(speaker), output_label


def verify_local_runtime(repo_root: Path) -> dict[str, str]:
    pins = {
        ACTIVATION: ACTIVATION_BLOB_SHA,
        VOICE_CONFIG: VOICE_CONFIG_BLOB_SHA,
        VOICE_RUNNER: VOICE_RUNNER_BLOB_SHA,
    }
    observed: dict[str, str] = {}
    for relative, expected in pins.items():
        path = repo_root / relative
        if not path.is_file():
            raise RuntimeError(f"Pinned Voice runtime file is missing: {relative}")
        actual = git_blob_sha(path)
        if actual != expected:
            raise RuntimeError(f"Pinned Voice runtime drift: {relative}: {actual} != {expected}")
        observed[relative] = actual
    model = repo_root / MODEL_PATH
    if not model.is_file():
        raise RuntimeError(
            "NEURAL_MODEL_MISSING: place v5_5_ru.pt at The-Voice-of-Janus/models/v5_5_ru.pt; "
            "automatic download is intentionally disabled"
        )
    observed[MODEL_PATH] = hashlib.sha256(model.read_bytes()).hexdigest()
    return observed


def execute(request: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    speaker, output_label = validate_request(request)
    observed = verify_local_runtime(repo_root)

    canonical_config_path = repo_root / VOICE_CONFIG
    config = json.loads(canonical_config_path.read_text(encoding="utf-8"))
    config["larynx"]["speaker"] = speaker
    config["larynx"]["model_path"] = MODEL_PATH
    config["larynx"]["allow_model_download"] = False
    config["larynx"]["network_io_during_render"] = False
    config["output"]["automatic_playback"] = False
    config["output"]["recording"] = False

    output_path = repo_root / "outputs" / f"{output_label}.wav"
    receipt_path = repo_root / "receipts" / f"{output_label}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    previous_cwd = Path.cwd()
    try:
        os.chdir(repo_root)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".json", prefix="nexus_voice_v27_", delete=False
        ) as tmp:
            tmp.write(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
            temp_config_path = Path(tmp.name)
        try:
            receipt = render(temp_config_path, output_path, receipt_path)
        finally:
            temp_config_path.unlink(missing_ok=True)
    finally:
        os.chdir(previous_cwd)

    receipt["nexus_binding"] = {
        "contract": CONTRACT,
        "request_sha256": request["request_sha256"],
        "target_head": "VOICE_RUNTIME",
        "speaker": speaker,
        "pinned_runtime_verified": True,
        "pinned_git_blobs": {k: v for k, v in observed.items() if k != MODEL_PATH},
        "model_sha256": observed[MODEL_PATH],
        "explicit_execute": True,
        "automatic_playback": False,
        "automatic_bluetooth": False,
        "physical_handoff_performed": False,
        "authority_delta": 0,
        "mass_effect_budget_delta": 0,
    }
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def load_request(path: Path | None) -> dict[str, Any]:
    if path is None:
        raw = sys.stdin.read()
    else:
        raw = path.read_text(encoding="utf-8")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Request JSON must be an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Explicit Nexus v2.7 neural Voice runtime executor")
    parser.add_argument("--request", type=Path, default=None, help="Request JSON; stdin when omitted")
    parser.add_argument("--execute", action="store_true", help="Required explicit local audio-render permission")
    args = parser.parse_args()
    request = load_request(args.request)
    validate_request(request)
    if not args.execute:
        print(json.dumps({
            "status": "VALIDATED_NOT_EXECUTED",
            "request_sha256": request["request_sha256"],
            "rule": "EXPLICIT_--execute_REQUIRED",
        }, ensure_ascii=False, indent=2))
        return 0
    repo_root = Path(__file__).resolve().parents[1]
    receipt = execute(request, repo_root=repo_root)
    print(json.dumps({
        "status": "PASS",
        "request_sha256": request["request_sha256"],
        "wav": receipt["output"]["path"],
        "wav_sha256": receipt["output"]["sha256"],
        "receipt": str(repo_root / "receipts" / f"{request['voice_runtime']['output_label']}.json"),
        "physical_handoff_performed": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
