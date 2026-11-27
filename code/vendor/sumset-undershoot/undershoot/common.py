"""Shared input handling only. No sumset, semigroup or undershoot logic lives here."""
from math import gcd
from functools import reduce


def normalize(parts):
    """Return (g, A0) with A0 = sorted({0} u parts/g), gcd of the positive part equal to 1."""
    parts = sorted(set(int(p) for p in parts if int(p) > 0))
    if not parts:
        raise ValueError("need at least one positive part")
    g = reduce(gcd, parts)
    return g, [0] + [p // g for p in parts]
