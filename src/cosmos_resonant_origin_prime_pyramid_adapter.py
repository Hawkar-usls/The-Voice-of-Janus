#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

import cosmos_origin_prime_pyramid_adapter as base

COSMOS_SHA = "c543eb6ed753339fabed33d7f0ab880d43433d0f"
CONTRACT_PATH = Path(__file__).resolve().parents[1] / "data" / "COSMOS_RESONANT_ORIGIN_PRIME_PYRAMID_RENDER_FROZEN_CONTRACT.v1.json"
CONTRACT_ID = "VOICE_COSMOS_RESONANT_ORIGIN_PRIME_PYRAMID_RENDER_FROZEN_CONTRACT_V1"
EXTENSION_SCHEMA = "janus.cosmos.origin_prime_resonant_representation_extension.v1"
ORION_ANCHOR = "ORION_BELT_SAH_OSIRIS_CONTEXT_v1"
TRANSFER_CLASS = "VARIABLE_RENAMING_BIJECTION"
ORIGINAL_VALIDATE_PACKET = base.validate_cosmos_packet
ORIGINAL_LOAD_CONTRACT = base.load_contract

ASTRAL_REPRESENTATION = {
    "anchor_id": ORION_ANCHOR,
    "star_triplet": ["Mintaka", "Alnilam", "Alnitak"],
    "egyptological_context": "SAH_ORION_OSIRIS_RELIGIOUS_TEXTUAL_CONTEXT",
    "giza_orion_correlation": "HYPOTHESIS_NOT_ASSERTED_AS_ARCHITECTURAL_FACT",
    "janus_rebus_alias": "S𓂸ḥ",
    "janus_rebus_alias_is_historical_transliteration": False,
    "seasonal_visibility": "CONTEXT_ONLY",
    "role": "ASTRAL_CONTEXT_AND_NAVIGATION_REPRESENTATION_ONLY",
    "authority_delta": 0,
    "astral_geometry_is_proof": False,
    "astral_context_changes_solver_correctness": False,
}


def load_contract() -> dict[str, Any]:
    value = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if value.get("status") != "FROZEN_BEFORE_IMPLEMENTATION":
        raise ValueError("RESONANT_COSMOS_PYRAMID_CONTRACT_NOT_FROZEN")
    source = value.get("source_provider")
    if not isinstance(source, Mapping) or source.get("sha") != COSMOS_SHA:
        raise ValueError("RESONANT_COSMOS_PROVIDER_PIN_MISMATCH")
    if value.get("parent_adapter_rewritten") is not False:
        raise ValueError("RESONANT_PARENT_ADAPTER_LINEAGE_INVALID")
    return value


def _representation_binding_core(packet: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "origin_prime_state_commitment": packet["origin_prime"]["state_commitment"],
        "experience_commitment": packet["origin_prime"].get("experience_commitment"),
        "voice_representation": packet["voice_representation"],
        "astral_representation": packet["astral_representation"],
        "lineage_representation": packet["lineage_representation"],
        "authority_delta": 0,
    }


@contextmanager
def _pin_cosmos_sha_only():
    prior = base.COSMOS_SHA
    base.COSMOS_SHA = COSMOS_SHA
    try:
        yield
    finally:
        base.COSMOS_SHA = prior


def validate_resonant_packet(packet: Mapping[str, Any]) -> None:
    with _pin_cosmos_sha_only():
        ORIGINAL_VALIDATE_PACKET(packet)
    if packet.get("representation_extension_schema") != EXTENSION_SCHEMA:
        raise ValueError("RESONANT_PACKET_EXTENSION_SCHEMA_INVALID")
    if packet.get("astral_representation") != ASTRAL_REPRESENTATION:
        raise ValueError("RESONANT_PACKET_ASTRAL_REPRESENTATION_INVALID")

    lineage = packet.get("lineage_representation")
    if not isinstance(lineage, Mapping):
        raise ValueError("RESONANT_PACKET_LINEAGE_REPRESENTATION_INVALID")
    if lineage.get("memory_may_propose_not_verdict") is not True or lineage.get("authority_delta") != 0:
        raise ValueError("RESONANT_PACKET_LINEAGE_AUTHORITY_LEAK")
    if lineage.get("transfer_present"):
        if lineage.get("transfer_class") != TRANSFER_CLASS:
            raise ValueError("RESONANT_PACKET_TRANSFER_CLASS_INVALID")
        for field in ("source_experience_commitment", "transformation_certificate_sha256"):
            value = lineage.get(field)
            if not isinstance(value, str) or base.HEX64.fullmatch(value) is None:
                raise ValueError(f"RESONANT_PACKET_{field.upper()}_INVALID")
        experience = packet.get("bound_experience")
        transfer = experience.get("lineage_transfer") if isinstance(experience, Mapping) else None
        if not isinstance(transfer, Mapping):
            raise ValueError("RESONANT_PACKET_BOUND_LINEAGE_TRANSFER_MISSING")
        if transfer.get("class") != lineage.get("transfer_class"):
            raise ValueError("RESONANT_PACKET_BOUND_LINEAGE_CLASS_MISMATCH")
        if transfer.get("source_experience_commitment") != lineage.get("source_experience_commitment"):
            raise ValueError("RESONANT_PACKET_BOUND_LINEAGE_SOURCE_MISMATCH")
        if transfer.get("transformation_certificate_sha256") != lineage.get("transformation_certificate_sha256"):
            raise ValueError("RESONANT_PACKET_BOUND_LINEAGE_CERTIFICATE_MISMATCH")
        if transfer.get("memory_may_propose_not_verdict") is not True or transfer.get("authority_delta") != 0:
            raise ValueError("RESONANT_PACKET_BOUND_LINEAGE_AUTHORITY_LEAK")

    claimed = packet.get("representation_binding_sha256")
    if not isinstance(claimed, str) or base.HEX64.fullmatch(claimed) is None:
        raise ValueError("RESONANT_PACKET_REPRESENTATION_BINDING_INVALID")
    if claimed != base.digest(_representation_binding_core(packet)):
        raise ValueError("RESONANT_PACKET_REPRESENTATION_BINDING_TAMPERED")


def validate_request(request: Mapping[str, Any]) -> None:
    with _patch_parent_adapter():
        base.validate_request(request)


@contextmanager
def _patch_parent_adapter():
    prior_sha = base.COSMOS_SHA
    prior_load = base.load_contract
    prior_validate = base.validate_cosmos_packet
    base.COSMOS_SHA = COSMOS_SHA
    base.load_contract = load_contract
    base.validate_cosmos_packet = validate_resonant_packet
    try:
        yield
    finally:
        base.COSMOS_SHA = prior_sha
        base.load_contract = prior_load
        base.validate_cosmos_packet = prior_validate


def _enhance_receipt(receipt: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, Any]:
    packet = request["inline_json"]["cosmos_packet"]
    lineage = packet["lineage_representation"]
    core = copy.deepcopy(dict(receipt))
    core.pop("receipt_sha256", None)
    core["contract"] = CONTRACT_ID
    core["cosmos"]["representation_binding_sha256"] = packet["representation_binding_sha256"]
    core["resonant_representation"] = {
        "lineage_transfer_present": bool(lineage.get("transfer_present")),
        "lineage_transfer_class": lineage.get("transfer_class"),
        "transformation_certificate_sha256": lineage.get("transformation_certificate_sha256"),
        "memory_may_propose_not_verdict": True,
        "voice_profile": packet["voice_representation"]["profile_id"],
        "orion_anchor": packet["astral_representation"]["anchor_id"],
        "janus_rebus_alias": packet["astral_representation"]["janus_rebus_alias"],
        "janus_rebus_alias_is_historical_transliteration": False,
        "authority_delta": 0,
    }
    core["claim_boundary"] = dict(core["claim_boundary"])
    core["claim_boundary"].update({
        "astral_geometry_is_proof": False,
        "orion_giza_architectural_intent": "NOT_ESTABLISHED",
    })
    return {**core, "receipt_sha256": base.digest(core)}


def validate_receipt(receipt: Mapping[str, Any]) -> None:
    if not isinstance(receipt, Mapping) or receipt.get("contract") != CONTRACT_ID:
        raise ValueError("RESONANT_RECEIPT_CONTRACT_INVALID")
    resonant = receipt.get("resonant_representation")
    if not isinstance(resonant, Mapping):
        raise ValueError("RESONANT_RECEIPT_REPRESENTATION_MISSING")
    if resonant.get("memory_may_propose_not_verdict") is not True or resonant.get("authority_delta") != 0:
        raise ValueError("RESONANT_RECEIPT_AUTHORITY_LEAK")
    if resonant.get("orion_anchor") != ORION_ANCHOR:
        raise ValueError("RESONANT_RECEIPT_ORION_ANCHOR_INVALID")
    if resonant.get("janus_rebus_alias_is_historical_transliteration") is not False:
        raise ValueError("RESONANT_RECEIPT_REBUS_TRANSLITERATION_ESCALATION")
    control = receipt.get("control")
    if not isinstance(control, Mapping) or control.get("automatic_playback_performed") is not False or control.get("authority_delta") != 0:
        raise ValueError("RESONANT_RECEIPT_CONTROL_INVALID")
    boundary = receipt.get("claim_boundary")
    if not isinstance(boundary, Mapping) or boundary.get("P_VS_NP") != "OPEN" or boundary.get("audio_is_proof") is not False:
        raise ValueError("RESONANT_RECEIPT_CLAIM_CEILING_INVALID")
    if boundary.get("astral_geometry_is_proof") is not False or boundary.get("orion_giza_architectural_intent") != "NOT_ESTABLISHED":
        raise ValueError("RESONANT_RECEIPT_ASTRAL_CLAIM_ESCALATION")
    claimed = receipt.get("receipt_sha256")
    if not isinstance(claimed, str) or base.HEX64.fullmatch(claimed) is None:
        raise ValueError("RESONANT_RECEIPT_HASH_INVALID")
    core = dict(receipt)
    core.pop("receipt_sha256", None)
    if claimed != base.digest(core):
        raise ValueError("RESONANT_RECEIPT_HASH_TAMPERED")


def render_request(request: Mapping[str, Any], repo_root: Path, out_dir: Path) -> dict[str, Any]:
    load_contract()
    validate_resonant_packet(request["inline_json"]["cosmos_packet"])
    with _patch_parent_adapter():
        parent_receipt = base.render_request(request, repo_root, out_dir)
    receipt = _enhance_receipt(parent_receipt, request)
    validate_receipt(receipt)
    receipt_path = out_dir.resolve() / f"{request['output_label']}.cosmos-state.pyramid.receipt.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a DemiHead-mediated resonant ORIGIN_PRIME packet through Pyramid Language")
    parser.add_argument("request", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out-dir", type=Path, default=Path("outputs"))
    args = parser.parse_args()
    request = base.load_request(args.request)
    receipt = render_request(request, args.repo_root, args.out_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
