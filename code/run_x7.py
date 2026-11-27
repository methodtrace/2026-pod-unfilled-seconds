"""X7: integer seconds versus 90 kHz ticks (podsim/ticks.py).

Part A (exact): demand unlimited, systematic perturbations sys+ (every creative +eps), sys- (-eps) and ntsc
(derived 1001/1000 stretch), eps in {3003 ticks = 1 frame at 29.97 fps, 15 ms, 50 ms, 100 ms, 0.5 s},
tolerance in {0, eps} (ntsc: eps = largest menu delta, 90 * max A ticks), all seven menus, caps {4, 6, 8,
uncapped}, laws L1, L2 (a), L3 uniform. Reports E[U_tick], E[overrun], and
Delta = E[U_tick] - E[U_int] - 89999/180000 s (the mean sub-second offset), the same at offset 0 (delta0 =
E[U_tick] - E[U_int] on breaks that are whole seconds, as on a scheduled grid), plus the two-player arithmetic and
cap split of the structural floor (decompose.struct_split), in ticks and in integer seconds.

Part B (Monte Carlo, common random numbers): lambda = 16 balanced, independent per-creative perturbation
uniform on [-eps, eps] (same uniforms for every eps), and the ntsc model; same breaks, offsets and pools as
the integer model; paired differences with standard errors of U, the structural floor, the demand part and the
arithmetic and cap parts of the structural split. The pod builder is bid-priority within each nominal length:
for each length it takes a bid-order prefix of the creatives offered at that length, choosing the prefix lengths
that maximize filled ticks. The structural benchmark is the same builder on the demand-relaxed list (the actual
pool in bid order, then 48 extra creatives per length), so the demand part is nonnegative break by break.
Writes data/results/x7/.
"""
import csv
import json
import math
import os
import random
import sys
import time
from fractions import Fraction
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import ticks, structural, pools, decompose  # noqa: E402
from podsim.pod import select_menu, select_elastic  # noqa: E402
from podsim.laws import dynamic_cap  # noqa: E402
from podsim import engines as E  # noqa: E402
from podsim import registry as REG  # noqa: E402
import run_x1  # noqa: E402
from podsim.numeric import xsum  # noqa: E402

TPS = ticks.TPS
CFG = REG.config()
EPS = [tuple(e) for e in CFG["x7_eps"]]
MENUS = CFG["x7_menus"]
LAWS = CFG["x7_laws"]
CAPS = CFG["x7_caps"]
PARTB_MENUS = [m for m in MENUS if m in REG.M7]
PARTB_LAWS = [lc for lc in LAWS if lc in [("L1", "a"), ("L2", "a"), ("L3u", "a")]]
PARTB_CAPS = [c for c in CAPS if c in (4, 6, 8, None)]
OFF = Fraction(TPS - 1, 2 * TPS)
N3 = frozenset


def part_a_menu(menu):
    rows = []
    for lawname, conv in LAWS:
        law = run_x1.law_obj(lawname)
        if True:
            base = {h: xsum((w * structural.D(menu, dynamic_cap(h, st, conv), T) for (T, st), w in law.support), Fraction(0))
                    for h in CAPS}
            rng = structural.range_menu(menu)
            base_ar = {h: xsum((w * structural.D(rng, dynamic_cap(h, st, conv), T) for (T, st), w in law.support), Fraction(0))
                       for h in CAPS}
            configs = []
            for lab, e in EPS:
                for model in ("sys+", "sys-"):
                    for tol in (0, e):
                        configs.append((model, lab, e, tol))
            emax = 90 * max(menu)
            configs.append(("ntsc", "derived 1001/1000", emax, 0))
            configs.append(("ntsc", "derived 1001/1000", emax, emax))
            for model, lab, e, tol in configs:
                r = ticks.exact_sys_unlimited(menu, model, e, tol, law, CAPS, conv)
                r0 = ticks.exact_sys_unlimited(menu, model, e, tol, law, CAPS, conv, offset0=True)
                ra = ticks.exact_sys_unlimited(menu, model, e, tol, law, CAPS, conv, arith=True)
                for h in CAPS:
                    U = {N3(): r[h][0], N3(["cap"]): r[None][0], N3(["arith"]): ra[h][0], N3(["arith", "cap"]): ra[None][0]}
                    Ui = {N3(): base[h] + OFF, N3(["cap"]): base[None] + OFF, N3(["arith"]): base_ar[h] + OFF,
                          N3(["arith", "cap"]): base_ar[None] + OFF}
                    ph = decompose.struct_split(U[N3()], U[N3(["arith"])], U[N3(["cap"])], U[N3(["arith", "cap"])])
                    pi = decompose.struct_split(Ui[N3()], Ui[N3(["arith"])], Ui[N3(["cap"])], Ui[N3(["arith", "cap"])])
                    ph = {k: float(v) for k, v in ph.items()}
                    pi = {k: float(v) for k, v in pi.items()}
                    rows.append(dict(part="A", law=lawname, conv=conv, menu=" ".join(map(str, menu)),
                                     h=("none" if h is None else h), model=model, eps_label=lab, eps_ticks=e,
                                     tol_ticks=tol, U_int=float(base[h]), U_tick=float(r[h][0]),
                                     overrun=float(r[h][1]), delta=float(r[h][0] - base[h] - OFF),
                                     delta_exact=str(r[h][0] - base[h] - OFF),
                                     U_tick0=float(r0[h][0]), overrun0=float(r0[h][1]),
                                     delta0=float(r0[h][0] - base[h]),
                                     phi_arith_tick=ph["arith"], phi_cap_tick=ph["cap"],
                                     phi_arith_int=pi["arith"], phi_cap_int=pi["cap"]))
    return [REG.canon(r) for r in rows]


def part_a_units():
    return [("menu_" + "-".join(map(str, m)), tuple(m)) for m in MENUS]


# ------------------------------------------------------------------------------- part B

MASTER = "pods-x7-v1"
KPOOL = 48


def mc_break(i, law, conv, menu, cfgs, w, vl):
    """One break: {(cfg, h, quantity): value} for cfg in ['int'] + indices of cfgs. Quantities: U (actual pool,
    exact menu, cap h), Ustruct (demand-relaxed pool), demand = U - Ustruct, and the arithmetic and cap parts of
    the structural split on the demand-relaxed pool (decompose.struct_split)."""
    m, M = min(menu), max(menu)
    T, st = pools.break_target(MASTER, law, i)
    o = random.Random("%s|off|%d" % (MASTER, i)).randrange(TPS)
    pbd = {a: pools.duration_stream(MASTER, i, a, 16 * w[a], KPOOL, vl) for a in menu}
    uu = {}
    for a in menu:
        tr = ticks.tick_rng(MASTER, i, a)
        pool, extras = pbd[a]
        for c in pool + extras:
            uu[c.ident] = tr.random()
    Tt = TPS * T + o
    res = {}
    for dem in (False, True):
        # The demand-relaxed list keeps the actual pool's bid order first and appends the extra creatives, so
        # every bid-order prefix of the actual pool is also a prefix of the relaxed list and the relaxed fill is
        # at least the actual fill break by break, also when creatives of one nominal length differ in ticks.
        by = decompose.build_pools(menu, pbd, dem, extras_last=True)
        flat = sorted([c for a in menu for c in pbd[a][0]], key=lambda c: -c.v)
        if dem:  # extras after the whole actual pool (only the relaxed list has range fills)
            flat += sorted([c for a in menu for c in pbd[a][1]], key=lambda c: -c.v)
        combos = [(False, False)] if not dem else [(False, False), (False, True), (True, False), (True, True)]
        for h in PARTB_CAPS:
            for ar, capr in combos:
                cap = None if capr else dynamic_cap(h, st, conv)
                if ar:
                    res[("int", h, dem, ar, capr)] = T - select_elastic(T, cap, flat, m, M)[0].seconds + o / TPS
                else:
                    res[("int", h, dem, ar, capr)] = T - select_menu(T, cap, by)[0].seconds + o / TPS
                for ci, (model, lab, e, tol) in enumerate(cfgs):
                    if model == "indep":
                        dl = {c.ident: int(round((2 * uu[c.ident] - 1) * e)) for a in menu for c in by[a]}
                        if ar:
                            f = ticks.select_ticks_elastic(Tt + tol, cap, [dl[c.ident] for c in flat], m, M)
                        else:
                            tl = {a: [TPS * a + dl[c.ident] for c in by[a]] for a in menu}
                            f = ticks.select_ticks(Tt + tol, cap, tl, menu)
                    else:
                        if ar:
                            f = ticks.select_ticks_elastic(Tt + tol, cap, [0] * len(flat), m, M, ntsc=True)
                        else:
                            tl = {a: [(TPS + 90) * a] * len(by[a]) for a in menu}
                            f = ticks.select_ticks(Tt + tol, cap, tl, menu)
                    res[(ci, h, dem, ar, capr)] = max(0, Tt - f) / TPS
    out = {}
    for k in ["int"] + list(range(len(cfgs))):
        for h in PARTB_CAPS:
            V = [res[(k, h, True, ar, capr)] for ar, capr in ((False, False), (True, False), (False, True), (True, True))]
            # the range relaxation may use any of its lengths, so it fills at least what the menu fills on the same
            # list; in ticks the range builder (one value-ordered prefix with fixed deltas) can do worse than the
            # menu's per-length prefixes, so the relaxed fill is the better of the two
            V[1] = min(V[1], V[0])
            V[3] = min(V[3], V[2])
            sp = decompose.struct_split(*V)
            u = res[(k, h, False, False, False)]
            out[(k, h, "U")] = u
            out[(k, h, "Ustruct")] = V[0]
            if u - V[0] < -1e-9:
                raise AssertionError("negative demand part: break %d, %s, h %s, %s: U %r < Ustruct %r"
                                     % (i, law, h, k, u, V[0]))
            out[(k, h, "demand")] = u - V[0]
            out[(k, h, "arith")] = sp["arith"]
            out[(k, h, "cap")] = sp["cap"]
    return out


def mc_block(args):
    lawname, conv, menu, n = args
    law = run_x1.law_obj(lawname)
    w = pools.weights("balanced")
    vl = pools.ValueLaw()
    M = max(menu)
    cfgs = [("indep", lab, e, tol) for lab, e in EPS for tol in (0, e)]
    cfgs.append(("ntsc", "derived 1001/1000", 90 * M, 0))
    cfgs.append(("ntsc", "derived 1001/1000", 90 * M, 90 * M))
    S, S2, D, D2 = {}, {}, {}, {}
    t0 = time.time()
    for i in range(n):
        r = mc_break(i, law, conv, menu, cfgs, w, vl)
        for key, v in r.items():
            S[key] = S.get(key, 0.0) + v
            S2[key] = S2.get(key, 0.0) + v * v
            if key[0] != "int":
                d = v - r[("int",) + key[1:]]
                D[key] = D.get(key, 0.0) + d
                D2[key] = D2.get(key, 0.0) + d * d
    rows = []
    for ci, (model, lab, e, tol) in enumerate(cfgs):
        for h in PARTB_CAPS:
            for q in ("U", "Ustruct", "demand", "arith", "cap"):
                k = (ci, h, q)
                ki = ("int", h, q)
                mi = S[ki] / n
                md = D[k] / n
                sd = math.sqrt(max(D2[k] / n - md * md, 0.0) * n / (n - 1) / n)
                rows.append(REG.canon(dict(part="B", law=lawname, conv=conv, menu=" ".join(map(str, menu)),
                                 h=("none" if h is None else h), model=model, eps_label=lab, eps_ticks=e, tol_ticks=tol,
                                 quantity=q, int_mean=mi, tick_mean=S[k] / n, paired_diff=md, paired_se=sd,
                                 offset_mean=float(OFF), n=n)))
    return rows, time.time() - t0, (lawname, conv, menu)


def part_b_units():
    return [("%s-%s_%s" % (l, c, "-".join(map(str, m))), (l, c, tuple(m), CFG["x7_n"])) for l, c in PARTB_LAWS
            for m in PARTB_MENUS]


def part_b_unit(args):
    rows, dt, k = mc_block(args)
    return dict(rows=rows, seconds=round(dt, 3), key=[k[0], k[1], list(k[2])])


def main():
    ua, ub = part_a_units(), part_b_units()
    if REG.units_only([("x7a", ua, part_a_menu, False), ("x7b", ub, part_b_unit, False)]):
        return
    nb = CFG["x7_n"]
    out = REG.out_dir("x7")
    t0 = time.time()
    sa = REG.CsvStream(os.path.join(out, REG.table_name("x7_partA")))
    na = 0
    for part in REG.iter_units("x7a", ua, part_a_menu):
        sa.write(part)
        na += len(part)
    sa.close()
    ta = time.time() - t0
    print("part A rows", na, "%.0f s" % ta, flush=True)
    t1 = time.time()
    outs = REG.map_units("x7b", ub, part_b_unit)
    rb = [r for o in outs for r in o["rows"]]
    tb = time.time() - t1
    REG.write_csv(os.path.join(out, REG.table_name("x7_partB")), rb)
    REG.write_json(os.path.join(out, "x7_meta.json"), dict(tier=CFG["tier"], master=MASTER, n=nb, partA_rows=na,
                                                           partB_rows=len(rb), engine_hashes=E.HASHES))
    REG.write_timing(out, "partA", ta)
    REG.write_timing(out, "partB", tb)
    for o in outs:
        k = o["key"]
        REG.write_timing(out, "partB_" + "_".join(map(str, k[:2])) + "_" + "-".join(map(str, k[2])), o["seconds"])
    print("part B rows", len(rb), "%.0f s" % tb)


if __name__ == "__main__":
    main()
