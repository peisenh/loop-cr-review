"""Wird von 'git archive' (export-subst) bzw. der CI mit der echten Version befuellt.

Im normalen Checkout/Clone bleibt der Platzhalter unaufgeloest -- das ist erwartet
und wird von tool_version() erkannt (siehe loop_cr_review.py).

Wichtig: %(describe) loest nur zu annotierten Tags auf (git tag -a ...), wie sie
diese Projekt-Releases ohnehin verwenden. Ein rein lightweight Tag (git tag x)
bliebe unaufgeloest -- betrifft nur ad-hoc Tags, nicht den normalen Release-Flow.
"""
VERSION = "$Format:%(describe)$"
