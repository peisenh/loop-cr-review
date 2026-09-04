"""AGP als SVG, aus denselben Werten wie das PNG."""
import numpy as np
from lcr.svg import Chart, path_d, band_d

from palette import PALETTE

def agp_svg(times, gluc, g, unit, label_time="Uhrzeit"):
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

    # Top margin holds the highest tick label; the unit goes above the
    # plot rather than beside it, where it would sit on that label.
    ch = Chart(1000, 372, margins=(52, 26, 40, 14), palette=PALETTE)
    sx, sy = ch.scales((0, 24), (g(40), g(300)))

    ch.hspan(sy, g(70), g(180), "tir")
    ch.grid_y(sy, [g(v) for v in (50, 100, 150, 200, 250, 300)], "grid")
    ch.grid_x(sx, range(0, 25, 3), "grid")
    for bound in (70, 180):
        y = sy(g(bound))
        ch.add(f'<line x1="{ch.left}" y1="{y}" x2="{ch.right}" y2="{y}" '
               f'class="target" stroke-width="0.9"/>')

    ch.band(band_d(xs, perc[5], perc[95], sx, sy), "p5", 0.6)
    ch.band(band_d(xs, perc[25], perc[75], sx, sy), "p25", 0.55)
    ch.line(path_d(xs, perc[50], sx, sy), "median", 2)

    ch.frame("frame")
    ch.ticks_x(sx, range(0, 25, 3), "ink", fmt=lambda v: f"{int(v)}")
    ch.ticks_y(sy, [g(v) for v in (50, 100, 150, 200, 250, 300)], "ink",
               fmt=lambda v: f"{v:.0f}")
    ch.text(ch.left, ch.height - 6, label_time, "ink", size=10)
    ch.text(ch.left - 6, ch.top - 10, unit, "ink", size=10, anchor="end")
    return ch.to_svg("AGP")
