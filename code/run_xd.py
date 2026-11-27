"""XD: demand sweep (catalog D3 fine lambda grid, D4 negative binomial pools) and readiness by creative age
(R2), exact, per menu.

For each menu of the tier, each law-convention pair, each cap and each demand scenario (Poisson counts on the
lambda grid 1, 2, 4, ..., 256 for every weight scheme, then negative binomial counts with dispersion k in
{1, 4} on the same grid; podsim/demand.py), the accounting identity at rho = 1 (decompose.py): E[U], the
structural floor and the demand part (exact finite sums, double precision), the structural split into
arith_part, cap_part and range_residual (exact at unlimited demand, the same in every demand scenario), and
the top structural lever of X2 restricted to cap+1 (exact) and range (eligibility of fixed-length creatives at
the declared nonstandard share, sampled with standard errors, podsim/eligibility.py); the added-duration lever
needs one extra menu per duration and is in X2 on the X1 grid.

R2 (xd_r2.csv): for a few demand scenarios per cell and every (share new, rho_new, rho_old) of demand.R2 grid,
the identity at rho_eff = s rho_new + (1 - s) rho_old (exact under independence of age from selection; demand.py
states the assumption and why it holds here).

Writes <out>/xd/{xd_table.csv[.gz], xd_r2.csv[.gz], xd_meta.json}; timing in timing.json only.
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import demand, decompose, eligibility, exact, grid, levers, structural  # noqa: E402
from podsim import engines as E  # noqa: E402
from podsim.laws import dynamic_cap  # noqa: E402
import run_x1  # noqa: E402
from podsim.numeric import xsum, nondominated  # noqa: E402

N = frozenset
TIE = 1e-9


def top_label(g, ses=None):
    """Top lever(s) joined by " & " ("none" if nothing recovers more than 1e-9 s).
    Winners by numeric.nondominated (the X2 rule)."""
    ses = ses or {}
    vals = [(v, k) for k, v in g.items() if v is not None]
    if not vals:
        return "n/a"
    w = nondominated(vals, ses, TIE)
    return " & ".join(w) if w else "none"


def scen_for(cfg):
    return demand.scenarios(cfg["xd_schemes"], cfg["xd_lams"], cfg["xd_ks"])


def menu_job(args):
    menu, cfg = args
    menu = tuple(menu)
    scens = scen_for(cfg)
    ml = [s[4] for s in scens]
    lawnames = sorted({l for l, _ in cfg["xd_laws"]})
    LD = {n: run_x1.law_obj(n) for n in lawnames}
    caps = cfg["xd_caps"]
    convs = sorted({c for _, c in cfg["xd_laws"]})
    capsx = caps + [h + 1 for h in caps if h is not None]
    kcaps = grid.needed_caps(sorted(set(capsx), key=lambda x: (x is None, x)), convs)
    me = levers.MenuExpect(menu, ml, LD, caps=kcaps or [1])
    vals = grid.menu_values(menu, LD, cfg["xd_laws"], sorted(set(capsx), key=lambda x: (x is None, x)), ml, me=me)
    ed = eligibility.EPS_DECLARED
    RG = eligibility.range_gains(menu, LD, cfg["xd_laws"], caps, ml, [ed], cfg["xd_range_n"]) if ml else {}
    rmenu = structural.range_menu(menu)
    r2 = demand.r2_configs()
    r2_idx = [i for i, s in enumerate(scens) if (s[3], s[1], s[2]) in [tuple(x) for x in cfg["xd_r2_scen"]]]
    rows = []
    rrows = []
    S = len(ml)
    for lawname, conv in cfg["xd_laws"]:
        law = LD[lawname]
        for h in caps:
            unl = vals[(lawname, conv, h, S)]["U"]
            us = unl[N(["dem"])]
            g_unl = {"cap+1": (float(us - vals[(lawname, conv, h + 1, S)]["U"][N(["dem"])]) if h is not None else None),
                     "range": float(us - xsum((w * structural.D(rmenu, dynamic_cap(h, st, conv), T)
                                              for (T, st), w in law.support), 0))}
            sp = decompose.struct_split(us, unl[N(["arith", "dem"])], unl[N(["cap", "dem"])],
                                        unl[N(["arith", "cap", "dem"])])
            for si, (lab, sc, lam, cl, _) in enumerate(scens):
                r = vals[(lawname, conv, h, si)]
                u0 = float(r["U"][N()])
                gr, gse, _, _ = RG[(lawname, conv, h, si, ed)]
                g = {"cap+1": (u0 - me.U(lawname, conv, h + 1, si)) if h is not None else None, "range": gr}
                top = top_label(g, {"range": gse})
                tied = top.split(" & ")
                # structural if any lever in the tied winning set has a positive structural gain (as in X2's split)
                kind = "" if tied[0] in ("none", "n/a") else (
                    "structural" if any((g_unl.get(lv) or 0) > TIE for lv in tied) else "no structural gain")
                rows.append(REG.canon(dict(law=lawname, conv=conv, menu=" ".join(map(str, menu)),
                                           h=("none" if h is None else h), count_law=cl, weights=sc, lam=lam,
                                           ET=float(r["ET"]), U=u0, Ustruct=float(us),
                                           share=(float(us) / u0 if u0 > 0 else None), demand_part=u0 - float(us),
                                           arith_part=float(sp["arith"]), cap_part=float(sp["cap"]),
                                           range_residual=float(sp["residual"]),
                                           gain_cap1=g["cap+1"], gain_range=g["range"], gain_range_se=gse,
                                           top_lever=top, top_kind=kind, pruned=me.pruned[si])))
                if si in r2_idx:
                    for s_new, rn, ro, rho in r2:
                        ip = decompose.identity_parts(u0, float(us), float(r["ET"]), rho)
                        rrows.append(REG.canon(dict(law=lawname, conv=conv, menu=" ".join(map(str, menu)),
                                                    h=("none" if h is None else h), count_law=cl, weights=sc,
                                                    lam=lam, share_new=s_new, rho_new=rn, rho_old=ro, rho_eff=rho,
                                                    U=ip["U"], Ustruct=ip["structural"], demand_part=ip["demand"],
                                                    ready_part=ip["readiness"])))
    return dict(rows=rows, r2=rrows, pruned=max(me.pruned) if me.pruned else 0.0)


FIELDS = ["law", "conv", "menu", "h", "count_law", "weights", "lam", "ET", "U", "Ustruct", "share", "demand_part",
          "arith_part", "cap_part", "range_residual", "gain_cap1", "gain_range", "gain_range_se", "top_lever",
          "top_kind", "pruned"]
R2_FIELDS = ["law", "conv", "menu", "h", "count_law", "weights", "lam", "share_new", "rho_new", "rho_old",
             "rho_eff", "U", "Ustruct", "demand_part", "ready_part"]


def units(cfg):
    return [("menu_" + "-".join(map(str, m)), (tuple(m), cfg)) for m in cfg["xd_menus"]]


def main():
    cfg = REG.config()
    us = units(cfg)
    if REG.units_only([("xd", us, menu_job, False)]):
        return
    out = REG.out_dir("xd")
    t0 = time.time()
    st = REG.CsvStream(os.path.join(out, REG.table_name("xd_table")))
    sr = REG.CsvStream(os.path.join(out, REG.table_name("xd_r2")))
    n = nr = 0
    pruned = 0.0
    for r in REG.iter_units("xd", us, menu_job):
        st.write([{k: x.get(k) for k in FIELDS} for x in r["rows"]])
        sr.write([{k: x.get(k) for k in R2_FIELDS} for x in r["r2"]])
        n += len(r["rows"])
        nr += len(r["r2"])
        pruned = max(pruned, r["pruned"])
    st.close()
    sr.close()
    REG.write_json(os.path.join(out, "xd_meta.json"), dict(
        tier=cfg["tier"], rows=n, r2_rows=nr, menus=[list(m) for m in cfg["xd_menus"]],
        laws=[list(x) for x in cfg["xd_laws"]], caps=cfg["xd_caps"], schemes=list(cfg["xd_schemes"]),
        lams=list(cfg["xd_lams"]), nb_dispersion=list(cfg["xd_ks"]), r2_scenarios=[list(x) for x in cfg["xd_r2_scen"]],
        r2_grid=[list(x) for x in demand.r2_configs()], pruned_max=pruned, tmax=exact.TMAX, engine_hashes=E.HASHES,
        exact="finite sums over truncated Poisson or negative binomial count laws, double precision; R2 exact "
              "under independence of creative age from selection; gain_range sampled (eligibility.py)",
        range_samples=cfg["xd_range_n"], range_eps=eligibility.EPS_DECLARED, range_master=eligibility.MASTER))
    REG.write_timing(out, "wall", time.time() - t0)
    print("xd rows", n, "r2 rows", nr, "%.1f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
