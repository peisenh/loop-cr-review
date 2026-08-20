from sim.blind_score import class_of, score, truth


def test_truth():
    assert truth(0.0) == "ok"
    assert truth(0.2) == "weak"
    assert truth(-0.2) == "strong"


def test_zero_all_ok():
    slots = [{"key": "breakfast", "cls": "ok"}, {"key": "lunch", "cls": "ok"},
             {"key": "dinner", "cls": "ok"}]
    assert score(0.0, slots) == "ok"


def test_zero_fp():
    slots = [{"key": "breakfast", "cls": "weak"}, {"key": "lunch", "cls": "ok"},
             {"key": "dinner", "cls": "ok"}]
    assert score(0.0, slots) == "fp"


def test_translated_flag():
    assert class_of({"flag": "too weak → tighten"}) == "weak"
    assert class_of({"flag": "plausibly adequate"}) == "ok"


def test_hit_and_miss():
    slots = [{"key": "breakfast", "cls": "weak"}, {"key": "lunch", "cls": "ok"},
             {"key": "dinner", "cls": "ok"}]
    assert score(0.2, slots) == "hit"
    assert score(-0.2, slots) == "wrong"
    assert score(0.2, [{"key": "breakfast", "cls": "ok"}, {"key": "lunch", "cls": "ok"},
                       {"key": "dinner", "cls": "ok"}]) == "miss"
