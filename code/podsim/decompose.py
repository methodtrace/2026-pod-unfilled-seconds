"""Loss decomposition by an exact accounting identity, with common random numbers.

For one break of target T (the dynamic portion), cap k and pool n, with seller-maximal fill under the
seconds-max policy:
  F_inf = T - D_k(A;T)   the fill at unlimited demand (every duration of the menu in unlimited supply)
  F_n                    the fill of the actual pool (a subset of the unlimited pool, so F_n <= F_inf)
  readiness              each selected creative is ready at the deadline with probability rho, drawn after
                         selection, so the expected ready seconds are rho F_n.
Then, exactly and with no ordering choice,
  U = T - rho F_n = (T - F_inf) + (F_inf - F_n) + (1 - rho) F_n
    =  structural    +  demand       +  readiness,
each part nonnegative. Expectations of each part are taken over the break law and the count law.

The structural part D_k(A;T) splits into arithmetic and cap by a two-player Shapley value at unlimited
demand. The players: "arith" replaces the exact menu A by every integer duration in [min A, max A]
(rqddurs -> minduration/maxduration with creatives available at every length; R = range_menu(A)); "cap"
lifts the cap. With V(.) the structural floor under the relaxations,
  V()            = D_k(A;T)     V(arith)      = D_k(R;T)
  V(cap)         = D_inf(A;T)   V(arith, cap) = D_inf(R;T)
  arith part     = [(V() - V(arith)) + (V(cap) - V(arith, cap))] / 2
  cap part       = [(V() - V(cap)) + (V(arith) - V(arith, cap))] / 2
  range residual = V(arith, cap)    (seconds no range of lengths fills: breaks shorter than min A, or between
                                     the sums of j and j + 1 range creatives)
so structural = arith part + cap part + range residual. Interaction I_AC = V() - V(arith) - V(cap) +
V(arith, cap) (> 0: the two relaxations substitute). No elastic creatives: demand never enters the split.
"""
import math
from itertools import combinations

from . import structural
from .laws import dynamic_cap
from .pod import select_menu, select_elastic


def struct_split(Va, Var, Vc, Varc):
    """Two-player split of the structural floor. Arguments: V(), V(arith), V(cap), V(arith, cap), any
    numeric type (Fractions stay exact). Returns dict arith, cap, residual, I_AC."""
    return dict(arith=((Va - Var) + (Vc - Varc)) / 2, cap=((Va - Vc) + (Var - Varc)) / 2, residual=Varc,
                I_AC=Va - Var - Vc + Varc)


def identity_parts(U_r1, U_struct, ET, rho):
    """Exact identity at readiness rho from E[T], E[U at rho = 1] = E[T - F_n] and E[U_struct] = E[T - F_inf].
    Returns dict U, structural, demand, readiness (U = structural + demand + readiness)."""
    F_n = ET - U_r1
    ready = (1 - rho) * F_n
    return dict(U=U_struct + (U_r1 - U_struct) + ready, structural=U_struct, demand=U_r1 - U_struct,
                readiness=ready)


def subsets(chs):
    out = []
    for k in range(len(chs) + 1):
        out.extend(frozenset(c) for c in combinations(chs, k))
    return out


def shapley(U, chs):
    """General Shapley value of a cooperative game. U: dict frozenset -> value. Kept for the tests that check
    struct_split against it."""
    n = len(chs)
    fact = math.factorial
    phi = {}
    for j in chs:
        rest = [c for c in chs if c != j]
        tot = 0.0
        for k in range(len(rest) + 1):
            w = fact(k) * fact(n - 1 - k) / fact(n)
            for S in combinations(rest, k):
                S = frozenset(S)
                tot += w * (U[S] - U[S | {j}])
        phi[j] = tot
    return phi


def build_pools(menu, pools_by_dur, use_extras, extras_last=False):
    """dict duration -> creatives in bid order (bid order equals v order within a duration): pool and extras
    sorted together, or with extras_last the pool sorted by bid followed by the extras sorted by bid, so prefixes
    of the pool stay prefixes of the list."""
    by = {}
    for a in menu:
        pool, extras = pools_by_dur[a]
        if extras_last:
            lst = sorted(pool, key=lambda c: -c.v) + (sorted(extras, key=lambda c: -c.v) if use_extras else [])
        else:
            lst = list(pool) + (list(extras) if use_extras else [])
            lst.sort(key=lambda c: -c.v)
        by[a] = lst
    return by


def pods_for_break(T, structured, menu, hs, conv, pools_by_dur, check_struct=True):
    """Pods for one break. Returns {(h, key): (pod_sec, pod_rev)} with key "pool" (the actual pool, exact menu,
    cap h) and, on the demand-relaxed pool, "dem" (exact menu, cap h), "dem_cap" (exact menu, uncapped),
    "dem_ar" (range of lengths, cap h) and "dem_arcap" (range, uncapped). The demand-relaxed pool is the real
    pool plus enough extra creatives per duration that no pod is short of creatives (pools.py); with
    check_struct every relaxed fill is asserted equal to the exact structural value D (menu or range)."""
    m, M = min(menu), max(menu)
    rng = structural.range_menu(menu)
    out = {}
    by0 = build_pools(menu, pools_by_dur, False)
    by1 = build_pools(menu, pools_by_dur, True)
    flat1 = [c for a in menu for c in by1[a]]
    cache = {}
    for h in hs:
        cap = dynamic_cap(h, structured, conv)
        out[(h, "pool")] = select_menu(T, cap, by0)
        for key, capx, ar in (("dem", cap, False), ("dem_cap", None, False), ("dem_ar", cap, True),
                              ("dem_arcap", None, True)):
            ck = (capx, ar)
            if ck not in cache:
                cache[ck] = select_elastic(T, capx, flat1, m, M) if ar else select_menu(T, capx, by1)
            out[(h, key)] = cache[ck]
    if check_struct:
        for (capx, ar), (ps, _) in cache.items():
            A = rng if ar else menu
            exp = structural.D(A, capx, T) if (capx is None or capx > 0) else T
            if T - ps.seconds != exp:
                raise AssertionError("demand-relaxed fill %d != D %d (%s %s, cap %s, T %d)"
                                     % (T - ps.seconds, exp, "range" if ar else "menu", menu, capx, T))
    return out


class Stat(object):
    """Running sums for means, standard errors and ratio-of-means standard errors (delta method)."""

    def __init__(self):
        self.n = 0
        self.s = {}
        self.ss = {}
        self.cross = {}

    def add(self, vals, cross_pairs=()):
        self.n += 1
        for k, v in vals.items():
            self.s[k] = self.s.get(k, 0.0) + v
            self.ss[k] = self.ss.get(k, 0.0) + v * v
        for a, b in cross_pairs:
            key = (a, b)
            self.cross[key] = self.cross.get(key, 0.0) + vals[a] * vals[b]

    def mean(self, k):
        return self.s[k] / self.n

    def se(self, k):
        n = self.n
        m = self.s[k] / n
        var = max(self.ss[k] / n - m * m, 0.0) * n / (n - 1)
        return math.sqrt(var / n)

    def ratio(self, a, b):
        """E[a]/E[b] and its delta-method standard error."""
        n = self.n
        ma, mb = self.s[a] / n, self.s[b] / n
        if mb == 0:
            return float("nan"), float("nan")
        va = max(self.ss[a] / n - ma * ma, 0.0) * n / (n - 1)
        vb = max(self.ss[b] / n - mb * mb, 0.0) * n / (n - 1)
        cab = (self.cross[(a, b)] / n - ma * mb) * n / (n - 1)
        r = ma / mb
        var = (va - 2 * r * cab + r * r * vb) / (mb * mb) / n
        return r, math.sqrt(max(var, 0.0))
