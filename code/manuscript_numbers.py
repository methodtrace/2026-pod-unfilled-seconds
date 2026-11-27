"""Every number the manuscript cites, computed from the tier outputs, with its source file.

Usage: python3 manuscript_numbers.py --full DIR --narrow DIR --rules DIR --out DIR
  --full    full-tier output folder (extracts and small tables)
  --narrow  narrow-tier output folder (the sampled verifier of the exact sums runs at narrow size in every tier)
  --rules   output folder of analysis_rules.py
  --out     writes numbers.json and numbers.md

Each entry is (key, value, source). The manuscript's numbers are copied from numbers.md; a reviewer can rerun this
script on the released outputs and compare. Values are rounded only for display (numbers.md); numbers.json keeps
full precision.
"""
import argparse
import csv
import gzip
import json
import os
import statistics
import re
import sys
from collections import defaultdict
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("PODSIM_TMAX", "360")

from podsim import structural  # noqa: E402
from podsim.numeric import xsum  # noqa: E402

M7 = ["15 30", "15 30 60", "10 15 30", "6 15 30", "5 15 30", "10 15 20 30", "15 20 30 45 60"]
SHORT3 = ["10 15 30", "6 15 30", "10 15 20 30"]
OUT = []



def hu(x, n):
    """x rounded half up to n decimals, as text (decimal rounding of the shortest repr, so 7.35 gives 7.4, not the
    binary 7.3 of "%.1f")."""
    from decimal import Decimal, ROUND_HALF_UP
    return str(Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP))

def put(key, value, source):
    OUT.append((key, value, source))


def rd(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(x):
    return None if x in ("", None) else float(x)


def intro():
    put("intro.D_15_30_h6_T142", structural.D((15, 30), 6, 142), "podsim.structural.D")
    put("intro.D_15_30_h7_T142", structural.D((15, 30), 7, 142), "podsim.structural.D")
    put("intro.D_15_30_unc_T142", structural.D((15, 30), None, 142), "podsim.structural.D")
    put("intro.D_10_15_30_h6_T142", structural.D((10, 15, 30), 6, 142), "podsim.structural.D")


def structural_table(full):
    src = "full/extracts/x1_structural.csv.gz"
    S = {}
    for r in rd(os.path.join(full, "extracts", "x1_structural.csv.gz")):
        S[(r["law"], r["conv"], r["menu"], r["h"])] = float(r["Ustruct"])
    for m in M7:
        for law, conv, h in (("L1", "a", "6"), ("L2", "a", "6"), ("L2", "a", "8"), ("L2", "b", "8"), ("L3u", "a", "6"),
                             ("L3u", "a", "none"), ("L3s", "a", "none"), ("L7", "a", "none"), ("L6", "a", "none")):
            put("struct.%s.%s%s.h%s" % (m.replace(" ", "_"), law, conv, h), S[(law, conv, m, h)], src)
    # grid control: least cap with zero floor on L1, per menu
    for m in M7:
        z = next(h for h in range(1, 21) if S[("L1", "a", m, str(h))] == 0)
        put("struct.L1_zero_from.%s" % m.replace(" ", "_"), z, src)
    # Wurl slice: uncapped, fully dynamic, demand unlimited, U/ET
    ET = {"L3u": 150, "L3s": None}
    for r in rd(os.path.join(full, "extracts", "x1_structural.csv.gz")):
        if r["menu"] == "15 30" and r["h"] == "none" and r["law"] in ("L3u", "L3s", "L4u5", "L4u15", "L1"):
            put("wurl.15_30.%s.pct" % r["law"], 100 * float(r["unfilled_frac_of_time"]), src)
    # Wurl's 30-second measure: the one-duration menu {30}, uncapped, exact (not on the 86-menu grid)
    from podsim import laws as LW
    for lawname in ("L1", "L4u15", "L4u5", "L3u", "L3s"):
        law = LW.named(lawname)
        et = xsum((w * T for (T, _), w in law.support), Fraction(0))
        d = xsum((w * structural.D((30,), None, T) for (T, _), w in law.support), Fraction(0))
        put("wurl.30.%s.pct" % lawname, float(100 * d / et), "code/podsim (exact, recomputed here)")
    # Reading Wurl's "below 2%" under a mixture: a share q of breaks from an irregular law X, the rest grid breaks
    # (L1, no lattice loss for {15,30}); the time share lost is q E[D; X] / (q E[T; X] + (1 - q) E[T; L1]).
    # Largest q with a loss of at most 2%, and the share of all breaks then off the 15-second lattice.
    et1 = xsum((w * T for (T, _), w in LW.named("L1").support), Fraction(0))
    for lawname in ("L3u", "L3s"):
        law = LW.named(lawname)
        etx = xsum((w * T for (T, _), w in law.support), Fraction(0))
        dx = xsum((w * structural.D((15, 30), None, T) for (T, _), w in law.support), Fraction(0))
        off = xsum((w for (T, _), w in law.support if T % 15), Fraction(0))
        lim = Fraction(2, 100)
        q = lim * et1 / (dx - lim * etx + lim * et1)
        put("wurl.bound.%s.member_pct" % lawname, float(100 * q), "code/podsim (exact, recomputed here)")
        put("wurl.bound.%s.offlattice_pct" % lawname, float(100 * q * off), "code/podsim (exact, recomputed here)")
    # 60-second menu against short-duration menus on L3u: last cap where {15,30,60} is strictly better
    for law, conv in (("L3u", "a"), ("L4u5", "a"), ("L2", "a"), ("L4u15", "a")):
        for m in ("10 15 30", "6 15 30", "5 15 30", "10 15 20 30"):
            better = [h for h in range(1, 21) if S[(law, conv, "15 30 60", str(h))] < S[(law, conv, m, str(h))]]
            worse = [h for h in range(1, 21) if S[(law, conv, "15 30 60", str(h))] > S[(law, conv, m, str(h))]]
            put("rev60.%s%s.%s.better_caps" % (law, conv, m.replace(" ", "_")),
                "%s to %s" % (min(better), max(better)) if better else "none", src)
            put("rev60.%s%s.%s.worse_from" % (law, conv, m.replace(" ", "_")), min(worse) if worse else "none", src)


def rules(rdir):
    src = "analysis/rules/menu_law.csv"
    rows = rd(os.path.join(rdir, "menu_law.csv"))
    n = len(rows)
    put("rules.cells", n, src)
    for h in (3, 4, 6, 8, 20):
        sf = xsum(float(r["feas_%d" % h]) for r in rows)
        st = xsum(float(r["S_%d" % h]) for r in rows)
        put("rule1.share_of_floor.h%d" % h, 100 * sf / st, src)
        put("rule1.cells_with_shortfall.h%d" % h, xsum(1 for r in rows if float(r["feas_%d" % h]) > 0), src)
    for h in (3, 4, 6, 8):
        for lab, f in (("M30plus", lambda r: int(r["M"]) >= 30), ("M20minus", lambda r: int(r["M"]) <= 20)):
            rs = [r for r in rows if f(r)]
            sf = xsum(float(r["feas_%d" % h]) for r in rs)
            st = xsum(float(r["S_%d" % h]) for r in rs)
            put("rule1.%s.share.h%d" % (lab, h), 100 * sf / st, src)
            put("rule1.%s.cells_with_shortfall.h%d" % (lab, h),
                "%d of %d" % (xsum(1 for r in rs if float(r["feas_%d" % h]) > 0), len(rs)), src)
            put("rule1.%s.median_cell_share.h%d" % (lab, h),
                100 * statistics.median(float(r["feas_%d" % h]) / float(r["S_%d" % h]) for r in rs
                                        if float(r["S_%d" % h]) > 0), src)
        for lab, f in (("all", lambda r: True), ("M30plus", lambda r: int(r["M"]) >= 30)):
            for col in ("capcost", "capbeyond"):
                v = [float(r["%s_%d" % (col, h)]) for r in rows if f(r)]
                bl = defaultdict(list)
                for r in rows:
                    if f(r):
                        bl[(r["law"], r["conv"])].append(float(r["%s_%d" % (col, h)]))
                meds = sorted(statistics.median(x) for x in bl.values())
                put("rule2.%s.%s.median.h%d" % (col, lab, h), statistics.median(v), src)
                put("rule2.%s.%s.bylaw_median_range.h%d" % (col, lab, h), "%s to %s" % (hu(meds[0], 2), hu(meds[-1], 2)), src)
    # the FreeWheel mid-roll length bins (L5) at the caps sellers run
    for h in (4, 6, 8):
        a_ = xsum(float(r["feas_%d" % h]) for r in rows if r["law"] == "L5" and int(r["M"]) >= 30)
        b_ = xsum(float(r["S_%d" % h]) for r in rows if r["law"] == "L5" and int(r["M"]) >= 30)
        put("rule1.M30plus.L5.share.h%d" % h, 100 * a_ / b_, src)
        put("rule1.M30plus.L5.mean_shortfall.h%d" % h,
            a_ / xsum(1 for r in rows if r["law"] == "L5" and int(r["M"]) >= 30), src)
        for m in ("15 30", "15 30 60"):
            for r in rows:
                if r["law"] == "L5" and r["menu"] == m:
                    put("rule1.L5.%s.h%d" % (m.replace(" ", "_"), h), "%s of %s s" % (hu(float(r["feas_%d" % h]), 2),
                                                                         hu(float(r["S_%d" % h]), 2)), src)
    for h in (3, 6):
        bl = defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            if int(r["M"]) >= 30:
                bl[(r["law"], r["conv"])][0] += float(r["feas_%d" % h])
                bl[(r["law"], r["conv"])][1] += float(r["S_%d" % h])
        sh = {k: 100 * a_ / b_ for k, (a_, b_) in bl.items()}
        ex = [v for k, v in sh.items() if k[0] != "L6"]
        put("rule1.M30plus.bylaw_range_excl_L6.h%d" % h, "%s to %s" % (hu(min(ex), 1), hu(max(ex), 1)), src)
        put("rule1.M30plus.bylaw_below50_excl_L6.h%d" % h, xsum(1 for v in ex if v < 50), src)
        put("rule1.M30plus.L6.h%d" % h, sh[("L6", "a")], src)
    menus_m = defaultdict(set)
    for r in rows:
        menus_m["M30plus" if int(r["M"]) >= 30 else "M20minus"].add(r["menu"])
    for k, v in menus_m.items():
        put("rule1.%s.menus" % k, len(v), src)
    for h in (3, 6):
        bl = defaultdict(lambda: [0.0, 0.0])
        for r in rows:
            bl[(r["law"], r["conv"])][0] += float(r["feas_%d" % h])
            bl[(r["law"], r["conv"])][1] += float(r["S_%d" % h])
        sh = {k: 100 * a / b for k, (a, b) in bl.items()}
        put("rule1.bylaw_share_range.h%d" % h, "%s to %s" % (hu(min(sh.values()), 1), hu(max(sh.values()), 1)), src)
        put("rule1.bylaw_share_range_excl_L6.h%d" % h,
            "%s to %s" % (hu(min(v for k, v in sh.items() if k[0] != "L6"), 1), hu(max(v for k, v in sh.items() if k[0] != "L6"), 1)), src)
        for law in ("L3u", "L6", "L1", "L7", "L3s"):
            put("rule1.share.%s.h%d" % (law, h), sh[(law, "a")], src)
        put("rule1.share.L2a.h%d" % h, sh[("L2", "a")], src)
    # net cap-regime loss, median over all cells and range of per-law medians
    for h in (3, 4, 6):
        v = sorted(float(r["S_%d" % h]) - float(r["feas_%d" % h]) for r in rows)
        put("rule2.net_median_all.h%d" % h, statistics.median(v), src)
        bylaw = defaultdict(list)
        for r in rows:
            bylaw[(r["law"], r["conv"])].append(float(r["S_%d" % h]) - float(r["feas_%d" % h]))
        meds = sorted(statistics.median(x) for x in bylaw.values())
        put("rule2.net_median_bylaw_range.h%d" % h, "%s to %s" % (hu(meds[0], 1), hu(meds[-1], 1)), src)
    # 15,30 on L3u: gross, feasibility, net at h=3,6
    for r in rows:
        if r["menu"] == "15 30" and r["law"] == "L3u":
            for h in (3, 4, 6):
                put("rule2.15_30.L3u.h%d.gross" % h, float(r["S_%d" % h]), src)
                put("rule2.15_30.L3u.h%d.feas" % h, float(r["feas_%d" % h]), src)
                put("rule2.15_30.L3u.h%d.capbeyond" % h, float(r["capbeyond_%d" % h]), src)
                put("rule2.15_30.L3u.h%d.capcost" % h, float(r["capcost_%d" % h]), src)
    hs = defaultdict(list)
    for r in rows:
        hs[r["law"]].append(99 if r["h_star"] == "none" else int(r["h_star"]))
    for law in ("L1", "L3u", "L6", "L7", "L5"):
        v = sorted(hs[law])
        put("rule2.hstar_median.%s" % law, statistics.median(v), src)
    put("rule2.never_by_20", xsum(1 for r in rows if r["law"] == "L3u" and r["h_star"] == "none"), src)
    put("rule2.never_by_20.L7", xsum(1 for r in rows if r["law"] == "L7" and r["h_star"] == "none"), src)
    # convention (b) with two reserved spots: at cap 1 the reserved spots are placed past the cap
    put("hybrid.conv_b_cap_below_spots.cells", xsum(1 for r in rows if r["law"] == "L2two" and r["conv"] == "b"),
        src)
    # rule 3
    IRR = {"L3u": 60, "L6": 15, "L7": 240}
    for law, lo in IRR.items():
        rs = [r for r in rows if r["law"] == law]
        past = [r for r in rs if int(r["conductor"]) <= lo]
        ok = [r for r in past if abs(float(r["S_unc"]) - float(r["half_g"])) <= 0.1]
        put("rule3.%s.past_conductor" % law, len(past), src)
        put("rule3.%s.within_0.1_of_half_g" % law, len(ok), src)
        eq = [r for r in past if Fraction(r["S_unc_exact"]) == Fraction(int(r["g"]) - 1, 2)]
        put("rule3.%s.equal_half_g" % law, len(eq), src)
    fam = {"irregular": lambda r: r["law"] in IRR, "hybrid": lambda r: r["law"].startswith("L2"),
           "livemix": lambda r: r["law"].startswith("L8"), "lattice": lambda r: r["law"].startswith("L4"),
           "skewed_binned": lambda r: r["law"] in ("L3s", "L5"), "grid": lambda r: r["law"] == "L1"}
    tot = ok = 0
    for k, f in fam.items():
        rs = [r for r in rows if f(r)]
        o = [r for r in rs if abs(float(r["gap_unc_minus_lattice"])) <= 0.1]
        put("rule3.Tmodg.%s.cells" % k, len(rs), src)
        put("rule3.Tmodg.%s.within" % k, len(o), src)
        tot += len(rs)
        ok += len(o)
    put("rule3.Tmodg.all.cells", tot, src)
    put("rule3.Tmodg.all.within", ok, src)
    for g in (1, 2, 3, 5, 6, 10, 15, 20, 30):
        v = sorted({round(float(r["S_unc"]), 2) for r in rows if r["law"] == "L3u" and int(r["g"]) == g and
                    int(r["conductor"]) <= 60})
        put("rule3.L3u.floor_by_g.%d" % g, ", ".join(hu(x, 2) for x in v), src)
    # distinct uncapped cells: conventions (a) and (b) share the uncapped floor, so count hybrid laws once
    dist = [r for r in rows if r["conv"] != "b"]
    okd = [r for r in dist if abs(float(r["gap_unc_minus_lattice"])) <= 0.1]
    put("rule3.Tmodg.distinct.cells", len(dist), src)
    put("rule3.Tmodg.distinct.within", len(okd), src)
    hd = [r for r in dist if r["law"].startswith("L2")]
    put("rule3.Tmodg.distinct.hybrid.cells", len(hd), src)
    put("rule3.Tmodg.distinct.hybrid.within",
        xsum(1 for r in hd if abs(float(r["gap_unc_minus_lattice"])) <= 0.1), src)
    # rule 4: hybrid predictions
    spots = {"L2": (5, 10, 15, 20, 45), "L2s1530": (15, 30), "L2s510": (5, 10), "L2s7812": (7, 8, 12), "L2s60": (60,)}
    for law, Sset in spots.items():
        for g in (5, 15):
            pred = Fraction(xsum((-x) % g for x in Sset), len(Sset))
            rs = [r for r in rows if r["law"] == law and r["conv"] == "a" and int(r["g"]) == g]
            o = xsum(1 for r in rs if abs(float(r["S_unc"]) - float(pred)) <= 0.1)
            put("rule4.%s.g%d.pred" % (law, g), float(pred), src)
            put("rule4.%s.g%d.match" % (law, g), "%d of %d" % (o, len(rs)), src)
    # rule 5
    idx = {(r["law"], r["menu"]): r for r in rows}
    lin = xsum(1 for m in {r["menu"] for r in rows}
              if 2 * Fraction(idx[("L8q50", m)]["S_unc_exact"]) ==
              Fraction(idx[("L8q25", m)]["S_unc_exact"]) + Fraction(idx[("L8q75", m)]["S_unc_exact"]))
    put("rule5.linear_menus", lin, src)
    for m in ("15 30", "10 15 30"):
        for q in ("25", "50", "75"):
            put("rule5.%s.q%s" % (m.replace(" ", "_"), q), float(idx[("L8q" + q, m)]["S_unc"]), src)
    # rule 6
    src6 = "analysis/rules/levers.csv"
    lev = rd(os.path.join(rdir, "levers.csv"))
    nb = cap = lng = shrt = tie = 0
    nb60 = cap60 = lng60 = shrt60 = tie60 = 0
    tp = fp = fn = tn = 0
    tpi = fpi = fni = tni = 0
    pc = defaultdict(int)
    for r in lev:
        adds = {int(k[4:]): float(v) for k, v in r.items() if k.startswith("add_") and v != ""}
        below = r["below_hstar"] in ("True", "1", "true")
        if below:
            # exact classification written by analysis_rules.py (the CSV floats are rounded)
            c = r["below_class"]
            if not c:
                continue
            nb += 1
            cap += c == "cap"
            lng += c == "long"
            shrt += c == "short"
            tie += c == "long-short tie"
            if int(r["M"]) < 60:  # menus whose longest duration is below the union's longest, 60 s
                nb60 += 1
                cap60 += c == "cap"
                lng60 += c == "long"
                shrt60 += c == "short"
                tie60 += c == "long-short tie"
        else:
            for d, v in adds.items():
                pred = r["gcd_drop_%d" % d] in ("1", "True")
                got = r["gain_pos_%d" % d] in ("1", "True")
                irr = r["law"] in IRR
                if float(r["mass_below_conductor"]) == 0:
                    pc[(pred, got)] += 1
                if pred and got:
                    tp += 1
                    tpi += irr
                elif pred:
                    fp += 1
                    fpi += irr
                elif got:
                    fn += 1
                    fni += irr
                else:
                    tn += 1
                    tni += irr
    put("rule6.below.cells", nb, src6)
    put("rule6.below.cap_best_pct", 100 * cap / nb, src6)
    put("rule6.below.long_add_pct", 100 * lng / nb, src6)
    put("rule6.below.short_add_pct", 100 * shrt / nb, src6)
    put("rule6.below.long_short_tie_pct", 100 * tie / nb, src6)
    put("rule6.below.classes", "cap %d, long %d, short %d, long-short tie %d" % (cap, lng, shrt, tie), src6)
    put("rule6.below.cap_or_long_pct", 100 * (cap + lng) / nb, src6)
    put("rule6.below.M_lt60.cells", nb60, src6)
    put("rule6.below.M_lt60.cap_best_pct", 100 * cap60 / nb60, src6)
    put("rule6.below.M_lt60.long_add_pct", 100 * lng60 / nb60, src6)
    put("rule6.below.M_lt60.short_add_pct", 100 * shrt60 / nb60, src6)
    put("rule6.below.M_lt60.long_short_tie_pct", 100 * tie60 / nb60, src6)
    put("rule6.above.precision_all", tp / (tp + fp), src6)
    put("rule6.above.recall_all", tp / (tp + fn), src6)
    put("rule6.above.precision_irregular", tpi / (tpi + fpi), src6)
    put("rule6.above.recall_irregular", tpi / (tpi + fni), src6)
    put("rule6.above.counts_irregular", "%d, %d, %d, %d" % (tpi, fpi, fni, tni), src6)
    put("rule6.above.past_conductor.items", xsum(pc.values()), src6)
    put("rule6.above.past_conductor.gain_without_gcd_drop", pc[(False, True)], src6)
    put("rule6.above.past_conductor.no_gcd_drop", pc[(False, True)] + pc[(False, False)], src6)
    put("rule6.above.past_conductor.gain_with_gcd_drop", pc[(True, True)], src6)
    # lever table for {15,30} on L2 a
    for r in lev:
        if r["menu"] == "15 30" and r["law"] == "L2" and r["conv"] == "a" and r["h"] in ("4", "6", "8"):
            for k in ("S", "cap1", "add_6", "add_10", "add_60", "add_20", "add_45", "add_5"):
                put("rule6.tab.15_30.L2a.h%s.%s" % (r["h"], k), num(r[k]), src6)


def interaction():
    """Exact two-player split terms for the Fig. 3 menus (L3u, h = 6)."""
    from podsim import laws as LW
    src = "code/podsim (exact, recomputed here)"
    law = LW.named("L3u")
    for A, lab in (((15, 30), "15_30"), ((10, 15, 30), "10_15_30")):
        R = tuple(range(min(A), max(A) + 1))
        V = {}
        for nm, menu in (("menu", A), ("range", R)):
            for h in (6, None):
                V[(nm, h)] = xsum((w * structural.D(menu, h, T) for (T, _), w in law.support), Fraction(0))
        iac = V[("menu", 6)] - V[("range", 6)] - V[("menu", None)] + V[("range", None)]
        put("split.%s.L3u.h6.V_range_h" % lab, float(V[("range", 6)]), src)
        put("split.%s.L3u.h6.I_AC" % lab, float(iac), src)


def demand(full):
    src = "full/extracts/xd_m7.csv.gz"
    rows = rd(os.path.join(full, "extracts", "xd_m7.csv.gz"))
    for r in rows:
        if r["law"] == "L3u" and r["h"] == "6" and r["count_law"] == "poisson" and r["weights"] == "d1530" and \
                r["menu"] in ("15 30", "10 15 30") and r["lam"] in ("1", "4", "16", "64", "256"):
            m = r["menu"].replace(" ", "_")
            U, us, ET = float(r["U"]), float(r["Ustruct"]), float(r["ET"])
            put("fig3.%s.lam%s.U" % (m, r["lam"]), U, src)
            put("fig3.%s.lam%s.struct" % (m, r["lam"]), us, src)
            put("fig3.%s.lam%s.demand" % (m, r["lam"]), float(r["demand_part"]), src)
            put("fig3.%s.lam%s.ready95" % (m, r["lam"]), 0.05 * (ET - U), src)
            put("fig3.%s.lam%s.U95" % (m, r["lam"]), U + 0.05 * (ET - U), src)
            put("fig3.%s.lam%s.arith" % (m, r["lam"]), float(r["arith_part"]), src)
            put("fig3.%s.lam%s.cap" % (m, r["lam"]), float(r["cap_part"]), src)
    # eq. (4) under other orders, {15,30}, h 6, L3u, lambda 1, readiness 0.95, from the same unrounded record
    for r in rows:
        if r["law"] == "L3u" and r["h"] == "6" and r["count_law"] == "poisson" and r["weights"] == "d1530" and \
                r["menu"] == "15 30" and r["lam"] == "1":
            st_, dem, ET, rho = float(r["Ustruct"]), float(r["demand_part"]), float(r["ET"]), 0.95
            Finf, Fn = ET - st_, ET - st_ - dem
            o = src + " (eq. 4 under other orders)"
            put("order.paper.demand", dem, o)
            put("order.paper.ready", (1 - rho) * Fn, o)
            put("order.ready_first.demand", rho * (Finf - Fn), o)
            put("order.ready_first.ready", (1 - rho) * Finf, o)
            put("order.shapley.demand", (dem + rho * dem) / 2, o)
            put("order.shapley.ready", ((1 - rho) * Fn + (1 - rho) * Finf) / 2, o)
    # overdispersion effect: nb1 versus poisson at lambda 16, {15,30}, L3u, h 6, d1530
    for r in rows:
        if r["law"] == "L3u" and r["h"] == "6" and r["weights"] == "d1530" and r["menu"] == "15 30" and r["lam"] == "16":
            put("demand.15_30.L3u.h6.d1530.lam16.U.%s" % r["count_law"], float(r["U"]), src)


def demand_x1(full):
    src1 = "full/extracts/x1_m7.csv.gz"
    x1 = rd(os.path.join(full, "extracts", "x1_m7.csv.gz"))
    sh = [float(r["share"]) for r in x1 if r["law"] == "L3u" and r["h"] == "8" and r["weights"] == "d1530" and
          r["lam"] == "64" and float(r["rho"]) == 1.0 and r["share"] != ""]
    put("share.L3u.h8.d1530.lam64.range", "%s to %s" % (hu(min(sh), 2), hu(max(sh), 2)), src1)
    for r in x1:
        if r["law"] == "L3u" and r["h"] == "6" and r["menu"] == "15 30" and float(r["rho"]) == 1.0 and \
                r["weights"] in ("balanced", "d1530") and r["lam"] in ("2", "16", "64"):
            put("share.15_30.L3u.h6.%s.lam%s" % (r["weights"], r["lam"]), float(r["share"]), src1)
    rp = [float(r["ready_part"]) for r in x1 if r["law"] in ("L3u", "L2") and r["conv"] == "a" and
          r["weights"] == "balanced" and r["lam"] == "8" and abs(float(r["rho"]) - 0.95) < 1e-9 and
          r["h"] in ("4", "6", "8")]
    put("ready.rho95.bal.lam8.range", "%s to %s" % (hu(min(rp), 2), hu(max(rp), 2)), src1)


def levers_finite(full):
    src = "full/extracts/x2_m7.csv.gz"
    rows = [r for r in rd(os.path.join(full, "extracts", "x2_m7.csv.gz")) if r["weights"] != "unlimited" and
            float(r["rho"]) == 1.0]
    put("range.baselines", len(rows), src)
    by = defaultdict(lambda: [0.0, 0.0, 0, 0.0, 0.0, 0.0])
    for r in rows:
        a = by[r["weights"]]
        a[0] += float(r["range"])
        a[1] += float(r["dur_best"] or 0)
        a[2] += 1
        a[3] = max(a[3], float(r["range_se"]))
        a[4] += float(r["range_e0"])
        a[5] += float(r["range_e0.2"])
    for w, a in by.items():
        put("range.%s.mean" % w, a[0] / a[2], src)
        put("range.%s.mean_dur_best" % w, a[1] / a[2], src)
        put("range.%s.max_se" % w, a[3], src)
        put("range.%s.mean_eps0" % w, a[4] / a[2], src)
        put("range.%s.mean_eps0.2" % w, a[5] / a[2], src)
    for w in sorted(by):
        v = sorted(float(r["range"]) for r in rows if r["weights"] == w)
        put("range.%s.median" % w, statistics.median(v), src)
        put("range.%s.p90" % w, v[int(0.9 * (len(v) - 1))], src)
        pm = defaultdict(list)
        for r in rows:
            if r["weights"] == w:
                pm[r["menu"]].append(float(r["range"]))
        mm = sorted((xsum(x) / len(x), m) for m, x in pm.items())
        put("range.%s.per_menu_mean_range" % w, "%s s ({%s}) to %s s ({%s})" % (
            hu(mm[0][0], 2), ",".join(mm[0][1].split()), hu(mm[-1][0], 2), ",".join(mm[-1][1].split())), src)
    # control: for {15,30} at nonstandard share 0 the range admits exactly one more standard length, 20 s, whose
    # exact gain is the dur:20 column; the sampled range gain should match it
    ctl = [(float(r["range_e0"]), float(r["dur:20"])) for r in rows if r["menu"] == "15 30" and r.get("dur:20") not in
           (None, "")]
    put("range.control_15_30.cells", len(ctl), src)
    put("range.control_15_30.max_abs_err", max(abs(a - b) for a, b in ctl), src)
    put("range.control_15_30.mean_err", xsum(a - b for a, b in ctl) / len(ctl), src)
    put("range.control_15_30.zero_sampled_positive_exact", xsum(1 for a, b in ctl if a <= 1e-9 < b), src)
    # the same control for {10,15,30}: at share 0 the range [10, 30] admits exactly one more standard length, 20 s
    ctl = [(float(r["range_e0"]), float(r["dur:20"])) for r in rows if r["menu"] == "10 15 30" and r.get("dur:20") not in
           (None, "")]
    put("range.control_10_15_30.cells", len(ctl), src)
    put("range.control_10_15_30.max_abs_err", max(abs(a - b) for a, b in ctl), src)
    put("range.control_10_15_30.mean_err", xsum(a - b for a, b in ctl) / len(ctl), src)
    put("range.control_10_15_30.zero_sampled_positive_exact", xsum(1 for a, b in ctl if a <= 1e-9 < b), src)
    # cells where the sampled range falls more than two standard errors below an exact interior added duration
    # that it dominates (the ranking uses the bound; this counts how often the estimate alone would contradict it)
    viol = 0
    for r in rows:
        menu = [int(x) for x in r["menu"].split()]
        inner = [float(r["dur:%d" % c]) for c in (5, 6, 10, 15, 20, 30, 45, 60)
                 if min(menu) < c < max(menu) and c not in menu and r.get("dur:%d" % c) not in (None, "")]
        if inner and float(r["range"]) + 2 * float(r["range_se"]) < max(inner) - 1e-9:
            viol += 1
    put("range.below_dominance_bound", "%d of %d" % (viol, len(rows)), src)
    win = xsum(1 for r in rows if r["best_primary"] == "range")
    tie = xsum(1 for r in rows if r["best_primary"].startswith("tie:") and "range" in r["best_primary"])
    put("range.wins_outright", win, src)
    put("range.ties", tie, src)
    for k in ("dur_best", "cap+1"):
        put("winner.%s" % k, xsum(1 for r in rows if r["best_primary"] == k), src)
    put("winner.none", xsum(1 for r in rows if r["best_primary"] == "none"), src)


def levers_split(full):
    """Share of finite-demand lever winners with no structural gain, by cap regime (x2/split.md)."""
    src = "full/x2/split.md"
    t = defaultdict(lambda: [0, 0])
    with open(os.path.join(full, "x2", "split.md"), encoding="utf-8") as f:
        for line in f:
            p = [x.strip() for x in line.split("|")]
            if len(p) < 7 or not p[5].isdigit():
                continue
            n = int(p[5])
            t[p[1]][1] += n
            if p[4] == "no structural gain":
                t[p[1]][0] += n
    for reg, name in (("h <= 4", "h_le4"), ("h 5-7", "h5_7"), ("h >= 8", "h_ge8"), ("uncapped", "uncapped")):
        a, b = t[reg]
        put("split.no_structural_gain_pct.%s" % name, 100 * a / b, src)


def table_sizes(full):
    for f, k in (("x1/x1_meta.json", "x1"), ("x2/x2_meta.json", "x2"), ("xd/xd_meta.json", "xd")):
        put("rows.%s" % k, json.load(open(os.path.join(full, f)))["rows"], "full/" + f)


def levers_meta(full):
    meta = json.load(open(os.path.join(full, "x2", "x2_meta.json")))
    rl = meta["range_lever"]
    put("range.check.cells", rl["baseline_check_cells"], "full/x2/x2_meta.json")
    put("range.check.max_abs_diff", rl["baseline_check_max_abs_diff"], "full/x2/x2_meta.json")
    put("range.check.z_over_4", rl["baseline_check_z_over_4"], "full/x2/x2_meta.json")
    put("range.check.zero_se", rl["baseline_check_zero_se_diff"], "full/x2/x2_meta.json")
    put("range.samples_full", rl["samples"], "full/x2/x2_meta.json")
    put("x2.negative_gains", meta["negative_gains"], "full/x2/x2_meta.json")
    st = meta["stability"]
    for k in ("cases", "stable_targets", "targets", "gain_targets_at_stable"):
        put("stability.%s" % k, st[k], "full/x2/x2_meta.json")
    # split of finite-demand winners by regime (all 86 menus)
    txt = open(os.path.join(full, "x2", "split.md"), encoding="utf-8").read()
    agg = defaultdict(int)
    for m in re.finditer(r"^\| (h <= 4|h 5-7|h >= 8|uncapped) \| ([^|]+) \| ([^|]+) \| (structural|no structural gain) \| (\d+) \|",
                         txt, flags=re.M):
        agg[(m.group(1), "structural" if m.group(4) == "structural" else "no structural gain")] += int(m.group(5))
    for reg in ("h <= 4", "h 5-7", "h >= 8", "uncapped"):
        s, u = agg[(reg, "structural")], agg[(reg, "no structural gain")]
        put("split.%s.no_structural_gain" % reg.replace(" ", ""), "%d of %d" % (u, s + u), "full/x2/split.md")
    put("split.baselines", int(re.search(r"(\d+) baselines", txt).group(1)), "full/x2/split.md")
    put("split.with_winner", xsum(int(x) for x in re.findall(r"^\|[^|]+\|[^|]+\|[^|]+\| (?:structural|no structural gain) \| (\d+) \|",
                                                           txt, flags=re.M)), "full/x2/split.md")


def hybrid(full):
    src = "full/x3/x3_slopes.csv.gz"
    for r in rd(os.path.join(full, "x3", "x3_slopes.csv.gz")):
        if r["menu"] == "15 30" and r["demand"] == "unlimited" and r["h"] in ("3", "8", "9", "12"):
            put("hyb.slope.15_30.%s.h%s" % (r["conv"], r["h"]), float(r["slope_struct"]), src)
    rows = rd(os.path.join(full, "x3", "x3_slopes.csv.gz"))
    lam = [float(r["slope_U"]) for r in rows if r["demand"] != "unlimited"]
    put("hyb.slopeU.lam8.neg", "%d of %d" % (xsum(1 for x in lam if x < 0), len(lam)), src)
    sb = rd(os.path.join(full, "x3b", "x3b_slopes.csv.gz"))
    put("hyb.x3b.rows", len(sb), "full/x3b/x3b_slopes.csv.gz")


def offset0(rows, prefix, src):
    """Breaks that are whole seconds (offset 0, as on a scheduled grid): every creative one frame long (sys+) or
    short (sys-), with no overrun tolerance or a one-frame tolerance; delta0 = E[U_tick] - E[U_int]."""
    if not rows or "delta0" not in rows[0]:
        return
    for law, conv in (("L1", "a"), ("L2", "a"), ("L3u", "a")):
        for model in ("sys+", "sys-"):
            for tol in ("0", "3003"):
                v = [(float(r["delta0"]), r["menu"], r["h"]) for r in rows if r["law"] == law and r["conv"] == conv
                     and r["model"] == model and r["eps_ticks"] == "3003" and r["tol_ticks"] == tol]
                if not v:
                    continue
                key = "%s.%s%s.%s.tol%s" % (prefix, law, conv, model, tol)
                put(key + ".delta_range", "%s to %s" % (hu(min(v)[0], 2), hu(max(v)[0], 2)), src)
                mx = max(v)
                put(key + ".max_cell", "%s s, {%s}, h %s" % (hu(mx[0], 2), ",".join(mx[1].split()), mx[2]), src)
                fin = [x for x in v if x[2] != "none"]
                unc = [x for x in v if x[2] == "none"]
                if fin:
                    put(key + ".finite_max", max(fin)[0], src)
                if unc:
                    put(key + ".uncapped_range", "%s to %s" % (hu(min(unc)[0], 2), hu(max(unc)[0], 2)), src)
    for menu, h in (("15 30", "8"), ("30 60", "4"), ("15 30", "4"), ("15 30", "6")):
        for r in rows:
            if r["law"] == "L1" and r["conv"] == "a" and r["menu"] == menu and r["h"] == h and \
                    r["model"] == "sys+" and r["eps_ticks"] == "3003" and r["tol_ticks"] == "0":
                put("%s.L1a.sys+.tol0.%s.h%s" % (prefix, menu.replace(" ", "_"), h), float(r["delta0"]), src)


def ticks(full):
    src = "full/extracts/x7a_m7.csv.gz"
    rows = rd(os.path.join(full, "extracts", "x7a_m7.csv.gz"))
    small = [r for r in rows if r["model"] in ("sys+", "sys-") and int(r["eps_ticks"]) <= 3003 or r["model"] == "ntsc"]
    for law, conv in (("L3u", "a"), ("L2", "a"), ("L1", "a")):
        for capd in ("capped", "uncapped"):
            v = [float(r["delta"]) for r in small if r["law"] == law and r["conv"] == conv and
                 ((r["h"] == "none") == (capd == "uncapped"))]
            if v:
                put("ticks.%s%s.%s.delta_range" % (law, conv, capd), "%s to %s" % (hu(min(v), 2), hu(max(v), 2)), src)
    for model in ("sys+", "ntsc"):
        v = [float(r["delta"]) for r in rows if r["law"] == "L1" and r["model"] == model and
             (int(r["eps_ticks"]) <= 3003 or model == "ntsc")]
        put("ticks.L1.%s.max_delta" % model, max(v), src)
    for et, lab in ((9000, "100ms"), (45000, "500ms")):
        v = [float(r["delta"]) for r in rows if r["law"] == "L1" and r["model"] == "sys+" and int(r["eps_ticks"]) == et]
        if v:
            put("ticks.L1.sys+.%s.max_delta" % lab, max(v), src)
    n = ch = 0
    for r in rows:
        if int(r["eps_ticks"]) > 9000 and r["model"] != "ntsc":
            continue
        di = float(r["phi_arith_int"]) - float(r["phi_cap_int"])
        dt = float(r["phi_arith_tick"]) - float(r["phi_cap_tick"])
        if abs(di) >= 0.5:
            n += 1
            ch += di * dt < 0
    put("ticks.order_changes_up_to_100ms", "%d of %d" % (ch, n), src)
    offset0(rows, "ticks.offset0", src)
    # independent per-creative perturbation up to one frame (part B, sampled; study menus, L1, L2 and L3u)
    srcb = "full/x7/x7_partB.csv.gz"
    pb = [r for r in rd(os.path.join(full, "x7", "x7_partB.csv.gz")) if r["model"] == "indep" and
          int(r["eps_ticks"]) <= 3003]
    for q in ("U", "Ustruct", "demand"):
        v = [float(r["paired_diff"]) for r in pb if r["quantity"] == q]
        put("ticks.partB.%s.diff_range" % q, "%s to %s" % (hu(min(v), 2), hu(max(v), 2)), srcb)
    put("ticks.partB.max_se", max(float(r["paired_se"]) for r in pb), srcb)
    # the same systematic-perturbation quantities over every menu, where the extract exists
    pa = os.path.join(full, "extracts", "x7a_l3.csv.gz")
    if os.path.exists(pa):
        src3 = "full/extracts/x7a_l3.csv.gz"
        rows = rd(pa)
        small = [r for r in rows if r["model"] in ("sys+", "sys-") and int(r["eps_ticks"]) <= 3003 or r["model"] == "ntsc"]
        for law, conv in (("L3u", "a"), ("L2", "a")):
            for capd in ("capped", "uncapped"):
                v = [float(r["delta"]) for r in small if r["law"] == law and r["conv"] == conv and
                     ((r["h"] == "none") == (capd == "uncapped"))]
                if v:
                    put("ticks.all.%s%s.%s.delta_range" % (law, conv, capd), "%s to %s" % (hu(min(v), 2), hu(max(v), 2)), src3)
        for model in ("sys+", "ntsc"):
            v = [float(r["delta"]) for r in rows if r["law"] == "L1" and r["model"] == model and
                 (int(r["eps_ticks"]) <= 3003 or model == "ntsc")]
            put("ticks.all.L1.%s.max_delta" % model, max(v), src3)
        offset0(rows, "ticks.all.offset0", src3)
        for et, lab in ((9000, "100ms"), (45000, "500ms")):
            v = [float(r["delta"]) for r in rows if r["law"] == "L1" and r["model"] == "sys+" and int(r["eps_ticks"]) == et]
            if v:
                put("ticks.all.L1.sys+.%s.max_delta" % lab, max(v), src3)


def clutter(full):
    src = "full/extracts/x5_frontier_m7.csv.gz"
    rows = rd(os.path.join(full, "extracts", "x5_frontier_m7.csv.gz"))
    for r in rows:
        if r["law"] == "L2" and r["conv"] == "a" and r["lam"] == "64" and r["scheme"] == "balanced" and r["h"] == "8" \
                and r["anchor"] == "base":
            m = r["menu"].strip("{}").replace(",", "_")
            c = round(float(r["c_dollars"]))
            if abs(float(r["c_dollars"]) - c) < 1e-6 and c in (0, 5, 10, 15, 20):
                put("clutter.L2a.h8.%s.c%d" % (m, c), "%s s, %s ads" % (hu(float(r["unfilled_s"]), 1), hu(float(r["ads"]), 2)), src)
        if r["law"] == "L3u" and r["lam"] == "64" and r["scheme"] == "balanced" and r["h"] == "none" \
                and r["anchor"] == "base":
            m = r["menu"].strip("{}").replace(",", "_")
            c = round(float(r["c_dollars"]))
            if abs(float(r["c_dollars"]) - c) < 1e-6 and c in (0, 10, 20):
                put("fig4.L3u.unc.%s.c%d" % (m, c), "%s s, %s ads" % (hu(float(r["unfilled_s"]), 1), hu(float(r["ads"]), 2)), src)


def clutter_matched(full):
    v = json.load(gzip.open(os.path.join(full, "x5", "matched_cells.json.gz"), "rt"))
    # A cell counts as "below" in two ways: the short-duration frontier is below the {15,30} frontier at h + 1 at a
    # majority of the clutter costs where the two frontiers overlap in ads per break ("overlap"), or at a majority
    # of all 13 costs ("strict"); "none" counts cells where the frontiers never overlap.
    agg = defaultdict(lambda: [0, 0, 0, 0])
    for k, d in v.items():
        law, lam, sc, menu, h, an = k.split("|")
        menu = " ".join(menu.strip("{}").split(","))
        if an != "base" or menu not in SHORT3:
            continue
        defined = d["k_points"] - d["frontier_na"]
        below = defined > 0 and d["frontier_below"] > defined / 2
        strict = d["frontier_below"] > d["k_points"] / 2
        key = (sc, "h<=6" if h != "none" and int(h) <= 6 else "h>=7")
        agg[key][0] += below
        agg[key][1] += 1
        agg[key][2] += strict
        agg[key][3] += defined == 0
    tot = defaultdict(lambda: [0, 0, 0, 0])
    for (sc, hr), vals in agg.items():
        for i, x in enumerate(vals):
            tot[sc][i] += x
    for sc, (b, n, st, na) in sorted(tot.items()):
        put("clutter.short_below.%s.all" % sc, "%d of %d" % (b, n), "full/x5/matched_cells.json.gz")
        put("clutter.short_below_strict.%s.all" % sc, "%d of %d" % (st, n), "full/x5/matched_cells.json.gz")
        put("clutter.no_overlap.%s.all" % sc, "%d of %d" % (na, n), "full/x5/matched_cells.json.gz")
    for (sc, hr), (b, n, st, na) in sorted(agg.items()):
        put("clutter.short_below.%s.%s" % (sc, hr), "%d of %d" % (b, n), "full/x5/matched_cells.json.gz")
        put("clutter.short_below_strict.%s.%s" % (sc, hr), "%d of %d" % (st, n), "full/x5/matched_cells.json.gz")
        put("clutter.no_overlap.%s.%s" % (sc, hr), "%d of %d" % (na, n), "full/x5/matched_cells.json.gz")



def hulls(full):
    hc = json.load(open(os.path.join(full, "x5", "hullchecks.json")))
    put("hull.pairs", hc["total"], "full/x5/hullchecks.json")
    put("hull.violations", hc["violations"], "full/x5/hullchecks.json")
    put("hull.menus", len(hc["menus"]), "full/x5/hullchecks.json")


def practice(full):
    src = "full/x6/x6_aggregates.json"
    A = json.load(open(os.path.join(full, "x6", "x6_aggregates.json")))
    keys = ["conditions", "gap_nofloor_mean", "floor_added_mean", "P3.short", "P3.max", "P3.rev", "P3d.short",
            "P3d.max", "P3d.rev", "P3d.rev_max_condition", "P4.short", "P4.rev", "V1.gap_mean", "V2.gap_mean",
            "V1.rev_gain", "V2.rev_gain", "V1.floor_adds.ps50", "V1.floor_adds.ps67", "V1.floor_adds.ps100",
            "V1.floor_adds.dfA", "nofloor.gap_above_2se", "V1.nofloor_gap", "V2.nofloor_gap", "gap_max"]
    keys += sorted(k for k in A if ".short_nofloor" in k or ".short_floored" in k or ".short_floor." in k)
    for k in keys:
        put("x6." + k, A[k], src)


def reversals(full):
    """Reversal shares and magnitudes from the unrounded by-law table, precision and recall from the exact counts."""
    src = "full/x4/by_law.csv"
    for r in rd(os.path.join(full, "x4", "by_law.csv")):
        if r["pairs"] != "3655":
            continue
        put("rev.%s.share" % r["law"], float(r["share"]), src)
        put("rev.%s.median_cap" % r["law"], r["point_median"], src)
        put("rev.%s.mag_median" % r["law"], float(r["mag_median_s"]), src)
        put("rev.%s.mag_max" % r["law"], float(r["mag_max_s"]), src)
    src = "full/x4/x4_summary.json"
    p3 = json.load(open(os.path.join(full, "x4", "x4_summary.json")))["p3"]
    put("rev.cells", p3["tp"] + p3["fp"] + p3["fn"] + p3["tn"], src)
    put("rev.observed", p3["tp"] + p3["fn"], src)
    put("rev.precision", p3["tp"] / (p3["tp"] + p3["fp"]), src)
    put("rev.recall", p3["tp"] / (p3["tp"] + p3["fn"]), src)
    d = p3["defined"]
    put("rev.recall_defined", d["tp"] / (d["tp"] + d["fn"]), src)


def checks(narrow, full):
    v = json.load(open(os.path.join(narrow, "x1", "x1_verify.json")))
    z = [abs(r["z"]) for r in v["rows"]]
    put("verify.comparisons", len(z), "narrow/x1/x1_verify.json")
    put("verify.max_abs_z", max(z), "narrow/x1/x1_verify.json")
    put("verify.blocks", v["blocks"], "narrow/x1/x1_verify.json")
    put("verify.breaks_per_block", v["n"], "narrow/x1/x1_verify.json")
    put("verify.max_se_U", max(r["se"] for r in v["rows"] if r["q"] == "U"), "narrow/x1/x1_verify.json")
    c = json.load(open(os.path.join(full, "checks", "checks.json")))
    put("checks.EA", c["item1"]["E-A comparisons"], "full/checks/checks.json")
    put("checks.EB", c["item1"]["E-B comparisons"], "full/checks/checks.json")
    put("checks.pool_cases", c["item2"]["menu_cases"], "full/checks/checks.json")
    put("checks.range_cases", c["item2"]["elastic_cases"], "full/checks/checks.json")
    put("checks.noncm", xsum(1 for x in c["item8"] if not x["cm"]), "full/checks/checks.json")
    put("checks.three_part_menus", len(c["item8"]), "full/checks/checks.json")
    put("checks.stability_caps", c["item7"]["caps_checked"], "full/checks/checks.json")


def l5_cut(rdir):
    """Rule-1 share of the floor on the L5 bins with the open top bin [240, cut] s, for menus with M >= 30 s:
    sum over menus of E[(T - hM)^+] over sum of E[D_h], exact; cut 300 s is the law of the paper."""
    src = "code/podsim (exact, recomputed here)"
    menus = sorted({tuple(int(x) for x in r["menu"].split()) for r in rd(os.path.join(rdir, "menu_law.csv"))
                    if int(r["M"]) >= 30})
    bins = [((1, 59), Fraction(8, 100)), ((60, 119), Fraction(32, 100)), ((120, 179), Fraction(26, 100)),
            ((180, 239), Fraction(10, 100))]
    for cut in (270, 300, 330, 360, 420):
        law = []
        for (lo, hi), sh in bins + [((240, cut), Fraction(24, 100))]:
            law.extend((t, sh / (hi - lo + 1)) for t in range(lo, hi + 1))
        for h in (6, 8):
            feas = tot = Fraction(0)
            for A in menus:
                D = structural.undershoot_table(A, h, cut)
                M = max(A)
                for t, w in law:
                    feas += w * max(0, t - h * M)
                    tot += w * D[t]
            put("rule1.M30plus.L5cut%d.share.h%d" % (cut, h), 100 * float(feas / tot), src)
    put("rule1.M30plus.menus_L5cut", len(menus), src)


def examples():
    """Exact values the text states as examples (recomputed here from podsim)."""
    src = "code/podsim (exact, recomputed here)"
    from math import gcd, ceil
    from functools import reduce

    def cond(gens):
        N = 4000
        r = [False] * N
        r[0] = True
        for x in range(1, N):
            r[x] = any(x >= a and r[x - a] for a in gens)
        gaps = [i for i in range(N) if not r[i]]
        return gaps[-1] + 1 if gaps else 0

    def hstar_w(A, lo, hi):
        g = reduce(gcd, A)
        A0 = [0] + [a // g for a in A]
        d = max(A0)
        c2 = cond([d - a for a in A0 if a < d])
        return ceil((hi // g + c2) / d)
    for A in ((15, 30), (5, 15, 30), (10, 15, 30), (6, 15, 30), (15, 30, 60), (10, 15, 20, 30),
              (15, 20, 30, 45, 60), (5, 45, 60), (6, 45, 60), (10, 45, 60)):
        lab = "_".join(map(str, A))
        put("ex.hstarW.60_180.%s" % lab, hstar_w(A, 60, 180), src)
        put("ex.leastcap.60_180.%s" % lab, structural.least_cap_window(A, 60, 180), src)
    for A in ((10, 15, 30), (6, 15, 30)):
        Dn = structural.undershoot_table(A, None, 180)
        put("ex.mean_90_180.%s" % "_".join(map(str, A)), str(Fraction(xsum(Dn[90:181]), 91)), src)
    D2060 = structural.undershoot_table((20, 60), None, 240)
    put("ex.L1.20_60.uncapped", str(Fraction(xsum(D2060[t] for t in range(60, 241, 30)), 7)), src)
    put("ex.mean_offset_ticks", str(Fraction(89999, 2 * 90000)), "design: offset uniform on 0..89,999 ticks")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True)
    ap.add_argument("--narrow", required=True)
    ap.add_argument("--rules", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--allow-missing", action="store_true", help="write the numbers even if some source files are missing")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    skipped = []
    for name, fn, args in (("intro", intro, ()), ("structural", structural_table, (a.full,)), ("rules", rules, (a.rules,)),
                           ("demand", demand, (a.full,)), ("demand_x1", demand_x1, (a.full,)),
                           ("levers", levers_finite, (a.full,)), ("levers_meta", levers_meta, (a.full,)),
                           ("levers_split", levers_split, (a.full,)),
                           ("hybrid", hybrid, (a.full,)), ("ticks", ticks, (a.full,)),
                           ("interaction", interaction, ()), ("clutter", clutter, (a.full,)),
                           ("clutter_matched", clutter_matched, (a.full,)), ("hulls", hulls, (a.full,)),
                           ("practice", practice, (a.full,)), ("reversals", reversals, (a.full,)),
                           ("checks", checks, (a.narrow, a.full)), ("l5_cut", l5_cut, (a.rules,)),
                           ("examples", examples, ()), ("table_sizes", table_sizes, (a.full,))):
        try:
            fn(*args)
        except FileNotFoundError as e:
            # an output folder without some large tables (for example a trimmed copy): skip that group, say so
            skipped.append("%s (missing %s)" % (name, os.path.relpath(e.filename) if e.filename else e))
    for s_ in skipped:
        print("skipped:", s_)
    if skipped and not a.allow_missing:
        print("error: %d group(s) skipped; rerun with --allow-missing to write a partial set" % len(skipped))
        sys.exit(1)
    with open(os.path.join(a.out, "numbers.json"), "w", encoding="utf-8") as f:
        json.dump({k: v for k, v, _ in OUT}, f, indent=1, sort_keys=True)
        f.write("\n")

    def show(v):
        if isinstance(v, float):
            return hu(v, 4) if abs(v) < 10 else hu(v, 2)
        return str(v)
    L = ["# Numbers cited in the manuscript", "", "Generated by code/manuscript_numbers.py from the tier outputs; "
         "full precision in numbers.json.", "", "| Key | Value | Source |", "| --- | --- | --- |"]
    for k, v, s in OUT:
        L.append("| %s | %s | %s |" % (k, show(v), s))
    with open(os.path.join(a.out, "numbers.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("%d numbers written" % len(OUT))


if __name__ == "__main__":
    main()
