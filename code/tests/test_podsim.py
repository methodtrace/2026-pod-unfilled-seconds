import os
import random
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim import structural, x0, checks, laws, pools, decompose, scenario  # noqa: E402
from podsim import engines as E  # noqa: E402
from podsim.pod import Creative, select_menu, select_elastic, dp_select, pod_oracle  # noqa: E402



def _read(path, mode="r"):
    with open(path, mode) as f:
        return f.read()

class TestEngines(unittest.TestCase):
    def test_pinned_hashes(self):
        pins = E.pinned_hashes()
        for p, h in E.HASHES.items():
            self.assertEqual(pins[p], h)


class TestStructural(unittest.TestCase):
    def test_crosscheck_all_menus(self):
        r = structural.crosscheck()
        self.assertEqual(r["mismatches"], 0)
        self.assertGreaterEqual(r["menus"], 57)

    def test_uncapped_and_zero(self):
        self.assertEqual(structural.D((15, 30), None, 52), 7)
        self.assertEqual(structural.D((15, 30), 0, 52), 52)
        self.assertEqual(structural.D((6, 15, 30), None, 7), 1)

    def test_range_menu_fills_above_min(self):
        # max A >= 2 min A - 1: every T >= min A is filled exactly when uncapped
        for A in [(15, 30), (6, 15, 30), (10, 15, 30)]:
            R = structural.range_menu(A)
            for T in range(min(A), 300):
                self.assertEqual(structural.D(R, None, T), 0)


class TestX0(unittest.TestCase):
    def test_reference_check_1(self):
        for menu, cells in x0.reference_check_1():
            for c in cells:
                self.assertTrue(c["match"], (menu, c))

    def test_reference_check_2(self):
        for r in x0.reference_check_2():
            self.assertTrue(r["match"], r)


class TestPod(unittest.TestCase):
    def test_against_oracle(self):
        r = checks.pod_check(n_cases=800, seed=7)
        self.assertEqual(r["mismatches"], 0)

    def test_revenue_policy_can_leave_seconds(self):
        # a full 30 s pod of one cheap creative against a 20 s pod of one expensive creative, T = 30, cap 1:
        # seconds-max fills 30 s, revenue-max takes 20 s at higher revenue (the two policies differ)
        pool = [Creative(30, 1), Creative(20, 50), Creative(10, 2)]
        ps, pr = select_menu(30, 1, pool)
        self.assertEqual(ps.seconds, 30)
        self.assertEqual(pr.seconds, 20)
        self.assertGreater(pr.revenue, ps.revenue)
        self.assertEqual((ps.seconds, ps.revenue), dp_select(30, 1, pool)[0])
        self.assertEqual((pr.revenue, pr.seconds), dp_select(30, 1, pool)[1])

    def test_readiness(self):
        pool = [Creative(15, 5, 0.97), Creative(30, 5, 0.10)]
        ps, _ = select_menu(45, None, pool)
        self.assertEqual(ps.ready_seconds(1.0), 45)
        self.assertEqual(ps.ready_seconds(0.95), 30)


class TestLaws(unittest.TestCase):
    def test_weights(self):
        for name in ("L1", "L2", "L3u", "L3s", "L4u5", "L4u15", "L4s5", "L4s15"):
            law = laws.named(name)
            self.assertEqual(sum(w for _, w in law.support), 1)
        l3s = laws.L3s()
        mean = sum(t * w for t, w in l3s)
        self.assertTrue(105 < mean < 120)

    def test_hybrid_p(self):
        law = laws.Law.hybrid("x", laws.L1(), (5, 10), Fraction(1, 2))
        tot_struct = sum(w for (t, s), w in law.support if s)
        self.assertEqual(tot_struct, Fraction(1, 2))

    def test_conventions(self):
        self.assertEqual(laws.dynamic_cap(6, True, "a"), 6)
        self.assertEqual(laws.dynamic_cap(6, True, "b"), 5)
        self.assertEqual(laws.dynamic_cap(6, False, "b"), 6)


class TestPools(unittest.TestCase):
    def test_poisson_mean(self):
        rng = random.Random(1)
        for lam in (0.5, 3.0, 45.0):
            xs = [pools.poisson(rng, lam) for _ in range(20000)]
            m = sum(xs) / len(xs)
            self.assertLess(abs(m - lam), 4 * (lam / len(xs)) ** 0.5 + 0.02)

    def test_crn_shared_across_menus(self):
        v = pools.ValueLaw()
        a1 = pools.duration_stream("m", 3, 15, 4.0, 48, v)
        a2 = pools.duration_stream("m", 3, 15, 4.0, 48, v)
        self.assertEqual([c.v for c in a1[0]], [c.v for c in a2[0]])
        self.assertEqual([c.u for c in a1[1]], [c.u for c in a2[1]])

    def test_floor(self):
        v = pools.ValueLaw(floor=80)
        pool, extras = pools.duration_stream("m", 0, 30, 50.0, 48, v)
        self.assertTrue(all(c.v >= 80 for c in pool + extras))


class TestDecompose(unittest.TestCase):
    def test_struct_split_is_two_player_shapley(self):
        rng = random.Random(3)
        for _ in range(50):
            V = {S: rng.random() * 10 for S in decompose.subsets(("arith", "cap"))}
            sp = decompose.struct_split(V[frozenset()], V[frozenset(["arith"])], V[frozenset(["cap"])],
                                        V[frozenset(["arith", "cap"])])
            phi = decompose.shapley(V, ("arith", "cap"))
            self.assertAlmostEqual(sp["arith"], phi["arith"])
            self.assertAlmostEqual(sp["cap"], phi["cap"])
            self.assertAlmostEqual(sp["arith"] + sp["cap"] + sp["residual"], V[frozenset()])

    def test_block_runs_and_struct_assert(self):
        stats, _ = scenario.run_block("t", laws.named("L2"), (6, 15, 30), 8, "balanced", [4, 6], [1.0, 0.95],
                                      "b", 60)
        for rho in (1.0, 0.95):
            s = stats[(6, rho)]
            self.assertAlmostEqual(s.mean("arith") + s.mean("cap") + s.mean("residual"), s.mean("Ustruct"))
            self.assertAlmostEqual(s.mean("Ustruct") + s.mean("demand") + s.mean("readiness"), s.mean("U"))
            self.assertGreaterEqual(min(s.mean("demand"), s.mean("readiness")), 0.0)

    def test_saturated_equals_struct(self):
        stats, _ = scenario.run_block("t", laws.named("L3u"), (10, 15, 30), 1000, "balanced", [4], [1.0], "a", 40)
        s = stats[(4, 1.0)]
        self.assertAlmostEqual(s.mean("U"), s.mean("Ustruct"))


class TestExact(unittest.TestCase):
    def test_profiles_match_pod_selection(self):
        from podsim import exact
        rng = random.Random(11)
        for menu in [(15, 30), (6, 15, 30), (10, 15, 20, 30)]:
            prof = exact.MenuProfiles(menu)
            for _ in range(150):
                counts = tuple(rng.randint(0, top) for top in prof.tops)
                pool = [Creative(a, rng.randint(1, 50), 0.0) for a, c in zip(prof.menu, counts) for _ in range(c)]
                tab = prof.tables[prof.profile_of[counts]]
                T = rng.randint(0, 240)
                cap = rng.choice([None, 2, 3, 5, 8, 12])
                ps, _ = select_menu(T, cap, pool)
                self.assertEqual(T - ps.seconds, tab[cap][T])
                # elastic pod depends only on the total count
                pe, _ = select_elastic(T, cap, pool, min(menu), max(menu))
                K = len(pool) if cap is None else min(cap, len(pool))
                self.assertEqual(T - pe.seconds, exact.elastic_U(T, K, min(menu), max(menu)))

    def test_unlimited_is_struct_and_linear_in_p(self):
        from podsim import exact
        lawp = lambda p: laws.Law.hybrid("x", laws.L1(), laws.S_SPOTS, p)
        vals = {}
        for p in (Fraction(0), Fraction(1, 2), Fraction(1)):
            r = exact.combos_for((6, 15, 30), lawp(p), "b", [6], [None])
            vals[p] = r[(0, 6)]["U"][frozenset()]
        self.assertEqual(vals[Fraction(1, 2)], (vals[Fraction(0)] + vals[Fraction(1)]) / 2)

    def test_reference_cell_via_exact(self):
        from podsim import exact
        law = laws.Law.hybrid("p1", laws.L1(60, 180, 30), laws.S_SPOTS, 1)
        r = exact.combos_for((10, 15, 30), law, "a", [6], [None])
        self.assertEqual(r[(0, 6)]["U"][frozenset()], Fraction(3, 5))  # X0 reference check 1: 0.60 s


class TestLevers(unittest.TestCase):
    def test_forward_dp_matches_combos(self):
        from podsim import exact
        w = pools.weights("d1530")
        ml = [{a: lam * w[a] for a in pools.UNION} for lam in (2, 16)]
        law = laws.named("L2")
        ref = exact.combos_for((6, 15, 30), law, "b", [3, 6, None], ml)
        fast = exact.expect_table((6, 15, 30), law, "b", [3, 6, None], ml)
        for s in range(2):
            for h in (3, 6, None):
                self.assertAlmostEqual(ref[(s, h)]["U"][frozenset()], fast[(s, h)]["none"], places=9)

    def test_menu_expect_and_paired_gain(self):
        from podsim import levers, exact
        w = pools.weights("balanced")
        ml = [{a: 8 * w[a] for a in pools.UNION}]
        LD = {"L3u": laws.named("L3u")}
        me = levers.MenuExpect((15, 30), ml, LD)
        me2 = levers.MenuExpect((10, 15, 30), ml, LD)
        ref = exact.combos_for((15, 30), LD["L3u"], "a", [6], ml)[(0, 6)]["U"][frozenset()]
        self.assertAlmostEqual(me.U("L3u", "a", 6, 0), ref, places=9)
        self.assertGreaterEqual(me.U("L3u", "a", 6, 0) - me2.U("L3u", "a", 6, 0), 0)

    def test_stability_assert(self):
        from podsim import levers
        ns, nt, allst, ng = levers.stability_assert((15, 30), 10, laws.named("L2"), "a", None)
        self.assertTrue(allst)
        self.assertGreater(ng, 0)


class TestTicks(unittest.TestCase):
    def test_zero_eps_is_integer_plus_offset(self):
        from podsim import ticks
        law = laws.Law.plain("x", laws.L3u(60, 90))
        r = ticks.exact_sys_unlimited((15, 30), "sys+", 0, 0, law, [3, None], "a")
        for h in (3, None):
            ed = sum((w * structural.D((15, 30), h, T) for (T, s), w in law.support), Fraction(0))
            self.assertEqual(r[h][0], ed + Fraction(89999, 180000))
            self.assertEqual(r[h][1], 0)

    def test_offset_mean_bruteforce(self):
        from podsim import ticks
        rng = random.Random(5)
        for _ in range(20):
            T = rng.randint(1, 3)
            tol = rng.choice([0, 500, 3003])
            fs = sorted({0} | {rng.randint(0, 90000 * (T + 1) + tol) for _ in range(6)})
            got = ticks.mean_unfilled_over_offset(T, fs, tol)
            tu = to = 0
            for o in range(0, 90000, 1):
                g = max(f for f in fs if f <= 90000 * T + o + tol)
                d = 90000 * T + o - g
                tu += max(d, 0)
                to += max(-d, 0)
            self.assertEqual(got, (Fraction(tu, 90000 ** 2), Fraction(to, 90000 ** 2)))

    def test_select_ticks_bruteforce(self):
        from itertools import combinations
        from podsim import ticks
        rng = random.Random(9)
        for _ in range(200):
            menu = (15, 30)
            by = {a: sorted([90000 * a + rng.randint(-3000, 3000) for _ in range(rng.randint(0, 3))], key=lambda x: 0)
                  for a in menu}
            Tt = rng.randint(0, 100) * 90000 + rng.randint(0, 89999)
            cap = rng.choice([None, 1, 2, 3])
            got = ticks.select_ticks(Tt, cap, by, menu)
            # brute force over prefix counts (bid order within a duration)
            best = 0
            for c1 in range(len(by[15]) + 1):
                for c2 in range(len(by[30]) + 1):
                    if cap is not None and c1 + c2 > cap:
                        continue
                    f = sum(by[15][:c1]) + sum(by[30][:c2])
                    if f <= Tt:
                        best = max(best, f)
            self.assertEqual(got, best)


class TestRegistry(unittest.TestCase):
    def test_catalog_and_tiers(self):
        from podsim import registry as REG
        ids = [a[1] for a in REG.AXES]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(REG.m85()), 85)
        for t in REG.TIERS:
            c = REG.config(t)
            for l, conv in c["laws"]:
                self.assertIn(conv, ("a", "b"))
        self.assertEqual(len(REG.config("full")["menus"]), 86)

    def test_canon_and_csv(self):
        import tempfile
        from podsim import registry as REG
        self.assertEqual(REG.canon(-0.0), 0.0)
        self.assertEqual(REG.canon(Fraction(1, 3)), "1/3")
        self.assertEqual(REG.cell(0.1 + 0.2), "0.3")
        d = tempfile.mkdtemp()
        rows = [dict(a=1, b=0.5, c=None, d="x"), dict(a=2, b=1e-12, c=Fraction(2, 3), d="y")]
        for name in ("t.csv", "t.csv.gz"):
            p = os.path.join(d, name)
            REG.write_csv(p, rows)
            h1 = _read(p, "rb")
            REG.write_csv(p, rows)
            self.assertEqual(h1, _read(p, "rb"))
            back = REG.read_csv(p)
            self.assertEqual(back[0]["a"], 1)
            self.assertEqual(back[1]["b"], 0)
            self.assertEqual(back[1]["c"], "2/3")

    def test_new_laws(self):
        l5 = laws.named("L5")
        self.assertEqual(sum(w for _, w in l5.support), 1)
        top = sum((w for (t, s), w in l5.support if t >= 240), Fraction(0))
        self.assertEqual(top, Fraction(24, 100))
        self.assertEqual(laws.named("L7").Tmax, 360)
        self.assertEqual(min(t for (t, s), _ in laws.named("L6").support), 15)

    def test_grid_matches_combos(self):
        from podsim import grid, exact
        w = pools.weights("w15")
        ml = [{a: 4 * w[a] for a in pools.UNION}]
        LD = {"L2": laws.named("L2")}
        g = grid.menu_values((10, 15, 30), LD, [("L2", "b")], [1, 3, 5, None], ml)
        ref = exact.combos_for((10, 15, 30), LD["L2"], "b", [3, 5, None], ml + [None])  # its tables cover caps 2..12
        # h = 1 under convention b leaves the remainder no ads: U = E[T] for every non-arith combo
        ET = sum((w * T for (T, s), w in LD["L2"].support), Fraction(0))
        self.assertEqual(g[("L2", "b", 1, 1)]["U"][frozenset(["dem"])], ET)
        for si in (0, 1):
            for h in (3, 5, None):
                for k, v in ref[(si, h)]["U"].items():
                    self.assertAlmostEqual(float(v), float(g[("L2", "b", h, si)]["U"][k]), places=9)


class TestStructuralChecks(unittest.TestCase):
    def test_stability(self):
        checks.stability_examples()
        r = checks.stability_check()
        self.assertEqual(r["pairs"], 448)

    def test_tau(self):
        rows = checks.tau_check()
        self.assertEqual(len(rows), 56)
        self.assertEqual(sum(1 for r in rows if not r["cm"]), 9)


if __name__ == "__main__":
    unittest.main()
