import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyramid_anchor_filter import Pyramid117121Filter


def probe_rms(frequency_hz: float, sample_rate_hz: int = 22050) -> float:
    filter_ = Pyramid117121Filter(sample_rate_hz)
    samples = []
    for index in range(sample_rate_hz * 2):
        sample = 0.12 * math.sin(2.0 * math.pi * frequency_hz * index / sample_rate_hz)
        output = filter_.process_sample(sample)
        if index >= sample_rate_hz:
            samples.append(output)
    return math.sqrt(sum(value * value for value in samples) / len(samples))


class PyramidAnchorFilterTests(unittest.TestCase):
    def test_anchor_band_is_dominant(self):
        at_anchor = probe_rms(119.0)
        outside_anchor = probe_rms(135.0)
        self.assertGreater(at_anchor, outside_anchor * 1.5)

    def test_filter_is_stateful_and_finite(self):
        filter_ = Pyramid117121Filter(22050)
        impulse = [1.0] + [0.0] * 5000
        output = filter_.process_block(impulse)
        self.assertEqual(len(output), len(impulse))
        self.assertTrue(all(math.isfinite(value) for value in output))
        self.assertGreater(sum(abs(value) for value in output[1:]), 0.0)

    def test_invalid_anchor_rejected(self):
        with self.assertRaises(ValueError):
            Pyramid117121Filter(22050, anchor_low_hz=121.0, anchor_high_hz=117.0)


if __name__ == "__main__":
    unittest.main()
