import importlib.util
import math
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "voice_of_janus.py"
SPEC = importlib.util.spec_from_file_location("voice_of_janus", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class VoiceOfJanusTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "geometry_m": {"Lx": 10.45, "Ly": 5.20, "Lz": 5.80},
            "environment": {"speed_of_sound_m_s": 343.0},
            "solver": {"max_index": 5, "frequency_limit_hz": 240.0},
            "render": {
                "min_render_hz": 20.0,
                "max_render_hz": 220.0,
                "max_render_modes": 12,
            },
            "creative_translation": {
                "enabled": False,
                "minimum_audible_hz": 20.0,
            },
        }

    def test_first_long_axis_mode(self):
        modes = MODULE.calculate_modes(self.config)
        target = next(m for m in modes if (m.p, m.q, m.r) == (1, 0, 0))
        expected = 343.0 / (2.0 * 10.45)
        self.assertTrue(math.isclose(target.physical_hz, expected, rel_tol=0.0, abs_tol=1e-8))
        self.assertEqual(target.mode_class, "axial")
        self.assertEqual(target.octave_multiplier, 1)

    def test_axis_modes_are_distinct(self):
        modes = MODULE.calculate_modes(self.config)
        by_index = {(m.p, m.q, m.r): m for m in modes}
        self.assertAlmostEqual(by_index[(1, 0, 0)].physical_hz, 16.411483254, places=8)
        self.assertAlmostEqual(by_index[(0, 1, 0)].physical_hz, 32.980769231, places=8)
        self.assertAlmostEqual(by_index[(0, 0, 1)].physical_hz, 29.568965517, places=8)

    def test_creative_translation_preserves_physical_frequency(self):
        self.config["creative_translation"]["enabled"] = True
        modes = MODULE.calculate_modes(self.config)
        target = next(m for m in modes if (m.p, m.q, m.r) == (1, 0, 0))
        self.assertAlmostEqual(target.physical_hz, 16.411483254, places=8)
        self.assertAlmostEqual(target.render_hz, 32.822966507, places=8)
        self.assertEqual(target.octave_multiplier, 2)

    def test_invalid_geometry_fails_closed(self):
        self.config["geometry_m"]["Lx"] = 0
        with self.assertRaises(ValueError):
            MODULE.calculate_modes(self.config)


if __name__ == "__main__":
    unittest.main()
