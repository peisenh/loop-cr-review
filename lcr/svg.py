# SPDX-FileCopyrightText: 2026 Peter Eisenhauer
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Just enough plotting to draw this report's charts, without matplotlib.

matplotlib is the only reason numpy has to be in the app at all, and it is the
one dependency here that needs a hand-built wheel — the whole 16 KB story, the
version coupling, the ABI that would not align. What it is actually asked to do
is modest: five kinds of chart made of bands, lines, a few labels and a pair of
axes.

Charts come out as inline SVG rather than a base64 PNG, which brings three
things beyond dropping the dependency: they stay sharp at any size, they are a
fraction of the bytes, and they follow the light or dark theme through CSS
instead of being rendered twice.

Colours come from a stylesheet inside the SVG, addressed by class. A CSS
variable in a presentation attribute — fill="var(--x, #fff)" — works in a
browser but is dropped by many standalone SVG viewers, which then fall back to
black. A class with a rule behind it is understood everywhere, and the dark
variant is one media query rather than a second rendering pass.
"""
from __future__ import annotations

import html
import math

_CLIP_SEQ = 0

__all__ = [
    "Scale",
    "Chart",
    "path_d",
    "band_d",
    "clip_halfplane",
    "polygon_d",
]


class Scale:
    """Maps a data range onto a pixel range. Linear, which is all this needs."""

    def __init__(self, lo, hi, out_lo, out_hi):
        self.lo, self.hi = float(lo), float(hi)
        self.out_lo, self.out_hi = float(out_lo), float(out_hi)
        span = self.hi - self.lo
        self._factor = (self.out_hi - self.out_lo) / (span if span else 1.0)

    def __call__(self, value):
        """-> pixel position, rounded to two decimals to keep the file small"""
        return round(self.out_lo + (float(value) - self.lo) * self._factor, 2)

    def ticks(self, step, start=None):
        """Tick values from *start* (default: lo) upwards in *step*."""
        first = self.lo if start is None else start
        out, value = [], first
        # Counting up rather than multiplying keeps 0.1 steps from drifting.
        while value <= self.hi + 1e-9:
            out.append(round(value, 6))
            value += step
        return out


def path_d(xs, ys, sx, sy):
    """Polyline through the points, skipping gaps. -> SVG path data

    A None or NaN breaks the line rather than joining across it: a sensor gap
    is not a straight run between the values on either side of it.
    """
    parts, pen_down = [], False
    for x, y in zip(xs, ys):
        if y is None or (isinstance(y, float) and math.isnan(y)):
            pen_down = False
            continue
        parts.append(f"{'L' if pen_down else 'M'}{sx(x)},{sy(y)}")
        pen_down = True
    return "".join(parts)


def band_d(xs, los, his, sx, sy):
    """Filled area between two series. -> SVG path data

    Built as one closed path per uninterrupted run, so a gap in the data leaves
    a gap in the band instead of a wedge across it.
    """
    runs, current = [], []
    for x, lo, hi in zip(xs, los, his):
        bad = any(v is None or (isinstance(v, float) and math.isnan(v))
                  for v in (lo, hi))
        if bad:
            if len(current) > 1:
                runs.append(current)
            current = []
            continue
        current.append((x, lo, hi))
    if len(current) > 1:
        runs.append(current)

    parts = []
    for run in runs:
        top = "".join(f"{'M' if i == 0 else 'L'}{sx(x)},{sy(hi)}"
                      for i, (x, _lo, hi) in enumerate(run))
        bottom = "".join(f"L{sx(x)},{sy(lo)}" for x, lo, _hi in reversed(run))
        parts.append(top + bottom + "Z")
    return "".join(parts)


def clip_halfplane(polygon, a, b, c):
    """Part of *polygon* where a*x + b*y <= c. -> list of points

    Sutherland-Hodgman against one line. Used for the GRI zones, which are
    bands of a linear score and therefore straight stripes — contouring a
    500x500 grid to find them, as matplotlib did, approximates what can simply
    be computed.
    """
    if not polygon:
        return []
    def inside(point):
        return a * point[0] + b * point[1] <= c + 1e-12

    out = []
    for i, current in enumerate(polygon):
        previous = polygon[i - 1]
        cur_in, prev_in = inside(current), inside(previous)
        if cur_in != prev_in:
            dx, dy = current[0] - previous[0], current[1] - previous[1]
            denominator = a * dx + b * dy
            if denominator:
                t = (c - a * previous[0] - b * previous[1]) / denominator
                out.append((previous[0] + t * dx, previous[1] + t * dy))
        if cur_in:
            out.append(current)
    return out


def polygon_d(points, sx, sy):
    """Closed path through the points. -> SVG path data"""
    if len(points) < 3:
        return ""
    parts = [f"{'M' if i == 0 else 'L'}{sx(x)},{sy(y)}"
             for i, (x, y) in enumerate(points)]
    return "".join(parts) + "Z"


class Chart:  # pylint: disable=too-many-instance-attributes
    """An SVG chart: a plot area with axes, and things drawn into it.

    The attribute count is the four edges of the plot area plus the canvas
    size, the parts collected so far and the palette — splitting that into
    helper objects would make every drawing call reach through one more level
    for nothing.
    """

    def __init__(self, width, height, margins=(46, 12, 34, 12), palette=None):
        """margins: left, top, bottom, right — room for labels.

        palette maps a role name to (light, dark). Everything drawn names a
        role; the colours land in a stylesheet inside the SVG.
        """
        self.width, self.height = width, height
        left, top, bottom, right = margins
        self.left, self.top = left, top
        self.right, self.bottom = width - right, height - bottom
        self.parts = []
        self.palette = dict(palette or {})
        self.rules = []
        self._clip = None

    def role(self, name, light, dark=None, prop="stroke"):
        """Register a colour that is not in the palette. -> class name

        Slot colours come from the slot configuration, which the user can
        change, so they cannot be fixed entries. They land in the same
        stylesheet as a rule of their own.
        """
        safe = "".join(c if c.isalnum() or c == "-" else "-" for c in str(name))
        # The rule carries the -s suffix for a stroke, the returned name does
        # not: callers pass it to line() or band(), which append the suffix
        # themselves. Returning it appended once produced -s-s and a class that
        # matched no rule, so the curve simply did not appear.
        klass = f"{safe}-s" if prop == "stroke" else safe
        self.rules.append(f".{klass}{{{prop}:{light}}}")
        if dark and dark != light:
            self.rules.append(f"@media(prefers-color-scheme:dark)"
                              f"{{.{klass}{{{prop}:{dark}}}}}")
        return safe

    def scales(self, x_range, y_range):
        """-> (x scale, y scale). y is inverted, as pixels grow downwards."""
        return (Scale(x_range[0], x_range[1], self.left, self.right),
                Scale(y_range[0], y_range[1], self.bottom, self.top))

    def add(self, markup):
        """Raw SVG, already escaped where it needed to be."""
        self.parts.append(markup)

    def clip_id(self):
        """A clip path for the plot area. -> the id to reference

        Values outside the y range have to be cut off at the frame, the way an
        axis does it. Without this a percentile band that runs past the top is
        drawn over the title, and a curve past the bottom over the axis labels.
        """
        if self._clip is None:
            # A counter, not id(): a panel that has been garbage collected can
            # hand its address to a later one, and two clip paths of the same
            # name would leave one of them cutting against the wrong rectangle.
            global _CLIP_SEQ                # pylint: disable=global-statement
            _CLIP_SEQ += 1
            self._clip = f"clip{_CLIP_SEQ}"
            self.parts.insert(0, (
                f'<defs><clipPath id="{self._clip}">'
                f'<rect x="{self.left}" y="{self.top}" '
                f'width="{self.right - self.left}" '
                f'height="{self.bottom - self.top}"/></clipPath></defs>'))
        return self._clip

    def band(self, data, role, opacity=1.0):
        """A filled area, coloured by the palette role."""
        self.add(f'<path d="{data}" class="{role}" fill-opacity="{opacity}" '
                 f'clip-path="url(#{self.clip_id()})"/>')

    def line(self, data, role, width=1.0, opacity=1.0, dash=None):
        """A stroked path, coloured by the palette role."""
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{data}" class="{role}-s" fill="none" '
                 f'stroke-width="{width}" stroke-opacity="{opacity}"'
                 f'{dash_attr} stroke-linejoin="round" stroke-linecap="round" '
                 f'clip-path="url(#{self.clip_id()})"/>')

    def hspan(self, sy, lo, hi, role):
        """Horizontal band across the whole plot area, e.g. the target range."""
        top, bottom = sy(hi), sy(lo)
        self.add(f'<rect x="{self.left}" y="{top}" width="{self.right - self.left}" '
                 f'height="{round(bottom - top, 2)}" class="{role}"/>')

    def text(self, x, y, value, role, size=9, anchor="start", weight=None):
        """A label. The value is escaped, so it may come from a catalogue."""
        weight_attr = f' font-weight="{weight}"' if weight else ""
        self.add(f'<text x="{x}" y="{y}" class="{role}" font-size="{size}" '
                 f'text-anchor="{anchor}"{weight_attr}>{html.escape(str(value))}</text>')

    def frame(self, role):
        """Border around the plot area."""
        self.add(f'<rect x="{self.left}" y="{self.top}" '
                 f'width="{self.right - self.left}" height="{self.bottom - self.top}" '
                 f'fill="none" class="{role}-s" stroke-width="0.8"/>')

    def grid_y(self, sy, values, role, opacity=0.25):
        """Horizontal grid lines at the given data values."""
        for value in values:
            y = sy(value)
            self.add(f'<line x1="{self.left}" y1="{y}" x2="{self.right}" y2="{y}" '
                     f'class="{role}-s" stroke-opacity="{opacity}" stroke-width="0.7"/>')

    def grid_x(self, sx, values, role, opacity=0.25):
        """Vertical grid lines at the given data values."""
        for value in values:
            x = sx(value)
            self.add(f'<line x1="{x}" y1="{self.top}" x2="{x}" y2="{self.bottom}" '
                     f'class="{role}-s" stroke-opacity="{opacity}" stroke-width="0.7"/>')

    def ticks_x(self, sx, values, role, fmt=str, size=9, mark=3.5):
        """Labels below the plot area, each with a short mark on the axis."""
        for value in values:
            x = sx(value)
            if mark:
                self.add(f'<line x1="{x}" y1="{self.bottom}" x2="{x}" '
                         f'y2="{round(self.bottom + mark, 2)}" class="{role}-s" '
                         f'stroke-width="0.8"/>')
            self.text(x, self.bottom + 14, fmt(value), role,
                      size=size, anchor="middle")

    def ticks_y(self, sy, values, role, fmt=str, size=9, mark=3.5):
        """Labels left of the plot area, each with a short mark on the axis."""
        for value in values:
            y = sy(value)
            if mark:
                self.add(f'<line x1="{round(self.left - mark, 2)}" y1="{y}" '
                         f'x2="{self.left}" y2="{y}" class="{role}-s" '
                         f'stroke-width="0.8"/>')
            self.text(self.left - mark - 3, y + 3, fmt(value), role,
                      size=size, anchor="end")

    def panel(self, x, y, width, height, margins=(34, 8, 24, 8)):
        """A plot area inside this chart, drawing into the same SVG.

        The normalised curves are a grid of small charts that share a legend
        and a frame. Rather than nesting SVG elements, a panel is a second set
        of scales over a rectangle of the same canvas.
        """
        inner = Chart(width, height, margins)
        inner.left += x
        inner.right += x
        inner.top += y
        inner.bottom += y
        inner.parts = self.parts          # everything lands in one document
        return inner

    def legend(self, entries, ink, x=None, y=None, size=8.5, swatch=14):
        """Key for the series. entries: (palette role, label, filled).

        Placed inside the plot area at the top right by default, where these
        charts have room: the curves run low on the left and the bands taper
        towards the end.
        """
        if not entries:
            return
        pad = 6
        widest = max(len(label) for _c, label, _f in entries)
        box_w = swatch + 6 + widest * size * 0.56 + pad * 2
        box_h = len(entries) * (size + 5) + pad * 2 - 5
        left = self.right - box_w - 8 if x is None else x
        top = self.top + 8 if y is None else y
        self.add(f'<rect x="{round(left, 2)}" y="{round(top, 2)}" '
                 f'width="{round(box_w, 2)}" height="{round(box_h, 2)}" rx="3" '
                 f'class="legend-bg" fill-opacity="0.82" stroke="none"/>')
        for i, (role, label, filled) in enumerate(entries):
            row = top + pad + i * (size + 5) + size * 0.5
            if filled:
                self.add(f'<rect x="{round(left + pad, 2)}" y="{round(row - 4, 2)}" '
                         f'width="{swatch}" height="8" class="{role}"/>')
            else:
                self.add(f'<line x1="{round(left + pad, 2)}" y1="{round(row, 2)}" '
                         f'x2="{round(left + pad + swatch, 2)}" y2="{round(row, 2)}" '
                         f'class="{role}-s" stroke-width="2.2"/>')
            self.text(round(left + pad + swatch + 6, 2), round(row + 3, 2),
                      label, ink, size=size)

    def style_block(self):
        """The stylesheet: light rules, then the dark ones behind a query."""
        if not self.palette:
            return ""
        light, dark = [], []
        for role, (colour_light, colour_dark) in sorted(self.palette.items()):
            # The -s suffix stays in the class name. Stripping it made
            # "bolus" and "bolus-s" collide in one class that both filled and
            # stroked: text came out looking bold, and a line asking for the
            # fill-only role was drawn with no stroke at all, so it vanished.
            prop = "stroke" if role.endswith("-s") else "fill"
            light.append(f".{role}{{{prop}:{colour_light}}}")
            if colour_dark and colour_dark != colour_light:
                dark.append(f".{role}{{{prop}:{colour_dark}}}")
        rules = "".join(light) + "".join(self.rules)
        if dark:
            rules += ("@media(prefers-color-scheme:dark){"
                      + "".join(dark) + "}")
        return f"<style>{rules}</style>"

    def to_svg(self, label=""):
        """-> the finished SVG element"""
        title = f"<title>{html.escape(label)}</title>" if label else ""
        return (f'<svg viewBox="0 0 {self.width} {self.height}" '
                f'xmlns="http://www.w3.org/2000/svg" role="img" '
                f'preserveAspectRatio="xMidYMid meet">'
                f'{self.style_block()}{title}{"".join(self.parts)}</svg>')
