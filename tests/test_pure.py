# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every operation in lcr.pure, checked against the numpy call it replaces.

These are not tests of plausibility. Each one asserts that the two agree to the
last bit that floating point allows, on the shapes the real data takes: an AGP
bin holding one value per day, a bootstrap sample, a whole export, integer
glucose readings where ties are common, and traces with sensor gaps in them.

The percentile is the one that matters most — numpy interpolates linearly
between ranks and statistics.quantiles does not, and getting that wrong would
move the AGP bands and the time-in-range figures without anything looking
broken. It is checked first and hardest.

numpy is still a test dependency here on purpose: the point is to prove the
replacement matches, and that needs the original present to compare against. It
is in `requirements-dev.txt`, not in the runtime ones — where it is absent these
comparisons skip rather than fail, and the checks that need no comparison still
run.
"""
from __future__ import annotations

import math
import random
import unittest

try:
    import numpy as np
except ImportError:                                  # pragma: no cover
    np = None

from lcr import pure

QUANTILES = (2.5, 5, 10, 25, 50, 75, 90, 95, 97.5)
TOLERANCE = 1e-9


def _shapes():
    """The sizes and spreads the real data actually takes. -> list of lists"""
    random.seed(20260904)
    out = []
    for n in (1, 2, 3, 5, 7, 14, 89, 90, 91, 288, 2000, 26000):
        for spread in (0.5, 40.0):
            out.append([random.gauss(140, spread) for _ in range(n)])
    # Glucose is reported in whole mg/dL, so ties are the normal case and an
    # off-by-one in a rank shows up here rather than on smooth data.
    for n in (5, 14, 90, 288):
        out.append([float(random.randint(70, 180)) for _ in range(n)])
    return out


def _with_gaps():
    """Traces with sensor dropouts. -> list of lists"""
    random.seed(4092026)
    out = []
    for n, holes in ((14, 3), (90, 30), (288, 200), (30, 29)):
        vals = [random.gauss(140, 40) for _ in range(n)]
        for i in random.sample(range(n), holes):
            vals[i] = math.nan
        out.append(vals)
    out.append([120.0] * 30)
    return out


@unittest.skipIf(np is None, "numpy not installed (requirements-dev.txt)")
class TestPercentile(unittest.TestCase):
    """The one that can be subtly wrong and still look right."""

    def test_matches_numpy_on_every_shape(self):
        for values in _shapes():
            arr = np.array(values, dtype=float)
            for q in QUANTILES:
                with self.subTest(n=len(values), q=q):
                    self.assertAlmostEqual(pure.percentile(values, q),
                                           float(np.percentile(arr, q)), delta=TOLERANCE)

    def test_matches_numpy_where_values_are_missing(self):
        for values in _with_gaps():
            arr = np.array(values, dtype=float)
            for q in QUANTILES:
                with self.subTest(n=len(values), q=q):
                    self.assertAlmostEqual(pure.percentile(values, q),
                                           float(np.nanpercentile(arr, q)), delta=TOLERANCE)

    def test_nothing_present_is_not_zero(self):
        """An empty window has no median, and must not report one."""
        self.assertTrue(math.isnan(pure.percentile([math.nan, math.nan], 50)))


@unittest.skipIf(np is None, "numpy not installed (requirements-dev.txt)")
class TestAggregates(unittest.TestCase):
    """Medians, means and extremes, with and without gaps."""

    def test_median_and_nanmedian(self):
        for values in _shapes():
            arr = np.array(values, dtype=float)
            with self.subTest(n=len(values)):
                self.assertAlmostEqual(pure.median(values), float(np.median(arr)),
                                       delta=TOLERANCE)
        for values in _with_gaps():
            arr = np.array(values, dtype=float)
            with self.subTest(gaps=len(values)):
                self.assertAlmostEqual(pure.nanmedian(values),
                                       float(np.nanmedian(arr)), delta=TOLERANCE)

    def test_median_of_a_trace_with_gaps_is_not_a_number(self):
        """numpy's median, unlike nanmedian, refuses when values are missing."""
        self.assertTrue(math.isnan(pure.median([1.0, math.nan, 3.0])))

    def test_mean_and_nanmean(self):
        for values in _shapes():
            arr = np.array(values, dtype=float)
            with self.subTest(n=len(values)):
                self.assertAlmostEqual(pure.mean(values), float(np.mean(arr)),
                                       delta=1e-8)
        for values in _with_gaps():
            arr = np.array(values, dtype=float)
            with self.subTest(gaps=len(values)):
                self.assertAlmostEqual(pure.nanmean(values), float(np.nanmean(arr)),
                                       delta=1e-8)

    def test_extremes_and_their_positions(self):
        for values in _with_gaps():
            arr = np.array(values, dtype=float)
            with self.subTest(n=len(values)):
                self.assertAlmostEqual(pure.nanmax(values), float(np.nanmax(arr)),
                                       delta=TOLERANCE)
                self.assertAlmostEqual(pure.nanmin(values), float(np.nanmin(arr)),
                                       delta=TOLERANCE)
                self.assertEqual(pure.nanargmax(values), int(np.nanargmax(arr)))
                self.assertEqual(pure.nanargmin(values), int(np.nanargmin(arr)))


@unittest.skipIf(np is None, "numpy not installed (requirements-dev.txt)")
class TestSequenceOperations(unittest.TestCase):
    """Search, difference and sort order."""

    def test_searchsorted_both_sides(self):
        ordered = [0, 10, 10, 20, 30, 30, 30, 40]
        for value in range(-5, 46):
            for side in ("left", "right"):
                with self.subTest(value=value, side=side):
                    self.assertEqual(pure.searchsorted(ordered, value, side),
                                     int(np.searchsorted(ordered, value, side=side)))

    def test_searchsorted_on_datetimes(self):
        """The gap check searches a trace of timestamps, not of numbers."""
        from datetime import datetime, timedelta
        base = datetime(2026, 7, 1, 8, 0)
        stamps = [base + timedelta(minutes=5 * i) for i in range(20)]
        self.assertEqual(pure.searchsorted(stamps, base + timedelta(minutes=12)), 3)
        self.assertEqual(pure.searchsorted(stamps, base, side="right"), 1)

    def test_diff(self):
        for values in _shapes()[:8]:
            with self.subTest(n=len(values)):
                self.assertEqual([round(v, 9) for v in pure.diff(values)],
                                 [round(float(v), 9) for v in np.diff(values)])

    def test_argsort_is_stable_like_numpy(self):
        values = [3.0, 1.0, 2.0, 1.0, 3.0]
        self.assertEqual(pure.argsort(values), list(np.argsort(values, kind="stable")))

    def test_clip_and_digitize(self):
        edges = [0, 10, 20, 30]
        for value in (-1, 0, 5, 10, 25, 30, 40):
            with self.subTest(value=value):
                self.assertEqual(pure.digitize(value, edges),
                                 int(np.digitize(value, edges)))
        self.assertEqual(pure.clip(5, 0, 10), float(np.clip(5, 0, 10)))
        self.assertEqual(pure.clip(-3, 0, 10), float(np.clip(-3, 0, 10)))
        self.assertEqual(pure.clip(99, 0, 10), float(np.clip(99, 0, 10)))

    def test_ranges(self):
        for args in ((0, 24, 3), (0, 1441, 15), (0, 241, 10)):
            with self.subTest(args=args):
                self.assertEqual([round(v, 9) for v in pure.arange(*args)],
                                 [round(float(v), 9) for v in np.arange(*args)])
        self.assertEqual([round(v, 9) for v in pure.linspace(0, 1, 5)],
                         [round(float(v), 9) for v in np.linspace(0, 1, 5)])


class TestMissingValues(unittest.TestCase):
    """A gap has to stay distinguishable from a reading of zero."""

    def test_is_nan_accepts_what_the_readers_produce(self):
        for value in (math.nan, None, float("nan")):
            with self.subTest(value=value):
                self.assertTrue(pure.is_nan(value))
        for value in (0, 0.0, -1, 120.5):
            with self.subTest(value=value):
                self.assertFalse(pure.is_nan(value))

    def test_zero_is_kept(self):
        self.assertEqual(pure.clean([0.0, math.nan, 1.0]), [0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
