# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""numpy's default random generator, reproduced exactly.

The stability figure resamples the days two thousand times, and the report
prints the result. Any other stream of random numbers gives a statistically
equivalent answer and a different printed one — which would mean giving up the
one check that makes removing numpy safe at all: that the report comes out
identical, character for character.

So the generator is reproduced rather than replaced. All three parts of it are
pinned down here and checked against numpy in the tests:

* **SeedSequence** turns the fixed integer seed into four 32-bit words.
* **PCG64** (the XSL-RR variant, which is numpy's default) is a 128-bit state
  stepped by a multiply-add, with the output folded down to 64 bits.
* **Bounded integers** use Lemire's method with rejection. numpy takes the
  32-bit path for any range below 2**32 and draws two values per 64-bit step,
  which is why a 64-bit implementation produces every second number and looks
  almost right.

Python's own `random` is a Mersenne Twister and matches none of this. Nothing
here is a source of randomness worth using elsewhere — it exists to keep one
number in the report from moving.
"""
from __future__ import annotations

__all__ = ["Generator", "default_rng"]

_M32 = (1 << 32) - 1
_M64 = (1 << 64) - 1
_M128 = (1 << 128) - 1

# PCG64 XSL-RR
_PCG_MULT = 47026247687942121848144207491837523525

# SeedSequence mixing constants
_INIT_A, _MULT_A = 0x43B0D7E5, 0x931E8875
_INIT_B, _MULT_B = 0x8B51F9DD, 0x58F38DED
_MIX_L, _MIX_R = 0xCA01F9DD, 0x4973F715
_XSHIFT = 16
_POOL_SIZE = 4


def _entropy_words(seed):
    """The seed as 32-bit words, least significant first. -> list of int"""
    out = []
    while seed > 0:
        out.append(seed & _M32)
        seed >>= 32
    return out or [0]


def _mix_pool(words):
    """SeedSequence's entropy pool. -> list of _POOL_SIZE ints"""
    const = [_INIT_A]

    def hashed(value):
        value = (value ^ const[0]) & _M32
        const[0] = (const[0] * _MULT_A) & _M32
        value = (value * const[0]) & _M32
        return (value ^ (value >> _XSHIFT)) & _M32

    def mixed(left, right):
        result = (_MIX_L * left - _MIX_R * right) & _M32
        return (result ^ (result >> _XSHIFT)) & _M32

    pool = [hashed(words[i]) if i < len(words) else hashed(0)
            for i in range(_POOL_SIZE)]
    for source in range(_POOL_SIZE):
        for target in range(_POOL_SIZE):
            if source != target:
                pool[target] = mixed(pool[target], hashed(pool[source]))
    for source in range(_POOL_SIZE, len(words)):
        for target in range(_POOL_SIZE):
            pool[target] = mixed(pool[target], hashed(words[source]))
    return pool


def _generate_state(pool, count):
    """SeedSequence.generate_state, in 32-bit words. -> list of int"""
    const = [_INIT_B]
    out = []
    for i in range(count):
        value = pool[i % len(pool)]
        value = (value ^ const[0]) & _M32
        const[0] = (const[0] * _MULT_B) & _M32
        value = (value * const[0]) & _M32
        out.append((value ^ (value >> _XSHIFT)) & _M32)
    return out


def _seed_pcg64(seed):
    """Initial PCG64 state and increment for an integer seed. -> (int, int)"""
    words = _generate_state(_mix_pool(_entropy_words(seed)), 8)
    # Four 64-bit values, each a little-endian pair of the 32-bit words; then
    # the first two as the state and the last two as the sequence, high half
    # first.
    quads = [(words[2 * i + 1] << 32) | words[2 * i] for i in range(4)]
    initstate = (quads[0] << 64) | quads[1]
    initseq = (quads[2] << 64) | quads[3]

    inc = ((initseq << 1) | 1) & _M128
    state = inc                                  # from zero, one step
    state = (state + initstate) & _M128
    state = (state * _PCG_MULT + inc) & _M128
    return state, inc


class Generator:  # pylint: disable=too-few-public-methods
    """The subset of numpy's Generator this project uses."""

    def __init__(self, seed):
        self._state, self._inc = _seed_pcg64(seed)
        self._buffered = 0
        self._has_buffered = False

    def _raw(self):
        """One 64-bit output. -> int"""
        self._state = (self._state * _PCG_MULT + self._inc) & _M128
        state = self._state
        folded = ((state >> 64) ^ (state & _M64)) & _M64
        rotation = state >> 122
        return ((folded >> rotation) | (folded << ((-rotation) & 63))) & _M64

    def _next32(self):
        """One 32-bit output, low half of a step before the high half. -> int"""
        if self._has_buffered:
            self._has_buffered = False
            return self._buffered
        value = self._raw()
        self._buffered = value >> 32
        self._has_buffered = True
        return value & _M32

    def integers(self, low, high, size):
        """*size* integers in [low, high). -> list of int

        Only the 32-bit path is implemented, which is the one numpy takes for
        any range below 2**32 — and the ranges here are day counts.
        """
        span = high - low
        if span <= 0:
            raise ValueError("high must be greater than low")
        if span > (1 << 32):
            raise NotImplementedError("only ranges below 2**32 are reproduced")
        return [low + self._bounded32(span - 1) for _ in range(size)]

    def _bounded32(self, rng_max):
        """Lemire's bounded integer with rejection, as numpy does it. -> int"""
        span = rng_max + 1
        product = self._next32() * span
        leftover = product & _M32
        if leftover < span:
            threshold = ((1 << 32) - span) % span
            while leftover < threshold:
                product = self._next32() * span
                leftover = product & _M32
        return product >> 32


def default_rng(seed):
    """-> a Generator seeded like numpy's default_rng"""
    return Generator(seed)
