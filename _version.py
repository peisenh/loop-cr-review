"""Filled with the real version by 'git archive' (export-subst) or by CI.

In a normal checkout/clone the placeholder stays unresolved -- that is expected
and is handled by tool_version() (see loop_cr_review.py).

Note: %(describe) only resolves to annotated tags (git tag -a ...), which this
project's releases use anyway. A purely lightweight tag (git tag x) would stay
unresolved -- this only affects ad-hoc tags, not the normal release flow.
"""
VERSION = "$Format:%(describe)$"
