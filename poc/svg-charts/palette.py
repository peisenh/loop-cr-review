"""Farbrollen für die SVG-Diagramme: (hell, dunkel).

Die hellen Werte sind die des bisherigen PNG-Themas, die dunklen stammen aus
_chart_palette(dark=True) — dieselben Farben, nur jetzt in einem Stylesheet
statt in einem zweiten Rendering-Durchgang.
"""

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
    "frame-s":    ("#d8dee8", "#3a4556"),
    "edge-s":     ("#c5cdd9", "#4a5568"),
    "target-s":   ("#55aa55", "#4a8a4a"),
    "zero-s":     ("#888888", "#8a97a8"),
    "ink":        ("#45516b", "#a0aab8"),
    "title":      ("#1a2233", "#e8ecf2"),
    "sub":        ("#5a6577", "#a0aab8"),
    "legend-bg":  ("#ffffff", "#1c2330"),
    "dot":        ("#17202d", "#ffffff"),
    "dot-ring-s": ("#ffffff", "#17202d"),
}
