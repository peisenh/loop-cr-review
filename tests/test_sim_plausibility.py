"""Simulator checks (SIMULATION-SPEC). Skips without simglucose."""

from __future__ import annotations

import importlib
import unittest

try:
    importlib.import_module("simglucose")
    _HAS_SIM = True
except ImportError:
    _HAS_SIM = False


@unittest.skipUnless(_HAS_SIM, "simglucose not installed (requirements-sim.txt)")
class TestSimPlausibility(unittest.TestCase):
    def test_plausibility_script(self):
        from sim.check_plausibility import (
            check_bolus_returns, check_meal_rises, check_night_flat,
        )
        check_night_flat()
        check_meal_rises()
        check_bolus_returns()

    def test_cr_true_d4_near_zero(self):
        from sim.cr_true import measure
        out = measure()
        self.assertLess(abs(out.delta_4h), 3.0)
        self.assertGreater(out.cr_d4, 3.0)
        self.assertLess(out.cr_d4, 40.0)
        self.assertGreater(out.bolus_d4, 0.5)

    def test_controller_isolation_and_zero_error(self):
        from sim.check_controller import check_isolation, check_zero_error_extra
        check_isolation()
        check_zero_error_extra()

    def test_loop_uptake_positive_error_is_partial(self):
        from sim.cr_true import measure
        from sim.loop_uptake import one
        ref = measure()
        u = one(ref.cr_d4, 0.20)
        self.assertIsNotNone(u.L)
        self.assertGreater(u.L, 0.05)
        self.assertLess(u.L, 0.95)
        self.assertGreater(u.extra_u, 0.0)


if __name__ == "__main__":
    unittest.main()
