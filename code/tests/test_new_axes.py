"""Tests for the full-tier axes: L8, the law families H2 and H3 (laws.py), D3/D4 (exact.py, demand.py), R2 (demand.py),
the 31-menu sample (registry.py), X4 lattice table, X5 targets for new laws, and run_xd.py.
Run from code/: python3 -m unittest -q tests.test_new_axes"""
import math
import os
import random
import sys
import unittest
from fractions import Fraction as Q
from functools import reduce
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim import laws, structural, exact, demand, grid, levers, pools, registry as REG  # noqa: E402
from podsim.exact import NegBinMeans  # noqa: E402
import run_x4  # noqa: E402
import run_x5  # noqa: E402
import run_xd  # noqa: E402


def nb_pmf(n, mean, k):
    p = k / (k + mean)
    return math.exp(math.lgamma(n + k) - math.lgamma(k) - math.lgamma(n + 1) + k * math.log(p) + n * math.log(1 - p))


def brute_fill(T, cap, counts):
    """Max seconds <= T with at most cap creatives, c_a <= counts[a] (dict a -> count)."""
    durs = sorted(counts)
    best = 0
    for cs in product(*[range(counts[a] + 1) for a in durs]):
        sec = sum(c * a for c, a in zip(cs, durs))
        if sec <= T and (cap is None or sum(cs) <= cap) and sec > best:
            best = sec
    return best


class TestNewLaws(unittest.TestCase):
    def test_all_new_laws_are_pmfs(self):
        for name in laws.NEW_LAWS:
            law = laws.named(name)
            self.assertEqual(sum(w for _, w in law.support), 1, name)
            self.assertTrue(all(T >= 0 for (T, _), _ in law.support), name)

    def test_l8_mixture(self):
        for name, q in laws.L8_Q.items():
            law = laws.named(name)
            grid_pts = set(range(60, 241, 30))
            p_grid = sum(w for (T, _), w in law.support if T in grid_pts)
            # grid mass (1 - q) plus the stoppage law's mass on the grid points inside [30, 120] (60, 90, 120)
            self.assertEqual(p_grid, (1 - q) + q * Q(3, 91))
            self.assertEqual(sum(w for (T, _), w in law.support if T < 60), q * Q(30, 91))
            self.assertTrue(all(st is False for (T, st), _ in law.support))

    def test_h2_sets(self):
        for name, sset in laws.H2_SETS.items():
            law = laws.named(name)
            exp = {}
            for b in range(60, 241, 30):
                for s in sset:
                    exp[(b - s, True)] = exp.get((b - s, True), Q(0)) + Q(1, 7 * len(sset))
            self.assertEqual(dict(law.support), exp, name)

    def test_h3_two_spots(self):
        law = laws.named("L2two")
        self.assertTrue(all(st == 2 for (T, st), _ in law.support))
        # B = 60: pairs with S1 + S2 <= 60 among {5,10,15,20,45}^2: 20 of 25 small pairs plus (5,45),(10,45),(15,45),
        # (45,5),(45,10),(45,15): count them directly and check the mass of T = 0 (S1 + S2 = 60 at B = 60)
        S = laws.S_SPOTS
        p0 = sum(w for (T, st), w in law.support if T == 0)
        exp0 = Q(0)
        for b in range(60, 241, 30):
            ok = [(x, y) for x in S for y in S if x + y <= b]
            exp0 += Q(1, 7) * Q(sum(1 for x, y in ok if x + y == b), len(ok))
        self.assertEqual(p0, exp0)
        ET = sum(w * T for (T, _), w in law.support)
        direct = Q(0)
        for b in range(60, 241, 30):
            ok = [(x, y) for x in S for y in S if x + y <= b]
            direct += Q(1, 7) * sum(Q(b - x - y, len(ok)) for x, y in ok)
        self.assertEqual(ET, direct)

    def test_two_spot_caps(self):
        self.assertEqual(laws.dynamic_cap(6, 2, "b"), 4)
        self.assertEqual(laws.dynamic_cap(6, 2, "a"), 6)
        self.assertEqual(laws.dynamic_cap(1, 2, "b"), 0)
        self.assertEqual(laws.dynamic_cap(None, 2, "b"), None)
        self.assertEqual(laws.dynamic_cap(6, True, "b"), 5)
        with self.assertRaises(ValueError):
            laws.dynamic_cap(6, 1, "c")

    def test_unknown_law(self):
        with self.assertRaises(KeyError):
            laws.named("L99")

    def test_law_parts_refuses_two_spots(self):
        with self.assertRaises(ValueError):
            levers.law_parts(laws.named("L2two"))
        wu, ws = levers.law_parts(laws.named("L2s60"))
        self.assertAlmostEqual(sum(ws), 1.0)
        self.assertAlmostEqual(sum(wu), 0.0)

    def test_x4_lattice_table(self):
        for name, g in run_x4.LATTICE.items():
            law = laws.named(name) if name != "L1" else laws.Law.plain("L1", laws.L1())
            pts = [T for (T, _), _ in law.support if T > 0]
            self.assertEqual(reduce(math.gcd, pts), g, name)
        for l, _ in REG.FULL_LAWS:
            self.assertIn(l, run_x4.LATTICE)


class TestExactNewLaws(unittest.TestCase):
    def test_two_spot_grid_vs_combos(self):
        """grid.menu_values (dense parts by spot count) agrees with exact.combos_for (per support point) on H3 and
        an H2 set, both conventions, demand limited and unlimited. Caps from 4 so every dynamic cap is at least 2
        (the reference tabulates caps 2 to 12)."""
        w = pools.weights("balanced")
        ml = [{a: 8 * w[a] for a in pools.UNION}, NegBinMeans({a: 16 * w[a] for a in pools.UNION}, 1)]
        for name in ("L2two", "L2s7812"):
            law = laws.named(name)
            for conv in ("a", "b"):
                vals = grid.menu_values((15, 30), {name: law}, [(name, conv)], [4, 6, None], ml)
                ref = exact.combos_for((15, 30), law, conv, [4, 6, None], ml + [None])
                for h in (4, 6, None):
                    for si in range(3):
                        a = vals[(name, conv, h, si)]["U"]
                        b = ref[(si, h)]["U"]
                        for S in b:
                            self.assertAlmostEqual(float(a[S]), float(b[S]), places=9, msg=(name, conv, h, si, S))

    def test_two_spot_structural_direct(self):
        law = laws.named("L2two")
        for h in (3, 4, 6):
            v = grid.menu_values((15, 30), {"L2two": law}, [("L2two", "b")], [h], [])[("L2two", "b", h, 0)]
            direct = sum((w * structural.D((15, 30), h - 2, T) for (T, st), w in law.support), Q(0))
            self.assertEqual(v["U"][frozenset(["dem"])], direct)


class TestNegBin(unittest.TestCase):
    def test_nb_trunc(self):
        for mean, k in ((0.5, 1), (3.0, 4), (12.0, 1)):
            p = exact.nb_trunc(mean, k, 40)
            self.assertAlmostEqual(sum(p), 1.0, places=12)
            for n in range(10):
                self.assertAlmostEqual(p[n], nb_pmf(n, mean, k), places=12)
        self.assertEqual(exact.nb_trunc(0.0, 1, 5), [1.0, 0, 0, 0, 0, 0])
        with self.assertRaises(ValueError):
            exact.nb_trunc(1.0, 0, 5)
        with self.assertRaises(ValueError):
            NegBinMeans({5: 1.0}, -1)

    def test_nb_large_k_is_poisson(self):
        a = exact.nb_trunc(4.0, 1e7, 30)
        b = exact.poisson_trunc(4.0, 30)
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=6)

    def test_total_trunc_convolution(self):
        m = NegBinMeans({15: 2.0, 30: 5.0}, 4)
        top = 16
        got = exact.total_trunc(m, (15, 30), top)
        ref = [0.0] * (top + 1)
        for i in range(200):
            for j in range(200):
                ref[min(top, i + j)] += nb_pmf(i, 2.0, 4) * nb_pmf(j, 5.0, 4)
        for x, y in zip(got, ref):
            self.assertAlmostEqual(x, y, places=10)

    def test_menu_expect_nb_against_brute(self):
        """Exact E[U] under negative binomial counts equals a brute sum over count vectors with an
        independent pmf (lgamma) and brute-force fill."""
        means = NegBinMeans({15: 1.5, 30: 3.0}, 1)
        law = laws.Law.plain("t", [(t, Q(1, 4)) for t in (40, 52, 75, 90)])
        me = levers.MenuExpect((15, 30), [means], {"t": law}, caps=[3])
        top = 300
        for cap in (3, None):
            tot = 0.0
            for c15 in range(top):
                p15 = nb_pmf(c15, 1.5, 1)
                if p15 < 1e-18:
                    break
                for c30 in range(top):
                    p30 = nb_pmf(c30, 3.0, 1)
                    if p30 < 1e-18:
                        break
                    cc = {15: min(c15, 6), 30: min(c30, 3)}
                    for (T, _), w in law.support:
                        tot += p15 * p30 * float(w) * (T - brute_fill(T, cap, cc))
            self.assertAlmostEqual(me.U("t", "a", cap, 0), tot, places=7)

    def test_pickle(self):
        import pickle
        m = NegBinMeans({5: 1.0}, 4)
        m2 = pickle.loads(pickle.dumps(m))
        self.assertEqual(m2.k, 4)
        self.assertEqual(dict(m2), {5: 1.0})


class TestDemandSweep(unittest.TestCase):
    def test_scenarios(self):
        sc = demand.scenarios()
        self.assertEqual(len(sc), 5 * 9 * 3)
        self.assertEqual(len({s[0] for s in sc}), len(sc))
        self.assertEqual(demand.D3_LAMS, tuple(2 ** i for i in range(9)))

    def test_r2_closed_form(self):
        self.assertAlmostEqual(demand.rho_eff(0.25, 0.8, 1.0), 0.95)
        for s, rn, ro, rho in demand.r2_configs():
            self.assertLessEqual(rho, ro)
            self.assertGreaterEqual(rho, rn)
        pod = [30, 15, 15, 10]
        T = 75
        n = 60000
        mc = demand.sampled_check(pod, T, 0.3, 0.6, 0.98, n)
        cf = T - demand.rho_eff(0.3, 0.6, 0.98) * sum(pod)
        sd = math.sqrt(sum(d * d for d in pod) * 0.25 / n)
        self.assertLess(abs(mc - cf), 4 * sd)
        with self.assertRaises(ValueError):
            demand.rho_eff(0.5, 0.99, 0.9)
        with self.assertRaises(ValueError):
            demand.rho_eff(1.5, 0.5, 0.9)

    def test_xd_menu_job_consistent_with_x1(self):
        """run_xd rows at Poisson counts equal the X1 grid values (same exact routine) and the identity holds."""
        cfg = dict(REG.config("quick"))
        cfg.update(xd_laws=[("L3u", "a"), ("L2two", "b")], xd_caps=[3, None], xd_schemes=("balanced",),
                   xd_lams=(8,), xd_ks=(1,), xd_r2_scen=[("poisson", "balanced", 8)])
        res = run_xd.menu_job(((15, 30), cfg))
        w = pools.weights("balanced")
        LD = {"L3u": laws.named("L3u"), "L2two": laws.named("L2two")}
        ref = grid.menu_values((15, 30), LD, cfg["xd_laws"], [3, None], [{a: 8 * w[a] for a in pools.UNION}])
        for r in res["rows"]:
            if r["count_law"] == "poisson":
                h = None if r["h"] == "none" else r["h"]
                U = ref[(r["law"], r["conv"], h, 0)]["U"]
                self.assertAlmostEqual(r["U"], float(U[frozenset()]), places=8)
                self.assertAlmostEqual(r["Ustruct"] + r["demand_part"], r["U"], places=8)
                self.assertAlmostEqual(r["arith_part"] + r["cap_part"] + r["range_residual"], r["Ustruct"], places=8)
                self.assertGreaterEqual(r["demand_part"], -1e-9)
        self.assertEqual(len(res["r2"]), 2 * 2 * len(demand.r2_configs()))
        for r in res["r2"]:
            self.assertGreaterEqual(r["ready_part"], -1e-9)
            self.assertAlmostEqual(r["Ustruct"] + r["demand_part"] + r["ready_part"], r["U"], places=8)


class TestSplitStreaming(unittest.TestCase):
    def test_grouped_equals_whole(self):
        """run_x2_split per-menu grouping gives the same rows as one pass over the whole table."""
        import tempfile
        import run_x2_split as SP
        rows = []
        for m in ("15 30", "6 15 30"):
            for lam, wts in (("unlimited", "unlimited"), (8, "balanced"), (64, "d1530")):
                for h in (3, "none"):
                    rows.append(dict(law="L1", conv="a", menu=m, h=h, weights=wts, lam=lam, rho=1.0,
                                     dur_best=(0.5 if lam == 8 else 0.0), **{"cap+1": (1.0 if h == 3 else None),
                                                                            "range": 2.0, "dur:5": 0.5}, split_winners="range"))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            REG.write_csv(p, rows, list(rows[0].keys()))
            agg1, agg2 = {}, {}
            whole = SP.split_rows(REG.read_csv(p), agg1)
            grouped = [r for g in SP.iter_menu_groups(p) for r in SP.split_rows(g, agg2)]
        self.assertEqual(whole, grouped)
        self.assertEqual(agg1, agg2)
        self.assertEqual(len(whole), 8)


class TestMenuSample(unittest.TestCase):
    def test_sample(self):
        ms = REG.menu_sample()
        self.assertEqual(len(ms), 31)
        self.assertEqual(ms[:7], list(REG.M7))
        self.assertEqual(len(set(ms)), 31)
        m85 = set(REG.m85())
        self.assertTrue(all(m in m85 for m in ms[7:]))
        self.assertEqual(ms, REG.menu_sample())


class TestX5NewLaws(unittest.TestCase):
    def test_targets_follow_laws(self):
        for name in ("L2s7812", "L8q50", "L2two", "L7"):
            law = laws.named(name)
            sup = {k for k, _ in law.support}
            for i in range(200):
                B, T, st = run_x5.draw_target(name, i)
                self.assertIn((T, st), sup)
                if st is True:
                    self.assertIn(B - T, laws.H2_SETS.get(name, laws.S_SPOTS))

    def test_l2_and_l3u_unchanged(self):
        """The narrow-tier streams are untouched: L2 and L3u targets as before (fixed seeds)."""
        rng = random.Random("%s|break|%s|%d" % (run_x5.MASTER, "L2", 5))
        B = run_x5.L1PTS[rng.randrange(7)]
        S = laws.S_SPOTS[rng.randrange(5)]
        self.assertEqual(run_x5.draw_target("L2", 5), (B, B - S, True))
        rng = random.Random("%s|break|%s|%d" % (run_x5.MASTER, "L3u", 9))
        T = 60 + rng.randrange(181)
        self.assertEqual(run_x5.draw_target("L3u", 9), (T, T, False))

    def test_full_grid_contrasts(self):
        saved = run_x5.GRID_TIER
        try:
            run_x5.configure("full")
            self.assertIn(None, run_x5.CAPS_ALL)
            self.assertEqual(run_x5.CAPS_ALL[-1], None)
            self.assertNotIn(None, run_x5.HULL_CAPS)
            self.assertEqual(len(run_x5.MENUS), 31)
            for name, h, x, y in run_x5.CONTRASTS:
                if h is None:
                    self.assertEqual(name, "menu_vs_base_same_h")
        finally:
            run_x5.configure(saved)
        with self.assertRaises(SystemExit):
            run_x5.configure("bogus")


class TestLeverCandidates(unittest.TestCase):
    """Review fix: the add-duration lever tries every union duration not on the menu, at every tier that runs X2
    over all menus; a menu without 15 and 30 s must be offered both."""

    def test_x2_add_is_union(self):
        from podsim import registry as REG, pools
        for tier in ("quick", "narrow", "full"):
            self.assertEqual(tuple(REG.TIERS[tier]["x2_add"]), tuple(pools.UNION), tier)

    def test_menu_without_15_30_gets_both(self):
        from podsim import registry as REG
        menu = (10, 20, 45)
        add = [c for c in REG.TIERS["full"]["x2_add"] if c not in menu]
        self.assertIn(15, add)
        self.assertIn(30, add)

    def test_split_tie_rule_and_label(self):
        import run_x2_split as SP
        # range within two standard errors of the top ties with it; nothing positive gives no winner
        self.assertEqual(SP.tied_winners({"dur_best": (3.0, 0.0), "cap+1": (1.0, 1.0), "range": (2.5, 0.0)}, 0.5),
                         ["dur_best", "range"])
        self.assertEqual(SP.tied_winners({"cap+1": (0.0, 0.0)}, 0.0), [])
        # a lever that gains nothing is never a winner, even when a noisy sampled gain does not clearly beat it
        self.assertEqual(SP.tied_winners({"cap+1": (0.0, 0.0), "range": (1e-6, 0.0)}, 1e-3), ["range"])


class TestCapBeyond(unittest.TestCase):
    """The cap's loss beyond both lower bounds is zero once the cap is sufficient ({15, 30}, L3u, h = 8)."""

    def test_sufficient_cap_costs_nothing(self):
        import analysis_rules as AR
        import run_x1
        law = run_x1.law_obj("L3u")
        self.assertEqual(AR.cap_beyond((15, 30), law, "a", 8), 0)
        self.assertGreater(AR.cap_beyond((15, 30), law, "a", 3), -1e-12)


if __name__ == "__main__":
    unittest.main()
