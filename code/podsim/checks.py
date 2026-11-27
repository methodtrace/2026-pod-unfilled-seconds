"""Consistency checks, keyed in checks.json as item1, item2, item7 and item8: the structural cross-check against
the undershoot engines (item1), pod construction against brute force (item2), the stability criterion
Proposition 2 of the paper (item7) and the non-CM tau bound of the regularity companion (item8)."""
import random
from itertools import combinations
from math import gcd
from functools import reduce

from . import structural
from . import engines as E
from .pod import Creative, select_menu, select_elastic, dp_select, pod_oracle, elastic_oracle
from .numeric import xsum

GRID = structural.MENU_GRID


# ------------------------------------------------------------------------------------- item2: pods

def random_pool(rng, menu, n):
    return [Creative(rng.choice(menu), rng.randint(1, 60), rng.random(), j) for j in range(n)]


def pod_check(n_cases=3000, seed=20261021, nmax=8):
    """Random pools of 0..nmax creatives (ties in v likely: v in 1..60), random T and cap, several menus.
    Compares select_menu, dp_select and pod_oracle for both policies. Elastic: select_elastic,
    dp_select(elastic) and elastic_oracle on small spans."""
    rng = random.Random(seed)
    menus = [(15, 30), (10, 15, 30), (6, 15, 30), (5, 15, 30), (15, 30, 60), (10, 15, 20, 30), (7, 9, 11)]
    n = 0
    for _ in range(n_cases):
        menu = rng.choice(menus)
        pool = random_pool(rng, menu, rng.randint(0, nmax))
        T = rng.randint(0, 200)
        cap = rng.choice([None, 1, 2, 3, 4, 6])
        ps, pr = select_menu(T, cap, pool)
        o_s, o_r = pod_oracle(T, cap, pool)
        d_s, d_r = dp_select(T, cap, pool)
        got_s, got_r = (ps.seconds, ps.revenue), (pr.revenue, pr.seconds)
        if not (got_s == o_s == d_s and got_r == o_r == d_r):
            raise AssertionError("pod mismatch %s %s %s %s: %s %s / %s %s / %s %s" %
                                 (menu, T, cap, pool, got_s, got_r, o_s, o_r, d_s, d_r))
        if cap is not None and (ps.n_ads > cap or pr.n_ads > cap):
            raise AssertionError("cap violated")
        if len({id(c) for c, _ in ps.items}) != ps.n_ads:
            raise AssertionError("creative reused")
        n += 1
    ne = 0
    for _ in range(n_cases // 3):
        m = rng.randint(3, 8)
        M = m + rng.randint(0, 3)
        pool = [Creative(m, rng.randint(1, 30), 0.0, j) for j in range(rng.randint(0, 5))]
        T = rng.randint(0, 40)
        cap = rng.choice([None, 1, 2, 3])
        ps, pr = select_elastic(T, cap, pool, m, M)
        o_s, o_r = elastic_oracle(T, cap, pool, m, M)
        d_s, d_r = dp_select(T, cap, pool, elastic=(m, M))
        if not ((ps.seconds, ps.revenue) == o_s == d_s and (pr.revenue, pr.seconds) == o_r == d_r):
            raise AssertionError("elastic mismatch %s %s %s %s %s" % (m, M, T, cap, pool))
        ne += 1
    return {"menu_cases": n, "elastic_cases": ne, "pool_sizes": [0, nmax], "mismatches": 0, "seed": seed}


# ------------------------------------------------------------------------------------- item7: stability

def semigroup_member(menu):
    """Membership test for <menu> independent of the DP: via engine E-C gaps after gcd reduction."""
    g = reduce(gcd, menu)
    red = sorted(set(a // g for a in menu))
    gp = set(E.engine_c.gaps(red))

    def inside(x):
        return x >= 0 and x % g == 0 and (x // g) not in gp
    return inside


def stability_check(Tlo=60, Thi=240, hmax=40):
    """For each base menu A (2- and 3-subsets of GRID) and each c in GRID not in A:
    (i) pointwise: D_h(A;T) >= T - p_A(T), equality iff h >= l_A(p_A(T)) (all h <= hmax, T in window);
    (ii) window: at every cap h >= h_stab (both menus at their limits on the window), the window total
         drops on adding c iff some T in the window has a new semigroup element in (p_A(T), T], with
         p_A and membership in <A u {c}> computed from engine E-C gaps, independent of the DP;
    (iii) pointwise at stable caps: D drops at T iff such an element exists for that T.
    Returns counts."""
    W = list(range(Tlo, Thi + 1))
    stats = dict(pairs=0, caps_checked=0, window_helps=0, window_no_help=0, pointwise_helps=0,
                 pointwise_no_help=0, helps_target_stays_gap=0, pointwise_identity_checks=0,
                 h_stab_max=0)
    bases = [c for k in (2, 3) for c in combinations(GRID, k)]
    for A in bases:
        inA = semigroup_member(A)
        p = {}
        last = None
        for x in range(0, Thi + 1):
            if inA(x):
                last = x
            p[x] = last
        mA = structural.min_parts(tuple(A), Thi)
        for h in range(1, hmax + 1):
            tab = structural.undershoot_table(tuple(A), h, Thi)
            for T in W:
                if p[T] is None:
                    continue
                lb = T - p[T]
                if tab[T] < lb or ((tab[T] == lb) != (h >= mA[p[T]])):
                    raise AssertionError("pointwise stability identity fails %s h %d T %d" % (A, h, T))
                stats["pointwise_identity_checks"] += 1
        for c in GRID:
            if c in A:
                continue
            A2 = tuple(sorted(A + (c,)))
            in2 = semigroup_member(A2)
            m2 = structural.min_parts(A2, Thi)
            p2 = {}
            last = None
            for x in range(0, Thi + 1):
                if in2(x):
                    last = x
                p2[x] = last
            if any(p[T] is None for T in W):
                raise AssertionError("no predecessor for %s" % (A,))
            h_stab = max(max(mA[p[T]] for T in W), max(m2[p2[T]] for T in W))
            stats["h_stab_max"] = max(stats["h_stab_max"], h_stab)
            stats["pairs"] += 1
            for h in range(h_stab, h_stab + 3):
                t1 = structural.undershoot_table(tuple(A), h, Thi)
                t2 = structural.undershoot_table(A2, h, Thi)
                new_el = {}
                for T in W:
                    new_el[T] = any(in2(x) for x in range(p[T] + 1, T + 1))
                    drop = t2[T] < t1[T]
                    if drop != new_el[T]:
                        raise AssertionError("pointwise criterion fails %s + %d h %d T %d" % (A, c, h, T))
                    if h == h_stab:
                        stats["pointwise_helps" if drop else "pointwise_no_help"] += 1
                tot_drop = xsum(t2[T] for T in W) < xsum(t1[T] for T in W)
                crit = any(new_el.values())
                if tot_drop != crit:
                    raise AssertionError("window criterion fails %s + %d h %d" % (A, c, h))
                stats["caps_checked"] += 1
                if h == h_stab:
                    stats["window_helps" if tot_drop else "window_no_help"] += 1
                    if tot_drop and any(new_el[T] and not in2(T) for T in W):
                        stats["helps_target_stays_gap"] += 1
    stats["note"] = ("helps_target_stays_gap counts (A, c) pairs where at least one target T is helped "
                     "although T itself stays outside <A u {c}> (the Proposition 2 case: a new predecessor, "
                     "not a filled target)")
    return stats


def stability_examples():
    """Example 3 on reduced sets, as stated in Appendix A of the paper."""
    out = {}
    out["{0,4,7} W={6}: base"] = [structural.D((4, 7), h, 6) for h in range(1, 5)]
    out["{0,4,7} W={6}: add 5"] = [structural.D((4, 5, 7), h, 6) for h in range(1, 5)]
    out["{0,4,7} W={6}: add 3"] = [structural.D((3, 4, 7), h, 6) for h in range(1, 5)]
    out["{0,2,9} W={10}"] = [structural.D((2, 9), h, 10) for h in range(1, 8)]
    exp = {"{0,4,7} W={6}: base": [2, 2, 2, 2], "{0,4,7} W={6}: add 5": [1, 1, 1, 1],
           "{0,4,7} W={6}: add 3": [2, 0, 0, 0], "{0,2,9} W={10}": [1, 1, 1, 1, 0, 0, 0]}
    for k in exp:
        if out[k] != exp[k]:
            raise AssertionError("Example 3 %s: %s != %s" % (k, out[k], exp[k]))
    return out


# ------------------------------------------------------------------------------------- item8: non-CM tau

def conductor(gens):
    gens = sorted(set(gens))
    if 1 in gens:
        return 0
    return E.engine_c.frobenius(gens) + 1


def tau_check(Hmax=None):
    """Every 3-part menu from GRID, gcd-reduced to A0 = {0,a,b,d}. Direct sumsets (E-A) against
    I_h = {x in [0,hd]: x in <A>, hd - x in <d - A>} for h = 1..Hmax (default 3d + 10); tau = 1 + the
    last failing h (1 if none). Checks: CM status by direct comparison equals engine E-B's Apery test;
    non-CM implies (tau - 1) d >= c1 + c2 + d (the non-CM bound of the regularity companion), equality iff {0, b-1, b+1, 2b}, b even;
    the last failing level is well below Hmax (so tau is not truncated)."""
    rows = []
    for menu in combinations(GRID, 3):
        g, A0 = E.common.normalize(menu)
        a, b, d = A0[1], A0[2], A0[3]
        pos = [a, b, d]
        c1 = conductor(pos)
        c2 = conductor(E.engine_c.reflected_generators(A0))
        H = Hmax or (3 * d + 10)
        G1 = set(E.engine_c.gaps(pos))
        G2 = set(E.engine_c.gaps(E.engine_c.reflected_generators(A0)))
        ser = E.engine_a.sumset_series(A0, H)
        fails = []
        for h in range(1, H + 1):
            N = h * d
            I = 0
            for x in range(N + 1):
                if x not in G1 and (N - x) not in G2:
                    I |= 1 << x
            if ser[h] != I:
                fails.append(h)
        tau = (max(fails) + 1) if fails else 1
        cm_direct = not fails
        cm_b = E.engine_b.is_cm(A0)
        if cm_direct != cm_b:
            raise AssertionError("CM status disagrees for %s" % (menu,))
        if fails and max(fails) > H - d:
            raise AssertionError("tau may be truncated for %s" % (menu,))
        row = dict(menu=menu, A0=A0, g=g, cm=cm_direct, tau=tau, c1=c1, c2=c2, d=d, failing=fails)
        if not cm_direct:
            lhs = (tau - 1) * d
            rhs = c1 + c2 + d
            fam = E.fan.is_family(a, b, d)
            if lhs < rhs:
                raise AssertionError("regularity-companion non-CM bound fails for %s: %d < %d" % (menu, lhs, rhs))
            if (lhs == rhs) != fam:
                raise AssertionError("regularity-companion equality case fails for %s" % (menu,))
            row.update(lhs=lhs, rhs=rhs, equality=(lhs == rhs), family=fam,
                       bound_tau=1 + (c1 + c2 + d) / d)
            # fan regularity cross-check (undershoot engines fan.py, BGM Thm 2.8): reg(I) for non-CM sets
            try:
                F = E.fan.fan(a, b, d)
                row["fan_reg"] = E.fan.reg_ideal(F)[0]
            except Exception as e:  # pragma: no cover
                row["fan_reg"] = "error: %s" % e
        rows.append(row)
    return rows
