"""Tests for the analysis core: loop extra basal, CR_eff, verdicts, metrics.

These use tiny hand-built inputs with values computed by hand, so a subtly
wrong formula fails here even when the end-to-end demo verdicts still look
plausible. This is the part users take into a conversation with their care
team, so the arithmetic is pinned down explicitly rather than only checked
for direction.
"""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta

import numpy as np

import loop_cr_review as core


def _basal(rate_per_min, fasting, t0=None):
    """Build the basal tuple analyze_meals expects.

    ``rate_per_min`` is one U/h value per minute slot (that is what
    read_basal_timeline expands the segments to).
    """
    t0 = t0 or datetime(2026, 5, 1, 0, 0)
    rate = np.array(rate_per_min, dtype=float)
    return (rate, t0, len(rate), fasting, fasting, fasting)


def _const_lookup(pre, post):
    """val_at stub: returns ``pre`` at offset 0 and ``post`` otherwise."""
    def val_at(_ref, minutes, tol=12):       # noqa: ARG001 - signature must match
        return pre if minutes == 0 else post
    return val_at


class TestLoopExtraBasalAndCrEff(unittest.TestCase):
    """excess = sum(rate - fasting)/60 over the window; CR_eff = cho/(bolus+excess)."""

    def setUp(self):
        self.t0 = datetime(2026, 5, 1, 0, 0)
        self.window = 240                     # 4 h

    def _one_meal(self, rate_per_min, fasting, cho, bolus, meal_hour=8,
                  pre=120.0, post=120.0):
        meal_time = self.t0 + timedelta(hours=meal_hour)
        meals = [{"time": meal_time, "cho": cho, "bolus": bolus, "bg": pre}]
        rows = core.analyze_meals(meals, [], _basal(rate_per_min, fasting, self.t0),
                                  self.window, _const_lookup(pre, post))
        self.assertEqual(len(rows), 1, "meal should be inside the basal timeline")
        return rows[0]

    def test_no_extra_basal_means_cr_eff_equals_cr(self):
        """Rate exactly at fasting level -> excess 0 -> CR_eff == CR."""
        rate = [0.8] * (24 * 60)
        row = self._one_meal(rate, fasting=0.8, cho=60.0, bolus=6.0)
        self.assertAlmostEqual(row["exc"], 0.0, places=9)
        self.assertAlmostEqual(row["cr"], 10.0, places=9)          # 60 / 6
        self.assertAlmostEqual(row["cr_eff"], 10.0, places=9)      # 60 / (6 + 0)

    def test_extra_basal_is_integrated_over_the_window(self):
        """+0.6 U/h for 240 min = 0.6 * 4 h = 2.4 U extra insulin."""
        rate = [0.8] * (24 * 60)
        meal_idx = 8 * 60
        for i in range(meal_idx, meal_idx + 240):
            rate[i] = 1.4                                          # 0.8 + 0.6
        row = self._one_meal(rate, fasting=0.8, cho=60.0, bolus=6.0)
        self.assertAlmostEqual(row["exc"], 2.4, places=6)
        # CR_eff = 60 / (6 + 2.4) = 7.142857...
        self.assertAlmostEqual(row["cr_eff"], 60.0 / 8.4, places=6)
        self.assertLess(row["cr_eff"], row["cr"],
                        "extra basal must lower CR_eff below the nominal CR")

    def test_partial_window_extra_basal(self):
        """+1.2 U/h for only 60 of 240 min = 1.2 U, not 4.8 U."""
        rate = [0.8] * (24 * 60)
        meal_idx = 8 * 60
        for i in range(meal_idx, meal_idx + 60):
            rate[i] = 2.0                                          # 0.8 + 1.2
        row = self._one_meal(rate, fasting=0.8, cho=60.0, bolus=6.0)
        self.assertAlmostEqual(row["exc"], 1.2, places=6)

    def test_suspended_basal_gives_negative_excess(self):
        """Loop cutting basal below fasting is negative extra insulin."""
        rate = [0.8] * (24 * 60)
        meal_idx = 8 * 60
        for i in range(meal_idx, meal_idx + 240):
            rate[i] = 0.2                                          # 0.6 below fasting
        row = self._one_meal(rate, fasting=0.8, cho=60.0, bolus=6.0)
        self.assertAlmostEqual(row["exc"], -2.4, places=6)
        # CR_eff = 60 / (6 - 2.4) = 16.66...
        self.assertAlmostEqual(row["cr_eff"], 60.0 / 3.6, places=6)
        self.assertGreater(row["cr_eff"], row["cr"])

    def test_cr_eff_is_nan_when_total_insulin_not_positive(self):
        """A suspend larger than the bolus must not produce a negative ratio."""
        rate = [0.8] * (24 * 60)
        meal_idx = 8 * 60
        for i in range(meal_idx, meal_idx + 240):
            rate[i] = 0.0                                          # -0.8 U/h -> -3.2 U
        row = self._one_meal(rate, fasting=0.8, cho=60.0, bolus=3.0)
        self.assertAlmostEqual(row["exc"], -3.2, places=6)
        self.assertTrue(np.isnan(row["cr_eff"]))

    def test_delta_four_hours(self):
        """d4 is post-window glucose minus pre-meal glucose."""
        rate = [0.8] * (24 * 60)
        row = self._one_meal(rate, fasting=0.8, cho=60.0, bolus=6.0,
                             pre=110.0, post=175.0)
        self.assertAlmostEqual(row["d4"], 65.0, places=6)

    def test_meal_outside_basal_timeline_is_skipped(self):
        """A meal whose window runs past the timeline yields no row."""
        rate = [0.8] * (9 * 60)               # timeline ends 09:00
        meals = [{"time": self.t0 + timedelta(hours=8), "cho": 60.0,
                  "bolus": 6.0, "bg": 120.0}]
        rows = core.analyze_meals(meals, [], _basal(rate, 0.8, self.t0),
                                  self.window, _const_lookup(120.0, 120.0))
        self.assertEqual(rows, [])


class TestContamination(unittest.TestCase):
    """A second meal inside the window makes the row unusable for the median."""

    def setUp(self):
        self.t0 = datetime(2026, 5, 1, 0, 0)
        self.rate = [0.8] * (24 * 60)

    def _rows(self, meal_hours):
        meals = [{"time": self.t0 + timedelta(hours=h), "cho": 60.0,
                  "bolus": 6.0, "bg": 120.0} for h in meal_hours]
        return core.analyze_meals(meals, [], _basal(self.rate, 0.8, self.t0),
                                  240, _const_lookup(120.0, 120.0))

    def test_meal_within_window_contaminates(self):
        rows = self._rows([8, 10])            # 2 h apart, window is 4 h
        self.assertTrue(rows[0]["contam"], "second meal inside the window")

    def test_meal_beyond_window_does_not_contaminate(self):
        rows = self._rows([8, 13])            # 5 h apart
        self.assertFalse(rows[0]["contam"])

    def test_earlier_meal_does_not_contaminate_later_one(self):
        """Only meals *after* the start fall into its window."""
        rows = self._rows([8, 13])
        self.assertFalse(rows[1]["contam"], "the 08:00 meal is in the past")


class TestConsensusMetrics(unittest.TestCase):
    """Battelino consensus metrics on a hand-built glucose series (mg/dL)."""

    def setUp(self):
        core.setup_i18n("en")
        # 100 samples, 5 min apart: 60 in range, 20 high, 10 very high, 10 low
        self.times = [datetime(2026, 5, 1, 0, 0) + timedelta(minutes=5 * i)
                      for i in range(100)]
        self.gluc = np.array([120.0] * 60 + [200.0] * 20 + [300.0] * 10 + [60.0] * 10)

    def test_time_in_range_percentages(self):
        m = core.consensus_metrics(self.times, self.gluc)
        self.assertAlmostEqual(m["tir"], 60.0, places=6)    # 70..180
        self.assertAlmostEqual(m["tar1"], 20.0, places=6)   # 180..250
        self.assertAlmostEqual(m["tar2"], 10.0, places=6)   # >250
        self.assertAlmostEqual(m["tbr1"], 10.0, places=6)   # 54..70
        self.assertAlmostEqual(m["tbr2"], 0.0, places=6)    # <54

    def test_percentages_sum_to_hundred(self):
        m = core.consensus_metrics(self.times, self.gluc)
        total = m["tir"] + m["tar1"] + m["tar2"] + m["tbr1"] + m["tbr2"]
        self.assertAlmostEqual(total, 100.0, places=6)

    def test_mean_cv_and_gmi(self):
        m = core.consensus_metrics(self.times, self.gluc)
        mean = float(self.gluc.mean())
        self.assertAlmostEqual(m["mean"], mean, places=6)
        self.assertAlmostEqual(m["cv"], float(self.gluc.std()) / mean * 100, places=6)
        # GMI (Bergenstal): 3.31 + 0.02392 * mean(mg/dL)
        self.assertAlmostEqual(m["gmi"], 3.31 + 0.02392 * mean, places=9)

    def test_very_low_counts_separately(self):
        gluc = np.array([50.0] * 50 + [120.0] * 50)
        m = core.consensus_metrics(self.times, gluc)
        self.assertAlmostEqual(m["tbr2"], 50.0, places=6)   # <54
        self.assertAlmostEqual(m["tbr1"], 0.0, places=6)


class TestSlotVerdicts(unittest.TestCase):
    """Verdict thresholds: |extra basal / bolus| and the 4 h glucose delta."""

    def setUp(self):
        core.setup_i18n("en")

    @staticmethod
    def _rows(exc, bolus, d4, n=4, **extra):
        base = {"exc": exc, "bolus": bolus, "d4": d4, "cho": 60.0,
                "cr": 10.0, "cr_eff": 10.0, "contam": False, "cgm_gap": False,
                "hypo_rescue": False, "pre": 120.0, "bg": 120.0}
        base.update(extra)
        return [dict(base) for _ in range(n)]

    def test_much_extra_basal_reads_as_too_weak(self):
        """ratio = 2.0/6.0 = 0.33 > LOOP_RATIO -> the loop had to add insulin."""
        out = core.aggregate_slot(self._rows(exc=2.0, bolus=6.0, d4=10.0))
        self.assertEqual(out["cls"], "weak")

    def test_strong_suspend_reads_as_too_strong(self):
        """ratio = -2.0/6.0 -> the loop had to hold insulin back."""
        out = core.aggregate_slot(self._rows(exc=-2.0, bolus=6.0, d4=-10.0))
        self.assertEqual(out["cls"], "strong")

    def test_balanced_slot_reads_as_adequate(self):
        """ratio = 0.1/6.0 = 0.017 < LOOP_RATIO and a small delta."""
        out = core.aggregate_slot(self._rows(exc=0.1, bolus=6.0, d4=5.0))
        self.assertEqual(out["cls"], "ok")

    def test_high_delta_alone_reads_as_too_weak(self):
        """Even without a loop signal, a large Δ4h means the CR was too weak."""
        out = core.aggregate_slot(self._rows(exc=0.0, bolus=6.0,
                                             d4=core.D4_HIGH + 10))
        self.assertEqual(out["cls"], "weak")

    def test_ratio_just_below_threshold_stays_ok(self):
        """Boundary: ratio slightly under LOOP_RATIO must not flip the verdict."""
        exc = 6.0 * (core.LOOP_RATIO - 0.01)
        out = core.aggregate_slot(self._rows(exc=exc, bolus=6.0, d4=0.0))
        self.assertEqual(out["cls"], "ok")

    def test_ratio_just_above_threshold_flips_to_weak(self):
        exc = 6.0 * (core.LOOP_RATIO + 0.01)
        out = core.aggregate_slot(self._rows(exc=exc, bolus=6.0, d4=0.0))
        self.assertEqual(out["cls"], "weak")

    def test_verdict_uses_median_not_mean(self):
        """One extreme meal must not drag the whole slot's verdict."""
        rows = self._rows(exc=0.0, bolus=6.0, d4=0.0, n=4)
        rows.append(dict(rows[0], exc=50.0))          # single outlier
        out = core.aggregate_slot(rows)
        self.assertEqual(out["cls"], "ok", "median should absorb the outlier")

    def test_empty_slot_returns_none(self):
        self.assertIsNone(core.aggregate_slot([]))

    def test_few_clean_meals_marks_low_confidence(self):
        """Below MIN_CLEAN_MEALS clean rows the verdict is flagged as uncertain.

        The caveat lives in the ``low_confidence`` field (the report renders it
        as a badge), not as text appended to the verdict itself.
        """
        rows = self._rows(exc=0.0, bolus=6.0, d4=0.0, n=2, contam=True)
        out = core.aggregate_slot(rows)
        self.assertTrue(out["low_confidence"])


class TestSlotOf(unittest.TestCase):
    """Hour -> slot key mapping (built-in slots)."""

    def test_builtin_slot_boundaries(self):
        self.assertEqual(core.slot_of(7), "breakfast")     # 5..10
        self.assertEqual(core.slot_of(12), "lunch")        # 11..15
        self.assertEqual(core.slot_of(19), "dinner")       # 17..22
        self.assertEqual(core.slot_of(3), "other")         # catch-all


if __name__ == "__main__":
    unittest.main()


class TestDecisionStability(unittest.TestCase):
    """Bootstrap of the existing verdict — must never change the verdict itself."""

    @staticmethod
    def _rows(n_days, per_day=1, exc=1.0, bolus=6.0, d4=10.0, jitter=0.0):
        rows, day0 = [], datetime(2026, 5, 1, 8, 0)
        for d in range(n_days):
            for k in range(per_day):
                rows.append({
                    "time": day0 + timedelta(days=d, minutes=k),
                    "exc": exc + (jitter if d % 2 else -jitter), "bolus": bolus,
                    "d4": d4, "cho": 60.0, "cr": 10.0, "cr_eff": 8.0,
                    "contam": False, "cgm_gap": False, "hypo_rescue": False,
                    "pre": 120.0, "bg": 120.0})
        return rows

    def test_too_few_meals_returns_none(self):
        """Below the meal gate no figure is shown at all — see the n=3 problem."""
        self.assertIsNone(core.decision_stability(self._rows(4)))

    def test_too_few_days_returns_none(self):
        """Many meals but few days is not enough evidence either."""
        rows = self._rows(n_days=3, per_day=4)          # 12 meals, 3 days
        self.assertGreaterEqual(len(rows), core.MIN_MEALS_FOR_STABILITY)
        self.assertIsNone(core.decision_stability(rows))

    def test_gate_is_driven_by_days_not_meals(self):
        """5 days is the point where the spread's coverage becomes honest."""
        self.assertEqual(core.MIN_DAYS_FOR_STABILITY, 5)
        # Enough meals but only 4 days -> no bootstrap.
        self.assertIsNone(core.decision_stability(self._rows(n_days=4, per_day=3)))
        # Five days with one meal each is enough.
        self.assertIsNotNone(core.decision_stability(self._rows(n_days=5)))

    def test_clear_case_is_stable(self):
        """Every meal far above the threshold -> the verdict cannot flip."""
        out = core.decision_stability(self._rows(12, exc=3.0))
        self.assertEqual(out["cls"], "weak")
        self.assertEqual(out["pct"], 100.0)
        self.assertEqual(out["band"], "high")

    def test_borderline_case_is_unstable(self):
        """Meals straddling the threshold must not be reported as stable."""
        rows = self._rows(12, exc=6.0 * core.LOOP_RATIO, jitter=0.45, d4=0.0)
        out = core.decision_stability(rows)
        self.assertLess(out["pct"], 100.0)
        self.assertGreater(sum(1 for v in out["dist"].values() if v > 0), 1)

    def test_reported_class_matches_full_sample_verdict(self):
        """The bootstrap must describe the verdict the report actually shows."""
        rows = self._rows(12, exc=3.0)
        agg = core.aggregate_slot(rows)
        self.assertEqual(core.decision_stability(rows)["cls"], agg["cls"])

    def test_is_deterministic(self):
        """A report must not change between runs — fixed seed."""
        rows = self._rows(12, exc=6.0 * core.LOOP_RATIO, jitter=0.4, d4=0.0)
        first = core.decision_stability(rows)
        second = core.decision_stability(rows)
        self.assertEqual(first, second)

    def test_distribution_sums_to_hundred(self):
        out = core.decision_stability(self._rows(12, exc=1.0))
        self.assertAlmostEqual(sum(out["dist"].values()), 100.0, places=6)

    def test_resamples_days_not_single_meals(self):
        """Meals of one day travel together, so one odd day cannot be split up."""
        rows = self._rows(10, per_day=3, exc=0.0, d4=0.0)
        for r in rows[:3]:                               # one extreme day
            r["exc"] = 40.0
        out = core.decision_stability(rows)
        # With day blocks the outlier day is drawn as a unit: it either shifts
        # the median or it does not — it can never be spread across resamples.
        self.assertEqual(out["days"], 10)
        self.assertIn(out["cls"], ("ok", "weak"))

    def test_verdict_rule_is_shared_with_aggregate_slot(self):
        """Same inputs, same class — no second implementation of the rule."""
        for exc, d4 in ((2.0, 0.0), (-2.0, 0.0), (0.0, 0.0), (0.0, core.D4_HIGH + 5)):
            with self.subTest(exc=exc, d4=d4):
                rows = self._rows(12, exc=exc, d4=d4)
                self.assertEqual(core.verdict_class(exc, 6.0, d4),
                                 core.aggregate_slot(rows)["cls"])


class TestSpread(unittest.TestCase):
    """Day-clustered spread of CR_eff and the loop share."""

    @staticmethod
    def _rows(n_days, cre=8.0, exc=1.0, bolus=6.0, jitter=0.0):
        rows, day0 = [], datetime(2026, 5, 1, 8, 0)
        for d in range(n_days):
            sign = 1 if d % 2 else -1
            rows.append({"time": day0 + timedelta(days=d),
                         "exc": exc + sign * jitter, "bolus": bolus, "d4": 10.0,
                         "cho": 60.0, "cr": 10.0, "cr_eff": cre + sign * jitter,
                         "contam": False, "cgm_gap": False, "hypo_rescue": False,
                         "pre": 120.0, "bg": 120.0})
        return rows

    def test_spread_brackets_the_reported_value(self):
        """The median must lie inside its own spread."""
        out = core.decision_stability(self._rows(12, cre=8.0, jitter=1.5))
        lo, hi = out["spread"]["cre"]
        self.assertLessEqual(lo, 8.0)
        self.assertGreaterEqual(hi, 8.0)

    def test_noisier_days_give_a_wider_spread(self):
        narrow = core.decision_stability(self._rows(12, jitter=0.2))["spread"]["cre"]
        wide = core.decision_stability(self._rows(12, jitter=3.0))["spread"]["cre"]
        self.assertGreater(wide[1] - wide[0], narrow[1] - narrow[0])

    def test_identical_days_give_a_point_spread(self):
        """With no variation between days there is nothing to resample away."""
        lo, hi = core.decision_stability(self._rows(12, jitter=0.0))["spread"]["cre"]
        self.assertAlmostEqual(lo, hi, places=6)

    def test_loop_share_spread_is_a_ratio(self):
        """The loop share is extra basal / bolus, not the absolute units."""
        out = core.decision_stability(self._rows(12, exc=1.2, bolus=6.0, jitter=0.3))
        lo, hi = out["spread"]["ratio"]
        self.assertLessEqual(lo, 1.2 / 6.0)
        self.assertGreaterEqual(hi, 1.2 / 6.0)

    def test_no_spread_below_the_gates(self):
        self.assertIsNone(core.decision_stability(self._rows(4)))

    def test_display_strings_only_for_the_two_chosen_quantities(self):
        out = core._fmt_spread(core.decision_stability(self._rows(12, jitter=1.0)))
        self.assertEqual(set(out), {"cre", "ratio"})


class TestObservedRange(unittest.TestCase):
    """Fallback for slots below the bootstrap gates."""

    @staticmethod
    def _rows(values):
        day0 = datetime(2026, 5, 1, 12, 0)
        return [{"time": day0 + timedelta(days=i), "cr_eff": v, "exc": 1.0,
                 "bolus": 6.0, "d4": 10.0, "cho": 60.0, "cr": 10.0,
                 "contam": False, "cgm_gap": False, "hypo_rescue": False,
                 "pre": 120.0, "bg": 120.0} for i, v in enumerate(values)]

    def test_range_is_min_and_max(self):
        lo, hi, n = core.observed_range(self._rows([8.0, 6.5, 9.25, 7.0]))
        self.assertEqual((lo, hi, n), (6.5, 9.25, 4))

    def test_needs_at_least_two_values(self):
        self.assertIsNone(core.observed_range(self._rows([7.0])))

    def test_ignores_nan_values(self):
        lo, hi, n = core.observed_range(self._rows([7.0, float("nan"), 9.0]))
        self.assertEqual((lo, hi, n), (7.0, 9.0, 2))

    def test_display_string_for_gated_slot(self):
        out = core._fmt_range(self._rows([6.5, 8.7, 7.1, 7.9]))
        self.assertEqual(out["meals"], 4)
        self.assertIn("–", out["cre"])


class TestSelectionEffect(unittest.TestCase):
    """The number that tells the reader whether the neutral chart also holds
    for the verdict."""

    def test_reports_used_and_total_per_slot(self):
        from pathlib import Path
        import collections
        base = Path(__file__).resolve().parents[1] / "example-data"
        times, gluc, _n, _s = core.read_cgm(base)
        meals, minors, _p = core.read_meals(base)
        basal = core.read_basal_timeline(base)
        val_at = core.make_glucose_lookup(times, gluc)
        rows = core.analyze_meals(meals, minors, basal, 240, val_at, times)
        by_slot = collections.defaultdict(list)
        for row in rows:
            by_slot[row["slot"]].append(row)
        out = core.selection_effect(meals, by_slot, 240, val_at)
        self.assertTrue(out)
        for entry in out:
            with self.subTest(slot=entry["label"]):
                self.assertLessEqual(entry["used"], entry["total"])
                self.assertTrue(entry["shift"])

    def test_no_selection_means_no_shift(self):
        """If every meal is clean, the curves coincide and the shift is zero."""
        from pathlib import Path
        import collections
        base = Path(__file__).resolve().parents[1] / "example-data"
        times, gluc, _n, _s = core.read_cgm(base)
        meals, minors, _p = core.read_meals(base)
        basal = core.read_basal_timeline(base)
        val_at = core.make_glucose_lookup(times, gluc)
        rows = core.analyze_meals(meals, minors, basal, 240, val_at, times)
        by_slot = collections.defaultdict(list)
        for row in rows:
            row["contam"] = False
            row["cgm_gap"] = False
            by_slot[row["slot"]].append(row)
        for entry in core.selection_effect(meals, by_slot, 240, val_at):
            with self.subTest(slot=entry["label"]):
                self.assertEqual(entry["used"], entry["total"])
                self.assertIn(entry["shift"], ("0", "0.0", "—"))
