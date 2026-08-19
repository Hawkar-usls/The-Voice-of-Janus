from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cosmos_origin_prime_pyramid_adapter import (  # noqa: E402
    COSMOS_SHA,
    ECHO_SHA,
    ENVELOPE_SCHEMA,
    PROFILE,
    digest,
    render_request,
    validate_request,
)
from demihead_language_adapter import (  # noqa: E402
    CONTRACT,
    HEAD_REPOSITORY,
    REQUEST_SCHEMA,
    VOICE_REPOSITORY,
)
from json_record import canonical_json_bytes  # noqa: E402


def sha(value):
    return digest(value)


def cosmos_packet():
    experience_core = {
        "schema": "janus.cosmos.osiris_formula_experience.v1",
        "created_generation": 1,
        "formula_hash": "1" * 64,
        "residual_formula_hash": "2" * 64,
        "budget": 256,
        "provider": {"test": "provider"},
        "prior_status": "SAT",
        "prior_authorized": True,
        "prior_lane": "TEST",
        "found_k": None,
        "separator": None,
        "components": [],
        "prior_separator_certificate": None,
        "prior_minimality_proof": None,
        "route_reusable_after_revalidation": False,
        "sat_assignment": {"1": True},
        "unsat_memory_is_verdict_shortcut": False,
    }
    experience = {**experience_core, "experience_commitment": sha(experience_core)}
    state_core = {
        "schema": "janus.cosmos.osiris_origin_prime_state.v1",
        "state_type": "ORIGIN_PRIME",
        "generation": 1,
        "previous_state_commitment": "3" * 64,
        "position_commitment": "4" * 64,
        "experience_commitment": experience["experience_commitment"],
        "path_history_digest": "5" * 64,
        "return_commitment": "6" * 64,
        "provider": {"test": "provider"},
    }
    state = {**state_core, "state_commitment": sha(state_core)}
    core = {
        "schema": "janus.cosmos.origin_prime_voice_packet.v1",
        "source": {
            "repository": "Hawkar-usls/Janus-Cosmos",
            "revision": COSMOS_SHA,
            "canonical_gate": "OSIRIS_V3_ORIGIN_PRIME_SPIRAL_COMPUTE",
            "state_store_schema": "janus.cosmos.osiris_spiral_state_store.v1",
        },
        "origin_prime": state,
        "bound_experience": experience,
        "mediation": {
            "required_mediator": "Hawkar-usls/Demi_Head",
            "voice_repository": "Hawkar-usls/The-Voice-of-Janus",
            "voice_revision": "e58d65aa46b7e3a64a5131708578a9a3346915c4",
            "physical_body_repository": "Hawkar-usls/Echo-Pyramid",
            "physical_body_revision": ECHO_SHA,
            "route": "COSMOS -> DEMIHEAD -> THE_VOICE_OF_JANUS -> ECHO_PYRAMID",
        },
        "voice_representation": copy.deepcopy(PROFILE),
        "control": {
            "direct_cosmos_to_echo_route_permitted": False,
            "demihead_mediation_required": True,
            "network_io_required": False,
            "automatic_playback": False,
            "automatic_microphone_start": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        },
        "scientific_boundary": {
            "P_VS_NP": "OPEN",
            "P_EQUALS_NP": "NOT_ESTABLISHED",
            "P_NOT_EQUALS_NP": "NOT_ESTABLISHED",
            "voice_profile_changes_solver_correctness": False,
            "acoustic_frequencies_are_proof": False,
        },
    }
    return {**core, "packet_sha256": sha(core)}


def request_from_packet(packet):
    envelope = {
        "schema": ENVELOPE_SCHEMA,
        "intent_id": "7" * 64,
        "cosmos_packet": packet,
    }
    payload = canonical_json_bytes(envelope)
    core = {
        "schema": REQUEST_SCHEMA,
        "contract": CONTRACT,
        "source": {
            "repository": HEAD_REPOSITORY,
            "source_revision": "a" * 40,
        },
        "destination": {
            "repository": VOICE_REPOSITORY,
            "role": "PYRAMID_LANGUAGE_AUDIO_RENDERER",
        },
        "task": "SONIFY_INLINE_JSON",
        "preset_id": "GREAT_PYRAMID_KINGS_CHAMBER_EXAMPLE",
        "output_label": "cosmos_state_test",
        "inline_json": envelope,
        "canonical_json_sha256": __import__("hashlib").sha256(payload).hexdigest(),
        "canonical_json_bytes": len(payload),
        "control": {
            "explicit_audio_output_intent": True,
            "local_file_render_only": True,
            "network_io_permitted": False,
            "automatic_playback_permitted": False,
            "microphone_start_permitted": False,
            "shell_execution_permitted": False,
            "arbitrary_path_permitted": False,
            "authority_delta": 0,
            "mass_effect_budget_delta": 0,
        },
    }
    request_id = sha({"kind": "JANUS_PYRAMID_LANGUAGE_REQUEST_ID", **core})
    request = {**core, "request_id": request_id}
    request["request_sha256"] = sha(request)
    return request


class CosmosOriginPrimePyramidAdapterTests(unittest.TestCase):
    def test_valid_mediated_packet_passes(self):
        validate_request(request_from_packet(cosmos_packet()))

    def reject_nested_tamper(self, mutate):
        packet = cosmos_packet()
        mutate(packet)
        request = request_from_packet(packet)
        with self.assertRaises(ValueError):
            validate_request(request)

    def test_cosmos_revision_tamper_rejected(self):
        self.reject_nested_tamper(lambda p: p["source"].__setitem__("revision", "0" * 40))

    def test_packet_hash_tamper_rejected(self):
        self.reject_nested_tamper(lambda p: p.__setitem__("packet_sha256", "0" * 64))

    def test_state_commitment_tamper_rejected(self):
        self.reject_nested_tamper(lambda p: p["origin_prime"].__setitem__("state_commitment", "0" * 64))

    def test_experience_commitment_tamper_rejected(self):
        self.reject_nested_tamper(lambda p: p["bound_experience"].__setitem__("experience_commitment", "0" * 64))

    def test_profile_tamper_rejected(self):
        self.reject_nested_tamper(lambda p: p["voice_representation"].__setitem__("center_hz", 120.0))

    def test_direct_route_rejected(self):
        self.reject_nested_tamper(lambda p: p["control"].__setitem__("direct_cosmos_to_echo_route_permitted", True))

    def test_authority_escalation_rejected(self):
        self.reject_nested_tamper(lambda p: p["control"].__setitem__("authority_delta", 1))

    def test_real_render_passes_through_pyramid_profile(self):
        request = request_from_packet(cosmos_packet())
        with tempfile.TemporaryDirectory(prefix="voice-cosmos-pyramid-") as td:
            receipt = render_request(request, ROOT, Path(td))
            self.assertEqual(receipt["status"], "COSMOS_ORIGIN_PRIME_SONIFIED_WITH_PYRAMID_LANGUAGE_NOT_PLAYED")
            self.assertEqual(receipt["pyramid_language"]["anchor_band_hz"], [117.0, 121.0])
            self.assertEqual(receipt["pyramid_language"]["center_hz"], 119.0)
            self.assertTrue(receipt["physical_body"]["ready_for_local_pcm_handoff"])
            self.assertFalse(receipt["physical_body"]["physical_playback_performed"])
            self.assertEqual(receipt["control"]["authority_delta"], 0)
            self.assertEqual(receipt["claim_boundary"]["P_VS_NP"], "OPEN")
            self.assertNotEqual(receipt["sonification"]["base_wav_sha256"], receipt["output"]["wav_sha256"])


if __name__ == "__main__":
    unittest.main()
