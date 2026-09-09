# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The updated GMI (Xu/Dunn 2026) reported next to the established one."""
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lcr.analysis import consensus_metrics       # noqa: E402
from lcr.common import MGDL_PER_MMOL, set_glucose_unit   # noqa: E402


def _metrics(mean, unit="mg/dL"):
    start = datetime(2026, 5, 1)
    times = [start + timedelta(minutes=5 * i) for i in range(2016)]
    set_glucose_unit(unit)
    try:
        return consensus_metrics(times, [mean] * len(times))
    finally:
        set_glucose_unit("mg/dL")


class TestUpdatedGmi(unittest.TestCase):
    def test_published_formula(self):
        """uGMI(%) = 1/(15.36/AG + 0.0425), AG in mg/dL."""
        for mean in (80.0, 135.0, 180.0, 260.0):
            with self.subTest(mean=mean):
                self.assertAlmostEqual(_metrics(mean)["ugmi"],
                                       1 / (15.36 / mean + 0.0425), places=9)

    def test_same_in_either_glucose_unit(self):
        """Both GMIs are defined on a mg/dL mean, whatever the report shows."""
        mgdl = _metrics(135.0)
        mmol = _metrics(135.0 / MGDL_PER_MMOL, unit="mmol/L")
        for key in ("gmi", "gmi_mmol", "ugmi", "ugmi_mmol"):
            with self.subTest(key=key):
                self.assertAlmostEqual(mgdl[key], mmol[key], places=6)

    def test_crosses_the_classic_gmi_around_150(self):
        """Not an offset but a different curve: below it reads lower, above higher."""
        self.assertLess(_metrics(110.0)["ugmi"], _metrics(110.0)["gmi"])
        self.assertGreater(_metrics(220.0)["ugmi"], _metrics(220.0)["gmi"])

    def test_both_units_agree_within_rounding(self):
        """The per cent and mmol/mol forms are separate formulas from one paper."""
        met = _metrics(180.0)
        self.assertAlmostEqual((met["ugmi"] - 2.15) * 10.929, met["ugmi_mmol"], delta=1.0)


if __name__ == "__main__":
    unittest.main()
