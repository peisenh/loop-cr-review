"""Open-loop UVa/Padova S2008 patient (simglucose), no controller.

The meal and the bolus are applied by this module. The patient model never
sees a carb ratio. Basal is the published pump setting u2ss×BW/6000, read
once at setup.
"""

from __future__ import annotations

from dataclasses import dataclass

from simglucose.patient.t1dpatient import Action, T1DPatient

# Dexcom-like export grid comes later; the ODE runs at 1 min (patient native).
DT_MIN = 1
MEAL_EAT_RATE_G_PER_MIN = 5.0  # simglucose T1DPatient.EAT_RATE


def basal_u_per_min(patient: T1DPatient) -> float:
    """Pump basal from patient parameters, once at setup (spec §4)."""
    return float(patient._params.u2ss * patient._params.BW / 6000.0)


def basal_u_per_hour(patient: T1DPatient) -> float:
    return basal_u_per_min(patient) * 60.0


@dataclass(frozen=True)
class Trace:
    t_min: list[int]
    glucose: list[float]
    cho_g_per_min: list[float]
    insulin_u_per_min: list[float]


def run_open_loop(
    patient_name: str = "adult#001",
    minutes: int = 360,
    meal_at: int | None = None,
    meal_g: float = 0.0,
    bolus_at: int | None = None,
    bolus_u: float = 0.0,
) -> Trace:
    """One patient, fixed basal, optional one meal and one bolus.

    Meal is eaten at ``MEAL_EAT_RATE_G_PER_MIN`` starting at ``meal_at``.
    Bolus is a one-minute square at ``bolus_at`` (U/min = bolus_u).
    """
    patient = T1DPatient.withName(patient_name)
    basal = basal_u_per_min(patient)
    remaining_cho = 0.0
    t_min, glucose, cho_rate, insulin = [], [], [], []

    for minute in range(minutes):
        cho = 0.0
        if meal_at is not None and minute == meal_at:
            remaining_cho = float(meal_g)
        if remaining_cho > 0:
            cho = min(MEAL_EAT_RATE_G_PER_MIN, remaining_cho)
            remaining_cho -= cho
        ins = basal
        if bolus_at is not None and minute == bolus_at:
            ins += float(bolus_u)
        patient.step(Action(CHO=cho, insulin=ins))
        t_min.append(minute)
        glucose.append(float(patient.observation.Gsub))
        cho_rate.append(cho)
        insulin.append(ins)
    return Trace(t_min, glucose, cho_rate, insulin)


def at(trace: Trace, minute: int) -> float:
    return trace.glucose[min(max(minute, 0), len(trace.glucose) - 1)]
