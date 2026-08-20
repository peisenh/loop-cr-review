import random

from sim.noise import cgm_noise


def test_zero_sigma_unchanged():
    assert cgm_noise(120.0, random.Random(1), 0.0) == 120.0


def test_seed_reproducible():
    a = [cgm_noise(100.0, random.Random(7), 5.0) for _ in range(8)]
    b = [cgm_noise(100.0, random.Random(7), 5.0) for _ in range(8)]
    assert a == b
    assert a != [100.0] * 8


def test_floor():
    class Down:
        def gauss(self, m, s):
            return -20.0
    assert cgm_noise(41.0, Down(), 5.0) == 40.0
