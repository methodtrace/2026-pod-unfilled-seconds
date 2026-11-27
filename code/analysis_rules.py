"""Coverage of the configuration rules (structural floor, demand unlimited, readiness 1), exact.

Usage: python3 analysis_rules.py --res DIR --out DIR
  --res  a full-tier output folder (reads extracts/x1_structural.csv.gz, x2/x2_meta.json, x4/summary.md,
         x6/summary.md)
  --out  where to write rules.md and the CSV tables (menu_law.csv, levers.csv)

Everything structural is recomputed here from the simulator package (podsim.structural, podsim.laws) and every
value is checked against the tier's own table (Ustruct_exact), so the coverage numbers and the run agree exactly.

Definitions, per menu A (gcd g, longest part M), law (dynamic targets T with weights) and nominal cap h with
dynamic cap k (hybrid conventions as in podsim.laws.dynamic_cap):
  S_h              E[D_h(A;T)], the structural floor (seconds per break)
  feasibility      E[(T - k M)^+]: seconds no pod of at most k ads can reach (rule 1)
  h_star           least nominal cap with S_h = S_uncapped (the cap stops mattering; rule 2)
  conductor c      least multiple of g from which every multiple of g is a sum of parts of A
  lattice term     E[T mod g]; S_uncapped = E[T mod g] + E[D_inf(A;T) - T mod g; T < c] exactly, because a
                   target at or past the conductor misses exactly T mod g (rules 3 to 5)
  (g - 1) / 2      the lattice term of a target spread evenly over residues mod g (rule 3 closed form)
Levers at demand unlimited (rule 6): cap+1 (h -> h + 1) and adding one duration from {5, 6, 10, 15, 20, 30, 45, 60}
not in A, exact gains S_h(A) - S_h(A').
"""
import argparse
import csv
import gzip
import json
import os
import re
import statistics
import sys
from fractions import Fraction
from functools import reduce

TIE6 = Fraction(1, 10 ** 9)  # gains within 1e-9 s tie, as in the lever study (run_x2.TIE)
from math import gcd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("PODSIM_TMAX", "360")

from podsim import structural, laws, registry as REG  # noqa: E402
from podsim.laws import dynamic_cap  # noqa: E402
from podsim.numeric import xsum  # noqa: E402
import run_x1  # noqa: E402

CAPS = list(range(1, 21)) + [None]
UNION = (5, 6, 10, 15, 20, 30, 45, 60)
IRREGULAR = ("L3u", "L6", "L7")          # uniform on every integer of an interval
TOL = Fraction(1, 10)


def hlab(h):
    return "none" if h is None else str(h)


def mlab(m):
    return " ".join(map(str, m))


def conductor(A):
    g = reduce(gcd, A)
    N = 4000
    mp = structural.min_parts(tuple(sorted(A)), N)
    last_gap = -g
    for x in range(0, N + 1, g):
        if mp[x] >= structural.INF:
            last_gap = x
    return last_gap + g


def law_points(law, conv, h):
    return [(T, w, dynamic_cap(h, st, conv)) for (T, st), w in law.support]


_PTS = {}
_S = {}


def S(A, law, conv, h):
    """E[D_h(A;T)] as an exact Fraction; tables per (menu, dynamic cap), memoized per (menu, law, conv, h)."""
    key = (A, law.name, conv, h)
    v = _S.get(key)
    if v is None:
        pk = (law.name, conv, h)
        pts = _PTS.get(pk)
        if pts is None:
            pts = law_points(law, conv, h)
            _PTS[pk] = pts
        tabs = {}
        acc = []
        for T, w, k in pts:
            if k is not None and k <= 0:
                acc.append(w * T)
                continue
            t = tabs.get(k)
            if t is None:
                t = structural.undershoot_table(A, k, 512)
                tabs[k] = t
            if t[T]:
                acc.append(w * t[T])
        v = xsum(acc, Fraction(0))
        _S[key] = v
    return v


def cap_beyond(A, law, conv, h):
    """E[D_h(A;T) - max(D_inf(A;T), (T - kM)^+)]: the loss the cap adds beyond both lower bounds (rule 1 and the
    uncapped floor), exact. Nonnegative per target because D_h is at least each bound."""
    M = max(A)
    tinf = structural.undershoot_table(A, None, 512)
    tabs = {}
    acc = []
    for T, w, k in law_points(law, conv, h):
        if k is not None and k <= 0:
            dh, feas = T, T
        else:
            t = tabs.get(k)
            if t is None:
                t = structural.undershoot_table(A, k, 512)
                tabs[k] = t
            dh, feas = t[T], max(0, T - k * M)
        d = dh - max(tinf[T], feas)
        if d:
            acc.append(w * d)
    return xsum(acc, Fraction(0))


def load_extract(res):
    out = {}
    with gzip.open(os.path.join(res, "extracts", "x1_structural.csv.gz"), "rt", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["law"], r["conv"], r["menu"], r["h"])] = Fraction(r["Ustruct_exact"])
    return out


def pct(a, b):
    return "%.1f%%" % (100.0 * a / b) if b else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    ext = load_extract(a.res)
    menus = REG.menus_m7_m85()
    lawconvs = REG.FULL_LAWS
    LD = {n: run_x1.law_obj(n) for n in sorted({l for l, _ in lawconvs})}

    rows = []
    lever_rows = []
    checked = 0
    for A in menus:
        A = tuple(sorted(A))
        g, M = reduce(gcd, A), max(A)
        c = conductor(A)
        for name, conv in lawconvs:
            law = LD[name]
            if conv == "b" and name not in REG.HYBRID_LAWS:
                continue
            Sh = {}
            for h in CAPS:
                Sh[h] = S(A, law, conv, h)
                key = (name, conv, mlab(A), hlab(h))
                if key in ext:
                    if ext[key] != Sh[h]:
                        raise SystemExit("mismatch with the tier table at %s: %s != %s" % (key, Sh[h], ext[key]))
                    checked += 1
            unc = Sh[None]
            hstar = next(h for h in CAPS if Sh[h] == unc)
            pts = law_points(law, conv, None)
            lat = xsum((w * (T % g) for T, w, _ in pts), Fraction(0))
            below = xsum((w for T, w, _ in pts if T < c), Fraction(0))
            row = dict(law=name, conv=conv, menu=mlab(A), g=g, M=M, conductor=c, h_star=hlab(hstar),
                       S_unc=float(unc), S_unc_exact=str(unc), lattice_term=float(lat), lattice_term_exact=str(lat), half_g=(g - 1) / 2,
                       mass_below_conductor=float(below), gap_unc_minus_lattice=float(unc - lat))
            for h in CAPS:
                if h is None:
                    continue
                feas = xsum((w * (max(0, T - (k or 0) * M) if k is not None else 0) for T, w, k in
                             law_points(law, conv, h)), Fraction(0))
                row["S_%d" % h] = float(Sh[h])
                row["feas_%d" % h] = float(feas)
                row["capcost_%d" % h] = float(Sh[h] - unc)
                row["capbeyond_%d" % h] = float(cap_beyond(A, law, conv, h))
            rows.append(row)
            # levers at demand unlimited
            for h in CAPS:
                base = Sh[h]
                g_cap = (base - Sh[h + 1]) if (h is not None and h + 1 in Sh) else (base - S(A, law, conv, h + 1)
                                                                                    if h is not None else None)
                adds = {}
                for d in UNION:
                    if d in A:
                        continue
                    A2 = tuple(sorted(A + (d,)))
                    adds[d] = base - S(A2, law, conv, h)
                # classification below h* in exact arithmetic (CSV floats are rounded): the best lever with a
                # positive gain is the cap (or ties the best added duration), only durations longer than M, only
                # shorter ones, or a longer and a shorter duration tied exactly ("long-short tie"); no tie is broken
                is_below = h is not None and (hstar is None or h < hstar)
                cls = ""
                if is_below:
                    vbest = max(adds.values()) if adds else Fraction(0)
                    gc = g_cap if g_cap is not None else Fraction(0)
                    if max(gc, vbest) > 0:
                        if gc >= vbest - TIE6:
                            cls = "cap"
                        else:
                            sides = {d > M for d, v in adds.items() if v >= vbest - TIE6}
                            cls = "long" if sides == {True} else ("short" if sides == {False} else "long-short tie")
                lever_rows.append(dict(law=name, conv=conv, menu=mlab(A), h=hlab(h), g=g, M=M, h_star=hlab(hstar),
                                       below_hstar=(h is not None and (hstar is None or h < hstar)), S=float(base),
                                       mass_below_conductor=float(below),
                                       cap1=(None if g_cap is None else float(g_cap)),
                                       below_class=cls,
                                       **{"add_%d" % d: float(v) for d, v in adds.items()},
                                       **{"gain_pos_%d" % d: int(v > 0) for d, v in adds.items()},
                                       **{"gcd_drop_%d" % d: int(reduce(gcd, A + (d,)) < g) for d in adds}))
    write_csv(os.path.join(a.out, "menu_law.csv"), rows)
    write_csv(os.path.join(a.out, "levers.csv"), lever_rows)
    report(a, rows, lever_rows, checked, menus, lawconvs)


def write_csv(path, rows):
    fields = []
    for r in rows:
        for k in r:
            if k not in fields:
                fields.append(k)
    REG.write_csv(path, rows, fields)


def report(a, rows, lever_rows, checked, menus, lawconvs):
    L = []
    w = L.append
    nml = len(rows)
    w("# Configuration rules: coverage on the full tier")
    w("")
    w("Exact structural quantities (demand unlimited, readiness 1) for %d menus and %d law-convention pairs "
      "(%d menu-law cells), caps 1 to 20 and uncapped, recomputed from the simulator package and equal to the "
      "tier's own table in all %d cells checked. Definitions in code/analysis_rules.py." % (
          len(menus), len(lawconvs), nml, checked))
    w("")

    # ---------------- rule 1
    w("## Rule 1. Feasibility")
    w("")
    w("A pod of at most k ads of at most M seconds reaches at most kM seconds, so a break longer than kM leaves at "
      "least T - kM unsold whatever the demand. Share of menu-law cells with any such shortfall, and the share of "
      "the structural floor that is this certain shortfall, by nominal cap:")
    w("")
    w("| h | cells with shortfall | shortfall share of floor (pooled) |")
    w("| --- | --- | --- |")
    for h in range(1, 21):
        n = xsum(1 for r in rows if r["feas_%d" % h] > 0)
        sf = xsum(r["feas_%d" % h] for r in rows)
        st = xsum(r["S_%d" % h] for r in rows)
        if n == 0 and h > 6:
            w("| %d to 20 | 0 | 0 |" % h)
            break
        w("| %d | %d of %d (%s) | %s |" % (h, n, nml, pct(n, nml), pct(sf, st)))
    w("")
    w("Per law and convention (the pooled share is dominated by long-break laws): shortfall share of the floor at "
      "h = 3 and h = 6, summed over menus.")
    w("")
    w("| law | h = 3 | h = 6 |")
    w("| --- | --- | --- |")
    byl = {}
    for r in rows:
        byl.setdefault((r["law"], r["conv"]), []).append(r)
    for (l, cv), rs in sorted(byl.items()):
        cells = []
        for h in (3, 6):
            sf = xsum(r["feas_%d" % h] for r in rs)
            st = xsum(r["S_%d" % h] for r in rs)
            cells.append(pct(sf, st))
        w("| %s%s | %s | %s |" % (l, " (%s)" % cv if l in REG.HYBRID_LAWS else "", cells[0], cells[1]))
    w("")

    w("By the menu's longest duration M (menus with M <= 20 s are unlikely live-CTV offers and dominate the pooled "
      "share): pooled shortfall share, cells with a shortfall, and the median per-cell share (floor > 0).")
    w("")
    w("| h | M class | menus | pooled share | cells with shortfall | median per-cell share |")
    w("| --- | --- | --- | --- | --- | --- |")
    for h in (3, 4, 6, 8):
        for lab, f in (("M >= 30 s", lambda r: r["M"] >= 30), ("M <= 20 s", lambda r: r["M"] <= 20)):
            rs = [r for r in rows if f(r)]
            sf = xsum(r["feas_%d" % h] for r in rs)
            st = xsum(r["S_%d" % h] for r in rs)
            n = xsum(1 for r in rs if r["feas_%d" % h] > 0)
            sh = [r["feas_%d" % h] / r["S_%d" % h] for r in rs if r["S_%d" % h] > 0]
            w("| %d | %s | %d | %s | %d of %d | %.1f%% |" % (h, lab, len({r["menu"] for r in rs}), pct(sf, st), n,
                                                           len(rs), 100 * statistics.median(sh)))
    w("")

    # ---------------- rule 2
    w("## Rule 2. Cap regime")
    w("")
    w("h* = least cap at which the floor equals the uncapped floor. Distribution of h* over the %d menus, by law "
      "(quartiles and max):" % len(menus))
    w("")
    w("| law | h* q1 / median / q3 / max | floor minus the rule-1 shortfall at h = 3, 4, 6 (contains the lattice floor; median over menus, s per break) |")
    w("| --- | --- | --- |")
    by = {}
    for r in rows:
        by.setdefault((r["law"], r["conv"]), []).append(r)
    for (l, cv), rs in sorted(by.items()):
        hs = sorted(int(r["h_star"]) if r["h_star"] != "none" else 99 for r in rs)
        q = lambda p: hs[min(len(hs) - 1, int(p * (len(hs) - 1) + 0.5))]

        def med(h):
            return statistics.median(r["S_%d" % h] - r["feas_%d" % h] for r in rs)
        lab = lambda x: ">20" if x >= 99 else ("%g" % x)
        never = xsum(1 for x in hs if x == 99)
        w("| %s%s | %s / %s / %s / %s%s | %.1f, %.1f, %.1f |" % (
            l, " (%s)" % cv if l in REG.HYBRID_LAWS else "", lab(q(.25)), lab(statistics.median(hs)), lab(q(.75)),
            lab(hs[-1]),
            " (%d menus never within caps 1 to 20)" % never if never else "", med(3), med(4), med(6)))
    w("")

    w("Cap cost: E[D_h - D_inf] is everything the cap costs relative to no cap (it includes rule 1); the cap's loss "
      "beyond both lower bounds is E[D_h - max(D_inf, (T - kM)^+)], exact per target. Median over menu-law cells, range of "
      "per-law medians, seconds per break:")
    w("")
    w("| h | cap cost, all menus | beyond both bounds, all menus | cap cost, M >= 30 s | beyond both bounds, M >= 30 s |")
    w("| --- | --- | --- | --- | --- |")
    for h in (3, 4, 6, 8):
        cells = []
        for f in (lambda r: True, lambda r: r["M"] >= 30):
            for col in ("capcost_%d", "capbeyond_%d"):
                bl = {}
                for r in rows:
                    if f(r):
                        bl.setdefault((r["law"], r["conv"]), []).append(r[col % h])
                meds = sorted(statistics.median(v) for v in bl.values())
                allv = [r[col % h] for r in rows if f(r)]
                cells.append("%.2f (%.2f to %.2f)" % (statistics.median(allv), meds[0], meds[-1]))
        w("| %d | %s | %s | %s | %s |" % ((h,) + tuple(cells[i] for i in (0, 1, 2, 3))))
    w("")

    # ---------------- rules 3 to 5
    w("## Rules 3 to 5. Lattice floor, hybrid remainders, live mix")
    w("")
    w("Past the conductor a target misses exactly T mod g, so the uncapped floor equals E[T mod g] plus the excess "
      "of targets below the conductor. Cells where the uncapped floor is within 0.1 s of E[T mod g], by law family; "
      "the rest have targets below the conductor (mass shown).")
    w("")
    w("| law family | cells | within 0.1 s of E[T mod g] | largest gap (s) | median mass below conductor where off |")
    w("| --- | --- | --- | --- | --- |")
    fam = [("irregular uniform (L3u, L6, L7)", lambda r: r["law"] in IRREGULAR),
           ("irregular skewed and binned (L3s, L5)", lambda r: r["law"] in ("L3s", "L5")),
           ("lattice laws (L4)", lambda r: r["law"].startswith("L4")),
           ("grid (L1)", lambda r: r["law"] == "L1"),
           ("hybrid remainders (L2, L2s*, L2two)", lambda r: r["law"] in REG.HYBRID_LAWS),
           ("live mix (L8q25, L8q50, L8q75)", lambda r: r["law"].startswith("L8"))]
    for lab, f in fam:
        rs = [r for r in rows if f(r)]
        ok = [r for r in rs if abs(Fraction(r["S_unc_exact"]) - Fraction(r["lattice_term_exact"]))
              <= TOL]
        off = sorted(r["mass_below_conductor"] for r in rs if r not in ok)
        w("| %s | %d | %d (%s) | %.2f | %s |" % (lab, len(rs), len(ok), pct(len(ok), len(rs)),
                                                 max(r["gap_unc_minus_lattice"] for r in rs),
                                                 "%.2f" % statistics.median(off) if off else "-"))
    w("")
    w("Closed form (g - 1)/2 on irregular uniform breaks: cells within 0.1 s of (g - 1)/2, by law, among menus whose "
      "conductor is at or below the law's shortest break:")
    w("")
    w("| law | breaks | menus above conductor | within 0.1 s of (g - 1)/2 | all menus within 0.1 s |")
    w("| --- | --- | --- | --- | --- |")
    span = {"L3u": (60, 240), "L6": (15, 60), "L7": (240, 360)}
    for l in IRREGULAR:
        rs = [r for r in rows if r["law"] == l]
        lo = span[l][0]
        above = [r for r in rs if r["conductor"] <= lo]
        ok = [r for r in above if abs(r["S_unc"] - r["half_g"]) <= 0.1]
        allok = [r for r in rs if abs(r["S_unc"] - r["half_g"]) <= 0.1]
        w("| %s | uniform [%d, %d] | %d | %d | %d of %d |" % (l, span[l][0], span[l][1], len(above), len(ok),
                                                              len(allok), len(rs)))
    w("")
    w("Floor by gcd (uncapped, irregular uniform [60, 240], all menus): " + "; ".join(
        "g = %d: %s s (%d menus)" % (g, ", ".join(sorted({"%.2f" % r["S_unc"] for r in rows
                                                       if r["law"] == "L3u" and r["g"] == g})),
                                     xsum(1 for r in rows if r["law"] == "L3u" and r["g"] == g))
        for g in sorted({r["g"] for r in rows if r["law"] == "L3u"})) + ".")
    w("")
    hyb = [r for r in rows if r["law"] in REG.HYBRID_LAWS and r["conv"] == "a"]
    spots = {"L2": (5, 10, 15, 20, 45), "L2s1530": (15, 30), "L2s510": (5, 10), "L2s7812": (7, 8, 12), "L2s60": (60,)}
    w("Hybrid remainders T = B - S (B on the 30 s grid, S uniform on the spot set): when g divides 30 the lattice "
      "term is E[(-S) mod g], so spots on the menu's lattice add nothing and off-lattice spots add their residue. "
      "Predicted E[(-S) mod g] and the menus (convention a; the uncapped floor does not depend on the convention) "
      "whose uncapped floor matches it within 0.1 s, among menus with that gcd:")
    w("")
    gs = sorted({r["g"] for r in hyb if 30 % r["g"] == 0})
    w("| spot set | " + " | ".join("g = %d" % g for g in gs) + " |")
    w("| --- |" + " --- |" * len(gs))
    for l, Sset in spots.items():
        cells = []
        for g in gs:
            pred = Fraction(xsum((-x) % g for x in Sset), len(Sset))
            rs = [r for r in hyb if r["law"] == l and r["g"] == g]
            ok = xsum(1 for r in rs if abs(r["S_unc"] - float(pred)) <= 0.1)
            cells.append("%.2f: %d of %d" % (float(pred), ok, len(rs)))
        w("| {%s} | %s |" % (", ".join(map(str, Sset)), " | ".join(cells)))
    w("")
    w("Two spots (L2two, S1 + S2 <= B): see the E[T mod g] coverage above; the remainder's lattice term follows "
      "the sum of the two spots in the same way.")
    w("")
    l8 = [r for r in rows if r["law"].startswith("L8")]
    lin_ok = 0
    lin_n = 0
    idx = {(r["law"], r["menu"]): r for r in rows}
    for m in {r["menu"] for r in l8}:
        q = [Fraction(idx[(l, m)]["S_unc_exact"]) for l in ("L8q25", "L8q50", "L8q75")]
        lin_n += 1
        lin_ok += int(q[1] * 2 == q[0] + q[2])
    w("Live mix: the uncapped floor is exactly linear in the stoppage share q in %d of %d menus (q = 0.25, 0.5, "
      "0.75; exact rational check)." % (lin_ok, lin_n))
    w("")

    # ---------------- rule 6
    w("## Rule 6. Levers at demand unlimited")
    w("")
    below = [r for r in lever_rows if r["below_hstar"] == "True" or r["below_hstar"] is True]
    above = [r for r in lever_rows if not (r["below_hstar"] is True)]

    cls = [r["below_class"] for r in below if r["below_class"]]
    nb = len(cls)
    cap_wins, long_wins, other = cls.count("cap"), cls.count("long"), cls.count("short")
    ties = cls.count("long-short tie")
    w("Below h* (%d menu-law-cap cells with a positive best gain): raising the cap is the best lever or ties in %d "
      "(%s); only added durations longer than the menu's longest part are best in %d (%s); only shorter ones in %d "
      "(%s); a longer and a shorter added duration tie exactly in %d (%s)." % (
          nb, cap_wins, pct(cap_wins, nb), long_wins, pct(long_wins, nb), other, pct(other, nb), ties, pct(ties, nb)))
    w("")
    tp = fp = fn = tn = 0
    tp_i = fp_i = fn_i = tn_i = 0
    for r in above:
        for k, v in r.items():
            if not k.startswith("add_"):
                continue
            d = k[4:]
            pred = r["gcd_drop_" + d] == 1
            got = r["gain_pos_" + d] == 1
            irr = r["law"] in IRREGULAR
            if pred and got:
                tp += 1
                tp_i += irr
            elif pred:
                fp += 1
                fp_i += irr
            elif got:
                fn += 1
                fn_i += irr
            else:
                tn += 1
                tn_i += irr
    tp_c = fp_c = fn_c = tn_c = 0
    for r in above:
        if float(r["mass_below_conductor"]) > 0:
            continue
        for k, v in r.items():
            if not k.startswith("add_"):
                continue
            pred = r["gcd_drop_" + k[4:]] == 1
            got = r["gain_pos_" + k[4:]] == 1
            tp_c += pred and got
            fp_c += pred and not got
            fn_c += got and not pred
            tn_c += not pred and not got
    w("At or above h* the cap no longer matters. Prediction 'an added duration helps if and only if it lowers the "
      "gcd' over every (menu, law, cap, added duration): helps and predicted %d, predicted but no gain %d, gain but "
      "not predicted %d, neither %d (precision %.3f, recall %.3f). On irregular uniform laws: %d, %d, %d, %d. A "
      "gain without a gcd drop fills a target below the conductor (the exact criterion is the stability "
      "proposition; it is asserted on every stable target of the tier)." % (
          tp, fp, fn, tn, tp / max(1, tp + fp), tp / max(1, tp + fn), tp_i, fp_i, fn_i, tn_i))
    w("")
    w("Restricted to cells whose every target is at or past the menu's conductor: %d, %d, %d, %d (precision %.3f, "
      "recall %.3f)." % (tp_c, fp_c, fn_c, tn_c, tp_c / max(1, tp_c + fp_c), tp_c / max(1, tp_c + fn_c)))
    w("")
    meta = json.load(open(os.path.join(a.res, "x2", "x2_meta.json")))
    st = meta["stability"]
    w("Stability proposition (exact criterion for when adding a duration helps at a stable cap), asserted by the "
      "tier: %d (menu, law, cap, duration) cases, %d stable targets of %d, %d gain targets at stable caps, no "
      "violation." % (st["cases"], st["stable_targets"], st["targets"], st["gain_targets_at_stable"]))
    w("")
    x4 = open(os.path.join(a.res, "x4", "summary.md"), encoding="utf-8").read()
    m = re.search(r"Over (\d+) pair-law cells: (\d+) reversals observed", x4)
    if m:
        w("Menu-ranking reversals (designed consequence): %s of %s pair-law cells reverse at least once along the "
          "caps (x4/summary.md)." % (m.group(2), m.group(1)))
        w("")
    w("## Rule 7. Practice")
    w("")
    x6 = open(os.path.join(a.res, "x6", "summary.md"), encoding="utf-8").read()
    w("From the tier's X6 summary (sampled; full grid of 341,000 conditions on 31 menus; P1 exact seconds-max, P2 "
      "exact revenue-max, P3 greedy by price per second, P3d greedy longest first, P4 first come):")
    w("")
    for pat in (r"- P3 versus[^\n]+", r"- P3d versus[^\n]+", r"- P4 versus[^\n]+",
                r"- Policy component[^\n]+", r"- Floor component[^\n]+"):
        mm = re.search(pat, x6)
        if mm:
            w(mm.group(0))
    w("")
    REG.write_text(os.path.join(a.out, "rules.md"), "\n".join(L) + "\n")
    print("rules: %d menu-law cells, %d lever cells, %d table values checked" % (len(rows), len(lever_rows), checked))


if __name__ == "__main__":
    main()
