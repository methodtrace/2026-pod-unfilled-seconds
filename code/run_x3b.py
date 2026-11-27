"""X3b: X3 normalized by break length B. For each break, unsold seconds of the dynamic portion divided
by the full break length B (B from L1 = {60, ..., 240}; T = B - S when a structured portion S, uniform on
{5, 10, 15, 20, 45} s, is present with probability p). Reports E[U/B] (mean of ratios) and
60 E[U]/E[B] (seconds per 60 s of break, ratio of means), structural (demand unlimited, exact Fractions)
and total at lambda = 8 balanced (exact Poisson sums), both conventions, the X3 menus and caps of the tier.
Writes <out>/x3b/{x3b_table.csv, x3b_slopes.csv, x3b_meta.json, summary.md} (tables gzipped in the full tier)."""
import csv
import json
import os
import sys
import time
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import levers, laws, pools  # noqa: E402
from podsim import engines as E  # noqa: E402
from podsim.laws import dynamic_cap  # noqa: E402
from podsim.numeric import xsum  # noqa: E402


PS = [Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1)]
BS = list(range(60, 241, 30))
SS = list(laws.S_SPOTS)


def quantities(EU, h, conv, p, exact):
    """E[U/B], E[U] and E[B] for the hybrid law at probability p."""
    one = Fraction(1) if exact else 1.0
    pb = Fraction(1, len(BS))
    ps = Fraction(1, len(SS))
    if not exact:
        pb, ps, p = float(pb), float(ps), float(p)
    eub = 0 * one
    eu = 0 * one
    for B in BS:
        k0 = dynamic_cap(h, False, conv)
        u0 = EU[k0][B]
        eub += pb * (1 - p) * u0 / B
        eu += pb * (1 - p) * u0
        k1 = dynamic_cap(h, True, conv)
        for S in SS:
            u1 = EU[k1][B - S]
            eub += pb * p * ps * u1 / B
            eu += pb * p * ps * u1
    EB = xsum(BS) / len(BS)
    return eub, eu, EB


def sgn(x, tol=1e-12):
    return 0 if abs(x) <= tol else (1 if x > 0 else -1)


def menu_job(args):
    menu, HS = args
    w = pools.weights("balanced")
    m8 = {a: 8 * w[a] for a in pools.UNION}
    caps = sorted({c for h in HS for c in (h, h - 1) if c >= 1}) or [1]
    rows = []
    slopes = []
    for dem, means in (("unlimited", None), ("lambda8_balanced", m8)):
        EU = levers.per_T_expect(menu, means, caps + ([0] if 0 in [h - 1 for h in HS] else []))
        for conv in ("a", "b"):
            for h in HS:
                vals = {}
                for p in PS:
                    eub, eu, EB = quantities(EU, h, conv, p, means is None)
                    vals[p] = (eub, eu)
                    rows.append(REG.canon(dict(menu=" ".join(map(str, menu)), demand=dem, conv=conv, h=h, p=float(p),
                                               E_U=float(eu), E_U_over_B=float(eub),
                                               per60_ratio_of_means=float(60 * eu / EB),
                                               per60_mean_of_ratios=float(60 * eub),
                                               E_U_over_B_exact=(str(eub) if means is None else ""))))
                s_raw = vals[PS[-1]][1] - vals[PS[0]][1]
                s_norm = vals[PS[-1]][0] - vals[PS[0]][0]
                for p in PS:
                    lin = vals[PS[0]][0] + (vals[PS[-1]][0] - vals[PS[0]][0]) * (p if means is None else float(p))
                    assert abs(float(vals[p][0] - lin)) < 1e-12
                slopes.append(REG.canon(dict(menu=" ".join(map(str, menu)), demand=dem, conv=conv, h=h,
                                             slope_U=float(s_raw), slope_U_over_B=float(s_norm),
                                             slope_per60_mean_of_ratios=float(60 * s_norm),
                                             sign_raw=sgn(float(s_raw)), sign_norm=sgn(float(s_norm)),
                                             sign_changes=(sgn(float(s_raw)) != sgn(float(s_norm))))))
    return rows, slopes


def main():
    cfg = REG.config()
    us = [("menu_" + "-".join(map(str, m)), (tuple(m), cfg["x3_caps"])) for m in cfg["x3_menus"]]
    if REG.units_only([("x3b", us, menu_job, False)]):
        return
    out = REG.out_dir("x3b")
    t0 = time.time()
    parts = REG.map_units("x3b", us, menu_job)
    rows = [r for a, _ in parts for r in a]
    slopes = [r for _, b in parts for r in b]
    REG.write_csv(os.path.join(out, REG.table_name("x3b_table")), rows)
    REG.write_csv(os.path.join(out, REG.table_name("x3b_slopes")), slopes)
    REG.write_json(os.path.join(out, "x3b_meta.json"), dict(tier=cfg["tier"], rows=len(rows), engine_hashes=E.HASHES))
    write_md(slopes, cfg, out)
    REG.write_timing(out, "wall", time.time() - t0)
    print("x3b", len(rows), "rows", xsum(1 for s in slopes if s["sign_changes"]), "sign changes",
          "%.1f s" % (time.time() - t0))


def ms(m):
    return "{" + ", ".join(m.split()) + "}"


def write_md(slopes, cfg, out):
    HS = cfg["x3_caps"]
    MENUS = cfg["x3_menus"]
    L = []
    w = L.append
    ix = {(s["menu"], s["demand"], s["conv"], s["h"]): s for s in slopes}
    w("# X3b: X3 normalized by break length")
    w("")
    w("Same grid as X3 (B uniform on {60, 90, ..., 240} s; structured portion S uniform on {5, 10, 15, 20, 45} s "
      "present with probability p in {0, 0.25, 0.5, 0.75, 1}; %d menus; caps %d to %d; conventions a and b; "
      "demand unlimited, exact Fractions, and lambda = 8 balanced, exact Poisson sums; rho = 1). Two normalizations:"
      % (len(MENUS), min(HS), max(HS)))
    w("")
    w("- E[U/B]: unsold seconds of the dynamic portion divided by the full break length B, averaged over breaks "
      "(mean of ratios). Reported also as 60 E[U/B], seconds per 60 s of break.")
    w("- 60 E[U]/E[B]: ratio of means. E[B] = 150 s does not depend on p, so this is the X3 slope times 60/150 and "
      "its sign is the X3 sign by construction; it is in the CSV (`per60_ratio_of_means`) and not discussed further.")
    w("")
    w("Every quantity is affine in p (asserted at all five p), so the slope is the p = 1 value minus the p = 0 "
      "value.")
    w("")
    nchg = xsum(1 for s in slopes if s["sign_changes"])
    w("## Does the sign of the slope in p change?")
    w("")
    w("%d of %d (menu, demand, convention, cap) cells change sign between the raw slope (X3) and the slope of "
      "E[U/B]. Sign is counted with a tolerance of 1e-12 (zero slopes count as sign 0)." % (nchg, len(slopes)))
    w("")
    if nchg:
        w("| Menu | demand | conv | h | slope of E[U] (s per unit p) | slope of 60 E[U/B] (s per 60 s per unit p) |")
        w("| --- | --- | --- | --- | --- | --- |")
        for s in slopes:
            if s["sign_changes"]:
                w("| %s | %s | %s | %d | %.3f | %.3f |" % (ms(s["menu"]), s["demand"], s["conv"], s["h"], s["slope_U"],
                                                        s["slope_per60_mean_of_ratios"]))
        w("")
    for dem in ("unlimited", "lambda8_balanced"):
        w("## Slope of 60 E[U/B] in p (seconds per 60 s of break per unit p), %s" % dem)
        w("")
        w("| Menu | conv | " + " | ".join("h = %d" % h for h in HS) + " |")
        w("| --- | --- |" + " --- |" * len(HS))
        for m in [" ".join(map(str, x)) for x in MENUS]:
            for conv in ("a", "b"):
                w("| %s | %s | %s |" % (ms(m), conv, " | ".join("%.3f" % ix[(m, dem, conv, h)]["slope_per60_mean_of_ratios"]
                                                              for h in HS)))
        w("")
    REG.write_text(os.path.join(out, "summary.md"), "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
