from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from voice_of_janus import (
    calculate_modes,
    load_json,
    render_wav,
    select_render_modes,
    write_receipt,
)

REQUEST_SCHEMA = "janus.demihead.voice_request.v1"
RECEIPT_SCHEMA = "janus.voice.demihead_render_receipt.v1"
CONTRACT = "NEXUS_V2_5_VOICE_MOUTH_EDGE_FROZEN_CONTRACT"
HEAD_REPOSITORY = "Hawkar-usls/Demi_Head"
VOICE_REPOSITORY = "Hawkar-usls/The-Voice-of-Janus"
ALLOWED_TASKS = {"RENDER_PRESET"}
PRESET_ALLOWLIST = {
    "GREAT_PYRAMID_KINGS_CHAMBER_EXAMPLE": "presets/great_pyramid_kings_chamber.example.json",
}
SAFE_LABEL = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
GIT_DIGEST = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_request(request: Mapping[str, Any]) -> None:
    if not isinstance(request, Mapping):
        raise ValueError("VOICE_REQUEST_MUST_BE_OBJECT")
    expected_keys = {
        "schema", "contract", "source", "destination", "task", "preset_id",
        "output_label", "control", "request_id", "request_sha256",
    }
    if set(request) != expected_keys:
        raise ValueError("VOICE_REQUEST_FIELDS_INVALID")
    if request.get("schema") != REQUEST_SCHEMA or request.get("contract") != CONTRACT:
        raise ValueError("VOICE_REQUEST_CONTRACT_INVALID")

    source = request.get("source")
    if not isinstance(source, Mapping) or set(source) != {"repository", "source_revision"}:
        raise ValueError("VOICE_REQUEST_SOURCE_INVALID")
    if source.get("repository") != HEAD_REPOSITORY:
        raise ValueError("VOICE_REQUEST_SOURCE_REPOSITORY_INVALID")
    if not isinstance(source.get("source_revision"), str) or GIT_DIGEST.fullmatch(source["source_revision"]) is None:
        raise ValueError("VOICE_REQUEST_SOURCE_REVISION_INVALID")

    destination = request.get("destination")
    if not isinstance(destination, Mapping) or destination != {
        "repository": VOICE_REPOSITORY,
        "role": "LOCAL_AUDIO_RENDERER",
    }:
        raise ValueError("VOICE_REQUEST_DESTINATION_INVALID")

    if request.get("task") not in ALLOWED_TASKS:
        raise ValueError("VOICE_TASK_NOT_ALLOWLISTED")
    if request.get("preset_id") not in PRESET_ALLOWLIST:
        raise ValueError("VOICE_PRESET_NOT_ALLOWLISTED")
    if not isinstance(request.get("output_label"), str) or SAFE_LABEL.fullmatch(request["output_label"]) is None:
        raise ValueError("VOICE_OUTPUT_LABEL_UNSAFE")

    required_control = {
        "explicit_audio_output_intent": True,
        "local_file_render_only": True,
        "network_io_permitted": False,
        "automatic_playback_permitted": False,
        "shell_execution_permitted": False,
        "arbitrary_path_permitted": False,
        "authority_delta": 0,
        "mass_effect_budget_delta": 0,
    }
    if request.get("control") != required_control:
        raise ValueError("VOICE_REQUEST_CONTROL_INVALID")

    request_id = request.get("request_id")
    request_hash = request.get("request_sha256")
    if not isinstance(request_id, str) or HEX64.fullmatch(request_id) is None:
        raise ValueError("VOICE_REQUEST_ID_INVALID")
    if not isinstance(request_hash, str) or HEX64.fullmatch(request_hash) is None:
        raise ValueError("VOICE_REQUEST_HASH_INVALID")

    core = {key: request[key] for key in request if key not in {"request_id", "request_sha256"}}
    expected_id = sha256_json({"kind": "JANUS_VOICE_REQUEST_ID", **core})
    if request_id != expected_id:
        raise ValueError("VOICE_REQUEST_ID_TAMPERED")
    body = dict(request)
    body.pop("request_sha256")
    if request_hash != sha256_json(body):
        raise ValueError("VOICE_REQUEST_HASH_TAMPERED")


def verify_request(request: Mapping[str, Any]) -> bool:
    try:
        validate_request(request)
    except (TypeError, ValueError):
        return False
    return True


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


def prepare_render(request: Mapping[str, Any], repo_root: Path, out_dir: Path) -> dict[str, Any]:
    validate_request(request)
    preset_path = resolve_preset(repo_root, str(request["preset_id"]))
    safe_out_dir = out_dir.resolve()
    output_label = str(request["output_label"])
    return {
        "preset_path": preset_path,
        "wav_path": safe_out_dir / f"{output_label}.wav",
        "engine_receipt_path": safe_out_dir / f"{output_label}.engine-receipt.json",
        "bridge_receipt_path": safe_out_dir / f"{output_label}.demihead-receipt.json",
    }


def render_request(request: Mapping[str, Any], repo_root: Path, out_dir: Path) -> dict[str, Any]:
    paths = prepare_render(request, repo_root, out_dir)
    preset_path = paths["preset_path"]
    wav_path = paths["wav_path"]
    engine_receipt_path = paths["engine_receipt_path"]
    bridge_receipt_path = paths["bridge_receipt_path"]

    config, raw = load_json(preset_path)
    modes = calculate_modes(config)
    selected = select_render_modes(config, modes)
    wav_meta = render_wav(config, selected, wav_path)
    write_receipt(
        preset_path,
        raw,
        config,
        modes,
        selected,
        wav_path,
        wav_meta,
        engine_receipt_path,
    )

    receipt_core = {
        "schema": RECEIPT_SCHEMA,
        "contract": CONTRACT,
        "status": "RENDERED_NOT_PLAYED",
        "request": {
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "source_repository": request["source"]["repository"],
            "source_revision": request["source"]["source_revision"],
            "task": request["task"],
            "preset_id": request["preset_id"],
        },
        "voice": {
            "repository": VOICE_REPOSITORY,
            "renderer": "src/voice_of_janus.py",
            "adapter": "src/demihead_mouth_adapter.py",
            "preset_path": str(preset_path.relative_to(repo_root.resolve())),
        },
        "output": {
            "wav_path": str(wav_path),
            "wav_sha256": sha256_file(wav_path),
            "engine_receipt_path": str(engine_receipt_path),
            "engine_receipt_sha256": sha256_file(engine_receipt_path),
        },
        "control": {
            "network_io_performed": False,
            "automatic_playback_performed": False,
            "shell_execution_performed": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        },
        "claim_boundary": {
            "render_is_truth": False,
            "render_is_evidence_promotion": False,
            "speech_tts_implemented": False,
            "autonomous_playback_granted": False,
        },
    }
    receipt = {**receipt_core, "receipt_sha256": sha256_json(receipt_core)}
    bridge_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    bridge_receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def load_request(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("VOICE_REQUEST_MUST_BE_OBJECT")
    return value


def self_test(repo_root: Path) -> dict[str, Any]:
    source_revision = "a" * 40
    core = {
        "schema": REQUEST_SCHEMA,
        "contract": CONTRACT,
        "source": {"repository": HEAD_REPOSITORY, "source_revision": source_revision},
        "destination": {"repository": VOICE_REPOSITORY, "role": "LOCAL_AUDIO_RENDERER"},
        "task": "RENDER_PRESET",
        "preset_id": "GREAT_PYRAMID_KINGS_CHAMBER_EXAMPLE",
        "output_label": "selftest",
        "control": {
            "explicit_audio_output_intent": True,
            "local_file_render_only": True,
            "network_io_permitted": False,
            "automatic_playback_permitted": False,
            "shell_execution_permitted": False,
            "arbitrary_path_permitted": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        },
    }
    request = {**core, "request_id": sha256_json({"kind": "JANUS_VOICE_REQUEST_ID", **core})}
    request["request_sha256"] = sha256_json(request)
    validate_request(request)
    paths = prepare_render(request, repo_root, repo_root / "outputs")
    return {
        "status": "PASS",
        "request_valid": True,
        "preset_resolved": paths["preset_path"].is_file(),
        "network_io": False,
        "automatic_playback": False,
        "speech_tts": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Consume a typed DemiHead voice request")
    parser.add_argument("request", type=Path, nargs="?")
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        print(json.dumps(self_test(args.repo_root), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if args.request is None:
        parser.error("request is required unless --self-test is used")

    request = load_request(args.request)
    receipt = render_request(request, args.repo_root, args.out_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
