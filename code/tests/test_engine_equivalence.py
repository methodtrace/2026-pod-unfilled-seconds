"""The vendored undershoot engines against the undershoot companion's public package (sumset_undershoot).

Skipped unless the public package can be imported: install it, or set SUMSET_UNDERSHOOT_SRC to the src/ folder of
its release. Compares, for every menu of one to three durations from {5, 6, 10, 15, 20, 30, 45, 60} and caps 1 to 6:
the gcd reduction, the Cohen-Macaulay test, the Apery set, the sumset bitsets of engines A and C, and engine B's
undershoot formula at every target in [0, h d]. A wider sweep (561 menus of up to four durations, caps 1 to 10,
751,025 targets) found no difference.
"""
import importlib
import itertools
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from podsim import engines as E  # noqa: E402

SRC = os.environ.get("SUMSET_UNDERSHOOT_SRC")
if SRC and SRC not in sys.path:
    sys.path.insert(0, SRC)
try:
    PA = importlib.import_module("sumset_undershoot.engines.direct")
    PB = importlib.import_module("sumset_undershoot.engines.homogenized")
    PC = importlib.import_module("sumset_undershoot.engines.intersection")
    PS = importlib.import_module("sumset_undershoot.sumsets")
except ImportError:
    PA = None

DURS = (5, 6, 10, 15, 20, 30, 45, 60)


@unittest.skipIf(PA is None, "public sumset_undershoot package not installed (set SUMSET_UNDERSHOOT_SRC)")
class EngineEquivalence(unittest.TestCase):
    def test_same_results(self):
        for k in (1, 2, 3):
            for menu in itertools.combinations(DURS, k):
                g1, A = E.common.normalize(menu)
                g2, B = PS.normalize(menu)
                self.assertEqual((g1, list(A)), (g2, list(B)), menu)
                A0 = list(A)
                d = max(A0)
                self.assertEqual(E.engine_b.is_cm(A0), PB.is_cm(A0), menu)
                self.assertEqual(E.engine_b.apery(A0), PB.apery(A0), menu)
                for h in range(1, 7):
                    self.assertEqual(E.engine_a.sumset_bits(A0, h), PA.sumset_bits(A0, h), (menu, h))
                    self.assertEqual(E.engine_c.sumset_bits_intersection(A0, h),
                                     PC.sumset_bits_intersection(A0, h), (menu, h))
                    for T in range(h * d + 1):
                        self.assertEqual(E.engine_b.undershoot_formula(A0, h, T),
                                         PB.undershoot_formula(A0, h, T), (menu, h, T))


if __name__ == "__main__":
    unittest.main()
