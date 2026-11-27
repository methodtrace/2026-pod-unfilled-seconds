"""X0: regression checks of the simulator against two tables of fixed reference values.

The reference values are hard-coded below (REF1_VALUES for check 1, REF2_VALUES and COMPANION_TABLE for check 2).
They were computed independently of the dynamic program and serve as regression checks: every run recomputes
each cell and fails on any mismatch. (P1 and P2 here number the two checks; they are not pod policies.)

Reference check 1 (P1_*): B uniform on {60, 90, 120, 150, 180}; hybrid S uniform on {5, 10, 15, 20, 45},
always present, T = B - S; unlimited demand, rho = 1; mean unfilled seconds per break = exact mean of
D_h(A;T). Computed twice: by the direct DP (structural.py) and by engine E-A on raw seconds. Hybrid cap
convention (a) (maxseq on the dynamic portion alone) is the primary reading; convention (b) (K - 1) is also
computed and reported, which shows that the reference values follow convention (a).

Reference check 2 (P2_*): least maxseq h with D_h(A;T) = 0 for every multiple T of gcd(A) in [60, 180].
Computed by the direct DP, by E-A, and by the closed form of Proposition 1(c), h* = ceil((floor(U/g) + c2)/d),
c2 the conductor of the reflected semigroup <d - A> (E-C Frobenius + 1), valid for CM menus with L >= g c1.
COMPANION_TABLE holds the least caps on [60, 180] stated in Appendix A of the paper (part (c)
of the main proposition); the check requires all five values to agree.
"""
from fractions import Fraction
from math import gcd
from functools import reduce

from . import structural
from . import engines as E

P1_MENUS = [(15, 30), (10, 15, 30), (6, 15, 30), (15, 30, 60)]
P1_COLS = [(4, "grid"), (4, "remainder"), (6, "grid"), (6, "remainder"), (8, "remainder")]
REF1_VALUES = {
    (15, 30): ["18.00", "14.00", "0.00", "5.00", "5.00"],
    (10, 15, 30): ["18.00", "11.60", "0.00", "0.60", "0.00"],
    (6, 15, 30): ["18.00", "12.68", "0.00", "2.00", "1.04"],
    (15, 30, 60): ["0.00", "5.00", "0.00", "5.00", "5.00"],
}
B_SET = [60, 90, 120, 150, 180]
S_SET = [5, 10, 15, 20, 45]

REF2_VALUES = {(15, 30, 60): 4, (15, 30): 6, (10, 15, 30): 7, (10, 15, 20, 30): 7, (5, 15, 30): 8,
            (6, 15, 30): 9}
COMPANION_TABLE = {(15, 30): 6, (5, 15, 30): 8, (10, 15, 30): 7, (6, 15, 30): 9, (15, 30, 60): 4,
           (10, 15, 20, 30): 7}
P2_WINDOW = (60, 180)


def targets(kind):
    if kind == "grid":
        return [(b, False) for b in B_SET]
    return [(b - s, True) for b in B_SET for s in S_SET]


def mean_direct(menu, h, kind, conv="a"):
    pts = targets(kind)
    tot = 0
    for T, structured in pts:
        cap = h - 1 if (structured and conv == "b") else h
        tot += structural.D(menu, cap, T)
    return Fraction(tot, len(pts))


def mean_engine_a(menu, h, kind, conv="a"):
    pts = targets(kind)
    tot = 0
    for T, structured in pts:
        cap = h - 1 if (structured and conv == "b") else h
        bits = E.engine_a.sumset_bits([0] + list(menu), cap)
        tot += E.engine_a.undershoot_scan(bits, 0, T)[T]
    return Fraction(tot, len(pts))


def fmt(x):
    return "%.2f" % float(x)


def two_dp_exact(x):
    """True if x is exactly representable with two decimals (so the reference table's rounding hides nothing)."""
    return (x * 100).denominator == 1


def reference_check_1():
    rows = []
    for menu in P1_MENUS:
        cells = []
        for (h, kind), ref in zip(P1_COLS, REF1_VALUES[menu]):
            d = mean_direct(menu, h, kind)
            a = mean_engine_a(menu, h, kind)
            if d != a:
                raise AssertionError("reference check 1: engines disagree %s %s %s" % (menu, h, kind))
            b = mean_direct(menu, h, kind, "b") if kind == "remainder" else None
            cells.append(dict(h=h, kind=kind, exact=d, ours=fmt(d), reference=ref,
                              match=(fmt(d) == ref), exact_2dp=two_dp_exact(d),
                              conv_b=(fmt(b) if b is not None else None)))
        rows.append((menu, cells))
    return rows


def least_cap_engine_a(menu, L, U, hmax=60):
    g = reduce(gcd, menu)
    pts = [T for T in range(L, U + 1) if T % g == 0]
    for h in range(1, hmax + 1):
        bits = E.engine_a.sumset_bits([0] + list(menu), h)
        if all((bits >> T) & 1 for T in pts):
            return h
    return None


def closed_form(menu, L, U):
    g, A0 = E.common.normalize(menu)
    d = max(A0)
    pos = [a for a in A0 if a > 0]
    cm = E.engine_b.is_cm(A0)
    c1 = 0 if 1 in pos else E.engine_c.frobenius(pos) + 1
    refl = E.engine_c.reflected_generators(A0)
    c2 = 0 if 1 in refl else E.engine_c.frobenius(refl) + 1
    Up = U // g
    Lp = L // g
    hstar = -(-(Up + c2) // d)
    return dict(g=g, A0=A0, cm=cm, c1=c1, c2=c2, d=d, hstar=hstar,
                applies=(cm and L >= g * c1), least_by_b=(Up - Lp >= d - 1))


def reference_check_2():
    L, U = P2_WINDOW
    rows = []
    for menu in REF2_VALUES:
        direct = structural.least_cap_window(menu, L, U)
        ea = least_cap_engine_a(menu, L, U)
        cf = closed_form(menu, L, U)
        rows.append(dict(menu=menu, direct=direct, engine_a=ea, closed=cf["hstar"], cf=cf,
                         reference=REF2_VALUES[menu], companion=COMPANION_TABLE[menu],
                         match=(direct == ea == cf["hstar"] == REF2_VALUES[menu] == COMPANION_TABLE[menu])))
    return rows


def reference2_alternatives():
    """Least caps under other readings of 'lattice', reported for comparison: every integer target filled up to
    T mod g (identical to the gcd lattice by the reduction), and the 5-second and 15-second lattices."""
    L, U = P2_WINDOW
    out = {}
    for menu in REF2_VALUES:
        m = structural.min_parts(tuple(sorted(menu)), U)
        r = {}
        for name, step in (("5 s lattice", 5), ("15 s lattice", 15)):
            pts = [T for T in range(L, U + 1) if T % step == 0]
            need = max(m[T] for T in pts)
            r[name] = need if need < structural.INF else "never (some target off the menu lattice)"
        # integer targets, fill up to T mod g
        g = reduce(gcd, menu)
        need = 0
        for T in range(L, U + 1):
            need = max(need, m[T - T % g])
        r["integers, up to T mod g"] = need
        out[menu] = r
    return out
