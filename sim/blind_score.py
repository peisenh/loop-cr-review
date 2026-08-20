"""Score a blind analyzer result without running the physiology."""

MAIN = ("breakfast", "lunch", "dinner")


def truth(err: float) -> str:
    if err > 1e-9:
        return "weak"
    if err < -1e-9:
        return "strong"
    return "ok"


def is_main(key: str) -> bool:
    k = (key or "").lower()
    return any(m in k for m in MAIN)


def class_of(slot: dict) -> str:
    cls = slot.get("cls")
    if cls in ("weak", "strong", "ok"):
        return cls
    flag = (slot.get("flag") or "").lower()
    if "too weak" in flag or "zu schwach" in flag:
        return "weak"
    if "too strong" in flag or "zu stark" in flag:
        return "strong"
    if "plausibly" in flag or "plausibel" in flag or flag == "ok":
        return "ok"
    return flag


def wanted_slots(slots, names=None):
    names = tuple(names) if names else MAIN
    out = []
    for s in slots:
        k = (s.get("key") or "").lower()
        if any(n in k for n in names):
            out.append(s)
    return out or list(slots)


def score(err: float, slots: list, names=None) -> str:
    want = truth(err)
    flags = [class_of(s) for s in wanted_slots(slots, names)]
    if want == "ok":
        return "ok" if flags and all(f == "ok" for f in flags) else "fp"
    if any(f == want for f in flags):
        return "hit"
    if any(f != "ok" for f in flags):
        return "wrong"
    return "miss"
