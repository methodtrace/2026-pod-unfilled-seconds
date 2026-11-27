"""Structural floor U_struct(T) = D_h(A;T) = T - max(hA0 intersect [0,T]), A0 = A u {0}.

Computed here by a direct bounded DP (least number of parts, unlimited multiplicity), independent of
the undershoot engines; crosscheck() compares it with engine E-A (iterated sumsets on raw seconds)
and, on a slice, with engine E-B through the gcd reduction D = (T mod g) + g * D_norm(T div g).
"""
from fractions import Fraction
from functools import lru_cache
from itertools import combinations
from math import gcd
from functools import reduce
from .numeric import xsum

INF = 10 ** 9

MENU_GRID = (5, 6, 10, 15, 20, 30, 45, 60)
STUDY_MENUS = ((15, 30), (15, 30, 60), (10, 15, 30), (6, 15, 30), (5, 15, 30), (10, 15, 20, 30),
               (15, 20, 30, 45, 60))


def all_check_menus():
    """The seven study menus and the 85-menu grid (2- and 3-subsets of MENU_GRID plus {10,15,20,30})."""
    ms = set(STUDY_MENUS)
    for k in (2, 3):
        ms.update(combinations(MENU_GRID, k))
    return sorted(ms, key=lambda m: (len(m), m))


def menu_gcd(A):
    return reduce(gcd, A)


@lru_cache(maxsize=None)
def min_parts(A, N):
    """Tuple m[0..N]: least number of parts from A (repetition allowed) summing to s; INF if none."""
    m = [INF] * (N + 1)
    m[0] = 0
    for s in range(1, N + 1):
        best = INF
        for a in A:
            if a <= s and m[s - a] + 1 < best:
                best = m[s - a] + 1
        m[s] = best
    return tuple(m)


@lru_cache(maxsize=None)
def undershoot_table(A, h, N):
    """Tuple D[0..N] with D[T] = D_h(A;T); h None means no cap."""
    A = tuple(sorted(A))
    m = min_parts(A, N)
    hh = INF - 1 if h is None else h
    out = []
    last = 0
    for T in range(N + 1):
        if m[T] < INF and m[T] <= hh:  # INF marks an unreachable sum, whatever the cap
            last = T
        out.append(T - last)
    return tuple(out)


def _table_size(T):
    """Tables are built to a fixed size (512, or the next power of two above T) so that the caches hold one
    table per (menu, cap) instead of one per target."""
    n = 512
    while n < T:
        n *= 2
    return n


def D(A, h, T):
    if T < 0:
        return 0
    return undershoot_table(tuple(sorted(A)), h, _table_size(T))[T]


def range_menu(A):
    """Arithmetic relaxation: every integer duration in [min A, max A]."""
    return tuple(range(min(A), max(A) + 1))


def exact_mean(A, h, pmf):
    """Exact E[D_h(A;T)] for a pmf given as [(T, Fraction weight)] (weights sum to 1)."""
    N = max(t for t, _ in pmf)
    tab = undershoot_table(tuple(sorted(A)), h, N)
    return xsum((w * tab[t] for t, w in pmf), Fraction(0))


def least_cap_window(A, L, U, hmax=200):
    """Least h with D_h(A;T) equal to the uncapped floor D(A;T) for every integer T in [L, U] (direct DP); None
    if no h <= hmax does it. For a window past the conductor whose lower end is a multiple of gcd(A) this is the
    least h filling every multiple of gcd(A) in the window exactly (Proposition 1(c)); otherwise the multiple just
    below the window, or a target below the conductor, can need more ads."""
    A = tuple(sorted(A))
    unc = undershoot_table(A, None, U)
    for h in range(0, hmax + 1):
        tab = undershoot_table(A, h, U)
        if all(tab[T] == unc[T] for T in range(L, U + 1)):
            return h
    return None


def crosscheck(menus=None, hmax=12, Tmax=300, eng=None):
    """Compare undershoot_table with engine E-A on raw seconds for all menus, caps 1..hmax, T 0..Tmax,
    and with E-B (gcd-reduced) on every fifth menu. Returns a summary dict; raises on any mismatch."""
    if eng is None:
        from . import engines as eng
    EA, EB, normalize = eng.engine_a, eng.engine_b, eng.common.normalize
    menus = all_check_menus() if menus is None else menus
    n_a = n_b = 0
    for idx, A in enumerate(menus):
        ser = EA.sumset_series([0] + list(A), hmax)
        for h in range(1, hmax + 1):
            mine = undershoot_table(tuple(A), h, Tmax)
            theirs = EA.undershoot_scan(ser[h], 0, Tmax)
            if list(mine) != list(theirs):
                bad = [T for T in range(Tmax + 1) if mine[T] != theirs[T]][:5]
                raise AssertionError("E-A mismatch menu %s h %d at T %s" % (A, h, bad))
            n_a += Tmax + 1
        if idx % 5 == 0:
            g, A0 = normalize(A)
            ap = EB.apery(A0)
            for h in range(1, hmax + 1):
                mine = undershoot_table(tuple(A), h, Tmax)
                for T in range(0, Tmax + 1):
                    v = (T % g) + g * EB.undershoot_formula(A0, h, T // g, ap)
                    if v != mine[T]:
                        raise AssertionError("E-B mismatch menu %s h %d T %d" % (A, h, T))
                    n_b += 1
    return {"menus": len(menus), "caps": [1, hmax], "T": [0, Tmax],
            "E-A comparisons": n_a, "E-B comparisons": n_b, "mismatches": 0}
