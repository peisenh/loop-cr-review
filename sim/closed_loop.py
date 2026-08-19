"""Open physiology + CGM-only PID. Meal/bolus still applied by this module."""

from __future__ import annotations

from dataclasses import dataclass

from simglucose.patient.t1dpatient import Action, T1DPatient

from sim.controller import CGMOnlyPID, Gains, MID
from sim.physiology import MEAL_EAT_RATE_G_PER_MIN, basal_u_per_hour, basal_u_per_min


@dataclass(frozen=True)
class ClosedTrace:
    t_min: list[int]
    glucose: list[float]
    basal_u_per_hour: list[float]
    profile_u_per_hour: float
    extra_u: float  # ∫ (basal − profile) dt over the whole run, U


def run_closed_loop(
    patient_name: str = "adult#001",
    minutes: int = 360,
    meal_at: int | None = None,
    meal_g: float = 0.0,
    bolus_at: int | None = None,
    bolus_u: float = 0.0,
    gains: Gains = MID,
    target: float | None = None,
) -> ClosedTrace:
    patient = T1DPatient.withName(patient_name)
    profile_u_min = basal_u_per_min(patient)
    profile_u_h = basal_u_per_hour(patient)
    # Target = initial steady glucose so extra basal starts at 0.
    if target is None:
        target = float(patient.observation.Gsub)
    pid = CGMOnlyPID(profile_u_h, target, gains)
    remaining_cho = 0.0
    t_min, glucose, basal_h = [], [], []
    extra = 0.0

    for minute in range(minutes):
        cgm = float(patient.observation.Gsub)
        basal_uh = pid.policy(cgm, sample_min=1.0)
        cho = 0.0
        if meal_at is not None and minute == meal_at:
            remaining_cho = float(meal_g)
        if remaining_cho > 0:
            cho = min(MEAL_EAT_RATE_G_PER_MIN, remaining_cho)
            remaining_cho -= cho
        ins = basal_uh / 60.0
        if bolus_at is not None and minute == bolus_at:
            ins += float(bolus_u)
        patient.step(Action(CHO=cho, insulin=ins))
        extra += (basal_uh - profile_u_h) / 60.0
        t_min.append(minute)
        glucose.append(float(patient.observation.Gsub))
        basal_h.append(basal_uh)

    return ClosedTrace(t_min, glucose, basal_h, profile_u_h, extra)
