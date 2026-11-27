"""Summary for X7 from <out>/x7/{x7_partA.csv, x7_partB.csv, x7_meta.json} (run_x7.py). Writes <out>/x7/summary.md."""
import json
import os
from collections import defaultdict

import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from podsim import registry as REG  # noqa: E402
OUT = os.path.join(REG.out_root(), "x7")
MENUS = ["15 30", "15 30 60", "10 15 30", "6 15 30", "5 15 30", "10 15 20 30", "15 20 30 45 60"]
EPS = ["15 ms", "1 frame (3003 ticks)", "50 ms", "100 ms", "0.5 s"]


def ms(m):
    return "{" + ", ".join(m.split()) + "}"


def main():
    A = REG.read_csv(os.path.join(OUT, REG.table_name("x7_partA")))
    B = REG.read_csv(os.path.join(OUT, REG.table_name("x7_partB")))
    Bj = json.load(open(os.path.join(OUT, "x7_meta.json")))
    L = []
    w = L.append
    w("# X7: integer seconds versus 90 kHz ticks")
    w("")
    w("Model (podsim/ticks.py): 1 s = 90,000 ticks. A creative of nominal a s lasts 90,000 a + delta ticks; the "
      "dynamic target is 90,000 T + o ticks, T from the integer law and o uniform on {0, ..., 89,999}; a pod is "
      "accepted when its true total is at most the target plus a tolerance tol in {0, eps}. Unfilled seconds are "
      "max(0, target - filled) / 90,000; with tol > 0 a pod may run past the target, reported as overrun.")
    w("")
    w("Perturbations: sys+ (every creative +eps), sys- (every creative -eps), ntsc (DERIVED, not sourced: a "
      "creative made at 30 fps and played at 30000/1001 fps lasts a x 1001/1000 s, so delta = 90 a ticks: 15 s -> "
      "15.015 s, 30 s -> 30.03 s, 60 s -> 60.06 s), and indep (each creative uniform on the integers in "
      "[-eps, eps], drawn once per creative and shared across eps by scaling one uniform). eps in {15 ms = 1,350, "
      "1 frame at 29.97 fps = 3,003, 50 ms = 4,500, 100 ms = 9,000, 0.5 s = 45,000 ticks}; for ntsc, tol in "
      "{0, 90 max A}.")
    w("")
    w("Comparison: Delta = E[U_tick] - E[U_int] - 0.49999 s, where U_int is the integer model's unfilled seconds "
      "on the same break and pools and 0.49999 s = E[o] / 90,000 is the mean sub-second offset (which a tick "
      "model always leaves unless a pod fits it). Delta < 0: ticks fill more; Delta > 0: ticks fill less.")
    w("")
    w("Part A is exact (demand unlimited, systematic models; Fractions in `x7_partA.csv`, column delta_exact). "
      "Part B is Monte Carlo at lambda = 16 balanced, %d breaks per (law, menu), master seed `%s`, common random "
      "numbers with the integer model (same breaks, offsets, pools); paired standard errors." % (Bj["n"], Bj["master"]))
    w("")
    # Part A table: Delta by model/eps/tol, max |Delta| over menus, per law and cap
    idx = defaultdict(dict)
    for r in A:
        idx[(r["law"], r["model"], r["eps_label"], r["tol_ticks"] > 0, r["h"])][r["menu"]] = r
    w("## Part A: structural seconds, demand unlimited (exact)")
    w("")
    w("Delta in seconds per break, range over the seven menus [min, max].")
    w("")
    for law in ("L1", "L2", "L3u"):
        w("### %s" % law)
        w("")
        w("| model | eps | tol | h = 4 | h = 6 | h = 8 | uncapped |")
        w("| --- | --- | --- | --- | --- | --- | --- |")
        for model in ("sys+", "sys-"):
            for e in EPS:
                for tl in (False, True):
                    cells = []
                    for h in (4, 6, 8, "none"):
                        d = [x["delta"] for x in idx[(law, model, e, tl, h)].values()]
                        cells.append("[%.3f, %.3f]" % (min(d), max(d)))
                    w("| %s | %s | %s | %s |" % (model, e, "eps" if tl else "0", " | ".join(cells)))
        for tl in (False, True):
            cells = []
            for h in (4, 6, 8, "none"):
                d = [x["delta"] for x in idx[(law, "ntsc", "derived 1001/1000", tl, h)].values()]
                cells.append("[%.3f, %.3f]" % (min(d), max(d)))
            w("| ntsc (derived) | 90 a ticks | %s | %s |" % ("90 max A" if tl else "0", " | ".join(cells)))
        w("")
    w("Two-player split of the structural floor at demand unlimited (arith, cap): largest absolute change against the integer "
      "model, over all menus, laws and caps, by perturbation:")
    w("")
    w("| model | eps | tol | max abs change phi arith | max abs change phi cap |")
    w("| --- | --- | --- | --- | --- |")
    agg = defaultdict(lambda: [0.0, 0.0])
    for r in A:
        k = (r["model"], r["eps_label"], "eps" if r["tol_ticks"] > 0 else "0")
        agg[k][0] = max(agg[k][0], abs(r["phi_arith_tick"] - r["phi_arith_int"]))
        agg[k][1] = max(agg[k][1], abs(r["phi_cap_tick"] - r["phi_cap_int"]))
    for k in sorted(agg, key=lambda k: (k[0], EPS.index(k[1]) if k[1] in EPS else 9, k[2])):
        w("| %s | %s | %s | %.3f | %.3f |" % (k + tuple(agg[k])))
    w("")
    # Part B
    w("## Part B: lambda = 16 balanced, Monte Carlo with paired SEs")
    w("")
    w("Paired difference tick minus integer (seconds per break, offset mean not removed here: the 0.49999 s offset "
      "is in both 'int' and 'tick' columns by construction of the integer arm, which adds o/90,000). Largest |diff| "
      "and its SE over the seven menus and four caps, per law and perturbation:")
    w("")
    w("| law | model | eps | tol | quantity | max abs paired diff | its SE | max SE |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- |")
    g = defaultdict(list)
    for r in B:
        g[(r["law"], r["model"], r["eps_label"], "eps" if r["tol_ticks"] > 0 else "0", r["quantity"])].append(r)
    for k in sorted(g, key=lambda k: (k[0], k[1], EPS.index(k[2]) if k[2] in EPS else 9, k[3], k[4])):
        rs = g[k]
        top = max(rs, key=lambda r: abs(r["paired_diff"]))
        w("| %s | %s | %s | %s | %s | %.3f | %.3f | %.3f |" % (k + (abs(top["paired_diff"]), top["paired_se"],
                                                              max(r["paired_se"] for r in rs))))
    w("")
    # ---- stability for small eps, computed
    small = ["15 ms", "1 frame (3003 ticks)"]

    def maxabs(rows, laws_):
        v = [abs(r["delta"]) for r in rows if r["law"] in laws_]
        return max(v) if v else 0.0
    sel = lambda model, labs: [r for r in A if r["model"] == model and r["eps_label"] in labs]
    w("## Are X1 results stable for small eps?")
    w("")
    w("Criteria: (1) magnitude: |Delta| in structural seconds per break for "
      "eps <= 1 frame; (2) ranking: among cells where the integer model separates the two structural channels by "
      "at least 0.5 s (|phi arith - phi cap| >= 0.5), does the larger one stay larger in ticks?")
    w("")
    for model in ("sys+", "sys-", "ntsc"):
        labs = small if model != "ntsc" else ["derived 1001/1000"]
        w("- %s, eps <= 1 frame: max |Delta| on L1 %.3f s, on L2 (a) %.3f s, on L3 uniform %.3f s." % (
            model, maxabs(sel(model, labs), ["L1"]), maxabs(sel(model, labs), ["L2"]), maxabs(sel(model, labs), ["L3u"])))
    rev = defaultdict(lambda: [0, 0])
    for r in A:
        di = r["phi_arith_int"] - r["phi_cap_int"]
        dt = r["phi_arith_tick"] - r["phi_cap_tick"]
        if abs(di) >= 0.5:
            k = (r["model"], r["eps_label"])
            rev[k][1] += 1
            if di * dt < 0:
                rev[k][0] += 1
    w("- Ranking reversals of the two structural channels (part A, cells with an integer margin of at least "
      "0.5 s): " + "; ".join("%s %s: %d of %d" % (k[0], k[1], v[0], v[1]) for k, v in sorted(rev.items())) + ".")
    gb = defaultdict(lambda: [0, 0])
    gidx = defaultdict(dict)
    for r in B:
        gidx[(r["law"], r["menu"], r["h"], r["model"], r["eps_label"], r["tol_ticks"])][r["quantity"]] = r
    for k, q in gidx.items():
        ch = ["arith", "cap", "demand"]
        oi = sorted(ch, key=lambda j: -q[j]["int_mean"])
        if q[oi[0]]["int_mean"] - q[oi[1]]["int_mean"] < 0.5:
            continue
        ot = sorted(ch, key=lambda j: -q[j]["tick_mean"])
        gb[(k[3], k[4])][1] += 1
        if ot[0] != oi[0]:
            gb[(k[3], k[4])][0] += 1
    w("- Top part changes among arithmetic, cap and demand (part B, lambda = 16, cells where the integer top part "
      "leads by at least 0.5 s): " + "; ".join("%s %s: %d of %d" % (k[0], k[1], v[0], v[1]) for k, v in sorted(gb.items())) + ".")
    w("")
    w("Reading. The ranges above are computed from parts A and B. On grid breaks a pod of n creatives that each "
      "overrun by eps overruns by n eps, so a pod that fit exactly drops an ad; part A's delta0 columns give this "
      "for breaks of whole seconds, and a tolerance of eps does not cure it.")
    w("")
    w("")
    REG.write_text(os.path.join(OUT, "summary.md"), "\n".join(L) + "\n")
    print("x7 summary written")


if __name__ == "__main__":
    main()
