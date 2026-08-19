from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from json_record import canonical_json_bytes, render_json_record
from pyramid_dsp import load_preset

REQUEST_SCHEMA = "janus.demihead.voice_language_request.v1"
RECEIPT_SCHEMA = "janus.voice.demihead_language_receipt.v1"
CONTRACT = "NEXUS_V2_6_PYRAMID_LANGUAGE_JSON_EDGE_FROZEN_CONTRACT"
HEAD_REPOSITORY = "Hawkar-usls/Demi_Head"
VOICE_REPOSITORY = "Hawkar-usls/The-Voice-of-Janus"
TASK = "SONIFY_INLINE_JSON"
PRESET_ALLOWLIST = {
    "GREAT_PYRAMID_KINGS_CHAMBER_EXAMPLE": "presets/great_pyramid_kings_chamber.example.json",
}
SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
GIT_DIGEST = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
MAX_CANONICAL_JSON_BYTES = 65536


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def validate_request(request: Mapping[str, Any]) -> None:
    expected_keys = {
        "schema", "contract", "source", "destination", "task", "preset_id",
        "output_label", "inline_json", "canonical_json_sha256", "canonical_json_bytes",
        "control", "request_id", "request_sha256",
    }
    if not isinstance(request, Mapping) or set(request) != expected_keys:
        raise ValueError("VOICE_LANGUAGE_REQUEST_FIELDS_INVALID")
    if request.get("schema") != REQUEST_SCHEMA or request.get("contract") != CONTRACT:
        raise ValueError("VOICE_LANGUAGE_CONTRACT_INVALID")
    if request.get("task") != TASK:
        raise ValueError("VOICE_LANGUAGE_TASK_INVALID")
    if request.get("preset_id") not in PRESET_ALLOWLIST:
        raise ValueError("VOICE_PRESET_NOT_ALLOWLISTED")
    if not isinstance(request.get("output_label"), str) or SAFE_LABEL.fullmatch(request["output_label"]) is None:
        raise ValueError("VOICE_OUTPUT_LABEL_UNSAFE")

    source = request.get("source")
    if not isinstance(source, Mapping) or set(source) != {"repository", "source_revision"}:
        raise ValueError("VOICE_LANGUAGE_SOURCE_INVALID")
    if source.get("repository") != HEAD_REPOSITORY:
        raise ValueError("VOICE_LANGUAGE_SOURCE_REPOSITORY_INVALID")
    if not isinstance(source.get("source_revision"), str) or GIT_DIGEST.fullmatch(source["source_revision"]) is None:
        raise ValueError("VOICE_LANGUAGE_SOURCE_REVISION_INVALID")

    destination = request.get("destination")
    if not isinstance(destination, Mapping) or destination != {
        "repository": VOICE_REPOSITORY,
        "role": "PYRAMID_LANGUAGE_AUDIO_RENDERER",
    }:
        raise ValueError("VOICE_LANGUAGE_DESTINATION_INVALID")

    payload = canonical_json_bytes(request.get("inline_json"))
    if len(payload) > MAX_CANONICAL_JSON_BYTES:
        raise ValueError("INLINE_JSON_TOO_LARGE")
    if request.get("canonical_json_bytes") != len(payload):
        raise ValueError("CANONICAL_JSON_SIZE_TAMPERED")
    if request.get("canonical_json_sha256") != sha256_bytes(payload):
        raise ValueError("CANONICAL_JSON_HASH_TAMPERED")

    required_control = {
        "explicit_audio_output_intent": True,
        "local_file_render_only": True,
        "network_io_permitted": False,
        "automatic_playback_permitted": False,
        "microphone_start_permitted": False,
        "shell_execution_permitted": False,
        "arbitrary_path_permitted": False,
        "authority_delta": 0,
        "mass_effect_budget_delta": 0,
    }
    if request.get("control") != required_control:
        raise ValueError("VOICE_LANGUAGE_CONTROL_INVALID")

    request_id = request.get("request_id")
    request_hash = request.get("request_sha256")
    if not isinstance(request_id, str) or HEX64.fullmatch(request_id) is None:
        raise ValueError("VOICE_LANGUAGE_REQUEST_ID_INVALID")
    if not isinstance(request_hash, str) or HEX64.fullmatch(request_hash) is None:
        raise ValueError("VOICE_LANGUAGE_REQUEST_HASH_INVALID")

    core = {key: request[key] for key in request if key not in {"request_id", "request_sha256"}}
    expected_id = sha256_json({"kind": "JANUS_PYRAMID_LANGUAGE_REQUEST_ID", **core})
    if request_id != expected_id:
        raise ValueError("VOICE_LANGUAGE_REQUEST_ID_TAMPERED")
    body = dict(request)
    body.pop("request_sha256")
    if request_hash != sha256_json(body):
        raise ValueError("VOICE_LANGUAGE_REQUEST_HASH_TAMPERED")


def resolve_preset(repo_root: Path, preset_id: str) -> Path:
    relative = PRESET_ALLOWLIST.get(preset_id)
    if relative is None:
        raise ValueError("VOICE_PRESET_NOT_ALLOWLISTED")
    root = repo_root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("VOICE_PRESET_ESCAPES_REPOSITORY") from exc
    if not path.is_file():
        raise ValueError("VOICE_PRESET_FILE_MISSING")
    return path


def render_language_request(request: Mapping[str, Any], repo_root: Path, out_dir: Path) -> dict[str, Any]:
    validate_request(request)
    preset_path = resolve_preset(repo_root, str(request["preset_id"]))
    preset = load_preset(preset_path)
    safe_out = out_dir.resolve()
    safe_out.mkdir(parents=True, exist_ok=True)
    label = str(request["output_label"])
    wav_path = safe_out / f"{label}.json-record.wav"
    sonification_receipt = render_json_record(request["inline_json"], preset, wav_path)

    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "contract": CONTRACT,
        "status": "JSON_SONIFIED_NOT_PLAYED",
        "request": {
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "canonical_json_sha256": request["canonical_json_sha256"],
            "canonical_json_bytes": request["canonical_json_bytes"],
            "preset_id": request["preset_id"],
            "source_repository": request["source"]["repository"],
            "source_revision": request["source"]["source_revision"],
        },
        "voice": {
            "repository": VOICE_REPOSITORY,
            "adapter": "src/demihead_language_adapter.py",
            "sonifier": "src/json_record.py",
            "preset_path": str(preset_path.relative_to(repo_root.resolve())),
        },
        "output": {
            "wav_path": str(wav_path),
            "wav_sha256": sonification_receipt["audio"]["sha256"],
            "symbol_count": sonification_receipt["symbol_count"],
        },
        "control": {
            "network_io_performed": False,
            "automatic_playback_performed": False,
            "microphone_opened": False,
            "shell_execution_performed": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        },
        "claim_boundary": {
            "deterministic_sonification": True,
            "reversible_decode_established": False,
            "historical_pyramid_audio_technology_established": False,
        },
    }
    receipt = {**receipt_core, "receipt_sha256": sha256_json(receipt_core)}
    receipt_path = safe_out / f"{label}.json-record.receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def load_request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("VOICE_LANGUAGE_REQUEST_MUST_BE_OBJECT")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume a typed DemiHead Pyramid Language inline JSON request")
    parser.add_argument("request", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    receipt = render_language_request(load_request(args.request), args.repo_root, args.out_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
