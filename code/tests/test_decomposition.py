"""Accounting-identity decomposition (podsim/decompose.py) and the eligibility range lever (podsim/eligibility.py).

Agreement with Shapley decompositions over relaxation channels where the two must agree: the structural part is
E[D_h(A;T)]; the readiness part equals a four-channel decomposition's readiness marginal at the empty coalition,
U(rho) - U(rho = 1) = (1 - rho) E[F_n]; at unlimited demand a three-channel Shapley over {arith, cap, dem} has a
dummy demand player, so its arithmetic and cap shares equal the two-player split.
"""
import os
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim import decompose, eligibility, exact, grid, laws, levers, pools, structural  # noqa: E402
from podsim.exact import NegBinMeans  # noqa: E402

N = frozenset


def means(scheme, lam):
    w = pools.weights(scheme)
    return {a: lam * w[a] for a in pools.UNION}


class TestIdentity(unittest.TestCase):
    def test_parts_sum_and_sign_on_exact_tables(self):
        LD = {"L2": laws.named("L2"), "L3u": laws.named("L3u")}
        ml = [means("balanced", 2), means("d1530", 16), NegBinMeans(means("w30", 8), 1)]
        for menu in [(15, 30), (6, 15, 30), (10, 15, 20, 30)]:
            vals = grid.menu_values(menu, LD, [("L2", "b"), ("L3u", "a")], [3, 6, None], ml)
            for (l, c, h, s), r in vals.items():
                U, ET = r["U"], r["ET"]
                us = U[N(["dem"])]
                for rho in (1.0, 0.95, 0.9):
                    ip = decompose.identity_parts(float(U[N()]), float(us), float(ET), rho)
                    self.assertAlmostEqual(ip["U"], (1 - rho) * float(ET) + rho * float(U[N()]), places=9)
                    self.assertAlmostEqual(ip["structural"] + ip["demand"] + ip["readiness"], ip["U"], places=9)
                    self.assertGreaterEqual(ip["demand"], -1e-9)
                    self.assertGreaterEqual(ip["readiness"], -1e-12)
                sp = decompose.struct_split(us, U[N(["arith", "dem"])], U[N(["cap", "dem"])],
                                            U[N(["arith", "cap", "dem"])])
                self.assertEqual(sp["arith"] + sp["cap"] + sp["residual"], us)  # exact Fractions
                self.assertGreaterEqual(sp["residual"], 0)

    def test_old_three_channel_at_unlimited_demand_equals_split(self):
        """With demand unlimited the demand player is a dummy, so the three-channel Shapley shares of
        arith and cap equal the two-player split and the demand share is zero."""
        LD = {"L3u": laws.named("L3u"), "L2two": laws.named("L2two")}
        for menu in [(15, 30), (5, 15, 30), (15, 20, 30, 45, 60)]:
            vals = grid.menu_values(menu, LD, [("L3u", "a"), ("L2two", "b")], [3, 4, 8, None], [])
            for (l, c, h, s), r in vals.items():
                D = {k: float(v) for k, v in r["U"].items()}
                U3 = {}
                for S in decompose.subsets(("arith", "cap", "dem")):
                    U3[S] = D[N(x for x in S if x != "dem") | {"dem"}]
                phi = decompose.shapley(U3, ("arith", "cap", "dem"))
                sp = decompose.struct_split(*(D[N(k)] for k in (["dem"], ["arith", "dem"], ["cap", "dem"],
                                                               ["arith", "cap", "dem"])))
                self.assertAlmostEqual(phi["dem"], 0.0, places=12)
                self.assertAlmostEqual(phi["arith"], sp["arith"], places=9)
                self.assertAlmostEqual(phi["cap"], sp["cap"], places=9)

    def test_readiness_part_is_old_readiness_marginal(self):
        law = laws.named("L2")
        ml = [means("balanced", 4)]
        ref = exact.combos_for((6, 15, 30), law, "b", [4, 8], ml)
        for h in (4, 8):
            r = ref[(0, h)]
            ET, Ur1 = float(r["ET"]), float(r["U"][N()])
            for rho in (0.95, 0.9):
                old_U = (1 - rho) * ET + rho * Ur1          # four-channel U({}) at rho
                ip = decompose.identity_parts(Ur1, float(r["U"][N(["dem"])]), ET, rho)
                self.assertAlmostEqual(ip["readiness"], old_U - Ur1, places=9)
                self.assertAlmostEqual(ip["U"], old_U, places=9)

    def test_sampled_block_agrees_with_exact(self):
        from podsim import scenario
        law = laws.named("L3u")
        n = 1500
        st, _ = scenario.run_block("decomp-test", law, (10, 15, 30), 4, "balanced", [4, None], [1.0, 0.95], "a", n)
        ref = exact.combos_for((10, 15, 30), law, "a", [4, None], [means("balanced", 4)])
        for h in (4, None):
            r = ref[(0, h)]
            U = {k: float(v) for k, v in r["U"].items()}
            sp = decompose.struct_split(U[N(["dem"])], U[N(["arith", "dem"])], U[N(["cap", "dem"])],
                                        U[N(["arith", "cap", "dem"])])
            for rho in (1.0, 0.95):
                s = st[(h, rho)]
                ip = decompose.identity_parts(U[N()], U[N(["dem"])], float(r["ET"]), rho)
                for k, v in (("U", ip["U"]), ("demand", ip["demand"]), ("readiness", ip["readiness"]),
                             ("arith", sp["arith"]), ("cap", sp["cap"]), ("residual", sp["residual"])):
                    se = s.se(k)
                    self.assertLess(abs(s.mean(k) - v), 5 * se + 1e-9, msg=(h, rho, k, s.mean(k), v, se))


class TestEligibility(unittest.TestCase):
    LD = {"L3u": laws.named("L3u"), "L2": laws.named("L2")}
    LC = [("L3u", "a"), ("L2", "b")]

    def test_no_other_lengths_no_gain(self):
        # {5, 6}: no other integer length in [5, 6], so the range lever admits nothing
        r = eligibility.range_gains((5, 6), self.LD, self.LC, [3, None], [means("balanced", 8)], [0.0, 0.2], 50)
        for v in r.values():
            self.assertEqual(v[0], 0.0)
            self.assertEqual(v[1], 0.0)

    def test_eps0_equals_adding_union_lengths_exactly(self):
        """At eps = 0 the range lever admits exactly the union lengths inside the range, so its expected gain equals
        the exact paired gain of adding them all as listed durations."""
        menu = (10, 15, 30)  # range [10, 30] holds union lengths 20 (not in menu)
        ml = [means("balanced", 8), means("w30", 4)]
        r = eligibility.range_gains(menu, self.LD, self.LC, [4, 6, None], ml, [0.0], 3000)
        me0 = levers.MenuExpect(menu, ml, self.LD, caps=[3, 4, 5, 6])
        me1 = levers.MenuExpect((10, 15, 20, 30), ml, self.LD, caps=[3, 4, 5, 6])
        for (l, c, h, s, e), (g, se, b, seb) in r.items():
            exact_gain = me0.U(l, c, h, s) - me1.U(l, c, h, s)
            self.assertLess(abs(g - exact_gain), 5 * se + 0.02, msg=(l, c, h, s, g, exact_gain, se))
            self.assertLess(abs(b - me0.U(l, c, h, s)), 5 * seb + 0.05, msg=(l, c, h, s, b, me0.U(l, c, h, s), seb))

    def test_rich_supply_reaches_structural_range_gain(self):
        """With every length in plentiful supply the gain tends to the structural range gain D_h(A) - D_h(R)."""
        menu = (15, 30)
        ml = [means("balanced", 4000)]
        r = eligibility.range_gains(menu, self.LD, self.LC, [3, 6, None], ml, [0.5], 20)
        rng = structural.range_menu(menu)
        for (l, c, h, s, e), (g, se, b, seb) in r.items():
            law = self.LD[l]
            D0 = sum((w * structural.D(menu, laws.dynamic_cap(h, st, c), T) for (T, st), w in law.support), Fraction(0))
            D1 = sum((w * structural.D(rng, laws.dynamic_cap(h, st, c), T) for (T, st), w in law.support), Fraction(0))
            self.assertAlmostEqual(g, float(D0 - D1), places=6)
            self.assertAlmostEqual(b, float(D0), places=6)

    def test_monotone_in_eps_and_deterministic(self):
        menu = (15, 30)
        ml = [means("d1530", 16), NegBinMeans(means("balanced", 16), 1)]
        a = eligibility.range_gains(menu, self.LD, self.LC, [4, None], ml, list(eligibility.EPS_SWEEP), 300)
        b = eligibility.range_gains(menu, self.LD, self.LC, [4, None], ml, list(eligibility.EPS_SWEEP), 300)
        self.assertEqual(a, b)
        for (l, c, h, s, e), v in a.items():
            self.assertGreaterEqual(v[0], 0.0)
        for l, c in self.LC:
            for h in (4, None):
                for s in range(2):
                    g = [a[(l, c, h, s, e)][0] for e in eligibility.EPS_SWEEP]
                    self.assertEqual(g, sorted(g))  # same uniforms, more supply: pathwise more fill

    def test_menu_outside_union_refused(self):
        with self.assertRaises(ValueError):
            eligibility.range_gains((15, 16), self.LD, self.LC, [3], [means("balanced", 8)], [0.0], 5)

    def test_supply_does_not_depend_on_menu(self):
        lm = eligibility.length_means(means("balanced", 48), 0.48)
        self.assertEqual(len(lm), 56)
        self.assertAlmostEqual(lm[17], 0.48 * 48 / 48)
        self.assertEqual(lm[30], means("balanced", 48)[30])


class TestSampledTies(unittest.TestCase):
    def test_range_ties_within_two_se(self):
        import run_x2
        import run_xd
        g = {"dur_best": 3.0, "cap+1": 1.0, "range": 3.15}
        self.assertEqual(run_x2.best(g, ["dur_best", "cap+1", "range"], {"range": 0.1}), "tie:dur_best+range")
        self.assertEqual(run_x2.best(g, ["dur_best", "cap+1", "range"], {"range": 0.05}), "range")
        self.assertEqual(run_x2.best(g, ["dur_best", "cap+1", "range"]), "range")
        self.assertEqual(run_xd.top_label({"cap+1": 2.0, "range": 1.85}, {"range": 0.1}), "cap+1 & range")
        # pairwise non-domination: an exact lever beaten by another exact lever is not tied in through a sampled one
        self.assertEqual(run_x2.best({"dur_best": 0.324619, "cap+1": 0.317055, "range": 0.338363},
                                     ["dur_best", "cap+1", "range"], {"range": 0.0195}), "tie:dur_best+range")
