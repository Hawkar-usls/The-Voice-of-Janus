from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nexus_voice_spiral_runner import compare_receipts  # noqa: E402


def fake_receipt(speaker: str, wav_sha: str) -> dict:
    return {
        "status": "PASS",
        "source": {
            "sha256": "1" * 64,
            "semantic_text_sha256": "2" * 64,
        },
        "larynx": {"speaker": speaker},
        "language_operator": {
            "activation_sha256": "3" * 64,
            "anchor_band_hz": [117.0, 121.0],
            "anchor_center_hz": 119.0,
            "anchor_q": 29.75,
        },
        "output": {
            "path": f"outputs/{speaker}.wav",
            "sha256": wav_sha,
        },
        "nexus_binding": {
            "speaker": speaker,
            "request_sha256": ("a" if speaker == "aidar" else "b") * 64,
            "model_sha256": "4" * 64,
        },
    }


class NexusVoiceSpiralRunnerTests(unittest.TestCase):
    def test_compare_preserves_both_layers_without_winner(self) -> None:
        result = compare_receipts(
            [fake_receipt("aidar", "5" * 64), fake_receipt("eugene", "6" * 64)],
            "7" * 64,
        )
        self.assertEqual(result["status"], "PASS_AIDAR_EUGENE_SPIRAL_READY_FOR_HUMAN_LISTENING")
        self.assertEqual(result["spiral"]["preserved_layers"], ["LAYER_A_AIDAR", "LAYER_B_EUGENE"])
        self.assertFalse(result["spiral"]["automatic_winner_selection"])
        self.assertIsNone(result["human_evaluation"]["selected_voice_face"])
        self.assertTrue(result["shared_language"]["unchanged_between_layers"])

    def test_equal_wav_hashes_fail_closed(self) -> None:
        same = "8" * 64
        with self.assertRaises(RuntimeError):
            compare_receipts(
                [fake_receipt("aidar", same), fake_receipt("eugene", same)],
                "9" * 64,
            )

    def test_language_drift_fails_closed(self) -> None:
        aidar = fake_receipt("aidar", "a" * 64)
        eugene = fake_receipt("eugene", "b" * 64)
        eugene["language_operator"]["activation_sha256"] = "c" * 64
        with self.assertRaises(RuntimeError):
            compare_receipts([aidar, eugene], "d" * 64)


if __name__ == "__main__":
    unittest.main()
