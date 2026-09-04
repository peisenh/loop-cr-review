# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The handful of array operations this project asks of numpy, without numpy.

numpy is the last compiled dependency. Nothing in the app would need a
compiler without it — Flask, Jinja2 and waitress are pure Python — and with it
go the wheel, the ABI, the page-size question and the platform limits that
followed from them.

What is actually used is elementary: medians, means, percentiles, a sorted
search, a difference, a sort order. No linear algebra, no transforms. The
sizes are small too: an AGP bin holds one value per day, a whole export a few
tens of thousands of readings, and a median over 26 000 floats is milliseconds
either way.

The one place where a reimplementation can be subtly wrong and still look right
is the percentile, so that is pinned down explicitly here and checked against
numpy on real distributions in the tests.

Missing values are NaN floats, as they were in the arrays: a gap in a sensor
trace has to stay distinguishable from a reading of zero.
"""
from __future__ import annotations

import math

__all__ = [
    "is_nan",
    "clean",
    "percentile",
    "column_percentile",
    "column_median",
    "median",
    "nanmedian",
    "mean",
    "nanmean",
    "stdev",
    "nanmax",
    "nanmin",
    "nanargmax",
    "nanargmin",
    "searchsorted",
    "diff",
    "argsort",
    "clip",
    "digitize",
    "arange",
    "linspace",
]

NAN = float("nan")


def is_nan(value):
    """True for a missing value. -> bool

    Written out rather than calling math.isnan directly: values arrive as
    floats, ints and None depending on the reader, and math.isnan raises on
    None instead of answering the question.
    """
    if value is None:
        return True
    try:
        return math.isnan(value)
    except TypeError:
        return False


def clean(values):
    """The values that are actually present, in order. -> list of float"""
    return [float(v) for v in values if not is_nan(v)]


def percentile(values, q):
    """numpy's default 'linear' method, over the present values. -> float

    numpy places the requested rank at (n-1) * q/100 and interpolates linearly
    between the two neighbouring order statistics. Not (n+1) * q/100, and not a
    nearest rank — statistics.quantiles uses a different method by default, and
    the difference would move the AGP bands and the time-in-range figures
    quietly.
    """
    ordered = sorted(clean(values))
    if not ordered:
        return NAN
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * (q / 100.0)
    low = math.floor(pos)
    high = math.ceil(pos)
    if low == high:
        return ordered[low]
    return ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def column_percentile(rows, q):
    """Percentile down each column of a list of equally long rows. -> list

    This is numpy's `nanpercentile(arr, q, axis=0)`: the AGP and the
    baseline-normalised bands stack one row per meal or per day and then ask
    what the spread is at each point on the time grid. A column where every
    value is missing yields NaN rather than raising, as numpy does.
    """
    if not rows:
        return []
    width = len(rows[0])
    return [percentile([row[i] for row in rows], q) for i in range(width)]


def column_median(rows):
    """Median down each column. -> list"""
    return column_percentile(rows, 50)


def median(values):
    """Median of all values; NaN if any are missing, like numpy's median."""
    listed = list(values)
    if any(is_nan(v) for v in listed):
        return NAN
    return percentile(listed, 50)


def nanmedian(values):
    """Median of the present values. NaN if there are none."""
    return percentile(values, 50)


def mean(values):
    """Arithmetic mean; NaN if any value is missing, like numpy's mean."""
    listed = list(values)
    if not listed or any(is_nan(v) for v in listed):
        return NAN
    return math.fsum(float(v) for v in listed) / len(listed)


def nanmean(values):
    """Arithmetic mean of the present values. NaN if there are none."""
    present = clean(values)
    if not present:
        return NAN
    return math.fsum(present) / len(present)


def stdev(values):
    """Population standard deviation, as numpy's std is. -> float

    Divides by n, not n-1: the coefficient of variation in the consensus
    metrics is defined on the population form, and switching would move it.
    """
    present = clean(values)
    if not present:
        return NAN
    avg = math.fsum(present) / len(present)
    return math.sqrt(math.fsum((v - avg) ** 2 for v in present) / len(present))


def nanmax(values):
    """Largest present value, NaN if there is none."""
    present = clean(values)
    return max(present) if present else NAN


def nanmin(values):
    """Smallest present value, NaN if there is none."""
    present = clean(values)
    return min(present) if present else NAN


def nanargmax(values):
    """Index of the largest present value. -> int

    Ties go to the first, as numpy does.
    """
    best, best_i = None, None
    for i, value in enumerate(values):
        if is_nan(value):
            continue
        if best is None or value > best:
            best, best_i = value, i
    if best_i is None:
        raise ValueError("all values are missing")
    return best_i


def nanargmin(values):
    """Index of the smallest present value. -> int"""
    best, best_i = None, None
    for i, value in enumerate(values):
        if is_nan(value):
            continue
        if best is None or value < best:
            best, best_i = value, i
    if best_i is None:
        raise ValueError("all values are missing")
    return best_i


def searchsorted(ordered, value, side="left"):
    """Where *value* belongs in the sorted sequence. -> int

    Binary search rather than bisect, because the sequences here hold datetimes
    as well as numbers and bisect's key handling differs between versions.
    """
    low, high = 0, len(ordered)
    while low < high:
        mid = (low + high) // 2
        if (ordered[mid] < value) if side == "left" else (ordered[mid] <= value):
            low = mid + 1
        else:
            high = mid
    return low


def diff(values):
    """Differences between neighbours. -> list, one shorter than the input"""
    listed = list(values)
    return [b - a for a, b in zip(listed, listed[1:])]


def argsort(values):
    """Indices that would sort the values. -> list of int

    Stable, as numpy's default is.
    """
    return sorted(range(len(values)), key=lambda i: values[i])


def clip(value, low, high):
    """Value held between the two bounds. -> float"""
    return low if value < low else (high if value > high else value)


def digitize(value, edges):
    """Index of the bin *value* falls into, edges ascending. -> int

    Matches numpy's default right=False: an edge belongs to the bin it opens.
    Zero means below the first edge, len(edges) means at or past the last.
    """
    return searchsorted(edges, value, side="right")


def arange(start, stop, step=1):
    """Evenly spaced values, excluding the stop. -> list

    Counted rather than multiplied out, so a fractional step does not drift.
    """
    out, value, i = [], start, 0
    while (value < stop) if step > 0 else (value > stop):
        out.append(value)
        i += 1
        value = start + i * step
    return out


def linspace(start, stop, count):
    """*count* evenly spaced values, including both ends. -> list"""
    if count <= 1:
        return [start] if count == 1 else []
    span = (stop - start) / (count - 1)
    return [start + i * span for i in range(count)]
