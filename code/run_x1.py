"""X1: structural unfilled seconds and the accounting-identity decomposition (podsim/decompose.py), exact, over the
tier's grid (registry.TIERS), plus a sampled verifier.

Per row (law, convention, menu, cap, demand scenario, rho): U = structural + demand + readiness exactly, with
structural = E[D_h(A;T)] split at unlimited demand into arith_part + cap_part + range_residual (two-player
Shapley over the exact menu versus the range of lengths and the cap; I_AC their interaction).

Usage: python3 run_x1.py   (tier from PODSIM_TIER, output root from PODSIM_OUT)
Writes <out>/x1/{x1_table.csv[.gz], x1_verify.json, x1_meta.json, timing.json}.
"""
import os
import sys
import time
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import exact, laws, pools, decompose, scenario, grid  # noqa: E402
from podsim import engines as E  # noqa: E402

N = frozenset
LAW_NAMES = {"L1": None, "L2": None, "L3u": None, "L3s": None, "L4u5": None, "L4u15": None, "L4s5": None,
             "L4s15": None, "L5": None, "L6": None, "L7": None}


def law_obj(name):
    if name == "L1":
        return laws.Law.plain("L1", laws.L1(60, 240, 30))
    return laws.named(name)


# kept for scripts that import them
MENUS = REG.M7
LAWS = REG.NARROW_LAWS
HS = list(range(3, 13)) + [None]
LAMS = list(REG.LAMS)
SCHEMES = list(REG.SCHEMES)


def scen_list(schemes=None, lams=None):
    out = [("unlimited", None, None)]
    for sc in (schemes or REG.SCHEMES):
        w = pools.weights(sc)
        for lam in (lams or REG.LAMS):
            out.append((sc, lam, {a: lam * w[a] for a in pools.UNION}))
    return out


def f(x):
    return float(x)


def menu_rows(args):
    menu, cfg = args
    scens = [s for s in scen_list(cfg["schemes"], cfg["lams"]) if s[2] is not None]
    lawnames = sorted({l for l, _ in cfg["laws"]})
    LD = {n: law_obj(n) for n in lawnames}
    vals = grid.menu_values(menu, LD, cfg["laws"], cfg["caps"], [s[2] for s in scens])
    allsc = scens + [("unlimited", "unlimited", None)]
    rows = []
    for lawname, conv in cfg["laws"]:
        for si, (sc, lam, _) in enumerate(allsc):
            for h in cfg["caps"]:
                r = vals[(lawname, conv, h, si)]
                U, ET = r["U"], r["ET"]
                us = U[N(["dem"])]
                sp = decompose.struct_split(us, U[N(["arith", "dem"])], U[N(["cap", "dem"])],
                                            U[N(["arith", "cap", "dem"])])
                u_r1 = f(U[N()])
                for rho in cfg["rhos"]:
                    ip = decompose.identity_parts(u_r1, f(us), f(ET), rho)
                    u = ip["U"]
                    rows.append(REG.canon(dict(
                        law=lawname, conv=conv, menu=" ".join(map(str, menu)), h=("none" if h is None else h),
                        weights=sc, lam=lam, rho=rho, ET=f(ET), U=u, Ustruct=f(us), Ustruct_exact=str(us),
                        share=(f(us) / u if u > 0 else None), demand_part=ip["demand"], ready_part=ip["readiness"],
                        arith_part=f(sp["arith"]), cap_part=f(sp["cap"]), range_residual=f(sp["residual"]),
                        I_AC=f(sp["I_AC"]), I_AC_exact=str(sp["I_AC"]),
                        struct_cap_part=f(us - U[N(["cap", "dem"])]), struct_arith_floor=f(U[N(["cap", "dem"])]),
                        unfilled_frac_of_time=u / f(ET), P_struct_pos=f(r["P_struct_pos"]))))
    return rows


FIELDS = ["law", "conv", "menu", "h", "weights", "lam", "rho", "ET", "U", "Ustruct", "Ustruct_exact", "share",
          "demand_part", "ready_part", "arith_part", "cap_part", "range_residual", "I_AC", "I_AC_exact",
          "struct_cap_part", "struct_arith_floor", "unfilled_frac_of_time", "P_struct_pos"]


def menu_key(menu):
    return "menu_" + "-".join(map(str, menu))


def menu_units(cfg):
    return [(menu_key(m), (m, cfg)) for m in cfg["menus"]]


def cached_menu_rows(args):
    menu, cfg = args
    return REG.cached("x1", menu_key(menu), lambda: menu_rows(args))


# ------------------------------------------------------------------------- Monte Carlo verifier

MASTER = "pods-x1-verify-v1"


def verify_one(args):
    lawname, conv, menu, lam, sc, n, caps = args
    law = law_obj(lawname)
    t0 = time.time()
    st, _ = scenario.run_block(MASTER, law, menu, lam, sc, caps, [1.0, 0.95], conv, n)
    w = pools.weights(sc)
    res = exact.combos_for(menu, law, conv, caps, [{a: lam * w[a] for a in pools.UNION}])
    out = []
    for h in caps:
        r = res[(0, h)]
        U = r["U"]
        sp = decompose.struct_split(*(f(U[N(k)]) for k in (["dem"], ["arith", "dem"], ["cap", "dem"],
                                                            ["arith", "cap", "dem"])))
        for rho in (1.0, 0.95):
            s = st[(h, rho)]
            ip = decompose.identity_parts(f(U[N()]), f(U[N(["dem"])]), f(r["ET"]), rho)
            ex = {"U": ip["U"], "Ustruct": ip["structural"], "demand": ip["demand"], "readiness": ip["readiness"],
                  "arith": sp["arith"], "cap": sp["cap"], "residual": sp["residual"]}
            for k in sorted(ex):
                v = ex[k]
                se = s.se(k)
                if se > 0:
                    z = (s.mean(k) - v) / se
                elif abs(s.mean(k) - v) <= 1e-9:
                    z = 0.0  # no sampling variance: the sampled value must equal the exact one
                else:
                    raise AssertionError("X1 verifier: zero-variance %s differs from exact (%r vs %r): %s %s %s h %s"
                                         % (k, s.mean(k), v, lawname, conv, menu, h))
                out.append(dict(law=lawname, conv=conv, menu=list(menu), lam=lam, weights=sc, h=h, rho=rho, q=k,
                                exact=v, mc=s.mean(k), se=se, z=z))
    return out, time.time() - t0


def verify_units(cfg):
    jobs = [v + (cfg["verify_n"], cfg["verify_caps"]) for v in cfg["verify"]]
    return [("block_%d_%s-%s_%s_l%d_%s" % (i, j[0], j[1], "-".join(map(str, j[2])), j[3], j[4]), j)
            for i, j in enumerate(jobs)]


def verify_unit(args):
    rows, dt = verify_one(args)
    return dict(rows=[REG.canon(r) for r in rows], seconds=round(dt, 3))


def main():
    cfg = REG.config()
    mu, vu = menu_units(cfg), verify_units(cfg)
    if REG.units_only([("x1", mu, menu_rows, False), ("x1v", vu, verify_unit, False)]):
        return
    out = REG.out_dir("x1")
    t0 = time.time()
    stream = REG.CsvStream(os.path.join(out, REG.table_name("x1_table")))
    nrows = 0
    for part in REG.iter_units("x1", mu, menu_rows):
        stream.write([{k: r.get(k) for k in FIELDS} for r in part])
        nrows += len(part)
    stream.close()
    t_exact = time.time() - t0
    t1 = time.time()
    vo = REG.map_units("x1v", vu, verify_unit)
    vrows = [x for o in vo for x in o["rows"]]
    REG.write_json(os.path.join(out, "x1_verify.json"), dict(n=cfg["verify_n"], master=MASTER, blocks=len(vu),
                                                             rows=vrows))
    REG.write_json(os.path.join(out, "x1_meta.json"), dict(tier=cfg["tier"], rows=nrows, engine_hashes=E.HASHES,
                                                           menus=[list(m) for m in cfg["menus"]],
                                                           laws=cfg["laws"], caps=cfg["caps"], schemes=cfg["schemes"],
                                                           lams=cfg["lams"], rhos=cfg["rhos"], tmax=exact.TMAX))
    REG.write_timing(out, "exact_wall", t_exact)
    REG.write_timing(out, "verify_wall", time.time() - t1)
    for i, o in enumerate(vo):
        REG.write_timing(out, "verify_block_%d" % i, o["seconds"])
    print("x1 rows", nrows, "exact %.1f s" % t_exact, "verify %.1f s" % (time.time() - t1))


if __name__ == "__main__":
    main()
