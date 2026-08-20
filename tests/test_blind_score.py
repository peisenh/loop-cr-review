from sim.blind_score import class_of, score, truth


def test_truth():
    assert truth(0.0) == "ok"
    assert truth(0.2) == "weak"
    assert truth(-0.2) == "strong"


def _slots(b="ok", l="ok", d="ok"):
    return [{"key": "breakfast", "cls": b}, {"key": "lunch", "cls": l},
            {"key": "dinner", "cls": d}]


def test_zero_all_ok():
    assert score(0.0, _slots()) == "ok"


def test_zero_fp_breakfast():
    assert score(0.0, _slots("weak")) == "fp"
    assert score(0.0, _slots("weak"), names=("lunch", "dinner")) == "ok"


def test_translated_flag():
    assert class_of({"flag": "too weak → tighten"}) == "weak"


def test_hit_and_miss():
    assert score(0.2, _slots("weak")) == "hit"
    assert score(-0.2, _slots("weak")) == "wrong"
    assert score(0.2, _slots()) == "miss"
