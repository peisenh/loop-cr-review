from lcr.svg import Chart, path_d

from palette import PALETTE

INK, GRID, TIR, TITLE = "ink", "grid", "tir", "title"
CGM, BOLUS, CARB, BASAL = "cgm", "bolus", "carb", "basal"

MIN_GAP, ROW = 1.6, 11        # Stunden Abstand, Zeilenhöhe für gestapelte Etiketten

def _labels(ch, sx, items, base_y, colour, bold=False):
    """Etiketten einer Art; nur bei echter Nähe in Zeilen stapeln."""
    lanes = []
    for hour, text in sorted(items):
        lane = next((i for i, last in enumerate(lanes) if hour - last >= MIN_GAP), None)
        if lane is None:
            lane = len(lanes); lanes.append(hour)
        else:
            lanes[lane] = hour
        x = sx(hour)
        ch.add(f'<line x1="{x}" y1="{ch.top}" x2="{x}" y2="{ch.bottom}" '
               f'class="{colour}" stroke-opacity="0.18" stroke-width="0.5"/>')
        ch.text(x, base_y + lane * ROW, text, colour, size=6.5, anchor="middle",
                weight="bold" if bold else None)

def daily_svg(day_title, cgm, events, basal_series, gmax, g):
    ch = Chart(1100, 250, margins=(46, 30, 26, 40), palette=PALETTE)
    sx, sy = ch.scales((0, 24), (g(40), g(470)))

    ch.hspan(sy, g(70), g(180), TIR)
    ch.grid_x(sx, range(0, 25, 3), GRID, 0.15)

    if basal_series:
        # Basal on its own scale, drawn as steps behind the glucose curve.
        top = gmax * 2.2 or 1.0
        by = ch.bottom - (ch.bottom - ch.top) * 0  # Basisbezug
        pts = []
        for hour, value in basal_series:
            y = ch.bottom - (value / top) * (ch.bottom - ch.top)
            pts.append((sx(hour), round(y, 2)))
        if pts:
            steps = [f"M{pts[0][0]},{ch.bottom}"]
            prev_y = pts[0][1]
            for x, y in pts:
                steps.append(f"L{x},{prev_y}L{x},{y}")
                prev_y = y
            steps.append(f"L{pts[-1][0]},{ch.bottom}Z")
            ch.add(f'<path d="{"".join(steps)}" class="basal" fill-opacity="0.35"/>')
        ch.text(ch.right + 6, ch.top + 8, "U/h", BASAL, size=6)
        ch.text(ch.right + 6, ch.bottom, "0", BASAL, size=6)
        ch.text(ch.right + 6, ch.top + (ch.bottom - ch.top) * (1 - 1/2.2),
                f"{gmax:.1f}", BASAL, size=6)

    ch.line(path_d([h for h, _ in cgm], [v for _, v in cgm], sx, sy), CGM, 1.0)

    _labels(ch, sx, [(h, f"{b:.1f} U") for h, b, _c in events if b > 0],
            ch.top + 12, BOLUS, bold=True)
    _labels(ch, sx, [(h, f"{c:.0f} g") for h, _b, c in events if c > 0],
            ch.top + 42, CARB)

    ch.frame("frame")
    ch.ticks_x(sx, range(0, 25, 3), INK, fmt=lambda v: f"{int(v)}", size=7)
    ch.ticks_y(sy, [g(70), g(180), g(300)], INK, fmt=lambda v: f"{v:.0f}", size=7)
    ch.text(ch.left, 14, day_title, TITLE, size=9)
    return ch.to_svg(day_title)
