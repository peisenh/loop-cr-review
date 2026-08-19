"""CGM-only basal modulator (SIMULATION-SPEC §4, M1).

Sees glucose and the sample interval. Does not read meal, CHO, CR, bolus
or patient state. Basal profile is taken once at construction.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Gains:
    name: str
    kp: float  # U/h per mg/dl
    ki: float
    kd: float
    k_cap: float  # max basal = k_cap × profile


# Weak / mid / strong — numbers are starting points, not CamAPS.
WEAK = Gains("weak", kp=0.010, ki=0.0004, kd=0.05, k_cap=2.0)
MID = Gains("mid", kp=0.020, ki=0.0008, kd=0.10, k_cap=3.0)
STRONG = Gains("strong", kp=0.040, ki=0.0015, kd=0.20, k_cap=4.0)


class CGMOnlyPID:
    def __init__(self, profile_u_per_hour: float, target: float, gains: Gains = MID):
        self.profile = float(profile_u_per_hour)
        self.target = float(target)
        self.gains = gains
        self._i = 0.0
        self._prev = None

    def reset(self) -> None:
        self._i = 0.0
        self._prev = None

    def policy(self, cgm: float, sample_min: float = 1.0, **ignored) -> float:
        """Return basal U/h. Extra kwargs must not change the result (M1)."""
        err = float(cgm) - self.target
        dt_h = float(sample_min) / 60.0
        self._i += err * dt_h
        d = 0.0 if self._prev is None else (float(cgm) - self._prev) / max(dt_h, 1e-6)
        self._prev = float(cgm)
        delta = self.gains.kp * err + self.gains.ki * self._i + self.gains.kd * d
        basal = self.profile + delta
        lo, hi = 0.0, self.gains.k_cap * self.profile
        if basal > hi:
            self._i -= err * dt_h  # no extra windup against the cap
            basal = hi
        if basal < lo:
            self._i -= err * dt_h
            basal = lo
        return basal
