"""Tests for X6: revenue.py, greedy.py and run_x6.py. Run from code/: python3 -m unittest tests.test_x6"""
import os
import random
import sys
import unittest
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim import pools as P, revenue as RV, greedy as G  # noqa: E402
from podsim.pod import Creative, select_menu, dp_select, pod_oracle  # noqa: E402
from podsim.laws import named  # noqa: E402

MENUS = [(15, 30), (10, 15, 30), (6, 15, 30), (15, 30, 60), (5, 6, 10)]


def rand_pool(rng, menu, n, vlo=20, vhi=200):
    return [Creative(rng.choice(menu), rng.randint(vlo, vhi), 0.0, k) for k in range(n)]


def by_dur(pool):
    by = {}
    for c in pool:
        by.setdefault(c.dur, []).append(c)
    for a in by:
        by[a].sort(key=lambda c: -c.bid)
    return by


class TestRevenueMaxBruteForce(unittest.TestCase):
    def test_pools_up_to_8(self):
        rng = random.Random("x6-test-brute")
        cnt = 0
        for trial in range(600):
            menu = MENUS[trial % len(MENUS)]
            n = rng.randint(0, 8)
            pool = rand_pool(rng, menu, n)
            T = rng.randint(1, 150)
            cap = rng.choice([1, 2, 3, 4, 6, None])
            (os_, or_), (rr, rs) = pod_oracle(T, cap, pool)
            p1, p2 = select_menu(T, cap, by_dur(pool))
            self.assertEqual((p2.revenue, p2.seconds), (rr, rs))
            self.assertEqual((p1.seconds, p1.revenue), (os_, or_))
            (ds, dr), (drr, drs) = dp_select(T, cap, pool)
            self.assertEqual((drr, drs), (rr, rs))
            cnt += 1
        self.assertEqual(cnt, 600)

    def test_floored_pools_brute_force(self):
        """Revenue-max on a floor-filtered pool equals brute force on the explicitly filtered subset."""
        rng = random.Random("x6-test-floor-brute")
        for trial in range(300):
            menu = MENUS[trial % len(MENUS)]
            vals = {a: sorted((rng.randint(10, 150) for _ in range(rng.randint(0, 4))), reverse=True) for a in menu}
            fl = RV.FLOORS_NARROW[trial % len(RV.FLOORS_NARROW)]

            D = type("D", (), {})()
            D.arr = {a: [rng.random() for _ in vals[a]] for a in menu}
            by, arr, ntot, nk = RV.build_pool(D, vals, fl)
            flat = [Creative(a, v, 0.0, (a, j)) for a in menu for j, v in enumerate(vals[a]) if fl.passes(a, v)]
            self.assertEqual(nk, len(flat))
            T = rng.randint(1, 150)
            cap = rng.choice([2, 4, None])
            (_, _), (rr, rs) = pod_oracle(T, cap, flat)
            pods = RV.all_policies(T, cap, by, arr)
            self.assertEqual((pods["P2"].revenue, pods["P2"].seconds), (rr, rs))


class TestFloors(unittest.TestCase):
    def test_mincpmpersec(self):
        f = RV.Floor("t", "ps", ps=67)
        for a in (5, 15, 30, 60):
            self.assertFalse(f.passes(a, 66))
            self.assertTrue(f.passes(a, 67))

    def test_durfloors_ranges(self):
        f = RV.FLOORS_NARROW[-1]  # 1-15: $10, 16-30: $20, 31+: $40 CPM (cents 1000/2000/4000)
        self.assertEqual(f.min_v(15), 67)   # 67 * 15 = 1005 >= 1000; 66 * 15 = 990 < 1000
        self.assertEqual(f.min_v(6), 167)
        self.assertEqual(f.min_v(10), 100)
        self.assertEqual(f.min_v(16), 125)
        self.assertEqual(f.min_v(30), 67)
        self.assertEqual(f.min_v(60), 67)
        for a in (5, 6, 10, 15, 20, 30, 45, 60):
            m = f.min_v(a)
            fl = [x for lo, hi, x in f.ranges if a >= lo and (hi is None or a <= hi)][0]
            self.assertGreaterEqual(m * a, fl)
            self.assertLess((m - 1) * a, fl)

    def test_durfloors_overlap_and_gap(self):
        f = RV.Floor("t", "dur", ranges=((1, 20, 600), (15, 30, 900)))
        self.assertEqual(f.min_v(15), 60)   # max(600, 900) / 15
        self.assertEqual(f.min_v(45), 1)    # no range: fallback (no floor)

    def test_filter_before_construction(self):
        draw = RV.BreakDraw("x6-test", named("L3u"), 3, (6, 15, 30), 64, P.weights("balanced"))
        for vn in RV.VALUE_LAWS:
            vals = draw.values(RV.value_law(vn))
            for fl in RV.FLOORS_NARROW:
                by, arr, ntot, nk = RV.build_pool(draw, vals, fl)
                self.assertEqual(ntot, sum(len(v) for v in vals.values()))
                for a, lst in by.items():
                    self.assertEqual(len(lst), sum(1 for v in vals[a] if fl.passes(a, v)))
                    for c in lst:
                        self.assertTrue(fl.passes(a, c.v))
                self.assertEqual(sorted(id(c) for a in by for c in by[a]), sorted(id(c) for c in arr))

    def test_pass_prob_matches_sample(self):
        rng = random.Random("x6-pp")
        for vn in RV.VALUE_LAWS:
            vl = RV.value_law(vn)
            for fl in RV.FLOORS_NARROW:
                for a in (6, 15, 30):
                    k = sum(1 for _ in range(20000) if fl.passes(a, vl.value(a, rng.random())))
                    self.assertAlmostEqual(k / 20000.0, RV.pass_prob(vl, a, fl), delta=0.015)

    def test_stream_matches_pools(self):
        """Top min(n, 48) order statistics equal pools.duration_stream's pools (CRN with the X1 simulator)."""
        vl = P.ValueLaw()
        for i in range(30):
            for a in (6, 15, 30):
                pool, _ = P.duration_stream("x6-crn", i, a, 8.0, 48, vl)
                n, qs = RV.stream_draw("x6-crn", i, a, 8.0)
                self.assertEqual([c.v for c in pool], [vl.value(a, q) for q in qs[:48]])

    def test_v2_premium(self):
        v1, v2 = RV.value_law("V1"), RV.value_law("V2")
        q = 0.5
        self.assertEqual(v1.value(30, q), v2.value(30, q))
        self.assertGreater(v2.value(15, q), v1.value(15, q))
        self.assertLess(v2.value(60, q), v1.value(60, q))


class TestGreedy(unittest.TestCase):
    def test_greedy_never_beats_dp(self):
        rng = random.Random("x6-greedy")
        for trial in range(1500):
            menu = MENUS[trial % len(MENUS)]
            pool = rand_pool(rng, menu, rng.randint(0, 25))
            arr = list(pool)
            rng.shuffle(arr)
            T = rng.randint(1, 240)
            cap = rng.choice([1, 3, 4, 6, 8, None])
            pods = RV.all_policies(T, cap, by_dur(pool), arr)  # asserts dominance internally
            for g in ("P3", "P3d", "P4"):
                self.assertLessEqual(pods[g].seconds, pods["P1"].seconds)
                self.assertLessEqual(pods[g].revenue, pods["P2"].revenue)

    def test_dominance_assert_fires(self):
        a = Creative(30, 100)
        from podsim.pod import Pod
        pods = {"P1": Pod(15, 10, []), "P2": Pod(15, 10, []), "X": Pod(30, 3000, [(a, 30)])}
        with self.assertRaises(AssertionError):
            G.assert_dominance(pods, 30, None)

    def test_greedy_rules(self):
        c = [Creative(30, 100, 0, "a"), Creative(15, 150, 0, "b"), Creative(15, 90, 0, "c"), Creative(30, 80, 0, "d")]
        by = by_dur(c)
        p3 = G.greedy_price(45, None, by)
        self.assertEqual([x.ident for x, _ in p3.items], ["b", "a"])
        p3d = G.greedy_duration(45, None, by)
        self.assertEqual([x.ident for x, _ in p3d.items], ["a", "b"])
        p4 = G.first_come(45, 1, [c[3], c[0]])
        self.assertEqual([x.ident for x, _ in p4.items], ["d"])
        # fill while it fits: a misfit is skipped, the scan continues
        p = G.greedy_price(40, None, by_dur([Creative(30, 200, 0, "x"), Creative(15, 150, 0, "y"),
                                             Creative(6, 10, 0, "z")]))
        self.assertEqual([x.ident for x, _ in p.items], ["x", "z"])


class TestRunner(unittest.TestCase):
    def test_tiny_block_deterministic(self):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import run_x6
        b = ("L2", "a", (6, 15, 30), 8, "balanced", 40, [4, None], ("V1", "V2"), ("none", "ps67", "dfA"))
        r1, _ = run_x6.run_block(b)
        r2, _ = run_x6.run_block(b)
        self.assertEqual(r1, r2)
        rows, _ = run_x6.rows_for_block(b, r1)
        self.assertEqual(len(rows), 2 * 2 * 3)
        for r in rows:
            self.assertGreaterEqual(r["gapS_P2"], 0)
            self.assertGreaterEqual(r["gapR_P2"], 0)
            if r["floor"] == "none":
                self.assertEqual(r["dU_floor_P1"], 0)
            self.assertGreaterEqual(r["dU_floor_P1"], 0)
            self.assertLessEqual(r["dR_floor_P2"], 1e-9)


if __name__ == "__main__":
    unittest.main()
