from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from demihead_mouth_adapter import (  # noqa: E402
    CONTRACT,
    HEAD_REPOSITORY,
    REQUEST_SCHEMA,
    VOICE_REPOSITORY,
    prepare_render,
    self_test,
    sha256_json,
    validate_request,
    verify_request,
)


def build_fixture(output_label: str = "test_voice"):
    core = {
        "schema": REQUEST_SCHEMA,
        "contract": CONTRACT,
        "source": {"repository": HEAD_REPOSITORY, "source_revision": "a" * 40},
        "destination": {"repository": VOICE_REPOSITORY, "role": "LOCAL_AUDIO_RENDERER"},
        "task": "RENDER_PRESET",
        "preset_id": "GREAT_PYRAMID_KINGS_CHAMBER_EXAMPLE",
        "output_label": output_label,
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
    return request


class DemiHeadMouthAdapterTests(unittest.TestCase):
    def test_valid_request_is_accepted(self):
        request = build_fixture()
        validate_request(request)
        self.assertTrue(verify_request(request))

    def test_unknown_preset_fails_closed(self):
        request = build_fixture()
        request["preset_id"] = "../../etc/passwd"
        self.assertFalse(verify_request(request))

    def test_network_autoplay_shell_and_authority_escalation_fail(self):
        for key, value in (
            ("network_io_permitted", True),
            ("automatic_playback_permitted", True),
            ("shell_execution_permitted", True),
            ("authority_delta", 1),
            ("mass_effect_budget_delta", 1),
        ):
            request = build_fixture()
            request["control"][key] = value
            self.assertFalse(verify_request(request), key)

    def test_extra_command_field_fails_closed(self):
        request = build_fixture()
        request["command"] = "echo bypass"
        self.assertFalse(verify_request(request))

    def test_hash_tamper_fails_closed(self):
        request = build_fixture()
        request["output_label"] = "changed"
        self.assertFalse(verify_request(request))

    def test_prepare_render_uses_allowlisted_preset_and_safe_label(self):
        request = build_fixture("safe_name")
        with tempfile.TemporaryDirectory() as tmp:
            paths = prepare_render(request, ROOT, Path(tmp))
            self.assertEqual(paths["preset_path"], (ROOT / "presets/great_pyramid_kings_chamber.example.json").resolve())
            self.assertEqual(paths["wav_path"].name, "safe_name.wav")
            self.assertEqual(paths["bridge_receipt_path"].name, "safe_name.demihead-receipt.json")

    def test_unsafe_label_fails_closed(self):
        request = build_fixture()
        request["output_label"] = "../escape"
        body = copy.deepcopy(request)
        body.pop("request_sha256")
        request["request_sha256"] = sha256_json(body)
        self.assertFalse(verify_request(request))

    def test_self_test_passes_without_rendering_or_playback(self):
        result = self_test(ROOT)
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["preset_resolved"])
        self.assertFalse(result["network_io"])
        self.assertFalse(result["automatic_playback"])
        self.assertFalse(result["speech_tts"])


if __name__ == "__main__":
    unittest.main()
