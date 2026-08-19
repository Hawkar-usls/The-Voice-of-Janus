from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from demihead_language_adapter import (  # noqa: E402
    CONTRACT,
    HEAD_REPOSITORY,
    REQUEST_SCHEMA,
    VOICE_REPOSITORY,
    render_language_request,
    sha256_bytes,
    sha256_json,
    validate_request,
)
from json_record import canonical_json_bytes  # noqa: E402


def build_request(value):
    payload = canonical_json_bytes(value)
    core = {
        "schema": REQUEST_SCHEMA,
        "contract": CONTRACT,
        "source": {"repository": HEAD_REPOSITORY, "source_revision": "a" * 40},
        "destination": {"repository": VOICE_REPOSITORY, "role": "PYRAMID_LANGUAGE_AUDIO_RENDERER"},
        "task": "SONIFY_INLINE_JSON",
        "preset_id": "GREAT_PYRAMID_KINGS_CHAMBER_EXAMPLE",
        "output_label": "language_test",
        "inline_json": value,
        "canonical_json_sha256": sha256_bytes(payload),
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
    request = {**core, "request_id": sha256_json({"kind": "JANUS_PYRAMID_LANGUAGE_REQUEST_ID", **core})}
    request["request_sha256"] = sha256_json(request)
    return request


class DemiHeadLanguageAdapterTests(unittest.TestCase):
    def test_valid_request_renders_hash_bound_record(self):
        request = build_request({"x": 1})
        validate_request(request)
        with tempfile.TemporaryDirectory() as temp_dir:
            receipt = render_language_request(request, ROOT, Path(temp_dir))
            self.assertEqual(receipt["status"], "JSON_SONIFIED_NOT_PLAYED")
            self.assertEqual(receipt["request"]["canonical_json_sha256"], request["canonical_json_sha256"])
            self.assertFalse(receipt["control"]["network_io_performed"])
            self.assertFalse(receipt["control"]["automatic_playback_performed"])
            self.assertFalse(receipt["control"]["microphone_opened"])
            wav_path = Path(receipt["output"]["wav_path"])
            self.assertTrue(wav_path.is_file())
            self.assertGreater(wav_path.stat().st_size, 44)

    def test_tampered_payload_rejected(self):
        request = build_request({"x": 1})
        tampered = copy.deepcopy(request)
        tampered["inline_json"]["x"] = 2
        with self.assertRaises(ValueError):
            validate_request(tampered)

    def test_mic_permission_escalation_rejected(self):
        request = build_request({"x": 1})
        request["control"]["microphone_start_permitted"] = True
        with self.assertRaises(ValueError):
            validate_request(request)


if __name__ == "__main__":
    unittest.main()
