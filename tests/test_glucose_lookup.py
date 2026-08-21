from datetime import datetime, timedelta

import numpy as np

import loop_cr_review as core


def test_val_at_matches_mask_mean():
    t0 = datetime(2026, 5, 1, 8, 0)
    times = np.array([t0 + timedelta(minutes=i) for i in range(200)])
    gluc = np.arange(200, dtype=float)
    val = core.make_glucose_lookup(times, gluc)
    ref = t0 + timedelta(minutes=50)
    got = val(ref, 0, tol=12)
    lo, hi = ref + timedelta(minutes=-12), ref + timedelta(minutes=12)
    mask = (times >= lo) & (times <= hi)
    assert got == float(gluc[mask].mean())
    assert np.isnan(val(t0 + timedelta(days=2), 0))


def test_cgm_gap_same_as_scan():
    t0 = datetime(2026, 5, 1, 8, 0)
    times = np.array([t0 + timedelta(minutes=i) for i in range(0, 240, 1)])
    assert core.cgm_gap_in_window(t0, 240, times) is False
    # 30 min hole
    times2 = np.concatenate([times[:60], times[100:]])
    assert core.cgm_gap_in_window(t0, 240, times2) is True
    assert core.cgm_gap_in_window(t0, 240, np.array([])) is True
