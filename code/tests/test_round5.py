"""Tests for the range dominance bound in lever ranking, the split's use of X2's unrounded winner sets, the
truncated count laws at a zero ceiling and the unreachable-sum sentinel of the undershoot table."""
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from podsim import exact, structural  # noqa: E402
from podsim import registry as REG  # noqa: E402


class TestCountLawZeroCeiling(unittest.TestCase):
    def test_poisson_and_nb_top_zero_carry_mass_one(self):
        self.assertEqual(exact.poisson_trunc(1.0, 0), [1.0])
        self.assertEqual(exact.nb_trunc(1.0, 4.0, 0), [1.0])

    def test_short_horizon_expectation(self):
        """With a horizon of 24 s a 30-second duration has a zero count ceiling, and its law is the single cell of
        mass one; a 15-second target at cap 1 with Poisson mean 1 then loses 15 s with probability 1 / e."""
        old = exact.TMAX, exact.MASK
        try:
            exact.TMAX = 24
            exact.MASK = (1 << 25) - 1
            p = exact.poisson_trunc(1.0, exact.TMAX // 30)
            self.assertEqual(p, [1.0])
            p15 = exact.poisson_trunc(1.0, exact.TMAX // 15)
            self.assertAlmostEqual(p15[0] * 15, 15 / math.e, places=12)
        finally:
            exact.TMAX, exact.MASK = old


class TestUnreachableSentinel(unittest.TestCase):
    def test_huge_cap_keeps_gaps(self):
        D = structural.undershoot_table((15, 30), 10 ** 9, 40)
        self.assertEqual(D[29], 14)
        self.assertEqual(D[30], 0)
        self.assertEqual(structural.undershoot_table((15, 30), None, 40)[29], 14)


class TestRangeDominanceInRanking(unittest.TestCase):
    def test_bound_respecting_range_value(self):
        """X2 ranks the range at max(sampled range, best exact interior added duration): an interior duration
        the range contains can never be the sole winner over it."""
        import run_x2
        from podsim.numeric import nondominated
        g = {"dur_best": 0.002052979, "cap+1": 0.00164483, "range": 0.0, "range_se": 0.0}
        rank = dict(g)
        rank["range"] = max(g["range"], 0.002052979)
        w = run_x2.best(rank, ["dur_best", "cap+1", "range"], {"range": 0.0})
        self.assertEqual(w, "tie:dur_best+range")
        self.assertEqual(nondominated([(0.002052979, "dur_best"), (0.0, "range")], {"range": 0.0}), ["dur_best"])


class TestSplitReadsX2Winners(unittest.TestCase):
    def test_gain_at_tolerance_kept(self):
        """A winner set chosen by X2 on unrounded gains survives even when both gains serialize to 1e-9 s."""
        import run_x2_split as SP
        base = dict(law="L1", conv="a", menu="15 30", h=10, rho=1.0)
        rows = [dict(base, weights="unlimited", lam="unlimited", dur_best=1e-9, **{"cap+1": 1e-9, "range": 0.0},
                     split_winners="cap+1|dur_best"),
                dict(base, weights="d1530", lam=64, dur_best=1e-9, **{"cap+1": 1e-9, "range": 0.0},
                     split_winners="cap+1|dur_best")]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            REG.write_csv(p, rows, list(rows[0].keys()))
            out = SP.split_rows(REG.read_csv(p), {})
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["winner"], "cap+1+dur_best")

    def test_missing_column_refused(self):
        import run_x2_split as SP
        base = dict(law="L1", conv="a", menu="15 30", h=3, rho=1.0, dur_best=1.0, range=0.0, **{"cap+1": 0.5})
        rows = [dict(base, weights="unlimited", lam="unlimited"), dict(base, weights="d1530", lam=64)]
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.csv")
            REG.write_csv(p, rows, list(rows[0].keys()))
            with self.assertRaises(ValueError):
                SP.split_rows(REG.read_csv(p), {})


if __name__ == "__main__":
    unittest.main()
