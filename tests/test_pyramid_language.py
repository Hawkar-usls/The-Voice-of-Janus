from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from json_record import canonical_json_bytes, render_json_record  # noqa: E402
from pyramid_dsp import build_filter_from_preset, load_preset  # noqa: E402


PRESET = ROOT / "presets" / "great_pyramid_kings_chamber.example.json"


class PyramidLanguageTests(unittest.TestCase):
    def test_canonical_json_is_order_invariant(self):
        left = {"b": 2, "a": [1, "x"]}
        right = {"a": [1, "x"], "b": 2}
        self.assertEqual(canonical_json_bytes(left), canonical_json_bytes(right))

    def test_modal_filter_is_finite_and_stateful(self):
        preset = load_preset(PRESET)
        filter_, modes = build_filter_from_preset(preset, mode_count=4)
        self.assertEqual(len(modes), 4)
        impulse = [1.0] + [0.0] * 2047
        output = filter_.process_block(impulse)
        self.assertEqual(len(output), len(impulse))
        self.assertTrue(all(math.isfinite(value) for value in output))
        self.assertTrue(any(abs(value) > 1e-8 for value in output[1:]))
        self.assertTrue(all(abs(value) <= 1.0 for value in output))

    def test_json_record_is_deterministic_and_hash_bound(self):
        preset = load_preset(PRESET)
        value = {"janus": "remembers", "n": 14}
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first.wav"
            second = Path(temp_dir) / "second.wav"
            receipt_a = render_json_record(value, preset, first, sample_rate_hz=8000, tone_ms=2.0, gap_ms=0.0)
            receipt_b = render_json_record(value, preset, second, sample_rate_hz=8000, tone_ms=2.0, gap_ms=0.0)
            self.assertEqual(receipt_a["canonical_json_sha256"], receipt_b["canonical_json_sha256"])
            self.assertEqual(receipt_a["audio"]["sha256"], receipt_b["audio"]["sha256"])
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertFalse(receipt_a["claim_boundary"]["reversible_decode_established"])


if __name__ == "__main__":
    unittest.main()
