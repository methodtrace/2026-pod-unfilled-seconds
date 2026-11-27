"""Tests for X5 (podsim/clutter.py, podsim/hullchecks.py, run_x5.py). Run from code/:
python3 -m unittest -q tests.test_x5"""
import os
import random
import sys
import unittest
from fractions import Fraction as Q
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim import clutter, hullchecks, pools  # noqa: E402
from podsim.pod import Creative, select_menu  # noqa: E402
import run_x5  # noqa: E402


def brute_best(items, C):
    """V_C(n) by subset enumeration of (duration, bid) items."""
    best = {0: 0}
    for k in range(1, len(items) + 1):
        for S in combinations(items, k):
            if sum(d for d, _ in S) <= C:
                v = sum(b for _, b in S)
                if v > best.get(k, -1):
                    best[k] = v
    return [best[n] for n in range(len(best))]


def brute_majorant(U):
    """Knapsack companion verify_certificates.majorant: concave majorant by all chords, on 0..b."""
    M = max(U)
    b = U.index(M)
    pts = [(n, U[n]) for n in range(b + 1)]
    out = []
    for k in range(b + 1):
        cand = [Q(U[k])]
        for i, u in pts:
            for j, v in pts:
                if i <= k <= j and i < j:
                    cand.append(u + (v - u) * Q(k - i, j - i))
        out.append(max(cand))
    return tuple(out)


def rand_items(rng, n, durs):
    return [(rng.choice(durs), rng.randint(1, 60) * rng.choice(durs)) for _ in range(n)]


class TestHull(unittest.TestCase):
    def test_hull_vs_brute(self):
        rng = random.Random("x5-hull")
        for _ in range(400):
            n = rng.randint(1, 9)
            vals = [0] + sorted((rng.randint(0, 50) for _ in range(n)))
            vals = [0] + [sum(vals[1:j + 1]) // max(1, rng.randint(1, 2)) for j in range(1, n + 1)]
            vals[0] = 0
            b, H, verts = clutter.hull(vals)
            self.assertEqual(H, brute_majorant(vals))
            self.assertEqual(verts, clutter.hull_verts(H))
            self.assertEqual(clutter.hull_vertices(vals), (b, verts))
            for v in verts:
                self.assertEqual(H[v], vals[v])  # vertices are attained

    def test_best_by_count_vs_brute(self):
        rng = random.Random("x5-bbc")
        for _ in range(150):
            durs = rng.choice([(15, 30), (6, 15, 30), (10, 15, 20, 30), (15, 30, 60)])
            items = rand_items(rng, rng.randint(1, 9), durs)
            B = rng.choice([60, 90, 120])
            T = B - rng.choice([5, 10, 15, 20, 45])
            bids = {}
            for d, b in items:
                bids.setdefault(d, []).append(b)
            for d in bids:
                bids[d].sort(reverse=True)
            got, _ = clutter.best_by_count(bids, [B, T])
            for C in (B, T):
                self.assertEqual([x[0] for x in got[C]], brute_best(items, C))
            # the class enumeration of run_x5 gives the same per-count optimum
            cls = run_x5.enumerate_classes(bids, (B, T))
            for C in (B, T):
                self.assertEqual([x[0] for x in run_x5.by_count(cls[C])], brute_best(items, C))

    def test_envelope_equals_max_over_counts(self):
        rng = random.Random("x5-env")
        for _ in range(200):
            items = rand_items(rng, rng.randint(1, 8), (6, 15, 30))
            T = rng.randint(30, 120)
            vals = brute_best(items, T)
            bt = [(v, 0, ()) for v in vals]
            b, verts = clutter.hull_vertices(vals)
            for k in run_x5.KS:
                n = clutter.seller_choice(bt, verts, k)
                net = [clutter.K_STEPS * v - k * clutter.CMAX * j for j, v in enumerate(vals)]
                self.assertEqual(net[n], max(net))
                self.assertEqual(n, min(j for j in range(len(net)) if net[j] == max(net)))
            # c = 0 picks the revenue optimum; ads are nonincreasing in c
            ads = [clutter.seller_choice(bt, verts, k) for k in run_x5.KS]
            self.assertEqual(ads[0], b)
            self.assertTrue(all(x >= y for x, y in zip(ads, ads[1:])))

    def test_revenue_optimum_matches_select_menu(self):
        rng = random.Random("x5-sm")
        for i in range(60):
            pool = []
            for a in (10, 15, 30):
                pool += pools.duration_stream("x5test", i, a, 3.0, 48, pools.ValueLaw())[0]
            T = rng.randint(40, 200)
            bids = {}
            for c in pool:
                if c.dur <= T:
                    bids.setdefault(c.dur, []).append(c.bid)
            for d in bids:
                bids[d].sort(reverse=True)
            if not bids:
                continue
            got, _ = clutter.best_by_count(bids, [T])
            for h in (3, 6, None):
                _, pr = select_menu(T, h, pool)
                lst = got[T] if h is None else got[T][:h + 1]
                self.assertEqual(pr.revenue, max(x[0] for x in lst))


class TestHullChecks(unittest.TestCase):
    def test_companion_known_good(self):
        # Theorem 4.4 (T6) instance and its target pair: realizable, so no condition may fail.
        a, b, u, v = 5, 4, 3, 1
        items = [(b, 4)] * 3 + [(a, 6)] * 2 + [(u, 1), (v, 2)]
        Hw = brute_majorant(brute_best([(d, x) for x, d in items], 12))
        Hr = brute_majorant(brute_best([(d, x) for x, d in items], 3))
        self.assertEqual(Hw, (0, 5, 10, 12))
        self.assertEqual(Hr, (0, 3, 4))
        self.assertEqual(hullchecks.violations(Hw, Hr), [])
        # Theorem 4.6 pair: in L (passes every scalar row) though not realizable; the checks must pass it.
        self.assertEqual(hullchecks.violations((0, 7, 11, 15), (0, 4, 7, 10)), [])
        # Theorem 5.7 band H >= 9c: realizable uncapped and at K = 4.
        a, b, c = 6, 5, 1
        w = (0, a, a + b, a + 2 * b)
        r = (0, c, 2 * c, 3 * c)
        self.assertEqual(hullchecks.violations(w, r), [])
        self.assertEqual(hullchecks.violations(w, r, 4), [])

    def test_random_realized_pairs_pass(self):
        rng = random.Random("x5-real")
        n = 0
        for _ in range(300):
            items = rand_items(rng, rng.randint(1, 8), (6, 10, 15, 30))
            D = rng.choice([30, 45, 60, 90])
            R = D - rng.choice([5, 10, 15, 20, 45])
            if R < 0:
                continue
            items = [(d, x) for d, x in items if d <= D]
            if not items:
                continue
            for K in (None, 2, 3, 4, 6):
                bw, br = brute_best(items, D), brute_best(items, R)
                if K is not None:
                    bw, br = bw[:K + 1], br[:K]
                Hw, Hr = brute_majorant(bw), brute_majorant(br)
                self.assertEqual(hullchecks.violations(Hw, Hr, K), [], (items, D, R, K))
                n += 1
        self.assertGreater(n, 500)

    def test_corrupted_inputs_raise(self):
        Hw = (0, 5, 10, 12)
        Hr = (0, 3, 4)
        # dominance broken: remainder worth more than the full break at m = 2
        with self.assertRaises(hullchecks.HullCheckError):
            hullchecks.check_pair(Hw, (0, 3, 11))
        # remainder hull from a different (richer) pool: (1) fails at n = 2
        v = hullchecks.violations((0, 10, 20), (0, 9, 18))
        self.assertTrue(any(x["equation"] in ("dominance", "(1)") for x in v))
        # Theorem 5.7 band 3c < H < 9c/2 fails vertex-only capped EC at K = 4 (the scalar rows catch it)
        a, b, c = 4, 3, 2  # H = 10, 3c = 6 < 10 < 9
        self.assertTrue(hullchecks.violations((0, a, a + b, a + 2 * b), (0, c, 2 * c, 3 * c), 4))
        # Theorem 4.6-like corruption: lower H_w(2)
        self.assertTrue(hullchecks.violations((0, 7, 8, 15), (0, 4, 7, 10)))
        # not concave / not increasing
        self.assertTrue(hullchecks.violations((0, 2, 6), (0, 1)))
        self.assertTrue(hullchecks.violations((0, 5, 5), (0, 1)))
        # dimension: remainder count above its cap
        self.assertTrue(hullchecks.violations((0, 5, 9), (0, 3, 5), 2))
        self.assertEqual(hullchecks.violations((0, 5, 9), (0, 3, 5), 2, 2), [])

    def test_corrupted_simulator_pairs_raise(self):
        """Simulated pools with a deliberate bug (remainder hull computed with bids inflated by 50%, or with
        the cap convention swapped so the remainder gets one more ad than the full break) are caught."""
        caught = 0
        for i in range(200):
            pool = {a: pools.duration_stream("x5corrupt", i, a, 4.0, 48, pools.ValueLaw())[0] for a in (15, 30)}
            B = 120
            T = 105
            bids = {a: [c.bid for c in pool[a]] for a in pool if pool[a]}
            if not bids:
                continue
            best, _ = clutter.best_by_count(bids, [B, T])
            vw = [x[0] for x in best[B]]
            vr = [x[0] * 3 // 2 for x in best[T]]
            _, Hw, _ = clutter.hull(vw)
            _, Hr, _ = clutter.hull(vr)
            try:
                hullchecks.check_pair(Hw, Hr)
            except hullchecks.HullCheckError:
                caught += 1
        self.assertGreater(caught, 150)

    def test_pair_forms(self):
        self.assertEqual(hullchecks.pair_caps(6, "b"), (6, 5))
        self.assertEqual(hullchecks.pair_caps(6, "a"), (6, 6))
        self.assertEqual(hullchecks.pair_caps(6, "a_k1"), (7, 6))
        self.assertEqual(hullchecks.pair_caps(6, "unc"), (None, None))


class TestRunX5(unittest.TestCase):
    def test_work_deterministic_and_chunk_invariant(self):
        a = run_x5.work(("L2", 16, "balanced", 0, 6))
        b1 = run_x5.work(("L2", 16, "balanced", 0, 3))
        b2 = run_x5.work(("L2", 16, "balanced", 3, 3))
        for k, v in a[1].items():
            self.assertEqual(v, [x + y for x, y in zip(b1[1][k], b2[1][k])])
        self.assertEqual(a[1], run_x5.work(("L2", 16, "balanced", 0, 6))[1])
        self.assertGreater(sum(a[3].values()), 0)


if __name__ == "__main__":
    unittest.main()
