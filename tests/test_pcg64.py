# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The reproduced generator, checked against the one it reproduces.

`lcr/pcg64.py` exists so the stability bootstrap keeps drawing the same days it
drew before, and so the report stays comparable character for character. That
claim is only worth anything if it is checked: a generator that is almost right
produces plausible numbers and a quietly different report.

Three things have to match, and each was wrong once while this was written:

* the seeding, where the two 64-bit halves go in high-first,
* the generator itself, which numpy advances before reading rather than after,
* the bounded integers, where numpy takes a 32-bit path below 2**32 and draws
  two values per step — a 64-bit implementation produces every second number,
  which looks nearly right until compared.

numpy is a development dependency, so these skip where it is absent.
"""
from __future__ import annotations

import unittest

try:
    import numpy as np
except ImportError:                                  # pragma: no cover
    np = None

from lcr import pcg64

# The project's own seed, plus values around the edges of the word sizes.
SEEDS = (20260817, 0, 1, 42, 999983, 2 ** 32 - 1, 2 ** 32, 2 ** 40 + 7)
# Day counts a bootstrap actually asks for, and the powers of two either side.
RANGES = (2, 5, 14, 90, 91, 256, 1000, 65536, 100000)


@unittest.skipIf(np is None, "numpy not installed (requirements-dev.txt)")
class TestMatchesNumpy(unittest.TestCase):  # pylint: disable=protected-access
    """Same seed, same numbers."""

    def test_bounded_integers(self):
        for seed in SEEDS:
            for high in RANGES:
                with self.subTest(seed=seed, high=high):
                    mine = pcg64.default_rng(seed).integers(0, high, 150)
                    theirs = np.random.default_rng(seed).integers(0, high, size=150).tolist()
                    self.assertEqual(mine, theirs)

    def test_seeding(self):
        """The initial state, before a single number is drawn."""
        for seed in SEEDS:
            with self.subTest(seed=seed):
                mine = pcg64.Generator(seed)
                theirs = np.random.default_rng(seed).bit_generator.state["state"]
                self.assertEqual(mine._state, int(theirs["state"]))
                self.assertEqual(mine._inc, int(theirs["inc"]))    

    def test_raw_output(self):
        """The generator itself, before any bounding is applied."""
        for seed in SEEDS[:4]:
            with self.subTest(seed=seed):
                mine = pcg64.Generator(seed)
                reference = np.random.default_rng(seed)
                drawn = [mine._raw() for _ in range(8)]            
                self.assertEqual(drawn,
                                 [int(v) for v in reference.bit_generator.random_raw(8)])

    def test_a_long_run_does_not_drift(self):
        """Rejection makes the streams diverge later if it is wrong."""
        mine = pcg64.default_rng(20260817).integers(0, 90, 20000)
        theirs = np.random.default_rng(20260817).integers(0, 90, size=20000).tolist()
        self.assertEqual(mine, theirs)


class TestWithoutNumpy(unittest.TestCase):
    """What can be said without the original to compare against."""

    def test_the_same_seed_gives_the_same_numbers(self):
        first = pcg64.default_rng(20260817).integers(0, 90, 100)
        second = pcg64.default_rng(20260817).integers(0, 90, 100)
        self.assertEqual(first, second)

    def test_different_seeds_give_different_numbers(self):
        self.assertNotEqual(pcg64.default_rng(1).integers(0, 90, 100),
                            pcg64.default_rng(2).integers(0, 90, 100))

    def test_values_stay_inside_the_range(self):
        for value in pcg64.default_rng(7).integers(0, 14, 5000):
            self.assertGreaterEqual(value, 0)
            self.assertLess(value, 14)

    def test_a_range_it_cannot_reproduce_is_refused(self):
        """Better to say so than to return numbers numpy would not have."""
        with self.assertRaises(NotImplementedError):
            pcg64.default_rng(1).integers(0, 2 ** 32 + 2, 1)

    def test_an_empty_range_is_an_error(self):
        with self.assertRaises(ValueError):
            pcg64.default_rng(1).integers(5, 5, 1)


if __name__ == "__main__":
    unittest.main()
