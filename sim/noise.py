"""Seeded CGM noise for the generator (no simglucose import)."""


def cgm_noise(glucose: float, rng, sigma: float) -> float:
    """Additive CGM noise (mg/dl). sigma=0 or rng=None leaves glucose as is."""
    if sigma <= 0 or rng is None:
        return glucose
    return max(40.0, glucose + rng.gauss(0.0, sigma))
