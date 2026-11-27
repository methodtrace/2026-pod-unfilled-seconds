"""Tests for the tie rule, whole-second tick breaks, the tick study's prefix property and the window cap."""
import os
import random
import sys
import unittest
from fractions import Fraction

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from podsim import numeric, structural, ticks  # noqa: E402

TPS = ticks.TPS


def ref_nondominated(vals, ses, tie):
    out = []
    for v, k in vals:
        if v <= tie:
            continue
        ok = True
        for vm, m in vals:
            d = (ses.get(k, 0.0) ** 2 + ses.get(m, 0.0) ** 2) ** 0.5
            if vm - v > tie + 2 * d:
                ok = False
        if ok:
            out.append(k)
    return sorted(out)


class TestTieRule(unittest.TestCase):
    def test_against_reference(self):
        rng = random.Random(5)
        for _ in range(5000):
            n = rng.randint(1, 5)
            keys = ["k%d" % i for i in range(n)]
            vals = [(rng.choice([0.0, -0.1, rng.uniform(-1, 3)]), k) for k in keys]
            ses = {k: rng.choice([0.0, rng.uniform(0, 0.5)]) for k in keys if rng.random() < 0.5}
            self.assertEqual(numeric.nondominated(vals, ses), ref_nondominated(vals, ses, 1e-9))

    def test_no_gain_never_wins(self):
        self.assertEqual(numeric.nondominated([(0.5, "cap+1"), (-0.1, "range")], {"range": 0.4}), ["cap+1"])
        self.assertEqual(numeric.nondominated([(0.0, "a"), (1e-12, "b")]), [])

    def test_nan_raises(self):
        with self.assertRaises(ValueError):
            numeric.nondominated([(float("nan"), "a"), (1.0, "b")])


class TestWholeSecondBreaks(unittest.TestCase):
    def test_offset0_matches_direct(self):
        rng = random.Random(9)
        for _ in range(300):
            fs = sorted({0} | {rng.randrange(0, TPS * 200) for _ in range(rng.randint(1, 30))})
            T = rng.randint(1, 180)
            tol = rng.choice([0, 3003, 9000])
            base = TPS * T
            g = max(f for f in fs if f <= base + tol)
            u, o = ticks.unfilled_at_offset0(T, fs, tol)
            self.assertEqual(u, Fraction(max(0, base - g), TPS))
            self.assertEqual(o, Fraction(max(0, g - base), TPS))

    def test_one_frame_overrun_drops_an_ad_on_whole_seconds(self):
        # {15,30}: a 60 s break filled by two 30 s ads that each run one frame long no longer fits
        fs = sorted({0} | {n * (TPS * 15 + 3003) for n in range(1, 5)} | {n * (TPS * 30 + 3003) for n in range(1, 3)}
                    | {TPS * 45 + 2 * 3003})
        u, _ = ticks.unfilled_at_offset0(60, fs, 0)
        self.assertGreater(u, Fraction(14))


class TestPrefixProperty(unittest.TestCase):
    def test_relaxed_list_contains_actual_prefixes(self):
        """With the actual pool first, every per-length prefix choice on the actual pool is also available on the
        relaxed list, so the best relaxed tick fill is at least the best actual one."""
        rng = random.Random(3)
        menu = (15, 30)
        for _ in range(300):
            act = {a: [TPS * a + rng.randint(-3003, 3003) for _ in range(rng.randint(0, 5))] for a in menu}
            rel = {a: act[a] + [TPS * a + rng.randint(-3003, 3003) for _ in range(rng.randint(0, 5))] for a in menu}
            T = rng.randint(30, 150) * TPS + rng.randrange(TPS)
            cap = rng.choice([2, 4, 6, None])
            fa = ticks.select_ticks(T, cap, act, menu)
            fr = ticks.select_ticks(T, cap, rel, menu)
            self.assertGreaterEqual(fr, fa)


class TestWindowCap(unittest.TestCase):
    def test_brute_force(self):
        rng = random.Random(11)
        for _ in range(150):
            A = tuple(sorted(rng.sample(range(2, 31), rng.randint(1, 3))))
            L = rng.randint(0, 100)
            U = L + rng.randint(0, 60)
            unc = structural.undershoot_table(A, None, U)
            want = None
            for h in range(0, 201):
                tab = structural.undershoot_table(A, h, U)
                if all(tab[T] == unc[T] for T in range(L, U + 1)):
                    want = h
                    break
            self.assertEqual(structural.least_cap_window(A, L, U), want)

    def test_known_windows(self):
        self.assertEqual(structural.least_cap_window((15, 30), 60, 180), 6)
        self.assertEqual(structural.least_cap_window((10, 15, 30), 60, 180), 7)
        self.assertEqual(structural.least_cap_window((6, 15, 30), 60, 180), 9)
        self.assertEqual(structural.least_cap_window((15, 45), 31, 45), 2)


if __name__ == "__main__":
    unittest.main()
