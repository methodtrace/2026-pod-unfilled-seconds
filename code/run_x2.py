"""X2: one lever at a time from every X1 baseline; exact seconds recovered per break.

Baselines: every (law, convention, menu, cap in 3..12 or uncapped, demand scenario, rho in {1, 0.95}) of X1.
Levers (gain = baseline E[U] minus E[U] after the lever, same pools, same breaks):
  dur:c     add duration c in the union {5, 6, 10, 15, 20, 30, 45, 60} not in the menu (its creatives drawn with the fixed
            union mean for c); dur_best = the best of these
  cap+1     h -> h + 1 (under convention b the remainder cap moves with h); not applicable when uncapped
  cap+2     h -> h + 2
  range     rqddurs -> [min A, max A]: creatives of every other length in the range become eligible (fixed
            lengths, nothing stretches). Demand unlimited: exact, D_h(A) - D_h(R). Finite demand: sampled with
            standard errors under the declared supply of nonstandard lengths (podsim/eligibility.py, eps = 0.01),
            with the sweep eps in {0, 0.01, 0.05, 0.2} in range_e*; paired with the exact baseline's counts
  floor     not applicable: no floor is set in X1 (mincpmpersec = 0), so lowering it recovers nothing
  ready.99  rho 0.95 -> 0.99 (rho = 0.95 baselines only)
  ready1    rho 0.95 -> 1
Readiness is drawn after selection, so at rho every non-readiness gain is rho times its rho = 1 gain and
ready gains are (rho' - rho) (E[T] - E[U at rho = 1]).

Primary ranking set (one step of each lever): dur_best, cap+1, range, ready.99. Full set adds cap+2 and
ready1. Gains within 1e-9 s count as ties, and the sampled range gain ties with any lever within two standard errors.
Writes data/results/x2/.
"""
import csv
import json
import os
import sys
import time
from fractions import Fraction
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import levers, laws, pools, structural, grid, eligibility  # noqa: E402
from podsim import engines as E  # noqa: E402
from podsim.exact import TMAX  # noqa: E402
from podsim.laws import dynamic_cap  # noqa: E402
import run_x1  # noqa: E402
from podsim.numeric import xsum, nondominated  # noqa: E402

TIE = 1e-9
PRIMARY = ["dur_best", "cap+1", "range", "ready.99"]
FULL = PRIMARY + ["cap+2", "ready1"]


def best(gains, keys, ses=None):
    """Winning lever among keys ("none" if nothing recovers more than 1e-9 s; "tie:a+b" for ties).
    Winners are the levers no other lever beats by more than 1e-9 s plus two standard errors of the difference
    (numeric.nondominated; exact gains have no standard error)."""
    ses = ses or {}
    vals = [(gains[k], k) for k in keys if gains.get(k) is not None]
    if not vals:
        return "n/a"
    order = {k: i for i, k in enumerate(keys)}
    winners = sorted(nondominated(vals, ses, TIE), key=lambda k: order[k])
    if not winners:
        return "none"
    return ("tie:" + "+".join(winners)) if len(winners) > 1 else winners[0]


def elabel(e):
    """Column name of the range lever at nonstandard share e: range_e0, range_e0.01, range_e0.05, range_e0.2."""
    return "range_e%s" % ("0" if e == 0 else repr(e))


def menu_job(args):
    menu, cfg = args
    add = [c for c in cfg["x2_add"] if c not in menu]
    scens = [s for s in run_x1.scen_list(cfg["schemes"], cfg["lams"]) if s[2] is not None]
    ml = [s[2] for s in scens]
    lawnames = sorted({l for l, _ in cfg["laws"]})
    LD = {n: run_x1.law_obj(n) for n in lawnames}
    caps = cfg["caps"]
    ext = sorted({c for c in caps if c is not None} | {c + 1 for c in caps if c is not None} |
                 {c + 2 for c in caps if c is not None})
    kcaps = grid.needed_caps(ext, [c for _, c in cfg["laws"]])
    ME = {menu: levers.MenuExpect(menu, ml, LD, caps=kcaps)}
    for c in add:
        m2 = tuple(sorted(menu + (c,)))
        ME[m2] = levers.MenuExpect(m2, ml, LD, caps=kcaps)
    eps = list(eligibility.EPS_SWEEP)
    RG = eligibility.range_gains(menu, LD, cfg["laws"], caps, ml, eps, cfg["range_n"]) if ml else {}
    rmenu = structural.range_menu(menu)

    def Uex(A, lawname, conv, h):
        return xsum((w * structural.D(A, dynamic_cap(h, st, conv), T) for (T, st), w in LD[lawname].support),
                   Fraction(0))
    rows = []
    neg = 0
    zchk = []
    for lawname, conv in cfg["laws"]:
        law = LD[lawname]
        ET = float(xsum(w * T for (T, _), w in law.support))
        for h in caps:
            hp1 = None if h is None else h + 1
            hp2 = None if h is None else h + 2
            for si in range(len(scens) + 1):
                if si == len(scens):
                    sc, lam = "unlimited", "unlimited"
                    U0x = Uex(menu, lawname, conv, h)
                    g1 = {"dur:%d" % c: U0x - Uex(tuple(sorted(menu + (c,))), lawname, conv, h) for c in add}
                    if h is not None:
                        g1["cap+1"] = U0x - Uex(menu, lawname, conv, hp1)
                        g1["cap+2"] = U0x - Uex(menu, lawname, conv, hp2)
                    g1["range"] = U0x - Uex(rmenu, lawname, conv, h)
                    g1 = {k: float(v) for k, v in g1.items()}
                    for e in eps:
                        g1[elabel(e)] = g1["range"]
                    g1["range_se"] = 0.0
                    U0 = float(U0x)
                else:
                    sc, lam, _ = scens[si]
                    me = ME[menu]
                    U0 = me.U(lawname, conv, h, si)
                    g1 = {"dur:%d" % c: U0 - ME[tuple(sorted(menu + (c,)))].U(lawname, conv, h, si) for c in add}
                    if h is not None:
                        g1["cap+1"] = U0 - me.U(lawname, conv, hp1, si)
                        g1["cap+2"] = U0 - me.U(lawname, conv, hp2, si)
                    for e in eps:
                        g, se, b, seb = RG[(lawname, conv, h, si, e)]
                        g1[elabel(e)] = g
                        if e == eligibility.EPS_DECLARED:
                            g1["range"], g1["range_se"] = g, se
                            zchk.append((abs(b - U0), seb))
                neg += xsum(1 for k, v in g1.items() if v < -TIE and not k.startswith("range"))
                # The range admits every creative that adding a single duration strictly inside [min A, M]
                # admits, so its gain is at least that duration's exact gain, pool by pool. The sampled range
                # estimate can fall below that bound; levers are ranked on the bound-respecting value
                # range_rank = max(sampled range, best exact interior added duration). The range column itself
                # stays the sampled estimate.
                inner = [g1["dur:%d" % c] for c in add if min(menu) < c < max(menu)]
                g1["range_rank"] = max([g1["range"]] + inner)
                durk = sorted(k for k in g1 if k.startswith("dur:"))
                db = max(durk, key=lambda k: (g1[k], -int(k[4:]))) if durk else None
                for rho in (1.0, 0.95):
                    g = {k: rho * v for k, v in g1.items()}
                    g["dur_best"] = g[db] if db else None
                    g["dur_best_c"] = int(db[4:]) if db else None
                    if rho < 1:
                        g["ready.99"] = (0.99 - rho) * (ET - U0)
                        g["ready1"] = (1 - rho) * (ET - U0)
                    Ub = (1 - rho) * ET + rho * U0
                    rank = dict(g)
                    rank["range"] = g["range_rank"]
                    if h is None or g["dur_best"] is None:
                        hh = "n/a"
                    else:
                        dd = g["dur_best"] - g["cap+1"]
                        hh = "dur" if dd > TIE else ("cap+1" if dd < -TIE else ("tie0" if g["cap+1"] <= TIE else "tie"))
                    row = dict(law=lawname, conv=conv, menu=" ".join(map(str, menu)), h=("none" if h is None else h),
                               weights=sc, lam=lam, rho=rho, ET=ET, U=Ub, best_primary=best(rank, PRIMARY, {"range": g["range_se"]}),
                               best_full=best(rank, FULL, {"range": g["range_se"]}), dur_vs_cap1=hh)
                    for k in ["dur:%d" % c for c in pools.UNION] + ["dur_best", "dur_best_c", "cap+1",
                                                                              "cap+2", "range", "range_se", "range_rank"] + \
                            [elabel(e) for e in eps] + ["ready.99", "ready1"]:
                        row[k] = g.get(k)
                    # winner set of the finite-demand split (dur_best, cap+1, range), chosen here on unrounded
                    # gains so that run_x2_split.py never re-selects on the nine-decimal serialized values
                    sw = nondominated([(g[k], k) for k in ("dur_best", "cap+1", "range_rank") if g.get(k) is not None],
                                      {"range_rank": g["range_se"]}, TIE)
                    row["split_winners"] = "|".join(sorted("range" if k == "range_rank" else k for k in sw)) or "none"
                    rows.append(REG.canon(row))
    # Proposition 2 at stable caps, demand unlimited
    stab = dict(cases=0, stable_targets=0, targets=0, gain_targets_at_stable=0, fully_stable_cases=0,
                positive_gain_cases_fully_stable=0)
    for lawname, conv in cfg["laws"]:
        for h in caps:
            for c in add:
                ns, nt, allst, ng = levers.stability_assert(menu, c, LD[lawname], conv, h)
                stab["cases"] += 1
                stab["stable_targets"] += ns
                stab["targets"] += nt
                stab["gain_targets_at_stable"] += ng
                if allst:
                    stab["fully_stable_cases"] += 1
                    if ng:
                        stab["positive_gain_cases_fully_stable"] += 1
    # sampler check: sampled baseline E[U] against the exact one, same cells (rare events make the SE small)
    zs = [d / se for d, se in zchk if se > 0]
    return dict(rows=rows, neg=neg, stab=stab, pruned=max(max(m.pruned) for m in ME.values()),
                range_check=dict(cells=len(zchk), max_abs_diff=max([d for d, _ in zchk] or [0.0]),
                                 sum_z2=xsum(z * z for z in zs), n_z=len(zs), z_over_4=xsum(1 for z in zs if z > 4),
                                 zero_se_diff=xsum(1 for d, se in zchk if se == 0 and d > 1e-9)))


def units(cfg):
    return [("menu_" + "-".join(map(str, m)), (m, cfg)) for m in cfg["x2_menus"]]


FIELDS = ["law", "conv", "menu", "h", "weights", "lam", "rho", "ET", "U", "best_primary", "best_full", "dur_vs_cap1"
          ] + ["dur:%d" % c for c in pools.UNION] + ["dur_best", "dur_best_c", "cap+1", "cap+2", "range",
          "range_se"] + [elabel(e) for e in eligibility.EPS_SWEEP] + ["ready.99", "ready1", "range_rank", "split_winners"]


def main():
    cfg = REG.config()
    us = units(cfg)
    if REG.units_only([("x2", us, menu_job, False)]):
        return
    out = REG.out_dir("x2")
    t0 = time.time()
    st = REG.CsvStream(os.path.join(out, REG.table_name("x2_table")))
    n = 0
    res = []
    for r in REG.iter_units("x2", us, menu_job):
        st.write([{k: x.get(k) for k in FIELDS} for x in r["rows"]])
        n += len(r["rows"])
        r["rows"] = None
        res.append(r)
    st.close()
    stab = {k: xsum(r["stab"][k] for r in res) for k in res[0]["stab"]}
    rc = [r["range_check"] for r in res]
    meta = dict(tier=cfg["tier"], rows=n, negative_gains=xsum(r["neg"] for r in res), stability=stab,
                pruned_max=max(r["pruned"] for r in res), engine_hashes=E.HASHES,
                range_lever=dict(model="eligibility of fixed-length creatives in [min A, max A]; finite demand sampled",
                                 samples=cfg["range_n"], master=eligibility.MASTER, eps_declared=eligibility.EPS_DECLARED,
                                 eps_sweep=list(eligibility.EPS_SWEEP),
                                 baseline_check="sampled baseline E[U] against the exact one in every finite-demand "
                                                "cell at eps = 0.01: |diff|, z = |diff| / se (rare-event cells have small "
                                                "se), and cells with se = 0 but a nonzero difference",
                                 baseline_check_cells=xsum(x["cells"] for x in rc),
                                 baseline_check_max_abs_diff=max(x["max_abs_diff"] for x in rc),
                                 baseline_check_mean_z2=(xsum(x["sum_z2"] for x in rc) / max(1, xsum(x["n_z"] for x in rc))),
                                 baseline_check_z_over_4=xsum(x["z_over_4"] for x in rc),
                                 baseline_check_zero_se_diff=xsum(x["zero_se_diff"] for x in rc)))
    REG.write_json(os.path.join(out, "x2_meta.json"), meta)
    REG.write_timing(out, "wall", time.time() - t0)
    print("x2 rows", n, "neg", meta["negative_gains"], "stab", stab, "%.1f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
