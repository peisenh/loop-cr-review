# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""All chart rendering. Pure presentation: takes data, returns inline SVG.

This was matplotlib, and dropping it is what lets numpy go too — between them
they are the only compiled code in the app, the reason for a hand-built wheel,
and the source of every Android problem this project has had. What they were
asked to draw is bands, lines, a few labels and a pair of axes.

Charts are returned as SVG markup rather than a base64 PNG. They stay sharp at
any size, weigh a fraction of the bytes, and follow the light or dark theme
through a stylesheet inside the file — so there is no second rendering pass and
no dark variant to generate.

The ``dark`` argument is kept on every function so callers need not change, and
ignored: one chart now serves both themes.
"""
import warnings
from collections import defaultdict
from datetime import datetime

import numpy as np

from lcr.common import (
    DAILY_MIN_GAP, WEEKDAYS, _, _slot_state,
    fmt_delta, g, glucose_unit, select_slot_rows, slot_median_curve, slot_norm_bands,
    slot_norm_curve, slot_of)
from lcr.svg import Chart, band_d, clip_halfplane, path_d, polygon_d

__all__ = [
    "_day_title",
    "PALETTE",
    "gri_grid_chart",
    "agp_chart",
    "slot_curves_chart",
    "selection_effect",
    "slot_norm_curves_chart",
    "daily_charts",
]

# Colour roles as (light, dark). The light values are the ones the PNG theme
# used; the dark ones come from what was a separate rendering pass. A role
# ending in -s is a stroke, everything else a fill.
PALETTE = {
    "tir":        ("#dff0df", "#1e3a28"),
    "p5":         ("#bcd4ff", "#2a4060"),
    "p25":        ("#5b8def", "#3a6aaa"),
    "median-s":   ("#0b2e6b", "#9ec0ff"),
    "cgm-s":      ("#0b2e6b", "#7eb0ff"),
    "basal":      ("#5b8def", "#6a90c0"),
    "bolus":      ("#0b2e6b", "#9ec0ff"),
    "bolus-s":    ("#0b2e6b", "#9ec0ff"),
    "carb":       ("#c0392b", "#f0a090"),
    "carb-s":     ("#c0392b", "#f0a090"),
    "grid-s":     ("#8a97a8", "#5a6577"),
    # The axis frame: near-black on light, as matplotlib drew it. A pale one
    # let the daily panels run into each other.
    "frame-s":    ("#1a2233", "#8a97a8"),
    # The small charts inside the normalised grid keep the pale frame; a
    # strong one there would compete with each card's own border.
    "frame-soft-s": ("#d8dee8", "#3a4556"),
    "edge-s":     ("#c5cdd9", "#4a5568"),
    "target-s":   ("#55aa55", "#4a8a4a"),
    "p5-s":       ("#bcd4ff", "#2a4060"),
    "p25-s":      ("#5b8def", "#3a6aaa"),
    "zero-s":     ("#888888", "#8a97a8"),
    "ink":        ("#45516b", "#a0aab8"),
    # Tick marks are lines and need a stroke of their own; the fill role
    # of the same name only colours the label text.
    "ink-s":      ("#45516b", "#a0aab8"),
    "title":      ("#1a2233", "#e8ecf2"),
    "sub":        ("#5a6577", "#a0aab8"),
    "legend-bg":  ("#ffffff", "#1c2330"),
    "dot":        ("#17202d", "#ffffff"),
    "dot-ring-s": ("#ffffff", "#17202d"),
}

WIDE, WIDE_HEIGHT = 1000, 392
GRI_SIDE = 240
DAY_W, DAY_H = 1100, 250
CARD_W, CARD_H, CARD_COLS, CARD_GAP = 496, 280, 2, 8
# The strip above the cards has to hold the legend box, which is as tall as
# its rows make it: three at 10.2 plus padding is about 53. Reserved less
# than that and the box hangs over the first row of card borders.
LEGEND_ROWS, LEGEND_SIZE_N = 3, 10.2
LEGEND_H = int(LEGEND_ROWS * (LEGEND_SIZE_N + 5) + 12 - 5) + 8
ZONE_COLOURS = ("#69a84f", "#f4cf2e", "#ef8a0c", "#e43d3d", "#8f3434")
ZONE_LEVELS = (0, 20, 40, 60, 80, 100)


def _day_title(day, tdd, cho=None):
    """Panel title: weekday + date, then TDD and the day's carbs if known.

    The carbs sit next to the insulin because that is the pair a reader wants:
    a day with a high TDD says little on its own, next to what was eaten it
    says something. Only counted meals appear here, so it matches the labels
    below.
    """
    title = f"{_(WEEKDAYS[day.weekday()])}, {day:%d.%m.%Y}"
    if day in tdd:
        bolus, total, basal_u = tdd[day]
        title += f"   ·   TDD {total:.1f} U (Bolus {bolus:.1f} / Basal {basal_u:.1f})"
    if cho:
        # "CHO" rather than a translated word: the report writes it that way
        # everywhere else, down to the column header in the slot table.
        title += f"   ·   CHO {cho:.0f} g"
    return title


def _wide_chart():
    """A page-wide chart with room for axis labels. -> (chart, sx, sy) later."""
    return Chart(WIDE, WIDE_HEIGHT, margins=(64, 20, 42, 18), palette=PALETTE)


# Font sizes converted from what matplotlib drew rather than copied. It measured
# in points at 120 dpi on a figure of a given width in inches; the SVG measures
# in units on a viewBox. Ten points on a ten-inch figure is 13.9 units on a
# thousand-unit box, not ten — carried over unchanged, every label came out
# roughly a third too small.
TICK_SIZE, LABEL_SIZE, LEGEND_SIZE = 13.9, 13.9, 11.1


def _axes(chart, sx, sy, x_ticks, y_ticks, x_label, y_label, size=TICK_SIZE):
    """Frame, ticks and the two axis captions, in one place.

    Captions sit where matplotlib put them: the y one turned on its side and
    centred on the axis, the x one centred below it.
    """
    chart.frame("frame")
    chart.ticks_x(sx, x_ticks, "ink", fmt=lambda v: f"{int(v)}", size=size)
    chart.ticks_y(sy, y_ticks, "ink", fmt=lambda v: f"{v:.0f}", size=size)
    # Captions hang off the axis, not off the edge of the canvas: tick labels
    # sit 14 below it and descend a few more, so a caption at +32 clears them
    # without drifting away from the picture it belongs to.
    chart.text((chart.left + chart.right) / 2, chart.bottom + 32, x_label, "ink",
               size=LABEL_SIZE, anchor="middle")
    chart.add(f'<text transform="translate({chart.left - 42},'
              f'{(chart.top + chart.bottom) / 2}) rotate(-90)" class="ink" '
              f'font-size="{LABEL_SIZE}" text-anchor="middle">{y_label}</text>')


def gri_grid_chart(gri, dark=False):
    """Compact square GRI grid using the published diagonal risk zones.

    The zones are bands of 3*hypo + 1.6*hyper, which is linear — so they are
    straight stripes, and clipping the plot rectangle against two lines gives
    them exactly. matplotlib contoured a 500x500 grid to find the same shapes.
    """
    del dark
    hypo, hyper = float(gri["hypo"]), float(gri["hyper"])
    # Same crop as before: focus on the clinically relevant range around the
    # observed point so the high-risk zone does not dominate a small card.
    xmax = max(15.0, min(20.0, float(np.ceil(max(hypo, 15.0) / 5.0) * 5.0)))
    ymax = max(30.0, min(40.0, float(np.ceil(max(hyper, 30.0) / 5.0) * 5.0)))

    # Room for axis captions. They matter here more than on other charts: the
    # card names both components above the picture, but only the axes say
    # which of the two is driving the score towards red. Short forms: the
    # full wording is directly above, and at this width it would not fit.
    chart = Chart(GRI_SIDE, GRI_SIDE, margins=(52, 10, 46, 10), palette=PALETTE)
    sx, sy = chart.scales((0, xmax), (0, ymax))
    rect = [(0, 0), (xmax, 0), (xmax, ymax), (0, ymax)]

    for i, colour in enumerate(ZONE_COLOURS):
        low, high = ZONE_LEVELS[i], ZONE_LEVELS[i + 1]
        poly = clip_halfplane(rect, 3.0, 1.6, high)
        if low > 0:
            poly = clip_halfplane(poly, -3.0, -1.6, -low)
        data = polygon_d(poly, sx, sy)
        if data:
            chart.add(f'<path d="{data}" fill="{colour}" fill-opacity="0.88"/>')

    # Few ticks, and large enough to read. The card is 128 px wide, so a label
    # converted faithfully from the old chart came out under five pixels — it
    # was already too small there. The axis captions are dropped entirely: the
    # card names both components with their values right above the grid, so
    # they said nothing the reader did not already have.
    x_ticks = list(range(0, int(xmax) + 1, 5))
    y_ticks = list(range(0, int(ymax) + 1, 10))
    chart.grid_x(sx, x_ticks, "grid", 0.10)
    chart.grid_y(sy, y_ticks, "grid", 0.10)
    chart.frame("frame")

    # The observed point, ringed so it stays legible on any zone colour.
    px, py = sx(hypo), sy(hyper)
    chart.add(f'<circle cx="{px}" cy="{py}" r="3.4" class="dot"/>')
    chart.add(f'<circle cx="{px}" cy="{py}" r="3.4" class="dot-ring-s" fill="none" '
              f'stroke-width="1.1"/>')

    chart.ticks_x(sx, x_ticks, "ink", fmt=lambda v: f"{int(v)}", size=14, mark=5)
    chart.ticks_y(sy, y_ticks, "ink", fmt=lambda v: f"{int(v)}", size=14, mark=5)
    chart.text((chart.left + chart.right) / 2, chart.bottom + 32,
               _("Hypoglycemia (%)"), "ink", size=14, anchor="middle")
    chart.add(f'<text transform="translate({chart.left - 36},'
              f'{(chart.top + chart.bottom) / 2}) rotate(-90)" class="ink" '
              f'font-size="14" text-anchor="middle">{_("Hyperglycemia (%)")}</text>')
    return chart.to_svg(_("Glycemia Risk Index"))


def agp_chart(times, gluc, dark=False):
    """AGP percentile chart."""
    del dark
    minute = np.array([t.hour * 60 + t.minute for t in times])
    bins = np.arange(0, 1441, 15)
    idx = np.digitize(minute, bins) - 1
    xs, perc = [], {q: [] for q in (5, 25, 50, 75, 95)}
    for bin_index in range(len(bins) - 1):
        vals = gluc[idx == bin_index]
        if len(vals) >= 5:
            xs.append((bins[bin_index] + 7.5) / 60)
            for q in perc:
                perc[q].append(np.percentile(vals, q))

    chart = _wide_chart()
    sx, sy = chart.scales((0, 24), (g(40), g(300)))
    y_ticks = [g(v) for v in (50, 100, 150, 200, 250, 300)]
    x_ticks = list(range(0, 25, 3))

    chart.hspan(sy, g(70), g(180), "tir")
    chart.grid_y(sy, y_ticks, "grid")
    chart.grid_x(sx, x_ticks, "grid")
    for bound in (70, 180):
        y = sy(g(bound))
        chart.add(f'<line x1="{chart.left}" y1="{y}" x2="{chart.right}" y2="{y}" '
                  f'class="target-s" stroke-width="0.9"/>')

    chart.band(band_d(xs, perc[5], perc[95], sx, sy), "p5", 0.6)
    chart.band(band_d(xs, perc[25], perc[75], sx, sy), "p25", 0.55)
    chart.line(path_d(xs, perc[50], sx, sy), "median", 2)

    _axes(chart, sx, sy, x_ticks, y_ticks, _("Time of day"), glucose_unit())
    chart.legend([("p5", "5–95 %", True), ("p25", "25–75 %", True),
                  ("median", _("Median"), False)], "ink", size=LEGEND_SIZE)
    return chart.to_svg("AGP")


def slot_curves_chart(meals, window, val_at, dark=False):
    """Median postprandial curves per slot."""
    del dark
    grid = list(np.arange(0, window + 1, 10))
    chart = _wide_chart()
    sx, sy = chart.scales((0, window), (g(60), g(240)))
    y_ticks = [g(v) for v in range(60, 241, 20)]
    x_ticks = list(range(0, int(window) + 1, 50))

    chart.hspan(sy, g(70), g(180), "tir")
    chart.grid_y(sy, y_ticks, "grid")
    chart.grid_x(sx, x_ticks, "grid")

    entries = []
    for slot in _slot_state()[1]:
        curve = slot_median_curve(meals, slot, window, val_at)
        if curve is None:
            continue
        count = sum(1 for meal in meals if slot_of(meal["time"].hour) == slot)
        # Slot colours come from the slot configuration, which the user can
        # change, so they are registered as rules rather than fixed roles.
        colour = _slot_state()[3][slot]
        role = chart.role(f"slot-{slot}", colour, colour)
        chart.line(path_d(grid, curve, sx, sy), role, 2)
        entries.append((role, f"{_slot_state()[2][slot]} (n={count})", False))

    _axes(chart, sx, sy, x_ticks, y_ticks, _("Minutes after meal"), glucose_unit())
    chart.legend(entries, "ink", size=LEGEND_SIZE)
    return chart.to_svg("Postprandial")


def selection_effect(meals, by_slot, window, val_at):
    """How much the verdict's meal selection would move the normalised curves.

    The chart shows all meals; the verdict uses only uncontaminated ones. This
    quantifies the gap instead of asking the reader to compare two pictures:
    per slot, how many meals are clean and the largest deviation between the
    all-meals curve and the clean-only curve. A small number means the neutral
    chart also describes what the verdict rests on. -> list of dicts.
    """
    out = []
    for slot in _slot_state()[1]:
        rows = by_slot.get(slot, [])
        if not rows:
            continue
        use, _n_clean, clean_only = select_slot_rows(rows)
        clean_times = {r["time"] for r in use} if clean_only else None
        curve_all, n_all = slot_norm_curve(meals, slot, window, val_at, None)
        curve_sel, n_sel = slot_norm_curve(meals, slot, window, val_at, clean_times)
        if curve_all is None or curve_sel is None:
            continue
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            shift = float(np.nanmax(np.abs(np.array(curve_all) - np.array(curve_sel))))
        out.append({"label": _slot_state()[2][slot], "used": n_sel, "total": n_all,
                    "shift": "—" if np.isnan(shift) else fmt_delta(shift).lstrip("+")})
    return out


def slot_norm_curves_chart(meals, window, val_at, dark=False):
    """One chart: a shared legend and one framed card per meal type."""
    del dark
    bands = []
    for slot in _slot_state()[1]:
        band = slot_norm_bands(meals, slot, window, val_at, None)
        if band is not None:
            bands.append((_slot_state()[2][slot], band))
    if not bands:
        empty = Chart(WIDE, 60, margins=(0, 0, 0, 0), palette=PALETTE)
        empty.text(WIDE / 2, 34, "—", "ink", size=16, anchor="middle")
        return empty.to_svg()

    rows = (len(bands) + CARD_COLS - 1) // CARD_COLS
    width = CARD_COLS * CARD_W + (CARD_COLS - 1) * CARD_GAP
    height = LEGEND_H + rows * CARD_H + (rows - 1) * CARD_GAP
    chart = Chart(width, height, margins=(0, 0, 0, 0), palette=PALETTE)
    # Fixed delta range; curves may run outside -100…+150 and are clipped there.
    y_lo, y_hi = -g(100), g(150)

    chart.legend([("median", _("Median"), False), ("p25", "25–75 %", True),
                  ("p5", "10–90 %", True)], "title",
                 x=width / 2 - 110, y=2, size=LEGEND_SIZE_N)

    for index, (label, band) in enumerate(bands):
        row, col = divmod(index, CARD_COLS)
        x = col * (CARD_W + CARD_GAP)
        y = LEGEND_H + row * (CARD_H + CARD_GAP)
        _norm_card(chart, x, y, label, band, window, (y_lo, y_hi))
    return chart.to_svg("Baseline-normalised")


def _norm_card(chart, x, y, label, band, window, y_range):
    """One framed card of the normalised-curves grid."""
    chart.add(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="4" '
              f'fill="none" class="edge-s" stroke-width="1.5"/>')
    chart.text(x + CARD_W / 2, y + 22, label, "title", size=15,
               anchor="middle", weight="bold")
    chart.text(x + CARD_W / 2, y + 40, f"n = {band['n']}", "sub", size=12.3,
               anchor="middle")

    panel = chart.panel(x, y + 50, CARD_W, CARD_H - 50, margins=(74, 8, 40, 16))
    sx, sy = panel.scales((0, window), y_range)
    y_ticks = list(range(int(y_range[0] // 50) * 50, int(y_range[1]) + 1, 50))
    x_ticks = list(range(0, int(window) + 1, 50))
    panel.grid_y(sy, y_ticks, "grid", 0.2)
    panel.grid_x(sx, x_ticks, "grid", 0.2)

    grid = band["grid"]
    panel.band(band_d(grid, band["p10"], band["p90"], sx, sy), "p5", 0.55)
    panel.band(band_d(grid, band["p25"], band["p75"], sx, sy), "p25", 0.45)
    panel.line(path_d(grid, band["p50"], sx, sy), "median", 2)
    zero = sy(0)
    panel.add(f'<line x1="{panel.left}" y1="{zero}" x2="{panel.right}" y2="{zero}" '
              f'class="zero-s" stroke-width="0.9" stroke-dasharray="4 3"/>')

    panel.frame("frame-soft")
    panel.ticks_x(sx, x_ticks, "ink", fmt=lambda v: f"{int(v)}", size=8.9)
    panel.ticks_y(sy, y_ticks, "ink", fmt=lambda v: f"{int(v)}", size=8.9)
    # Off the axis, like the other charts: at the card edge the caption drifted
    # away from the panel it labels, which is what one notices first.
    panel.text((panel.left + panel.right) / 2, panel.bottom + 26,
               _("Minutes after meal"), "ink", size=9.5, anchor="middle")
    caption = _("Δ %(u)s vs. meal start") % {"u": glucose_unit()}
    chart.add(f'<text transform="translate({panel.left - 34},'
              f'{(panel.top + panel.bottom) / 2}) rotate(-90)" class="ink" '
              f'font-size="9.5" text-anchor="middle">{caption}</text>')


def _day_labels(chart, sx, items, base_y, role, bold=False):
    """Labels of one kind; stagger into rows only on real proximity."""
    lanes = []
    for hour, text in sorted(items):
        lane = next((i for i, last in enumerate(lanes)
                     if hour - last >= DAILY_MIN_GAP), None)
        if lane is None:
            lane = len(lanes)
            lanes.append(hour)
        else:
            lanes[lane] = hour
        x = sx(hour)
        chart.add(f'<line x1="{x}" y1="{chart.top}" x2="{x}" y2="{chart.bottom}" '
                  f'class="{role}-s" stroke-opacity="0.18" stroke-width="0.5"/>')
        # Row spacing in SVG units, not in glucose units: DAILY_ROW is 18 mg/dL,
        # which on this axis is about eight pixels — less than a line of type
        # at this size, so stacked labels ran into each other.
        chart.text(x, base_y + lane * 10, text, role, size=7.6, anchor="middle",
                   weight="bold" if bold else None)


def _day_basal(chart, sx, series, gmax):
    """Basal rate as steps on its own scale, behind the glucose curve."""
    if not series:
        return
    top = gmax * 2.2 or 1.0
    height = chart.bottom - chart.top
    points = [(sx(hour), round(chart.bottom - (value / top) * height, 2))
              for hour, value in series]
    steps = [f"M{points[0][0]},{chart.bottom}"]
    previous = points[0][1]
    for x, y in points:
        steps.append(f"L{x},{previous}L{x},{y}")
        previous = y
    steps.append(f"L{points[-1][0]},{chart.bottom}Z")
    chart.add(f'<path d="{"".join(steps)}" class="basal" fill-opacity="0.35"/>')
    # 6 pt on an 11 inch figure is 8.3 units here — the last size that was
    # carried over instead of converted.
    chart.text(chart.right + 6, chart.top + 10, "U/h", "basal", size=8.3)
    chart.text(chart.right + 6, chart.bottom, "0.0", "basal", size=8.3)
    chart.text(chart.right + 6, chart.top + height * (1 - 1 / 2.2),
               f"{gmax:.1f}", "basal", size=8.3)


def daily_charts(times, gluc, events, basal, tdd, dark=False, progress=None):
    """One page-wide panel per day (CGM + bolus/carb + optional basal + TDD)."""
    del dark
    if basal is None:
        rate, t0, minutes, gmax = None, None, 0, 1.0
    else:
        rate, t0, minutes = basal[:3]
        gmax = float(np.nanmax(rate)) or 1.0
    cgm_by, ev_by = defaultdict(list), defaultdict(list)
    for time, value in zip(times, gluc):
        cgm_by[time.date()].append((time.hour + time.minute / 60, value))
    for event in events:
        ev_by[event["time"].date()].append(event)

    out = []
    days = sorted(cgm_by)
    for day_index, day in enumerate(days, 1):
        chart = Chart(DAY_W, DAY_H, margins=(46, 30, 26, 40), palette=PALETTE)
        sx, sy = chart.scales((0, 24), (g(40), g(470)))
        chart.hspan(sy, g(70), g(180), "tir")
        chart.grid_x(sx, range(0, 25, 3), "grid", 0.15)

        series = []
        if rate is not None:
            i0 = int((datetime(day.year, day.month, day.day) - t0).total_seconds() // 60)
            series = [(mnt / 60, rate[i0 + mnt] if 0 <= i0 + mnt < minutes else 0.0)
                      for mnt in range(0, 24 * 60, 5)]
        _day_basal(chart, sx, series, gmax)

        chart.line(path_d([h for h, _v in cgm_by[day]],
                          [v for _h, v in cgm_by[day]], sx, sy), "cgm", 1.0)

        day_events = ev_by.get(day, [])
        hours = {id(e): e["time"].hour + e["time"].minute / 60 for e in day_events}
        _day_labels(chart, sx,
                    [(hours[id(e)], f"{e['bolus']:.1f} U")
                     for e in day_events if e["bolus"] > 0],
                    chart.top + 12, "bolus", bold=True)
        _day_labels(chart, sx,
                    [(hours[id(e)], f"{e['cho']:.0f} g")
                     for e in day_events if e["cho"] > 0],
                    chart.top + 42, "carb")

        chart.frame("frame")
        chart.ticks_x(sx, range(0, 25, 3), "ink", fmt=lambda v: f"{int(v)}", size=9.5)
        chart.ticks_y(sy, [g(70), g(180), g(300)], "ink",
                      fmt=lambda v: f"{v:.0f}", size=9.5)
        day_cho = sum(e["cho"] for e in day_events if e["cho"] > 0)
        # Sizes converted from what matplotlib drew: 8 pt at 120 dpi on a
        # 1320 px figure is 11 units on a 1100 unit viewBox. Carried over as
        # they were, the title and the axes came out a fifth too small.
        chart.text(chart.left, 15, _day_title(day, tdd, day_cho), "title", size=11)

        out.append({"img": chart.to_svg()})
        if progress is not None and days:
            progress(day_index, len(days))
    return out
