# SPDX-FileCopyrightText: 2026 Peter Eisenhauer <github@peter-e.de>
# SPDX-License-Identifier: AGPL-3.0-or-later
"""All matplotlib rendering. Pure presentation: takes data, returns base64 PNGs."""
import os
from pathlib import Path
import base64
import io
import logging
import warnings
from collections import defaultdict
from datetime import datetime
from contextlib import contextmanager

import numpy as np

# Put the font cache in a fixed location (otherwise rebuilt on every start in the
# onefile binary) and silence the "building font cache" message — both must happen
# before matplotlib is imported.
os.environ.setdefault("MPLCONFIGDIR", str(Path.home() / ".cache" / "loop-cr-review-mpl"))
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

import matplotlib  # noqa: E402  pylint: disable=wrong-import-position
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  pylint: disable=wrong-import-position
from matplotlib.lines import Line2D  # noqa: E402  pylint: disable=wrong-import-position
from matplotlib.patches import Patch  # noqa: E402  pylint: disable=wrong-import-position

from lcr.common import (  # noqa: E402  pylint: disable=wrong-import-position
    DAILY_BOLUS_Y, DAILY_CARB_Y, DAILY_MIN_GAP, DAILY_ROW, WEEKDAYS, _, _slot_state,
    fmt_delta, g, glucose_unit, select_slot_rows, slot_median_curve, slot_norm_bands,
    slot_norm_curve, slot_of)

__all__ = [
    "_draw_day_events",
    "_day_title",
    "fig_to_b64",
    "_chart_theme",
    "_chart_palette",
    "gri_grid_chart",
    "agp_chart",
    "slot_curves_chart",
    "selection_effect",
    "slot_norm_curves_chart",
    "daily_charts",
]


def _draw_labels(axg, items, base_y, color, bold=False):
    """Place labels (hour, text) of one kind; stagger into rows only on real proximity."""
    lanes = []
    for hour, text in sorted(items):
        lane = next((i for i, last in enumerate(lanes) if hour - last >= DAILY_MIN_GAP), None)
        if lane is None:
            lane = len(lanes)
            lanes.append(hour)
        else:
            lanes[lane] = hour
        axg.axvline(hour, color=color, lw=.4, alpha=.18)
        axg.text(hour, base_y - lane * DAILY_ROW, text, fontsize=5.5,
                 color=color, ha="center", va="top", fontweight="bold" if bold else "normal")


def _draw_day_events(axg, events, pal):
    """All bolus entries (top) and carb entries (below) of a day."""
    def hour(event):
        return event["time"].hour + event["time"].minute / 60
    _draw_labels(axg, [(hour(e), f"{e['bolus']:.1f} U") for e in events if e["bolus"] > 0],
                 DAILY_BOLUS_Y, pal["bolus"], bold=True)
    _draw_labels(axg, [(hour(e), f"{e['cho']:.0f} g") for e in events if e["cho"] > 0],
                 DAILY_CARB_Y, pal["carb"])

def _day_title(day, tdd):
    """Panel title: weekday + date, plus TDD (bolus/basal) if available."""
    title = f"{_(WEEKDAYS[day.weekday()])}, {day:%d.%m.%Y}"
    if day in tdd:
        bolus, total, basal_u = tdd[day]
        title += f"   ·   TDD {total:.1f} U (Bolus {bolus:.1f} / Basal {basal_u:.1f})"
    return title


def fig_to_b64(fig):
    """Matplotlib figure -> base64 PNG string (keeps figure facecolor for dark charts)."""
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor(),
                edgecolor="none")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()

@contextmanager
def _chart_theme(dark=False):
    """Temporary matplotlib rc for light or dark embedded charts."""
    if dark:
        params = {
            "figure.facecolor": "#1c2330",
            "axes.facecolor": "#1c2330",
            "axes.edgecolor": "#8a97a8",
            "axes.labelcolor": "#e8ecf2",
            "xtick.color": "#c0c8d4",
            "ytick.color": "#c0c8d4",
            "text.color": "#e8ecf2",
            "grid.color": "#5a6b82",
            "legend.facecolor": "#243044",
            "legend.edgecolor": "#3a4556",
        }
    else:
        params = {
            "figure.facecolor": "#ffffff",
            "axes.facecolor": "#ffffff",
            "axes.edgecolor": "#1a2233",
            "axes.labelcolor": "#1a2233",
            "xtick.color": "#1a2233",
            "ytick.color": "#1a2233",
            "text.color": "#1a2233",
            "grid.color": "#b0b8c4",
            "legend.facecolor": "#ffffff",
            "legend.edgecolor": "#dde3ee",
        }
    with plt.rc_context(params):
        yield

def _chart_palette(dark=False):
    """Fill/band colours readable on light or dark chart backgrounds."""
    if dark:
        return {
            "tir": "#1e3a28", "p5": "#2a4060", "p25": "#3a6aaa", "median": "#9ec0ff",
            "bolus": "#9ec0ff", "carb": "#f0a090", "cgm": "#7eb0ff", "basal": "#6a90c0",
        }
    return {
        "tir": "#dff0df", "p5": "#bcd4ff", "p25": "#5b8def", "median": "#0b2e6b",
        "bolus": "#0b2e6b", "carb": "#c0392b", "cgm": "#0b2e6b", "basal": "#5b8def",
    }

# --- Charts -----------------------------------------------------------------
def gri_grid_chart(gri, dark=False):
    """Compact square GRI grid using the published diagonal risk zones."""
    hypo = float(gri["hypo"])
    hyper = float(gri["hyper"])
    with _chart_theme(dark):
        fig, ax = plt.subplots(figsize=(2.35, 2.35))
        ax.set_facecolor("#ffffff" if not dark else "#1c2330")

        # Compact report view: focus the grid on the clinically relevant
        # component range around the observed point. The GRI calculation and
        # zone boundaries remain unchanged; only the displayed axes are
        # cropped so the high-risk Zone E does not dominate the small card.
        xmax = max(15.0, min(20.0, float(np.ceil(max(hypo, 15.0) / 5.0) * 5.0)))
        ymax = max(30.0, min(40.0, float(np.ceil(max(hyper, 30.0) / 5.0) * 5.0)))
        x = np.linspace(0, xmax, 500)
        y = np.linspace(0, ymax, 500)
        xs, ys = np.meshgrid(x, y)
        score = 3.0 * xs + 1.6 * ys

        # Conventional GRI progression: A best/green → E worst/brown.
        zone_colors = ["#69a84f", "#f4cf2e", "#ef8a0c", "#e43d3d", "#8f3434"]
        levels = [0, 20, 40, 60, 80, 100]
        # Use the published zone colours without separator lines. A slightly
        # softer fill keeps Zone E from visually dominating the compact card.
        ax.contourf(xs, ys, np.clip(score, 0, 100), levels=levels,
                    colors=zone_colors, alpha=0.88, antialiased=False)
        # Zone names are given in the compact legend below the grid. Do not
        # place A–E letters at arbitrary coordinates inside the cropped plot.

        ax.scatter([hypo], [hyper], s=22,
                   color="#17202d" if not dark else "#ffffff",
                   edgecolor="#ffffff" if not dark else "#17202d",
                   linewidth=0.7, zorder=5)

        ax.set_xlim(0, xmax)
        ax.set_ylim(0, ymax)
        ax.set_xlabel(_("Hypoglycemia component (%)"), fontsize=6.2, labelpad=1)
        ax.set_ylabel(_("Hyperglycemia component (%)"), fontsize=6.2, labelpad=1)
        ax.tick_params(labelsize=5.2, pad=1)
        ax.set_box_aspect(1)
        ax.grid(alpha=0.08)
        for spine in ax.spines.values():
            spine.set_color("#d8dee8" if not dark else "#3a4556")
        fig.tight_layout(pad=0.12)
        return fig_to_b64(fig)

def agp_chart(times, gluc, dark=False):
    """AGP percentile chart as base64 PNG (light or dark theme)."""
    minute = np.array([t.hour * 60 + t.minute for t in times])
    bins = np.arange(0, 1441, 15)
    idx = np.digitize(minute, bins) - 1
    xs, perc = [], {q: [] for q in (5, 25, 50, 75, 95)}
    for b in range(len(bins) - 1):
        vals = gluc[idx == b]
        if len(vals) >= 5:
            xs.append((bins[b] + 7.5) / 60)
            for q in perc:
                perc[q].append(np.percentile(vals, q))
    xs = np.array(xs)
    pal = _chart_palette(dark)
    with _chart_theme(dark):
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.axhspan(g(70), g(180), color=pal["tir"])
        ax.axhline(g(70), color="#5a5", lw=.7)
        ax.axhline(g(180), color="#5a5", lw=.7)
        ax.fill_between(xs, perc[5], perc[95], color=pal["p5"], alpha=.6, label="5–95 %")
        ax.fill_between(xs, perc[25], perc[75], color=pal["p25"], alpha=.55, label="25–75 %")
        ax.plot(xs, perc[50], color=pal["median"], lw=2, label="Median")
        ax.set_xlim(0, 24)
        ax.set_xticks(range(0, 25, 3))
        ax.set_ylim(g(40), g(300))
        ax.set_xlabel("Uhrzeit")
        ax.set_ylabel(glucose_unit())
        ax.legend(fontsize=8, ncol=3, loc="upper right")
        ax.grid(alpha=.25)
        return fig_to_b64(fig)


def slot_curves_chart(meals, window, val_at, dark=False):
    """Median postprandial curves per slot as base64 PNG (light or dark theme)."""
    grid = np.arange(0, window + 1, 10)
    pal = _chart_palette(dark)
    with _chart_theme(dark):
        fig, ax = plt.subplots(figsize=(10, 3.6))
        ax.axhspan(g(70), g(180), color=pal["tir"])
        for slot in _slot_state()[1]:
            curve = slot_median_curve(meals, slot, window, val_at)
            if curve is not None:
                n = sum(1 for meal in meals if slot_of(meal["time"].hour) == slot)
                ax.plot(grid, curve, color=_slot_state()[3][slot], lw=2,
                        label=f"{_slot_state()[2][slot]} (n={n})")
        ax.set_xlim(0, window)
        ax.set_ylim(g(60), g(240))
        ax.set_xlabel(_("Minutes after meal"))
        ax.set_ylabel(glucose_unit())
        if ax.get_legend_handles_labels()[1]:
            ax.legend(fontsize=8)
        ax.grid(alpha=.25)
        return fig_to_b64(fig)


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
    """One figure: legend + one framed card per meal (title + plot inside).

    Layout matches the design mock: nothing outside its box, no label clipping.
    """

    bands = []
    for slot in _slot_state()[1]:
        b = slot_norm_bands(meals, slot, window, val_at, None)
        if b is not None:
            bands.append((slot, b))
    if not bands:
        with _chart_theme(dark):
            fig, ax = plt.subplots(figsize=(10, 2))
            ax.text(0.5, 0.5, "—", ha="center", va="center")
            ax.axis("off")
            return fig_to_b64(fig)

    n = len(bands)
    ncols = 2
    nrows = (n + ncols - 1) // ncols
    # Fixed Δ range; curves may clip outside −100…+150
    y_lo, y_hi = -g(100), g(150)

    pal = _chart_palette(dark)
    band90 = "#bcd4ff" if not dark else "#2a4060"
    band75 = "#5b8def" if not dark else "#3a6aaa"
    med_c = pal["median"]
    zero_c = "#888" if not dark else "#8a97a8"
    title_c = "#1a2233" if not dark else "#e8ecf2"
    edge = "#c5cdd9" if not dark else "#4a5568"
    face = "#ffffff" if not dark else "#1c2330"
    box_bg = face  # same white as plot; no grey fill around the chart
    fig_bg = face

    with _chart_theme(dark):
        # Extra top row for the legend strip
        fig = plt.figure(figsize=(10.2, 0.12 + 2.85 * nrows))
        fig.patch.set_facecolor(fig_bg)
        # gridspec: row 0 = legend, then meal rows
        height_ratios = [0.09] + [2.5] * nrows
        gs = fig.add_gridspec(
            1 + nrows, ncols,
            height_ratios=height_ratios,
            hspace=0.16, wspace=0.04,
            left=0.03, right=0.97, top=0.995, bottom=0.03,
        )

        # Legend centered across both columns
        leg_ax = fig.add_subplot(gs[0, :])
        leg_ax.set_axis_off()
        leg_ax.set_xlim(0, 1)
        leg_ax.set_ylim(0, 1)
        handles = [
            Line2D([0], [0], color=med_c, lw=2.2, label=_("Median")),
            Patch(facecolor=band75, edgecolor="none", alpha=0.85, label=_("25–75 %")),
            Patch(facecolor=band90, edgecolor="none", alpha=0.75, label=_("10–90 %")),
        ]
        leg = leg_ax.legend(
            handles=handles, loc="center", ncol=3, frameon=False,
            fontsize=7.5, handlelength=1.6, columnspacing=1.0,
            borderaxespad=0.0, handletextpad=0.35, borderpad=0.0,
        )
        for text in leg.get_texts():
            text.set_color(title_c)

        for i, (slot, b) in enumerate(bands):
            r, c = divmod(i, ncols)
            outer = fig.add_subplot(gs[1 + r, c])
            outer.set_xticks([])
            outer.set_yticks([])
            outer.set_xlim(0, 1)
            outer.set_ylim(0, 1)
            outer.set_facecolor(box_bg)
            for spine in outer.spines.values():
                spine.set_visible(True)
                spine.set_color(edge)
                spine.set_linewidth(1.5)

            outer.text(
                0.5, 0.97,
                f"{_slot_state()[2][slot]}",
                transform=outer.transAxes, ha="center", va="top",
                fontsize=11, color=title_c, fontweight="bold",
            )
            outer.text(
                0.5, 0.90,
                f"n = {b['n']}",
                transform=outer.transAxes, ha="center", va="top",
                fontsize=9, color="#5a6577" if not dark else "#a0aab8",
            )
            # Leave clear margins so axis labels never touch the outer frame
            ax = outer.inset_axes([0.15, 0.16, 0.76, 0.64])
            grid = b["grid"]
            ax.set_facecolor(face)
            ax.fill_between(grid, b["p10"], b["p90"], color=band90, alpha=.55, lw=0)
            ax.fill_between(grid, b["p25"], b["p75"], color=band75, alpha=.45, lw=0)
            ax.plot(grid, b["p50"], color=med_c, lw=2)
            ax.axhline(0, color=zero_c, lw=.8, ls="--")
            ax.set_xlim(0, window)
            ax.set_ylim(y_lo, y_hi)
            ax.set_xlabel(_("Minutes after meal"), fontsize=7, labelpad=2)
            ax.set_ylabel(
                _("Δ %(u)s vs. meal start") % {"u": glucose_unit()},
                fontsize=7, labelpad=2,
            )
            ax.tick_params(labelsize=6.5, pad=1)
            ax.grid(alpha=.2)
            for spine in ax.spines.values():
                spine.set_color("#d8dee8" if not dark else "#3a4556")

        for j in range(len(bands), nrows * ncols):
            r, c = divmod(j, ncols)
            blank = fig.add_subplot(gs[1 + r, c])
            blank.axis("off")
            blank.set_facecolor(fig_bg)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, facecolor=fig.get_facecolor(),
                    edgecolor="none", bbox_inches="tight", pad_inches=0.06)
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()


def daily_charts(times, gluc, events, basal, tdd, dark=False):
    """One page-wide panel per day (CGM + bolus/carb + optional basal + TDD)."""
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
    pal = _chart_palette(dark)
    out = []
    with _chart_theme(dark):
        for day in sorted(cgm_by):
            fig, axg = plt.subplots(figsize=(11, 2.5))
            axg.axhspan(g(70), g(180), color=pal["tir"])
            axg.plot([x for x, _ in cgm_by[day]], [y for _, y in cgm_by[day]],
                     color=pal["cgm"], lw=1.0)
            axg.set_xlim(0, 24)
            axg.set_ylim(g(40), g(470))
            axg.set_xticks(range(0, 25, 3))
            axg.set_yticks([g(70), g(180), g(300)])
            axg.tick_params(labelsize=7)
            axg.grid(axis="x", alpha=.15)
            title_color = "#e8ecf2" if dark else "#1a2233"
            axg.set_title(_day_title(day, tdd), fontsize=8, loc="left", color=title_color)
            if rate is not None:
                i0 = int((datetime(day.year, day.month, day.day) - t0).total_seconds() // 60)
                bxx = [mnt / 60 for mnt in range(0, 24 * 60, 5)]
                byy = [rate[i0 + mnt] if 0 <= i0 + mnt < minutes else 0.0
                       for mnt in range(0, 24 * 60, 5)]
                ax2 = axg.twinx()
                ax2.fill_between(bxx, byy, step="pre", color=pal["basal"], alpha=.35, lw=0)
                ax2.set_ylim(0, gmax * 2.2)
                ax2.set_xlim(0, 24)
                ax2.set_yticks([0, round(gmax, 1)])
                spine = "#8bb4ff" if dark else "#3a63a8"
                ax2.set_ylabel("U/h", fontsize=6, color=spine)
                ax2.tick_params(labelsize=6, colors=spine)
            _draw_day_events(axg, ev_by.get(day, []), pal)
            out.append({"img": fig_to_b64(fig)})
    return out
