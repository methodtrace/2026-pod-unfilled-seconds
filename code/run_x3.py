"""X3: hybrid remainder probability p in {0, 0.25, 0.5, 0.75, 1}, both cap conventions, the tier's menus and caps
(registry.TIERS x3_menus and x3_caps; narrow: seven menus, caps 3..12), demand unlimited (exact Fractions) and
lambda = 8 balanced (exact Poisson sums).
B from L1 = {60, 90, ..., 240}; S uniform on {5, 10, 15, 20, 45} s when present.
Writes <out>/x3/{x3_table.csv, x3_slopes.csv, x3_meta.json} (tables gzipped in the full tier).

Linearity: E[U | p] = (1 - p) E[U | no structured portion] + p E[U | structured portion], exactly, for
every quantity here (the law is a p-mixture and nothing else depends on p). So the slope in p is
E[U | S present] - E[U | S absent]; the script computes every p directly and asserts the identity.
"""
import csv
import json
import os
import sys
import time
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import laws, pools, decompose, grid  # noqa: E402
from podsim import engines as E  # noqa: E402

PS = [Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1)]


def law_for(p):
    return laws.Law.hybrid("L2p%s" % str(p).replace("/", "_"), laws.L1(60, 240, 30), laws.S_SPOTS, p)


def menu_job(args):
    menu, caps = args
    w = pools.weights("balanced")
    m8 = {a: 8 * w[a] for a in pools.UNION}
    LD = {law_for(p).name: law_for(p) for p in PS}
    lc = [(name, conv) for name in sorted(LD) for conv in ("a", "b")]
    vals = grid.menu_values(menu, LD, lc, caps, [m8])
    rows = []
    slopes = []
    for conv in ("a", "b"):
        for h in caps:
            got = {}
            for p in PS:
                name = law_for(p).name
                for si, dem in ((1, "unlimited"), (0, "lambda8_balanced")):
                    r = vals[(name, conv, h, si)]
                    U = r["U"]
                    u = U[frozenset()]
                    us = U[frozenset(["dem"])]
                    sp = decompose.struct_split(us, U[frozenset(["arith", "dem"])], U[frozenset(["cap", "dem"])],
                                                U[frozenset(["arith", "cap", "dem"])])
                    rows.append(REG.canon(dict(menu=" ".join(map(str, menu)), conv=conv, p=float(p), h=h, demand=dem,
                                               U=float(u), Ustruct=float(us), Ustruct_exact=str(us),
                                               share=(float(us) / float(u) if u > 0 else None),
                                               demand_part=float(u) - float(us), arith_part=float(sp["arith"]),
                                               cap_part=float(sp["cap"]), range_residual=float(sp["residual"]),
                                               ET=float(r["ET"]))))
                    got[(p, dem)] = (u, us)
            for dem in ("unlimited", "lambda8_balanced"):
                u0, s0 = got[(PS[0], dem)]
                u1, s1 = got[(PS[-1], dem)]
                for p in PS:
                    up, sp = got[(p, dem)]
                    if dem == "unlimited":
                        assert sp == (1 - p) * s0 + p * s1, (menu, conv, h, p)
                    else:
                        assert abs(up - ((1 - float(p)) * u0 + float(p) * u1)) < 1e-9
                slopes.append(REG.canon(dict(menu=" ".join(map(str, menu)), conv=conv, h=h, demand=dem,
                                             Ustruct_p0=float(s0), Ustruct_p1=float(s1), slope_struct=float(s1 - s0),
                                             slope_struct_exact=str(s1 - s0), U_p0=float(u0), U_p1=float(u1),
                                             slope_U=float(u1 - u0))))
    return rows, slopes


def main():
    cfg = REG.config()
    us = [("menu_" + "-".join(map(str, m)), (tuple(m), cfg["x3_caps"])) for m in cfg["x3_menus"]]
    if REG.units_only([("x3", us, menu_job, False)]):
        return
    out = REG.out_dir("x3")
    t0 = time.time()
    parts = REG.map_units("x3", us, menu_job)
    rows = [r for a, _ in parts for r in a]
    slopes = [r for _, b in parts for r in b]
    REG.write_csv(os.path.join(out, REG.table_name("x3_table")), rows)
    REG.write_csv(os.path.join(out, REG.table_name("x3_slopes")), slopes)
    REG.write_json(os.path.join(out, "x3_meta.json"), dict(tier=cfg["tier"], rows=len(rows), slopes=len(slopes),
                                                           engine_hashes=E.HASHES))
    REG.write_timing(out, "wall", time.time() - t0)
    print("x3 rows", len(rows), "slopes", len(slopes), "%.1f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
