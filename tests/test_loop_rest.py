from datetime import datetime, timedelta


import loop_cr_review as core


def _basal(hours, rate_u_h, fasting):
    t0 = datetime(2026, 5, 1, 0, 0)
    n = hours * 60
    rate = [float(rate_u_h)] * n
    return (rate, t0, n, fasting, fasting, fasting)


def _meal(day_hour):
    t0 = datetime(2026, 5, 1, 0, 0)
    return {"time": t0 + timedelta(hours=day_hour), "cho": 50.0, "bolus": 5.0}


def test_quiet_when_daytime_matches_fasting():
    # 3 days, meals at 8/13/19 so 10–12 and 15–17 stay free
    meals = []
    for d in range(3):
        for h in (8, 13, 19):
            meals.append({"time": datetime(2026, 5, 1+d, h, 0), "cho": 50, "bolus": 5})
    r = core.loop_rest(_basal(72, 0.80, 0.80), meals)
    assert r["state"] == "quiet"
    assert r["windows"] >= 3


def test_active_when_daytime_high():
    meals = []
    for d in range(3):
        for h in (8, 13, 19):
            meals.append({"time": datetime(2026, 5, 1+d, h, 0), "cho": 50, "bolus": 5})
    r = core.loop_rest(_basal(72, 1.20, 0.80), meals)
    assert r["state"] == "active"


def test_unclear_too_short():
    r = core.loop_rest(_basal(6, 0.80, 0.80), [])
    assert r["state"] == "unclear"
