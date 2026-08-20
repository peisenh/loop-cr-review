from sim.blind_score import deficit_u, run_seed


def test_seed_stable():
    a = run_seed(1, "adult#002", 0.2, 5, "mid", 3)
    b = run_seed(1, "adult#002", 0.2, 5, "mid", 3)
    assert a == b
    assert run_seed(1, "adult#002", 0.2, 5, "mid", 4) != a


def test_deficit():
    d = deficit_u(10.0, 0.2, "lunch")
    assert abs(d - 1.0) < 1e-9
    assert deficit_u(10.0, 0.0, "lunch") == 0.0
