from lcr.svg import Chart, path_d

from palette import PALETTE

INK, GRID, TIR = "ink", "grid", "tir"

def slot_curves_svg(grid_x, curves, window, g, unit, x_label):
    """curves: list of (label, colour, values or None)."""
    ch = Chart(1000, 372, margins=(52, 26, 40, 14), palette=PALETTE)
    sx, sy = ch.scales((0, window), (g(60), g(240)))
    ch.hspan(sy, g(70), g(180), TIR)

    y_ticks = [g(v) for v in range(60, 241, 20)]
    x_ticks = list(range(0, int(window) + 1, 50))
    ch.grid_y(sy, y_ticks, GRID)
    ch.grid_x(sx, x_ticks, GRID)

    entries = []
    for label, colour, values in curves:
        if values is None:
            continue
        # Slot colours come from the configuration, so they get their own rule.
        role = ch.role(f"slot-{label.split()[0].lower()}", colour, colour)
        ch.line(path_d(grid_x, values, sx, sy), role, 2)
        entries.append((role, label, False))

    ch.frame("frame")
    ch.ticks_x(sx, x_ticks, INK, fmt=lambda v: f"{int(v)}")
    ch.ticks_y(sy, y_ticks, INK, fmt=lambda v: f"{v:.0f}")
    ch.text(ch.left, ch.height - 6, x_label, INK, size=10)
    ch.text(ch.left - 6, ch.top - 10, unit, INK, size=10, anchor="end")
    ch.legend(entries, INK)
    return ch.to_svg("Postprandial")
