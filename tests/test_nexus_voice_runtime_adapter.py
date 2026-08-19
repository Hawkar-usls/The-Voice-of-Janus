from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import nexus_voice_runtime_adapter as adapter  # noqa: E402


class NexusVoiceRuntimeAdapterTests(unittest.TestCase):
    def request(self):
        core = {
            "schema": adapter.REQUEST_SCHEMA,
            "contract": adapter.CONTRACT,
            "task": adapter.TASK,
            "target_head": "VOICE_RUNTIME",
            "source": {
                "artifact_id": adapter.SOURCE_ARTIFACT_ID,
                "semantic_field": adapter.SEMANTIC_FIELD,
                "required_formula": adapter.REQUIRED_FORMULA,
            },
            "larynx": {
                "backend": "silero_v5_5_ru",
                "speaker": "aidar",
                "model_relative_path": adapter.MODEL_PATH,
                "model_download_permitted": False,
            },
            "language": {
                "profile_id": adapter.LANGUAGE_PROFILE,
                "activation": adapter.ACTIVATION,
                "activation_blob_sha": adapter.ACTIVATION_BLOB_SHA,
                "anchor_band_hz": [117.0, 121.0],
                "semantic_content_preserved": True,
            },
            "voice_runtime": {
                "config": adapter.VOICE_CONFIG,
                "config_blob_sha": adapter.VOICE_CONFIG_BLOB_SHA,
                "runner": adapter.VOICE_RUNNER,
                "runner_blob_sha": adapter.VOICE_RUNNER_BLOB_SHA,
                "output_label": "OSIRIS_ORIGIN_PRIME_NEURAL_AIDAR",
            },
            "physical_body": {
                "repository": "Hawkar-usls/Echo-Pyramid",
                "role": "PHYSICAL_VOICE_BODY",
                "automatic_handoff": False,
            },
            "control": {
                "prepared_by_nexus": True,
                "audio_rendered": False,
                "filesystem_io_performed": False,
                "network_io_performed": False,
                "automatic_playback": False,
                "automatic_bluetooth": False,
                "firmware_flash": False,
                "external_effect_permitted": False,
                "explicit_voice_execute_required": True,
                "explicit_physical_output_authorization_required": True,
                "authority_delta": 0,
                "mass_effect_budget_delta": 0,
            },
        }
        return {**core, "request_sha256": adapter.sha256(core)}

    def test_accepts_canonical_prepared_request(self):
        request = self.request()
        speaker, label = adapter.validate_request(request)
        self.assertEqual(speaker, "aidar")
        self.assertEqual(label, "OSIRIS_ORIGIN_PRIME_NEURAL_AIDAR")

    def test_rejects_tampered_hash(self):
        request = self.request()
        request["larynx"]["speaker"] = "eugene"
        with self.assertRaises(ValueError):
            adapter.validate_request(request)

    def test_rejects_model_path_override(self):
        request = self.request()
        request["larynx"]["model_relative_path"] = "/tmp/model.pt"
        core = {k: v for k, v in request.items() if k != "request_sha256"}
        request["request_sha256"] = adapter.sha256(core)
        with self.assertRaises(ValueError):
            adapter.validate_request(request)

    def test_rejects_autoplay(self):
        request = self.request()
        request["control"]["automatic_playback"] = True
        core = {k: v for k, v in request.items() if k != "request_sha256"}
        request["request_sha256"] = adapter.sha256(core)
        with self.assertRaises(ValueError):
            adapter.validate_request(request)

    def test_rejects_path_traversal_output_label(self):
        request = self.request()
        request["voice_runtime"]["output_label"] = "../escape"
        core = {k: v for k, v in request.items() if k != "request_sha256"}
        request["request_sha256"] = adapter.sha256(core)
        with self.assertRaises(ValueError):
            adapter.validate_request(request)

    def test_pinned_files_match_current_git_blobs(self):
        self.assertEqual(adapter.git_blob_sha(ROOT / adapter.ACTIVATION), adapter.ACTIVATION_BLOB_SHA)
        self.assertEqual(adapter.git_blob_sha(ROOT / adapter.VOICE_CONFIG), adapter.VOICE_CONFIG_BLOB_SHA)
        self.assertEqual(adapter.git_blob_sha(ROOT / adapter.VOICE_RUNNER), adapter.VOICE_RUNNER_BLOB_SHA)


if __name__ == "__main__":
    unittest.main()
