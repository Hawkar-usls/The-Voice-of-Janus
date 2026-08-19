#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from demihead_language_adapter import (
    PRESET_ALLOWLIST,
    load_request,
    resolve_preset,
    validate_request as validate_demihead_language_request,
)
from json_record import render_json_record
from pyramid_anchor_filter import Pyramid117121Filter, read_mono_pcm16, write_mono_pcm16
from pyramid_dsp import load_preset

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "data" / "COSMOS_ORIGIN_PRIME_PYRAMID_RENDER_FROZEN_CONTRACT.v1.json"
ENVELOPE_SCHEMA = "janus.demihead.cosmos_origin_prime_voice_envelope.v1"
PACKET_SCHEMA = "janus.cosmos.origin_prime_voice_packet.v1"
RECEIPT_SCHEMA = "janus.voice.cosmos_origin_prime_pyramid_receipt.v1"
COSMOS_REPOSITORY = "Hawkar-usls/Janus-Cosmos"
COSMOS_SHA = "07e35fdbd42621f9ed02b39b71f3b2ee4876ce95"
DEMIHEAD_REPOSITORY = "Hawkar-usls/Demi_Head"
VOICE_REPOSITORY = "Hawkar-usls/The-Voice-of-Janus"
ECHO_REPOSITORY = "Hawkar-usls/Echo-Pyramid"
ECHO_SHA = "15712f5b14b123d4e3cb64ddeaa693c5bf6af788"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
PROFILE = {
    "profile_id": "PYRAMID_LANGUAGE_117_121_ANCHORED_SPACE_v0.3",
    "anchor_band_hz": [117.0, 121.0],
    "center_hz": 119.0,
    "q": 29.75,
    "gain_db": 11.5,
    "decay_s": 1.65,
    "role": "REPRESENTATION_AND_ACOUSTIC_COLORATION_ONLY",
    "frequencies_create_math_authority": False,
    "audio_output_is_evidence": False,
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_IMPLEMENTATION":
        raise ValueError("COSMOS_PYRAMID_CONTRACT_NOT_FROZEN")
    if value.get("source_provider", {}).get("sha") != COSMOS_SHA:
        raise ValueError("COSMOS_PROVIDER_PIN_MISMATCH")
    return value


def verify_commitment(record: Mapping[str, Any], field: str) -> bool:
    claimed = record.get(field)
    if not isinstance(claimed, str) or HEX64.fullmatch(claimed) is None:
        return False
    core = dict(record)
    core.pop(field, None)
    return digest(core) == claimed


def validate_cosmos_packet(packet: Mapping[str, Any]) -> None:
    if not isinstance(packet, Mapping) or packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("COSMOS_PACKET_SCHEMA_INVALID")
    source = packet.get("source")
    if not isinstance(source, Mapping) or source.get("repository") != COSMOS_REPOSITORY:
        raise ValueError("COSMOS_PACKET_SOURCE_INVALID")
    if source.get("revision") != COSMOS_SHA:
        raise ValueError("COSMOS_PACKET_REVISION_INVALID")
    if source.get("canonical_gate") != "OSIRIS_V3_ORIGIN_PRIME_SPIRAL_COMPUTE":
        raise ValueError("COSMOS_PACKET_GATE_INVALID")

    state = packet.get("origin_prime")
    if not isinstance(state, Mapping) or state.get("state_type") != "ORIGIN_PRIME":
        raise ValueError("COSMOS_PACKET_STATE_INVALID")
    if not verify_commitment(state, "state_commitment"):
        raise ValueError("COSMOS_PACKET_STATE_COMMITMENT_INVALID")

    experience = packet.get("bound_experience")
    if experience is None:
        if state.get("experience_commitment") is not None:
            raise ValueError("COSMOS_PACKET_EXPERIENCE_MISSING")
    else:
        if not isinstance(experience, Mapping) or not verify_commitment(experience, "experience_commitment"):
            raise ValueError("COSMOS_PACKET_EXPERIENCE_INVALID")
        if experience.get("experience_commitment") != state.get("experience_commitment"):
            raise ValueError("COSMOS_PACKET_EXPERIENCE_BINDING_INVALID")

    mediation = packet.get("mediation")
    expected_mediation = {
        "required_mediator": DEMIHEAD_REPOSITORY,
        "voice_repository": VOICE_REPOSITORY,
        "voice_revision": "e58d65aa46b7e3a64a5131708578a9a3346915c4",
        "physical_body_repository": ECHO_REPOSITORY,
        "physical_body_revision": ECHO_SHA,
        "route": "COSMOS -> DEMIHEAD -> THE_VOICE_OF_JANUS -> ECHO_PYRAMID",
    }
    if mediation != expected_mediation:
        raise ValueError("COSMOS_PACKET_MEDIATION_INVALID")
    if packet.get("voice_representation") != PROFILE:
        raise ValueError("COSMOS_PACKET_PYRAMID_PROFILE_INVALID")

    control = packet.get("control")
    if not isinstance(control, Mapping):
        raise ValueError("COSMOS_PACKET_CONTROL_INVALID")
    if control.get("direct_cosmos_to_echo_route_permitted") is not False:
        raise ValueError("DIRECT_COSMOS_TO_ECHO_ROUTE_FORBIDDEN")
    if control.get("demihead_mediation_required") is not True:
        raise ValueError("DEMIHEAD_MEDIATION_REQUIRED")
    if control.get("authority_delta") != 0 or control.get("mass_effect_budget_delta") != 0:
        raise ValueError("COSMOS_PACKET_AUTHORITY_ESCALATION")

    boundary = packet.get("scientific_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("P_VS_NP") != "OPEN":
        raise ValueError("COSMOS_PACKET_SCIENTIFIC_BOUNDARY_INVALID")
    if boundary.get("voice_profile_changes_solver_correctness") is not False or boundary.get("acoustic_frequencies_are_proof") is not False:
        raise ValueError("COSMOS_PACKET_ACOUSTIC_AUTHORITY_LEAK")

    claimed = packet.get("packet_sha256")
    if not isinstance(claimed, str) or HEX64.fullmatch(claimed) is None:
        raise ValueError("COSMOS_PACKET_HASH_INVALID")
    body = dict(packet)
    body.pop("packet_sha256", None)
    if digest(body) != claimed:
        raise ValueError("COSMOS_PACKET_HASH_TAMPERED")


def validate_envelope(envelope: Mapping[str, Any]) -> None:
    if not isinstance(envelope, Mapping) or set(envelope) != {"schema", "intent_id", "cosmos_packet"}:
        raise ValueError("COSMOS_VOICE_ENVELOPE_FIELDS_INVALID")
    if envelope.get("schema") != ENVELOPE_SCHEMA:
        raise ValueError("COSMOS_VOICE_ENVELOPE_SCHEMA_INVALID")
    intent_id = envelope.get("intent_id")
    if not isinstance(intent_id, str) or HEX64.fullmatch(intent_id) is None:
        raise ValueError("COSMOS_VOICE_INTENT_ID_INVALID")
    packet = envelope.get("cosmos_packet")
    if not isinstance(packet, Mapping):
        raise ValueError("COSMOS_VOICE_PACKET_MISSING")
    validate_cosmos_packet(packet)


def validate_request(request: Mapping[str, Any]) -> None:
    validate_demihead_language_request(request)
    source = request.get("source")
    if not isinstance(source, Mapping) or source.get("repository") != DEMIHEAD_REPOSITORY:
        raise ValueError("COSMOS_VOICE_NON_DEMIHEAD_SOURCE_REJECTED")
    envelope = request.get("inline_json")
    if not isinstance(envelope, Mapping):
        raise ValueError("COSMOS_VOICE_ENVELOPE_MISSING")
    validate_envelope(envelope)


def render_request(request: Mapping[str, Any], repo_root: Path, out_dir: Path) -> dict[str, Any]:
    load_contract()
    validate_request(request)
    preset_path = resolve_preset(repo_root, str(request["preset_id"]))
    preset = load_preset(preset_path)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    label = str(request["output_label"])

    base_wav = out_dir / f"{label}.cosmos-state.base.wav"
    base_receipt = render_json_record(request["inline_json"], preset, base_wav)

    sample_rate_hz, samples = read_mono_pcm16(base_wav)
    filter_ = Pyramid117121Filter(sample_rate_hz)
    processed = filter_.process_block(samples)
    processed.extend(filter_.process_sample(0.0) for _ in range(int(sample_rate_hz * 2.0)))
    final_wav = out_dir / f"{label}.cosmos-state.pyramid.wav"
    final_meta = write_mono_pcm16(final_wav, sample_rate_hz, processed)

    envelope = request["inline_json"]
    packet = envelope["cosmos_packet"]
    state = packet["origin_prime"]
    core = {
        "schema": RECEIPT_SCHEMA,
        "contract": "VOICE_COSMOS_ORIGIN_PRIME_PYRAMID_RENDER_FROZEN_CONTRACT_V1",
        "status": "COSMOS_ORIGIN_PRIME_SONIFIED_WITH_PYRAMID_LANGUAGE_NOT_PLAYED",
        "request": {
            "request_id": request["request_id"],
            "request_sha256": request["request_sha256"],
            "intent_id": envelope["intent_id"],
            "source_repository": request["source"]["repository"],
            "source_revision": request["source"]["source_revision"],
        },
        "cosmos": {
            "repository": COSMOS_REPOSITORY,
            "revision": packet["source"]["revision"],
            "packet_sha256": packet["packet_sha256"],
            "state_generation": state["generation"],
            "state_commitment": state["state_commitment"],
            "experience_commitment": state.get("experience_commitment"),
        },
        "sonification": {
            "base_wav_path": str(base_wav),
            "base_wav_sha256": base_receipt["audio"]["sha256"],
            "canonical_json_sha256": request["canonical_json_sha256"],
            "symbol_count": base_receipt["symbol_count"],
            "reversible_decode_established": False,
        },
        "pyramid_language": {
            "implementation": "src/pyramid_anchor_filter.py::Pyramid117121Filter",
            "profile_id": PROFILE["profile_id"],
            "anchor_band_hz": PROFILE["anchor_band_hz"],
            "center_hz": PROFILE["center_hz"],
            "q": PROFILE["q"],
            "gain_db": PROFILE["gain_db"],
            "decay_s": PROFILE["decay_s"],
        },
        "physical_body": {
            "repository": ECHO_REPOSITORY,
            "revision": ECHO_SHA,
            "ready_for_local_pcm_handoff": True,
            "physical_playback_performed": False,
        },
        "output": {
            "wav_path": str(final_wav),
            "wav_sha256": final_meta["sha256"],
            "sample_rate_hz": sample_rate_hz,
            "frames": len(processed),
            "duration_s": len(processed) / sample_rate_hz,
            "peak": final_meta["peak"],
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
            "audio_is_proof": False,
            "117_121_hz_is_sat_evidence": False,
            "measured_chamber_ir_used": False,
            "historical_intentional_tuning_claimed": False,
            "P_VS_NP": "OPEN",
        },
    }
    receipt = {**core, "receipt_sha256": digest(core)}
    receipt_path = out_dir / f"{label}.cosmos-state.pyramid.receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a DemiHead-mediated OSIRIS ORIGIN_PRIME packet through Pyramid Language")
    parser.add_argument("request", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    request = load_request(args.request)
    receipt = render_request(request, args.repo_root, args.out_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
