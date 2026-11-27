"""Tests for X4 (podsim/reversal.py, run_x4.py). Run from code/: python3 -m unittest -q tests.test_x4"""
import os
import sys
import unittest
from fractions import Fraction as Q
from itertools import product

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim import reversal as RV, structural, laws  # noqa: E402
import run_x4  # noqa: E402


def brute_D(A, h, T):
    """T - max reachable sum <= T with at most h parts (h None: up to T // min A parts), by enumeration."""
    k = T // min(A) if h is None else h
    reach = {0}
    for _ in range(k):
        reach |= {s + a for s in reach for a in A if s + a <= T}
    return T - max(reach)


class TestReversalInfo(unittest.TestCase):
    def test_signs_and_points(self):
        caps = (1, 2, 3, 4, None)
        info = RV.reversal_info(caps, [Q(-2), Q(0), Q(-1), Q(3), Q(1)])
        self.assertEqual(info["signs"], "-0-++")
        self.assertEqual(info["points"], [4])
        self.assertEqual(info["magnitude"], Q(2))  # min(lead of A = 2, lead of A' = 3)
        info = RV.reversal_info(caps, [Q(1), Q(-1), Q(1), Q(0), Q(0)])
        self.assertEqual(info["points"], [2, 3])
        self.assertEqual(RV.reversal_info(caps, [Q(0)] * 5)["n_changes"], 0)

    def test_tolerance(self):
        info = RV.reversal_info((1, 2), [-1e-12, 1.0], tol=1e-9)
        self.assertEqual(info["n_changes"], 0)


class TestFloorsExact(unittest.TestCase):
    def test_floor_against_brute(self):
        law = laws.Law.plain("t", laws.uniform(range(20, 61)))
        for A in [(15, 30), (6, 15, 30), (10, 15, 30), (15, 30, 60)]:
            vals = RV.floor_values(A, law, "a", caps=(1, 2, 3, None))
            for h in (1, 2, 3, None):
                ref = sum(Q(brute_D(A, h, T), 41) for T in range(20, 61))
                self.assertEqual(vals[h], ref, (A, h))

    def test_known_reversal_l3u(self):
        """{15,30,60} beats {10,15,30} at low caps (longer longest part) and loses from h = 7 on (lattice 15
        versus 5): the sign string on L3u is ------+++... (reversal at 7)."""
        law = laws.named("L3u")
        a = RV.floor_values((15, 30, 60), law, "a")
        b = RV.floor_values((10, 15, 30), law, "a")
        info = RV.reversal_info(RV.CAPS, [a[h] - b[h] for h in RV.CAPS])
        self.assertEqual(info["signs"], "------" + "+" * 15)
        self.assertEqual(info["points"], [7])
        # limits are the lattice floors: mean of T mod 15 and T mod 5 over [60, 240]
        self.assertEqual(a[None], RV.lattice_floor((15, 30, 60), law))
        self.assertEqual(b[None], RV.lattice_floor((10, 15, 30), law))
        # on the 15 s lattice the reversal disappears (both fill to 0 once h is large)
        l15 = laws.named("L4u15")
        a = RV.floor_values((15, 30, 60), l15, "a")
        b = RV.floor_values((10, 15, 30), l15, "a")
        self.assertEqual(RV.reversal_info(RV.CAPS, [a[h] - b[h] for h in RV.CAPS])["n_changes"], 0)

    def test_stability_example(self):
        """Example 3: A0 = {0,4,7}, W = {6}. Adding 5 lowers D from 2 to 1 at every h >= 1; adding 3 leaves 2
        at h = 1 and gives 0 at h = 2 = l(6). So {3,4,7} versus {4,5,7} reverses at h = 2."""
        W = laws.Law.plain("W6", [(6, Q(1))])
        base = RV.floor_values((4, 7), W, "a", caps=(1, 2, 3, None))
        add5 = RV.floor_values((4, 5, 7), W, "a", caps=(1, 2, 3, None))
        add3 = RV.floor_values((3, 4, 7), W, "a", caps=(1, 2, 3, None))
        self.assertEqual([base[h] for h in (1, 2, 3, None)], [2, 2, 2, 2])
        self.assertEqual([add5[h] for h in (1, 2, 3, None)], [1, 1, 1, 1])
        self.assertEqual([add3[h] for h in (1, 2, 3, None)], [2, 0, 0, 0])
        info = RV.reversal_info((1, 2, 3, None), [add3[h] - add5[h] for h in (1, 2, 3, None)])
        self.assertEqual(info["signs"], "+---")
        self.assertEqual(info["points"], [2])
        # {0,2,9}, W = {10}: undershoot 1 for h <= 4, 0 for h >= 5 (a plateau does not certify the limit)
        W10 = laws.Law.plain("W10", [(10, Q(1))])
        v = RV.floor_values((2, 9), W10, "a", caps=(1, 2, 3, 4, 5, 6, None))
        self.assertEqual([v[h] for h in (1, 2, 3, 4, 5, 6, None)], [1, 1, 1, 1, 0, 0, 0])
        self.assertEqual(RV.stable_cap(v, caps=(1, 2, 3, 4, 5, 6, None)), 5)
        self.assertEqual(run_x4.stab_bound((2, 9), W10, "a"), 5)


class TestStabBound(unittest.TestCase):
    def test_matches_empirical(self):
        for name in ("L2", "L3u", "L6"):
            law = laws.named(name)
            for conv in ("a", "b") if name == "L2" else ("a",):
                for A in [(15, 30), (6, 15, 30), (5, 6), (20, 45)]:
                    vals = RV.floor_values(A, law, conv)
                    th = run_x4.stab_bound(A, law, conv)
                    emp = RV.stable_cap(vals)
                    if th > 20:
                        self.assertIsNone(emp)
                    else:
                        self.assertEqual(emp, th, (name, conv, A))


class TestFamilyAndCriterion(unittest.TestCase):
    def test_family_menus(self):
        """Example 6 Tot(h) rows."""
        want = {(15, 30, 60): [1, 1, 1], (5, 15, 30): [4, 5, 5], (10, 15, 30): [4, 5, 5],
                (6, 15, 30): [14, 20, 23, 24, 24]}
        for m, row in want.items():
            self.assertEqual([RV.family_tot(m, h) for h in range(1, len(row) + 1)], row, m)

    def test_mass_symmetry(self):
        """M(S) = sum of upward distances = sum of downward distances to S."""
        for gens in [(3, 5), (4, 7), (2, 9), (5, 7, 11), (6, 9, 20)]:
            gp, _ = RV._semigroup(gens)
            down = 0
            for y in gp:
                j = 0
                while (y - j) in gp:
                    j += 1
                down += j
            self.assertEqual(RV.mass(gp), down)

    def test_criterion_small_cases(self):
        """Corollary 4 on small reduced sets, brute-force window totals at equality levels."""
        n = 0
        for A0 in [(0, 2, 3, 6), (0, 1, 3, 6), (0, 3, 4, 7), (0, 2, 5), (0, 3, 5, 8)]:
            d = max(A0)
            for c in range(1, d):
                if c in A0:
                    continue
                for h in range(1, 6):
                    r = RV.criterion_case(A0, c, h)
                    if r is None:
                        continue
                    lo, hi = r["W_lo"], r["W_hi"]
                    pos = tuple(a for a in A0 if a > 0)
                    A1 = tuple(sorted(set(pos) | {c}))
                    self.assertEqual(r["tot_add_c_at_h"], sum(brute_D(A1, h, t) for t in range(lo, hi + 1)))
                    self.assertEqual(r["tot_cap_plus_1"], sum(brute_D(pos, h + 1, t) for t in range(lo, hi + 1)))
                    if r["eq_new_h"] and r["eq_old_h1"]:
                        self.assertEqual(r["tot_add_c_at_h"], r["M_S2new"])
                        self.assertEqual(r["tot_cap_plus_1"], r["M_S2"] - r["omega"])
                        self.assertEqual(r["computed_sign"], r["predicted_sign"])
                        n += 1
        self.assertGreater(n, 10)

    def test_criterion_check_menus(self):
        rows, st = RV.criterion_check([(10, 15, 30), (6, 15, 30), (5, 15, 30)], run_x4.ADDS, n_h=2)
        self.assertGreater(st["at_equality"], 0)
        self.assertEqual(st["sign_mismatch"], 0)
        self.assertEqual(st["identity_mismatch"], 0)
        self.assertEqual(st["base_identity_mismatch"], 0)
        self.assertEqual(st["h_dependent_pairs"], 0)


class TestRunQuick(unittest.TestCase):
    def test_quick_deterministic(self):
        import tempfile
        import subprocess
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        outs = []
        for jobs in ("1", "2"):
            with tempfile.TemporaryDirectory(prefix="x4test") as d:
                r = subprocess.call([sys.executable, os.path.join(here, "run_x4.py"), "--tier", "quick", "--jobs",
                                     jobs, "--out", d], stdout=subprocess.DEVNULL)
                self.assertEqual(r, 0)
                got = {}
                for f in sorted(os.listdir(d)):
                    if f not in ("timing.json", ".cache"):
                        with open(os.path.join(d, f), "rb") as fh:
                            got[f] = fh.read()
                outs.append(got)
        self.assertEqual(outs[0], outs[1])
        self.assertNotIn(b"\xe2\x80\x94", b"".join(outs[0].values()))  # no em dashes


if __name__ == "__main__":
    unittest.main()
