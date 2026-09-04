import math
from lcr.svg import Chart, clip_halfplane, polygon_d
from palette import PALETTE

ZONE_COLOURS = ["#69a84f", "#f4cf2e", "#ef8a0c", "#e43d3d", "#8f3434"]
LEVELS = [0, 20, 40, 60, 80, 100]

def gri_svg(gri, label_x, label_y):
    hypo, hyper = float(gri["hypo"]), float(gri["hyper"])
    xmax = max(15.0, min(20.0, math.ceil(max(hypo, 15.0) / 5.0) * 5.0))
    ymax = max(30.0, min(40.0, math.ceil(max(hyper, 30.0) / 5.0) * 5.0))

    ch = Chart(240, 240, margins=(30, 8, 26, 8), palette=PALETTE)
    sx, sy = ch.scales((0, xmax), (0, ymax))
    rect = [(0, 0), (xmax, 0), (xmax, ymax), (0, ymax)]

    # The zones are bands of 3*hypo + 1.6*hyper, so each is the rectangle cut
    # by two parallel lines — exact polygons rather than a contoured grid.
    for i, colour in enumerate(ZONE_COLOURS):
        low, high = LEVELS[i], LEVELS[i + 1]
        poly = clip_halfplane(rect, 3.0, 1.6, high)
        if low > 0:
            poly = clip_halfplane(poly, -3.0, -1.6, -low)
        data = polygon_d(poly, sx, sy)
        if data:
            ch.add(f'<path d="{data}" fill="{colour}" fill-opacity="0.88"/>')

    ch.grid_x(sx, range(0, int(xmax) + 1, 2), "grid", 0.10)
    ch.grid_y(sy, range(0, int(ymax) + 1, 5), "grid", 0.10)
    ch.frame("frame")

    # The observed point, ringed so it stays visible on any zone colour.
    px, py = sx(hypo), sy(hyper)
    ch.add(f'<circle cx="{px}" cy="{py}" r="3.4" class="dot" stroke-width="1.1"/>')
    ch.add(f'<circle cx="{px}" cy="{py}" r="3.4" class="dot-ring" fill="none" '
           f'stroke-width="1.1"/>')

    ink = "ink"
    ch.ticks_x(sx, range(0, int(xmax) + 1, 2), ink, fmt=lambda v: f"{int(v)}", size=6)
    ch.ticks_y(sy, range(0, int(ymax) + 1, 5), ink, fmt=lambda v: f"{int(v)}", size=6)
    ch.text(ch.width / 2, ch.height - 2, label_x, ink, size=6.5, anchor="middle")
    ch.add(f'<text transform="translate(8,{ch.height/2}) rotate(-90)" '
           f'fill="{ink}" font-size="6.5" text-anchor="middle">{label_y}</text>')
    return ch.to_svg("GRI")
