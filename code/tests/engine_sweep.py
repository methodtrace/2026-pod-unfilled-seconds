"""Optional wide comparison of the vendored undershoot engines with the undershoot companion's public package.

Usage (from code/): SUMSET_UNDERSHOOT_SRC=/path/to/the/release/src python3 tests/engine_sweep.py

Every menu of one to four durations from {5, 6, 10, 15, 20, 30, 45, 60, 75, 90, 120} (561 menus), caps 1 to 10:
gcd reduction, Cohen-Macaulay test, Apery set, the sumset bitsets of engines A and C, and engine B's undershoot
formula at every target in [0, h d] (751,025 targets). Prints the counts and exits 1 on any difference. Runtime:
about an hour on one core. tests/test_engine_equivalence.py runs a smaller grid of the same comparisons.
"""
import importlib
import itertools
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
SRC = os.environ.get("SUMSET_UNDERSHOOT_SRC")
if SRC:
    sys.path.insert(0, SRC)

from podsim import engines as E  # noqa: E402

try:
    PA = importlib.import_module("sumset_undershoot.engines.direct")
    PB = importlib.import_module("sumset_undershoot.engines.homogenized")
    PC = importlib.import_module("sumset_undershoot.engines.intersection")
    PS = importlib.import_module("sumset_undershoot.sumsets")
except ImportError:
    sys.exit("the public sumset_undershoot package is not importable; set SUMSET_UNDERSHOOT_SRC to its src/ folder")

DURS = (5, 6, 10, 15, 20, 30, 45, 60, 75, 90, 120)


def main():
    menus = [m for k in (1, 2, 3, 4) for m in itertools.combinations(DURS, k)]
    targets = bad = 0
    for menu in menus:
        g1, A = E.common.normalize(menu)
        g2, B = PS.normalize(menu)
        if (g1, list(A)) != (g2, list(B)):
            bad += 1
            print("normalize differs:", menu)
            continue
        A0 = list(A)
        d = max(A0)
        bad += E.engine_b.is_cm(A0) != PB.is_cm(A0)
        bad += E.engine_b.apery(A0) != PB.apery(A0)
        for h in range(1, 11):
            if E.engine_a.sumset_bits(A0, h) != PA.sumset_bits(A0, h) or \
                    E.engine_c.sumset_bits_intersection(A0, h) != PC.sumset_bits_intersection(A0, h):
                bad += 1
                print("sumset differs:", menu, h)
            for T in range(h * d + 1):
                targets += 1
                if E.engine_b.undershoot_formula(A0, h, T) != PB.undershoot_formula(A0, h, T):
                    bad += 1
                    print("undershoot differs:", menu, h, T)
                    break
    print("menus %d, targets %d, differences %d" % (len(menus), targets, bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
