"""Tests for podsim/numeric.py: float totals independent of the Python version and of summation order, exact
totals kept exact. Run from code/: python3 -m unittest -q tests.test_numeric"""
import math
import os
import random
import sys
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from podsim.numeric import xsum, fmean  # noqa: E402


def naive(xs, start=0.0):
    """Left-to-right float addition: the builtin sum of floats before Python 3.12."""
    t = start
    for x in xs:
        t += x
    return t


class TestXsum(unittest.TestCase):
    def test_exact_types_stay_exact(self):
        fr = [Fraction(1, 3), Fraction(1, 7), Fraction(5, 11)]
        self.assertEqual(xsum(fr), Fraction(1, 3) + Fraction(1, 7) + Fraction(5, 11))
        self.assertIsInstance(xsum(fr), Fraction)
        self.assertIsInstance(xsum(iter(fr), Fraction(0)), Fraction)
        self.assertEqual(xsum(x for x in range(10)), 45)
        self.assertIsInstance(xsum([1, 2, 3]), int)
        self.assertEqual(xsum([], Fraction(0)), Fraction(0))
        self.assertEqual(xsum([]), 0)
        # a huge exact total that float arithmetic would round
        self.assertEqual(xsum([10 ** 20, 1, -10 ** 20]), 1)

    def test_float_total_correctly_rounded(self):
        rng = random.Random("xsum-rounding")
        for _ in range(300):
            xs = [rng.uniform(-1, 1) * 10 ** rng.randint(-12, 12) for _ in range(rng.randint(1, 60))]
            exact = sum((Fraction(x) for x in xs), Fraction(0))
            self.assertEqual(xsum(xs), float(exact))
            self.assertEqual(xsum(xs), math.fsum(xs))

    def test_order_independent(self):
        """The pre-3.12 builtin (naive left-to-right) total depends on order; xsum does not."""
        rng = random.Random("xsum-shuffle")
        naive_differs = 0
        for _ in range(200):
            xs = [rng.random() * 10 ** rng.randint(-8, 8) for _ in range(rng.randint(2, 80))]
            ref = xsum(xs)
            for _ in range(5):
                ys = list(xs)
                rng.shuffle(ys)
                self.assertEqual(xsum(ys), ref)
                if naive(ys) != naive(xs):
                    naive_differs += 1
        self.assertGreater(naive_differs, 0)  # the test data does exercise order-dependent float sums

    def test_mixed_and_start(self):
        self.assertEqual(xsum([0.1] * 10), 1.0)
        self.assertEqual(xsum([Fraction(1, 2), 0.25]), 0.75)
        self.assertIsInstance(xsum([Fraction(1, 2), 0.25]), float)
        self.assertEqual(xsum([0.1, 0.2], 0.0), math.fsum([0.1, 0.2]))
        self.assertEqual(xsum([0.1, 0.2], 1.0), math.fsum([0.1, 0.2, 1.0]))
        self.assertEqual(xsum([1, 2], 0.5), 3.5)
        self.assertEqual(xsum(map(float, [1, 2, 3])), 6.0)
        self.assertEqual(fmean([0.1, 0.2, 0.3]), math.fsum([0.1, 0.2, 0.3]) / 3)

    def test_no_builtin_float_sum_in_result_code(self):
        """Every sum in the simulator package and the scripts that write results goes through xsum (tests may use
        the builtin)."""
        import re
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pat = re.compile(r"(?<![\w.])sum\(")
        bad = []
        files = [os.path.join("podsim", f) for f in os.listdir(os.path.join(here, "podsim")) if f.endswith(".py")]
        files += [f for f in os.listdir(here) if f.endswith(".py")]
        for rel in sorted(files):
            if rel in (os.path.join("podsim", "numeric.py"), "run_tier.py"):
                continue
            with open(os.path.join(here, rel)) as fh:
                for i, ln in enumerate(fh, 1):
                    if pat.search(ln.split("#", 1)[0]) and "rho_eff * sum(durations)" not in ln:
                        bad.append("%s:%d" % (rel, i))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
