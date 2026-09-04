from lcr.svg import Chart, path_d, band_d

from palette import PALETTE

INK, GRID, TITLE, SUB = "ink", "grid", "title", "sub"
BAND90, BAND75, MEDIAN = "p5", "p25", "median"

CARD_W, CARD_H, COLS = 496, 250, 2
# The legend sits above the cards, not on them: it needs its own height
# rather than a margin, or the first row's frame runs through it.
GAP, LEGEND_H = 8, 34

def norm_curves_svg(bands, window, y_lo, y_hi, unit, labels, texts):
    """bands: list of (title, n, dict with grid/p10/p25/p50/p75/p90)."""
    if not bands:
        ch = Chart(1000, 60, margins=(0, 0, 0, 0), palette=PALETTE)
        ch.text(500, 34, "—", INK, size=16, anchor="middle")
        return ch.to_svg()

    rows = (len(bands) + COLS - 1) // COLS
    width = COLS * CARD_W + (COLS - 1) * GAP
    height = LEGEND_H + rows * CARD_H + (rows - 1) * GAP
    ch = Chart(width, height, margins=(0, 0, 0, 0), palette=PALETTE)

    ch.legend([(MEDIAN, texts["median"], False),
               (BAND75, texts["p25"], True),
               (BAND90, texts["p10"], True)],
              TITLE, x=width / 2 - 90, y=1, size=8)

    for i, (title, n, band) in enumerate(bands):
        row, col = divmod(i, COLS)
        x = col * (CARD_W + GAP)
        y = LEGEND_H + row * (CARD_H + GAP)
        ch.add(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="4" '
               f'fill="none" class="edge" stroke-width="1.5"/>')
        ch.text(x + CARD_W / 2, y + 20, title, TITLE, size=12,
                anchor="middle", weight="bold")
        ch.text(x + CARD_W / 2, y + 36, f"n = {n}", SUB, size=9, anchor="middle")

        panel = ch.panel(x, y + 44, CARD_W, CARD_H - 44, margins=(64, 8, 30, 16))
        sx, sy = panel.scales((0, window), (y_lo, y_hi))
        y_ticks = [v for v in range(int(y_lo // 50) * 50, int(y_hi) + 1, 50)]
        x_ticks = list(range(0, int(window) + 1, 50))
        panel.grid_y(sy, y_ticks, GRID, 0.2)
        panel.grid_x(sx, x_ticks, GRID, 0.2)

        grid = band["grid"]
        panel.band(band_d(grid, band["p10"], band["p90"], sx, sy), BAND90, 0.55)
        panel.band(band_d(grid, band["p25"], band["p75"], sx, sy), BAND75, 0.45)
        panel.line(path_d(grid, band["p50"], sx, sy), MEDIAN, 2)
        zero = sy(0)
        panel.add(f'<line x1="{panel.left}" y1="{zero}" x2="{panel.right}" y2="{zero}" '
                  f'class="zero" stroke-width="0.9" stroke-dasharray="4 3"/>')
        panel.frame("frame")
        panel.ticks_x(sx, x_ticks, INK, fmt=lambda v: f"{int(v)}", size=6.5)
        panel.ticks_y(sy, y_ticks, INK, fmt=lambda v: f"{int(v)}", size=6.5)
        panel.text(panel.left, y + CARD_H - 6, labels["x"], INK, size=7)
        ch.add(f'<text transform="translate({x + 22},{y + 44 + (CARD_H - 44) / 2}) '
               f'rotate(-90)" class="ink" font-size="7" text-anchor="middle">'
               f'{labels["y"]}</text>')
    return ch.to_svg("Baseline-normalisiert")
