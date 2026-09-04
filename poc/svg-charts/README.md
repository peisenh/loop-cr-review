# Charts as SVG — working notes

**Status: integrated. The prototypes here are what `lcr/charts.py` grew from.**

## Why

matplotlib is the only reason numpy has to be in the app, and the only
dependency here that needs a hand-built wheel. Everything that cost time on the
Android side — the 16 KB alignment, the numpy version coupling, the x86_64 dead
end recorded in `poc/android-x86_64-16k/` — traces back to it.

Without matplotlib **and** numpy, nothing in the app is compiled: Flask, Jinja2
and waitress are pure Python. No ABI, no page size, no wheels to build, and
x86_64 works by itself. That is the prize, and it only arrives after both go.

The order is forced: matplotlib pulls numpy in regardless, so numpy can only
follow.

## What is done

`lcr/svg.py` — the primitives. Scales, paths, filled bands, axes, grid, ticks,
legend, sub-panels, half-plane polygon clipping. About 250 lines, and it is all
this report needs: the charts are bands, lines, a few labels and a pair of axes.

Two things it does that matter beyond drawing:

- A gap in the data **breaks** the line and the band rather than spanning it. A
  sensor dropout is not a straight run between the values on either side.
- Colours come from a stylesheet inside the SVG, addressed by class, with the
  dark variant behind one media query. The second rendering pass and the "also
  render dark charts" option can go.

  The first attempt used CSS variables in presentation attributes —
  `fill="var(--ch-tir, #dff0df)"`. That works in a browser and is dropped by
  many standalone SVG viewers, which then fall back to black: everything came
  out monochrome except the GRI, whose zone colours happened to be literal. A
  class with a rule behind it is understood everywhere.

  Slot colours come from the slot configuration and cannot be fixed entries, so
  `Chart.role()` registers them as rules of their own.

The five prototypes in this folder each render from the real example export and
were compared against the current PNG:

| chart | SVG | PNG before |
|---|---|---|
| AGP | 10.6 KB | ~90 KB |
| GRI grid | 4.2 KB | ~30 KB |
| slot curves | 5.8 KB | ~70 KB |
| normalised curves | 16.4 KB | ~180 KB |
| one daily panel | 16.7 KB | ~50 KB |

The GRI comes out **better** than before, not merely smaller: its zones are
bands of `3·hypo + 1.6·hyper`, which is linear, so they are straight stripes.
matplotlib contoured a 500×500 grid to find them; they are now clipped as exact
polygons, with straight edges instead of raster steps.

## What was done

`lcr/charts.py` draws the five charts as SVG, with the same function names and
signatures as before. The template embeds them inline; the `chart-light` /
`chart-dark` pair and the CSS that toggled them are gone. matplotlib is out of
the requirements, the Android build, the wheels folder and `NOTICE.md`, and the
wheel build script with it.

A report with daily panels went from **951 KB to 310 KB**, and the test suite
from 36 seconds to 13 — matplotlib is no longer imported anywhere.

Two things only showed once the charts sat in the report rather than on their
own: the daily panels need the near-black axis frame matplotlib gave them —
a pale one let them run into each other — and a rule between the rows, because
the old PNGs carried their own border. The small charts inside the normalised
grid keep the pale frame, where a strong one would compete with each card's
border.

One bug took three attempts because the symptom pointed away from the cause.
The stylesheet stripped the `-s` suffix when turning a role into a class name,
so `bolus` and `bolus-s` both became `.bolus` — one setting `fill`, the other
`stroke`. Text drawn with that class was filled *and* outlined, which reads as
bold; and a line asking for a fill-only role like `ink` got no stroke at all and
disappeared. Removing the bold attribute did not help, because the weight was
never an attribute. The suffix stays in the class name now, and every line asks
for a `-s` role.

Fixing that suffix broke `Chart.role()` in the same way from the other side: it
returned the name with `-s` already appended, `line()` appended another, and the
slot curves vanished into a class that matched no rule. The rule carries the
suffix, the returned name does not.

Values outside the axis range needed clipping. matplotlib cut at the axes; an
SVG path does not, so a percentile band running past the top was drawn over the
title. Each plot area gets a clip path, numbered from a counter rather than from
`id()` — a panel that has been garbage collected can hand its address to a later
one.

Font sizes needed converting rather than copying, and this was the single
biggest source of "it looks worse than before". matplotlib measured in points at
120 dpi on a figure of a given width in inches; the SVG measures in units on a
viewBox. Ten points on a ten-inch figure is 13.9 units on a thousand-unit box,
not ten. Every chart was affected, the wide ones worst — their labels were a
third too small. The conversion is written out at `TICK_SIZE` in `lcr/charts.py`
so the next size is derived rather than guessed.

The axis captions also had to go back where matplotlib put them: the y one
turned on its side and centred on the axis, the x one centred below it. Tucked
into the corners they read as an afterthought.

Two more that only the browser showed: the axes need the short tick marks
matplotlib drew beside each label, and the stacked event labels need their row
spacing in SVG units. `DAILY_ROW` is 18 mg/dL, which on that axis is about eight
pixels — less than a line of type, so two labels close together in time landed
on top of each other.

## What remains

- numpy, which is the point of all this: without it and matplotlib, nothing in
  the app is compiled. The percentile check that decides whether that is
  feasible has already passed — a full report came out byte-identical with a
  pure-Python percentile in place of numpy's.

The `dark_charts` option has since been removed: the command line flag, the
checkbox, the second rendering pass, the `*_img_dark` context keys and the
catalogue string. Dark mode itself is untouched.

## How to check it

Report diffing does not help here — every image changes by definition. The
check is looking at them, which is why each prototype was rendered and compared
before being called done. What can be checked mechanically is that the numbers
behind the curves are untouched: the analysis is not being changed in this step.
