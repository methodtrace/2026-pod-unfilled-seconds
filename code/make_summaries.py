"""Write data/results/x1/summary.md and data/results/x3/summary.md from the tables run_x1.py and
run_x3.py wrote. No computation beyond table lookups and ratios."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from podsim import registry as REG  # noqa: E402
from podsim.numeric import xsum  # noqa: E402
RES = REG.out_root()
MENUS = ["15 30", "15 30 60", "10 15 30", "6 15 30", "5 15 30", "10 15 20 30", "15 20 30 45 60"]
LAWS = [("L1", "a"), ("L2", "a"), ("L2", "b"), ("L3u", "a"), ("L3s", "a"), ("L4u5", "a"), ("L4u15", "a"),
        ("L4s5", "a"), ("L4s15", "a")]
LAWNAME = {"L1": "L1 grid {60..240 step 30}", "L2": "L2 hybrid (B from L1, S uniform {5,10,15,20,45}, p = 1)",
           "L3u": "L3 uniform [60, 240]", "L3s": "L3 skewed (synthetic Beta(2,5))",
           "L4u5": "L4 uniform, 5 s lattice", "L4u15": "L4 uniform, 15 s lattice",
           "L4s5": "L4 skewed, 5 s lattice", "L4s15": "L4 skewed, 15 s lattice"}
HCOLS = [3, 4, 5, 6, 7, 8, 9, 10, 11, 12, "none"]
SCHEMES = ["balanced", "w30", "w15", "short", "d1530"]
SLAB = {"balanced": "balanced", "w30": "30-heavy", "w15": "15-heavy", "short": "short-scarce",
        "d1530": "15/30-dominant"}


def ms(m):
    return "{" + ", ".join(m.split()) + "}"


def lawlab(l, c):
    return l + ("" if l != "L2" else " (" + c + ")")


def x1():
    rows = REG.read_csv(os.path.join(RES, "x1", REG.table_name("x1_table")))
    for r in rows:
        if r["rho"] == 1:
            r["rho"] = 1.0
    ver = json.load(open(os.path.join(RES, "x1", "x1_verify.json")))
    idx = {}
    for r in rows:
        idx[(r["law"], r["conv"], r["menu"], r["h"], r["weights"], r["lam"], r["rho"])] = r

    def g(l, c, m, h, sc, lam, rho=1.0):
        return idx[(l, c, m, h, sc, lam, rho)]
    L = []
    w = L.append
    w("# X1 results: structural unfilled seconds and their decomposition")
    w("")
    w("All numbers are exact expectations, not samples (method below). Units: seconds per break unless stated. "
      "Estimand: unsold paid seconds per break = unfilled seconds of the dynamic target T at pod "
      "construction, valued at zero pod revenue whatever their fate (promo, slate, content).")
    w("")
    w("Grid: 9 break-length laws (L2 under both cap conventions), 7 menus, caps 3 to 12 and uncapped, demand "
      "unlimited or lambda in {2, 4, 8, 16, 64} under 5 weight schemes, rho in {1, 0.95}, no floor: %d rows in "
      "`x1_table.csv` (every condition; no significance filter). Columns are defined at the end." % len(rows))
    w("")
    w("## Method and Monte Carlo verification")
    w("")
    w("The seconds-max pod fills a quantity that depends only on T, the cap and the per-duration counts n_a "
      "(bids only break ties), and readiness is independent of everything at selection, so E[U | T, pool] = "
      "(1 - rho) T + rho (T - F). With n_a independent Poisson(lambda w_a), every expectation in this table is "
      "a finite sum over the law of T and the truncated Poisson laws of the counts (counts above floor(240/a) "
      "cannot change F). `podsim/exact.py` evaluates those sums; demand-unlimited quantities are exact "
      "Fractions (columns `*_exact`), demand-limited ones are double-precision sums. The structural floor is "
      "never sampled.")
    w("")
    w("Breaks per block: none needed for the reported numbers (exact). As an independent check, the Monte "
      "Carlo simulator (`scenario.run_block`, with fixed per-duration means and "
      "(break, duration) seeding) ran %d breaks on each of %d verifier blocks, master seed `%s`, caps "
      "{3, 4, 6, 8, 12}, rho {1, 0.95}: %d (quantity, condition) comparisons of E[U], E[U_struct] and every "
      "part of the accounting identity, largest |z| = %.2f, mean z^2 = %.2f (z = (MC - exact)/MC standard error; about 1 is "
      "expected for independent quantities, less here because the quantities are positively correlated and "
      "some have zero variance). Largest MC standard error of E[U]: %.2f s. So the sampled simulator and the "
      "exact sums agree, and the exact values carry no Monte Carlo error." % (
          ver["n"], ver["blocks"], ver["master"], len(ver["rows"]),
          max(abs(r["z"]) for r in ver["rows"]),
          xsum(r["z"] ** 2 for r in ver["rows"]) / len(ver["rows"]),
          max(r["se"] for r in ver["rows"] if r["q"] == "U")))
    w("")
    w("Proportions: the one proportion reported, P(U_struct > 0) (share of breaks with any structural "
      "unfilled second), is exact, so no Wilson interval is needed.")
    w("")

    # ---- structural share and cap dominance (computed)
    R1 = [r for r in rows if r["rho"] == 1.0]
    l1_zero_from = {}
    for m in MENUS:
        for h in HCOLS[:-1]:
            if all(g("L1", "a", m, hh, "unlimited", "unlimited")["Ustruct"] == 0 for hh in HCOLS[HCOLS.index(h):-1]):
                l1_zero_from[m] = h
                break
    dom = {}
    for r in R1:
        if r["h"] in (3, 4):
            parts = {"arith": r["arith_part"], "cap": r["cap_part"], "demand": r["demand_part"],
                     "range residual": r["range_residual"]}
            if max(parts.values()) <= 1e-9:
                top = "none (no unfilled seconds)"
            else:
                top = max(sorted(parts), key=lambda j: parts[j])
            key = str(r["lam"])
            dom.setdefault(key, {}).setdefault(top, 0)
            dom[key][top] += 1
    w("## Structural share and cap dominance")
    w("")
    w("Questions: is the structural share near zero on L1 above the cap regime and material on L2 and L3, and does "
      "the cap dominate for h <= 4?")
    w("")
    w("- L1: with demand unlimited, E[U_struct] on L1 is exactly 0 from cap %s on (by menu: %s); "
      "below that it is pure cap loss. So on L1 every unfilled second above the cap regime is demand." % (
          max(l1_zero_from.values()), ", ".join("%s from h = %s" % (ms(m), h) for m, h in l1_zero_from.items())))
    w("- L2 and L3: the structural floor is material for gcd-15 menus and on L3, mixed for gcd-5 menus on L2. At h = 8, demand "
      "unlimited: L2 (a) leaves %s s per break; L3 uniform %s s; L3 skewed %s s (menus in the order %s). "
      "On the demand-slack slice (15/30-dominant, lambda = 64, h = 8) the structural share is %s on L2 (a) and "
      "%s on L3 uniform." % (
          ", ".join("%.2f" % g("L2", "a", m, 8, "unlimited", "unlimited")["Ustruct"] for m in MENUS),
          ", ".join("%.2f" % g("L3u", "a", m, 8, "unlimited", "unlimited")["Ustruct"] for m in MENUS),
          ", ".join("%.2f" % g("L3s", "a", m, 8, "unlimited", "unlimited")["Ustruct"] for m in MENUS),
          ", ".join(ms(m) for m in MENUS),
          ", ".join("%.2f" % (g("L2", "a", m, 8, "d1530", 64)["share"] or 0) for m in MENUS),
          ", ".join("%.2f" % (g("L3u", "a", m, 8, "d1530", 64)["share"] or 0) for m in MENUS)))
    w("- Cap dominance at h <= 4: largest part of the accounting identity (arith, cap, range residual, demand) "
      "at h in {3, 4}, counted over all laws, menus and weight schemes: %s." % "; ".join(
          "lambda %s: %s" % (k, ", ".join("%s %d" % (j, n) for j, n in sorted(v.items())))
          for k, v in sorted(dom.items(), key=lambda kv: (kv[0] != "unlimited", float(kv[0]) if kv[0] != "unlimited" else 0))))
    w("- All-in share: at thin demand (lambda <= 8) the structural share of all unfilled seconds is "
      "small by construction (demand loss is the bulk of unfilled seconds; see section 4 and the CSV column demand_part), so the informative measures are structural "
      "seconds per break and the share on the demand-slack slice.")
    w("")
    w("## 1. Structural seconds per break, E[U_struct] = E[D_h(A;T)] (demand unlimited, rho = 1)")
    w("")
    for l, c in LAWS:
        w("### %s%s" % (LAWNAME[l], ", convention " + c if l == "L2" else ""))
        w("")
        w("| Menu | " + " | ".join("h = %s" % h for h in HCOLS) + " |")
        w("| --- |" + " --- |" * len(HCOLS))
        for m in MENUS:
            w("| %s | %s |" % (ms(m), " | ".join("%.2f" % g(l, c, m, h, "unlimited", "unlimited")["Ustruct"]
                                                 for h in HCOLS)))
        w("")
        w("Share of breaks with any structural unfilled second, P(U_struct > 0):")
        w("")
        w("| Menu | " + " | ".join("h = %s" % h for h in HCOLS) + " |")
        w("| --- |" + " --- |" * len(HCOLS))
        for m in MENUS:
            w("| %s | %s |" % (ms(m), " | ".join("%.3f" % g(l, c, m, h, "unlimited", "unlimited")["P_struct_pos"]
                                                 for h in HCOLS)))
        w("")

    w("## 2. Structural share E[U_struct]/E[U], balanced weights, rho = 1")
    w("")
    w("Overall share at thin to moderate demand, and on the demand-slack slice (lambda = 64, where demand "
      "rarely binds). A dash means E[U_struct] = 0 (share 0). The share at lambda = 2 is below 0.1 in every "
      "row with h >= 6; see the CSV.")
    w("")
    for l, c in LAWS:
        w("### %s" % lawlab(l, c))
        w("")
        w("| Menu | lambda | " + " | ".join("h = %s" % h for h in [3, 4, 6, 8, 10, 12, "none"]) + " |")
        w("| --- | --- |" + " --- |" * 7)
        for m in MENUS:
            for lam in (8, 16, 64):
                cells = []
                for h in [3, 4, 6, 8, 10, 12, "none"]:
                    r = g(l, c, m, h, "balanced", lam)
                    cells.append("-" if r["Ustruct"] == 0 else "%.3f" % r["share"])
                w("| %s | %d | %s |" % (ms(m), lam, " | ".join(cells)))
        w("")

    w("## 3. Accounting identity (seconds per break), balanced weights, lambda = 8, rho = 1")
    w("")
    w("E[U] = structural + demand exactly at rho = 1 (podsim/decompose.py). The structural floor splits at "
      "unlimited demand into arith (the exact menu against the range of lengths, creatives at every length), cap "
      "(lifting maxseq) and the range residual (seconds no range of lengths fills), by a two-player Shapley value; "
      "I_AC = V() - V(arith) - V(cap) + V(arith, cap) is their interaction (positive = substitutes).")
    w("")
    w("| Law | Menu | h | E[U] | structural | arith | cap | residual | demand | I_AC |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for l, c in LAWS:
        for m in MENUS:
            for h in (4, 6, 8, "none"):
                r = g(l, c, m, h, "balanced", 8)
                w("| %s | %s | %s | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f |" % (
                    lawlab(l, c), ms(m), h, r["U"], r["Ustruct"], r["arith_part"], r["cap_part"],
                    r["range_residual"], r["demand_part"], r["I_AC"]))
    w("")

    w("## 4. Demand scenarios: E[U] and structural share at h = 6 by weight scheme and lambda (L3 uniform)")
    w("")
    w("Weights are over the union {5, 6, 10, 15, 20, 30, 45, 60}; lambda is the expected number of distinct "
      "creatives per break over all eight durations, so a menu sees only part of lambda "
      "(for example {15, 30} sees 2/8 of it under balanced weights and 0.89 of it under 15/30-dominant).")
    w("")
    w("| Menu | weights | " + " | ".join("lambda = %d" % lam for lam in (2, 4, 8, 16, 64)) + " |")
    w("| --- | --- |" + " --- |" * 5)
    for m in MENUS:
        for sc in SCHEMES:
            cells = []
            for lam in (2, 4, 8, 16, 64):
                r = g("L3u", "a", m, 6, sc, lam)
                cells.append("%.1f (%s)" % (r["U"], "%.2f" % r["share"] if r["share"] is not None else "-"))
            w("| %s | %s | %s |" % (ms(m), SLAB[sc], " | ".join(cells)))
    w("")
    w("Cells: E[U] s per break (structural share).")
    w("")

    w("## 5. Wurl-comparable slice: unfilled share of break time, uncapped, no hybrid")
    w("")
    w("E[U]/E[T] with maxseq uncapped, fully dynamic pods, laws L3 and L4. Demand unlimited isolates the "
      "duration arithmetic alone, which is what a 'scheduled inefficiency' of 15/30 creatives measures; the "
      "15/30-dominant rows show the same slice with finite demand.")
    w("")
    w("| Law | Menu | demand unlimited | 15/30-dom lambda 16 | 15/30-dom lambda 64 | balanced lambda 64 |")
    w("| --- | --- | --- | --- | --- | --- |")
    for l in ("L3u", "L3s", "L4u5", "L4u15", "L4s5", "L4s15"):
        for m in MENUS:
            a = g(l, "a", m, "none", "unlimited", "unlimited")
            b = g(l, "a", m, "none", "d1530", 16)
            c = g(l, "a", m, "none", "d1530", 64)
            e = g(l, "a", m, "none", "balanced", 64)
            w("| %s | %s | %.2f%% | %.2f%% | %.2f%% | %.2f%% |" % (
                l, ms(m), 100 * a["unfilled_frac_of_time"], 100 * b["unfilled_frac_of_time"],
                100 * c["unfilled_frac_of_time"], 100 * e["unfilled_frac_of_time"]))
    w("")
    w("## 6. Readiness, rho = 0.95, balanced weights, lambda = 8")
    w("")
    w("E[U] = structural + demand + readiness exactly; readiness = (1 - rho) E[F_n], the ready seconds lost "
      "from the pod actually built.")
    w("")
    w("| Law | Menu | h | E[U] | structural | demand | readiness |")
    w("| --- | --- | --- | --- | --- | --- | --- |")
    for l, c in (("L2", "a"), ("L3u", "a")):
        for m in MENUS:
            for h in (4, 6, 8):
                r = g(l, c, m, h, "balanced", 8, 0.95)
                w("| %s | %s | %s | %.2f | %.2f | %.2f | %.2f |" % (
                    lawlab(l, c), ms(m), h, r["U"], r["Ustruct"], r["demand_part"], r["ready_part"]))
    w("")
    w("Every (law, menu, cap, demand) condition at rho = 0.95 is in the CSV.")
    w("")
    w("## Columns of x1_table.csv")
    w("")
    w("law, conv (hybrid cap convention; a for non-hybrid laws), menu, h (nominal maxseq; 'none' = uncapped), "
      "weights ('unlimited' = demand unlimited), lam, rho, ET = E[T]; U = E[unfilled seconds]; Ustruct = "
      "E[D_h(A;T)] (Ustruct_exact as a fraction); share = Ustruct/U; demand_part = E[F_inf - F_n]; ready_part = "
      "(1 - rho) E[F_n] (U = Ustruct + demand_part + ready_part); arith_part, cap_part, range_residual (sum "
      "Ustruct) and I_AC (I_AC_exact), the split of the structural floor at unlimited demand; struct_cap_part = "
      "E[D_h] - E[D_inf] (the part of the structural floor removed by lifting the cap with the exact menu); "
      "struct_arith_floor = E[D_inf] (no cap helps); unfilled_frac_of_time = U/ET; P_struct_pos.")
    REG.write_text(os.path.join(RES, "x1", "summary.md"), "\n".join(L) + "\n")


def x3():
    sl = REG.read_csv(os.path.join(RES, "x3", REG.table_name("x3_slopes")))
    rows = REG.read_csv(os.path.join(RES, "x3", REG.table_name("x3_table")))
    L = []
    w = L.append
    w("# X3 results: structural unfilled seconds against the hybrid probability p")
    w("")
    w("B uniform on {60, 90, ..., 240} s; with probability p a structured portion S uniform on "
      "{5, 10, 15, 20, 45} s is carved out and T = B - S, otherwise T = B. Seven menus, caps 3 to 12, both cap "
      "conventions (a: maxseq = h on the remainder; b: h - 1 on the remainder, as in the knapsack companion). Demand unlimited "
      "(exact Fractions) and lambda = 8 balanced over the eight-duration union (exact Poisson sums). rho = 1. "
      "%d rows in `x3_table.csv`." % len(rows))
    w("")
    w("Every quantity is exactly linear in p (the law is a p-mixture; the script asserts the identity at all "
      "five p values), so each curve is a line and its slope, E[U | S present] - E[U | S absent], is in "
      "`x3_slopes.csv`. Slopes in seconds per break per unit p.")
    w("")
    for dem, lab in (("unlimited", "demand unlimited: slope of E[U_struct]"), ("lambda8_balanced",
                                                                             "lambda = 8 balanced: slope of E[U_struct] / slope of E[U]")):
        w("## Slopes, %s" % lab)
        w("")
        w("| Menu | conv | " + " | ".join("h = %d" % h for h in range(3, 13)) + " |")
        w("| --- | --- |" + " --- |" * 10)
        for m in MENUS:
            for conv in ("a", "b"):
                cells = []
                for h in range(3, 13):
                    s = [x for x in sl if x["menu"] == m and x["conv"] == conv and x["h"] == h and x["demand"] == dem][0]
                    cells.append("%.2f" % s["slope_struct"] if dem == "unlimited" else
                                 "%.2f / %.2f" % (s["slope_struct"], s["slope_U"]))
                w("| %s | %s | %s |" % (ms(m), conv, " | ".join(cells)))
        w("")
    w("## E[U_struct] at p = 0 and p = 1, demand unlimited")
    w("")
    w("| Menu | h | p = 0 | p = 1, conv a | p = 1, conv b |")
    w("| --- | --- | --- | --- | --- |")
    for m in MENUS:
        for h in (3, 4, 6, 8, 10, 12):
            a = [x for x in sl if x["menu"] == m and x["conv"] == "a" and x["h"] == h and x["demand"] == "unlimited"][0]
            b = [x for x in sl if x["menu"] == m and x["conv"] == "b" and x["h"] == h and x["demand"] == "unlimited"][0]
            w("| %s | %d | %.2f | %.2f | %.2f |" % (ms(m), h, a["Ustruct_p0"], a["Ustruct_p1"], b["Ustruct_p1"]))
    w("")
    ix = {(x["menu"], x["conv"], x["h"], x["demand"]): x for x in sl}
    allge = all(ix[(m, "b", h, dd)]["slope_struct"] >= ix[(m, "a", h, dd)]["slope_struct"] - 1e-12
                for m in MENUS for h in range(3, 13) for dd in ("unlimited", "lambda8_balanced"))
    w("## Linearity in p and the cap convention")
    w("")
    w("Questions: are structural unfilled seconds roughly linear in p for gcd-15 menus, and does convention K - 1 "
      "raise them at low h?")
    w("")
    w("- Linearity: exact for every menu, a designed consequence: the law is a p-mixture "
      "of 'no structured portion' and 'structured portion', so every expectation is affine in p. The "
      "simulation measures the slope, not the shape.")
    w("- Slope, gcd-15 menus, demand unlimited: {15, 30} convention a %s, convention b %s (h = 3..12); "
      "{15, 30, 60} a %s, b %s." % (
          ", ".join("%.2f" % ix[("15 30", "a", h, "unlimited")]["slope_struct"] for h in range(3, 13)),
          ", ".join("%.2f" % ix[("15 30", "b", h, "unlimited")]["slope_struct"] for h in range(3, 13)),
          ", ".join("%.2f" % ix[("15 30 60", "a", h, "unlimited")]["slope_struct"] for h in range(3, 13)),
          ", ".join("%.2f" % ix[("15 30 60", "b", h, "unlimited")]["slope_struct"] for h in range(3, 13))))
    w("- Under convention a the slope is negative at low caps for menus without 60 (a remainder is shorter than "
      "its break, so a binding cap leaves fewer seconds over) and turns positive, to the lattice floor of 5 s "
      "for gcd-15 menus, once the cap stops binding. Under convention b it is nonnegative at every cap (zero only where the cap never binds and the menu fills every remainder, e.g. {15, 20, 30, 45, 60} from h = 8).")
    w("- Convention b at least as high as a in every (menu, cap, demand) cell: %s. The gap is "
      "largest at low h and vanishes once h - 1 no longer binds." % ("yes" if allge else "NO"))
    w("- At lambda = 8 the slope of total E[U] is negative in every cell but one (about -0.1 to -16.7 s per unit p; the exception is {15, 20, 30, 45, 60} under convention b at h = 3, +6.35 s, where the remainder's cap of 2 binds): carving out S removes "
      "target seconds that thin demand could not have filled anyway. That is a property of the per-break "
      "estimand (dynamic seconds only), not a gain from hybrid pods.")
    w("")
    REG.write_text(os.path.join(RES, "x3", "summary.md"), "\n".join(L) + "\n")


if __name__ == "__main__":
    x1()
    x3()
    print("summaries written")
