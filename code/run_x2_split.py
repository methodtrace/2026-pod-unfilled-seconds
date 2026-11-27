"""Split each X2 lever gain into a structural part and a finite-demand residual.

For every finite-demand baseline (law, conv, menu, h, weights, lam, rho), the structural part of a lever's gain
is that lever's gain on the demand-unlimited row with the same law, conv, menu, h and rho; the residual is the
rest (finite-demand gain minus structural gain). The residual is a signed interaction between the lever and the
finite pool, not a count of admitted creatives: one more ad admits no creatives yet can have a positive residual,
and the residual can be negative. The winner among add duration, cap+1 and range uses the same rule as X2
(gains within 1e-9 s tie; the sampled range gain ties within two standard errors of the difference); a winner is
"structural" if any lever in the tied winning set has a positive structural part, else "no structural gain".
Reads x2/x2_table and writes x2/split.csv (split.csv.gz in the full tier) and x2/split.md under the results root.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim.numeric import nondominated  # noqa: E402

LEVERS = ["dur_best", "cap+1", "cap+2", "range"] + ["dur:%d" % c for c in (5, 6, 10, 15, 20, 30, 45, 60)]
PRIMARY = ("dur_best", "cap+1", "range")
TOL = 1e-9


def key(r):
    return (r["law"], r["conv"], str(r["menu"]), r["h"], r["rho"])


def num(x):
    return float(x) if x not in ("", None) else None


def regime(h):
    if h in ("", None, "none"):
        return "uncapped"
    h = int(h)
    return "h <= 4" if h <= 4 else ("h 5-7" if h <= 7 else "h >= 8")


def demand(lam):
    lam = int(lam)
    return "thin (2-8)" if lam <= 8 else "lambda %d" % lam


def iter_menu_groups(path):
    """Rows of the X2 table grouped by menu (the table is written one menu after another), so memory holds one
    menu's rows at a time."""
    cur, buf = None, []
    for r in REG.iter_csv(path):
        if r["menu"] != cur and buf:
            yield buf
            buf = []
        cur = r["menu"]
        buf.append(r)
    if buf:
        yield buf


def tied_winners(gains, range_se):
    """Levers tied for the top finite-demand gain (numeric.nondominated, the X2 rule). Empty if nothing gains more
    than 1e-9 s."""
    vals = [(g, lv) for lv, (g, _) in gains.items()]
    return nondominated(vals, {"range": range_se}, TOL)


def split_rows(rows, agg):
    unl = {key(r): r for r in rows if str(r["lam"]) in ("unlimited", "inf", "") or r["weights"] == "unlimited"}
    out = []
    for r in rows:
        if key(r) in unl and r is unl[key(r)]:
            continue
        u = unl.get(key(r))
        if u is None:
            continue
        rec = {"law": r["law"], "conv": r["conv"], "menu": r["menu"], "h": r["h"], "weights": r["weights"],
               "lam": r["lam"], "rho": r["rho"]}
        gains = {}
        for lv in LEVERS:
            # the structural part of "add the best duration" is the demand-unlimited gain of the SAME duration
            # c chosen at this baseline, not of the best duration at demand unlimited
            ulv = ("dur:%d" % int(r["dur_best_c"])) if lv == "dur_best" and r.get("dur_best_c") not in ("", None) else lv
            g, gs = num(r.get(lv)), num(u.get(ulv))
            if g is None or gs is None:
                continue
            rec[lv + ":struct"] = round(gs, 9)
            rec[lv + ":residual"] = round(g - gs, 9)
            if lv in PRIMARY:
                gains[lv] = (g, gs)
        # the winner set is chosen by X2 on unrounded gains, with the range ranked on its dominance bound
        # (run_x2.py, split_winners); re-selecting here on nine-decimal values would drop gains at the tolerance
        sw = r.get("split_winners")
        if sw in (None, ""):
            raise ValueError("x2 table has no split_winners column: rerun run_x2.py")
        winners = [] if sw == "none" else [w for w in sw.split("|") if w in gains]
        if winners:
            kind = "structural" if any(gains[w][1] > TOL for w in winners) else "no structural gain"
            lab = "+".join(winners)
            rec["winner"], rec["winner_kind"] = lab, kind
            k = (regime(r["h"]), demand(r["lam"]), lab, kind)
            agg[k] = agg.get(k, 0) + 1
        else:
            rec["winner"], rec["winner_kind"] = "none", ""
        out.append(rec)
    return out


def main():
    res = REG.out_root()
    fields = ["law", "conv", "menu", "h", "weights", "lam", "rho", "winner", "winner_kind"]
    for lv in LEVERS:
        fields += [lv + ":struct", lv + ":residual"]
    agg = {}
    n = 0
    st = REG.CsvStream(os.path.join(res, "x2", REG.table_name("split")), fields=fields)
    for rows in iter_menu_groups(os.path.join(res, "x2", REG.table_name("x2_table"))):
        part = split_rows(rows, agg)
        st.write(part)
        n += len(part)
    st.close()
    L = ["# X2 split: structural part of each winning lever's gain", "",
         "Structural part = the lever's exact gain at demand unlimited for the same law, convention, menu, cap and "
         "rho; residual = finite-demand gain minus structural part (a signed interaction with the finite pool, not "
         "a count of admitted creatives). Winner among add duration (best c over the union), cap+1 and range at each "
         "finite-demand baseline, with X2's tie rule (1e-9 s; the sampled range gain within two standard errors); "
         "tied winners are listed together. Kind: structural if any winner has a positive structural part, else no "
         "structural gain. %d baselines." % n, "",
         "| Cap regime | Demand | Winning lever | Kind | Baselines |", "| --- | --- | --- | --- | --- |"]
    for k in sorted(agg):
        L.append("| %s | %s | %s | %s | %d |" % (k[0], k[1], k[2], k[3], agg[k]))
    REG.write_text(os.path.join(res, "x2", "split.md"), "\n".join(L) + "\n")
    print("x2 split rows %d" % n)


if __name__ == "__main__":
    main()
