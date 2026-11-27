"""Summation that gives the same result on every Python 3 version.

Python 3.12 changed the builtin sum() of floats to a compensated (Neumaier) sum, so a float total could differ
in its last bits between Python 3.11 and 3.12. math.fsum is correctly rounded (the float nearest the exact sum
of its inputs) on every version since 2.6, so it does not depend on the interpreter, nor on the order of its
inputs. Exact values must stay exact: Fractions and ints go through the builtin sum, which is exact for them.

xsum(values, start=0) is a drop-in replacement for sum(values, start):
  any float among the values (or a float start)  ->  math.fsum (correctly rounded float)
  otherwise (ints, Fractions)                     ->  builtin sum, exact
"""
import math

__all__ = ["xsum", "fmean"]


def xsum(values, start=0):
    xs = values if isinstance(values, (list, tuple)) else list(values)
    # the builtin sum decides the type: a float result means some term (or start) was a float, so the total is
    # recomputed by fsum (the builtin float total is discarded); ints and Fractions keep the exact builtin total
    r = sum(xs, start)
    if type(r) is float:
        return math.fsum(list(xs) + [start]) if start else math.fsum(xs)
    return r


def fmean(values):
    """Arithmetic mean through xsum (correctly rounded total for floats, exact for Fractions)."""
    xs = values if isinstance(values, list) else list(values)
    return xsum(xs) / len(xs)


def nondominated(vals, ses=None, tie=1e-9):
    """Keys of the levers tied for the top gain. vals: [(gain, key)]; ses: {key: standard error} for sampled
    gains (exact gains have none; None counts as 0). A lever is a winner when its own gain exceeds tie and no
    other lever beats it by more than tie plus two standard errors of their difference (pairwise
    non-domination, so the set does not depend on which sampled lever happens to have the largest point
    estimate). Empty if no gain exceeds tie. A NaN gain raises."""
    ses = ses or {}
    for v, k in vals:
        if v != v:
            raise ValueError("nondominated: NaN gain for %r" % (k,))
    if not vals or max(v for v, _ in vals) <= tie:
        return []
    out = []
    for v, k in vals:
        if v <= tie:
            continue
        sk = ses.get(k) or 0.0
        if all(v >= vm - tie - 2 * (sk * sk + (ses.get(m) or 0.0) ** 2) ** 0.5 for vm, m in vals):
            out.append(k)
    return sorted(out)
