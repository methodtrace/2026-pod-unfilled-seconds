"""X4: menu-ranking reversal map. Exact.

Usage: python3 run_x4.py [--tier quick|narrow|full] [--jobs J] [--out DIR] [--report-only]

Part A (demand unlimited, exact Fractions). For every pair of menus (A, A') from the seven study menus and the
85-menu grid (registry.menus_m7_m85(), 86 menus), every law-convention pair of the tier and caps 1..20 and
uncapped, the sign of E[D_h(A;T)] - E[D_h(A')] along the caps, the reversal points, the leads and the magnitude
(podsim/reversal.py). Each unordered pair is listed once with A before A' in menu order; the ordered pair
(A', A) has the mirrored signs, so ordered counts are twice the unordered ones.
Checks (labels P1 to P4 name checks here, not pod policies): (P1) Proposition 2: the least cap at which the mean equals its uncapped value equals
max_T l(p(T)) computed independently (engine E-C membership), and no reversal lies above the larger of the two
menus' stability caps; (P2) Proposition 1(b, e) where both menus fill every target; (P3) a two-regime predictor
(longest part at h = 1, lattice floor at the limit), reported as a confusion matrix; (P4) Corollary 4 on
exact window totals in reduced units, where hd >= c1 + c2 and both sets are at equality levels.
Part B (demand limited, exact sums of truncated Poisson probabilities in double precision, exact.py): the
seven study menus, lambda 16 and 64, weights balanced and 15/30-dominant, caps 1..14 and uncapped, laws with T <= 240.

Determinism: no randomness; outputs do not depend on --jobs. Timing only in timing.json.
Designed consequence: that menu rankings can reverse with h is built into the arithmetic (undershoot companion); X4 measures
where, how often and how large.
"""
import argparse
import os
import sys
import time
from fractions import Fraction
from statistics import median

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import laws as LAWS  # noqa: E402
from podsim import structural, pools  # noqa: E402
from podsim import reversal as RV  # noqa: E402
from podsim.checks import semigroup_member  # noqa: E402
from podsim.laws import dynamic_cap  # noqa: E402
from podsim.numeric import xsum  # noqa: E402

ALL_LAWS = [("L1", "a"), ("L2", "a"), ("L2", "b"), ("L3u", "a"), ("L3s", "a"), ("L4u5", "a"), ("L4u15", "a"),
            ("L4s5", "a"), ("L4s15", "a"), ("L5", "a"), ("L6", "a"), ("L7", "a")]
DEM_LAWS_ALL = [("L1", "a"), ("L2", "a"), ("L2", "b"), ("L3u", "a"), ("L3s", "a"), ("L4u5", "a"), ("L4u15", "a")]
LATTICE = {"L3u": 1, "L4u5": 5, "L4u15": 15, "L3s": 1, "L4s5": 5, "L4s15": 15, "L1": 30, "L2": 5, "L5": 1,
           "L6": 1, "L7": 1, "L8q25": 1, "L8q50": 1, "L8q75": 1, "L2s1530": 15, "L2s510": 5, "L2s7812": 1,
           "L2s60": 30, "L2two": 5}  # gcd of each law's targets (asserted against the support in the tests)
FAMILIES = (("uniform", ("L3u", "L4u5", "L4u15")), ("skewed", ("L3s", "L4s5", "L4s15")))
DEM_CAPS = tuple(range(1, 15)) + (None,)
DEM_SCEN = [(16, "balanced"), (16, "d1530"), (64, "balanced"), (64, "d1530")]
TOL_DEM = 1e-9
MATERIAL = (Fraction(1, 20), Fraction(1))   # magnitude thresholds reported, seconds per break
ADDS = (5, 6, 10, 15, 20, 30, 45)

TIERS = {
    "quick": dict(menus="M7", laws=[("L1", "a"), ("L2", "a"), ("L3u", "a"), ("L4u5", "a"), ("L4u15", "a")]
                  + list(REG.QUICK_NEW_LAWS),
                  dem_laws=[("L2", "a"), ("L3u", "a"), ("L2two", "b")], dem_scen=[(16, "balanced"), (64, "d1530")],
                  crit_h=2),
    "narrow": dict(menus="M86", laws=ALL_LAWS, dem_laws=DEM_LAWS_ALL, dem_scen=DEM_SCEN, crit_h=4),
    # full: the narrow laws plus L8 (bimodal live), the H2 structured-spot sets and H3 (two spots), both
    # conventions for hybrid laws; the demand-limited part B adds every new law (all have breaks up to 240 s)
    "full": dict(menus="M86", laws=ALL_LAWS + list(REG.NEW_LAWS), dem_laws=DEM_LAWS_ALL + list(REG.NEW_LAWS),
                 dem_scen=DEM_SCEN, crit_h=8),
}
TIERS["fullsmoke"] = dict(TIERS["full"], menus="M7", crit_h=2, dem_scen=[(16, "d1530")])


def lawkey(l, c):
    return REG.lawkey(l, c)


def law_obj(name):
    return LAWS.named(name)


def f6(x):
    return "%.6f" % float(x)


def stab_bound(menu, law, conv):
    """max_T l(p(T)) over the law's targets (Proposition 2), with p from engine E-C membership and l from the
    least-parts DP; dynamic caps under convention b shift the requirement by one for structured targets, so the
    returned value is the least nominal cap h at which every target meets its requirement."""
    A = tuple(sorted(menu))
    N = max(T for (T, _), _ in law.support)
    inside = semigroup_member(A)
    lp = structural.min_parts(A, N)
    pred = []
    last = 0
    for x in range(N + 1):
        if inside(x):
            last = x
        pred.append(last)
    need = 0
    for (T, st), _ in law.support:
        req = lp[pred[T]]
        if conv == "b" and st:
            # dynamic cap max(0, h - n) must reach l; a target with l = 0 is met by every cap h >= 1 (caps start
            # at 1), which for one spot equals l + 1 = 1
            req = req + int(st) if req > 0 else max(req, 1)
        need = max(need, req)
    return need


def work_floor(args):
    menu, law_list = args
    out = {}
    for l, c in law_list:
        law = law_obj(l)
        vals = RV.floor_values(menu, law, c)
        out[(l, c)] = dict(vals=vals, stab_emp=RV.stable_cap(vals), stab_th=stab_bound(menu, law, c),
                           filled=RV.filled(menu, law, c), lf=RV.lattice_floor(menu, law))
    return menu, out


def work_dem(args):
    menu, dem_laws, scen = args
    from podsim import exact
    means_list = []
    for lam, sc in scen:
        w = pools.weights(sc)
        means_list.append({a: lam * w[a] for a in pools.UNION})
    kp = exact.profile_dist(menu, means_list, H=max(h for h in DEM_CAPS if h is not None))
    out = {}
    for l, c in dem_laws:
        law = law_obj(l)
        t = exact.expect_table(menu, law, c, list(DEM_CAPS), means_list, keys_probs=kp)
        for si in range(len(scen)):
            out[(l, c, si)] = [t[(si, h)]["none"] for h in DEM_CAPS]
        out[(l, c, "pruned")] = list(t["pruned"])
    return menu, out


def _menu_key(m):
    return "menu_" + "-".join(map(str, m))


def floor_unit(args):
    """work_floor in JSON-safe form (Fractions as 'p/q' strings, caps by label); decoded by floor_decode."""
    menu, out = work_floor(args)
    enc = {}
    for (l, c), r in out.items():
        enc["%s|%s" % (l, c)] = dict(vals={RV.cap_label(h): str(v) for h, v in r["vals"].items()},
                                     stab_emp=r["stab_emp"], stab_th=r["stab_th"], filled=r["filled"], lf=str(r["lf"]))
    return enc


def floor_decode(menu, enc):
    out = {}
    for k, r in enc.items():
        l, c = k.split("|")
        out[(l, c)] = dict(vals={(None if h == "unc" else int(h)): Fraction(v) for h, v in r["vals"].items()},
                           stab_emp=r["stab_emp"], stab_th=r["stab_th"], filled=r["filled"], lf=Fraction(r["lf"]))
    return out


def dem_unit(args):
    menu, out = work_dem(args)
    return [["|".join(str(x) for x in k), v] for k, v in out.items()]


def dem_decode(enc):
    out = {}
    for k, v in enc:
        l, c, si = k.split("|")
        out[(l, c, si if si == "pruned" else int(si))] = v
    return out


def run_map(fn, items, jobs):
    if jobs > 1 and len(items) > 1:
        with REG.pool(jobs) as p:
            return list(p.map(fn, items))
    return [fn(x) for x in items]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default=os.environ.get("PODSIM_TIER", "narrow"), choices=sorted(TIERS))
    ap.add_argument("--jobs", type=int, default=REG.jobs())
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    os.environ["PODSIM_TIER"] = a.tier  # unit cache folder follows the tier actually run
    if a.out:
        os.environ["PODSIM_OUT"] = os.path.abspath(a.out)  # --out is this experiment's folder; its cache goes inside
    cfg = TIERS[a.tier]
    menus = list(REG.M7) if cfg["menus"] == "M7" else REG.menus_m7_m85()
    laws_l = cfg["laws"]
    ufl = [(_menu_key(m), (m, laws_l)) for m in menus]
    udm = [(_menu_key(m), (m, cfg["dem_laws"], cfg["dem_scen"])) for m in REG.M7]
    if REG.units_only([("x4floor", ufl, floor_unit, False), ("x4dem", udm, dem_unit, True)]):
        return
    out = a.out or os.path.join(REG.out_root(), "x4")
    os.makedirs(out, exist_ok=True)
    t0 = time.time()

    # ---------------------------------------------------------------- part A: floors
    res = {m: floor_decode(m, e) for m, e in zip(menus, REG.iter_units("x4floor", ufl, floor_unit, n_jobs=a.jobs))}
    t_floor = time.time() - t0
    floor_rows = []
    p1_bad = 0
    p1_checked = 0
    for m in menus:
        for l, c in laws_l:
            r = res[m][(l, c)]
            p1_checked += 1
            if r["stab_emp"] != r["stab_th"] and not (r["stab_emp"] is None and r["stab_th"] > 20):
                p1_bad += 1
            for h in RV.CAPS:
                v = r["vals"][h]
                floor_rows.append(dict(law=l, conv=c, menu=RV.mstr(m), g=structural.menu_gcd(m), h=RV.cap_label(h),
                                       floor_exact=str(v), floor_s=f6(v)))
    REG.write_csv(os.path.join(out, REG.table_name("floors")), floor_rows)

    # ---------------------------------------------------------------- part A: pairs
    pair_rows = []
    by_law = {}
    rev_index = {}
    p1_above = 0
    conf = {}
    conf_def = {}
    miss = {}
    p2_checked = p2_bad = 0
    lat_rule = dict(checked=0, agree=0, disagree=0, rule_tie_disagree=0)
    lat_rule_rows = []
    m7set = set(REG.M7)
    for l, c in laws_l:
        lk = lawkey(l, c)
        st = dict(law=lk, pairs=0, reversing=0, multi=0, m7_pairs=0, m7_reversing=0, points=[], mags=[],
                  max_mag=Fraction(0), max_pair="", ties_all=0)
        law = law_obj(l)
        for i in range(len(menus)):
            for j in range(i + 1, len(menus)):
                A, B = menus[i], menus[j]
                ra, rb = res[A][(l, c)], res[B][(l, c)]
                diffs = [ra["vals"][h] - rb["vals"][h] for h in RV.CAPS]
                info = RV.reversal_info(RV.CAPS, diffs)
                st["pairs"] += 1
                inm7 = A in m7set and B in m7set
                st["m7_pairs"] += int(inm7)
                if all(x == 0 for x in diffs):
                    st["ties_all"] += 1
                # P1: no reversal above the larger stability cap
                sa = ra["stab_th"]
                sb = rb["stab_th"]
                hs = max(sa, sb)
                for p in info["points"]:
                    if (21 if p is None else p) > hs:
                        p1_above += 1
                # P2: lattice floor at the limit where both fill
                if ra["filled"] and rb["filled"]:
                    p2_checked += 1
                    if RV.sgn(ra["lf"] - rb["lf"]) != info["limit_sign"]:
                        p2_bad += 1
                # P3: two-regime predictor
                dA, dB = max(A), max(B)
                pf = RV.sgn(dB - dA)
                pl = RV.sgn(ra["lf"] - rb["lf"])
                pred = pf != 0 and pl != 0 and pf != pl
                obs = info["n_changes"] > 0
                k = (lk, pred, obs)
                conf[k] = conf.get(k, 0) + 1
                if pf != 0 and pl != 0:
                    kd = (pred, obs)
                    conf_def[kd] = conf_def.get(kd, 0) + 1
                if pred != obs:
                    s1 = RV.sgn(diffs[0])
                    why = []
                    if pf == 0 or pl == 0:
                        why.append("predictor tie (equal longest part or equal lattice floor)")
                    else:
                        if s1 != pf:
                            why.append("h = 1 sign differs from longest-part rule")
                        if info["limit_sign"] != pl:
                            why.append("limit sign differs from lattice floor (unfilled targets)")
                    if not why and obs:
                        why.append("even number of sign changes inside the cap regime")
                    if not why:
                        why.append("other")
                    for w in why:
                        kk = ("FN" if obs else "FP", w)
                        miss[kk] = miss.get(kk, 0) + 1
                # lattice rule g - gcd(g, l) on L4 laws (complete periods not guaranteed)
                if l.startswith("L4") and ra["filled"] and rb["filled"]:
                    ell = LATTICE[l]
                    lat_rule["checked"] += 1
                    rs = RV.lattice_rule_sign(A, B, ell)
                    if rs == info["limit_sign"]:
                        lat_rule["agree"] += 1
                    else:
                        lat_rule["disagree"] += 1
                        lat_rule["rule_tie_disagree"] += int(rs == 0)
                        if len(lat_rule_rows) < 200:
                            lat_rule_rows.append(dict(law=lk, A=RV.mstr(A), B=RV.mstr(B), rule_sign=rs,
                                                      limit_sign=info["limit_sign"], lf_A=f6(ra["lf"]),
                                                      lf_B=f6(rb["lf"])))
                rev_index[(l, c, A, B)] = info
                if obs:
                    st["reversing"] += 1
                    st["m7_reversing"] += int(inm7)
                    st["multi"] += int(info["n_changes"] > 1)
                    st["points"].extend(info["points"])
                    st["mags"].append(info["magnitude"])
                    for t in MATERIAL:
                        if info["magnitude"] >= t:
                            st["mat_%s" % t] = st.get("mat_%s" % t, 0) + 1
                    if info["magnitude"] > st["max_mag"]:
                        st["max_mag"] = info["magnitude"]
                        st["max_pair"] = "%s vs %s" % (RV.mstr(A), RV.mstr(B))
                    pair_rows.append(dict(
                        law=l, conv=c, A=RV.mstr(A), B=RV.mstr(B), both_m7=int(inm7), signs=info["signs"],
                        points=" ".join(RV.cap_label(p) for p in info["points"]), n_changes=info["n_changes"],
                        lead_A_s=f6(info["lead_a"]), lead_B_s=f6(info["lead_b"]), magnitude_s=f6(info["magnitude"]),
                        stab_A=sa, stab_B=sb, d_A=dA, d_B=dB, g_A=structural.menu_gcd(A), g_B=structural.menu_gcd(B),
                        limit_A_s=f6(ra["vals"][None]), limit_B_s=f6(rb["vals"][None]),
                        predicted=int(pred)))
        by_law[lk] = st
    REG.write_csv(os.path.join(out, REG.table_name("reversals")), pair_rows,
                  fields=["law", "conv", "A", "B", "both_m7", "signs", "points", "n_changes", "lead_A_s", "lead_B_s",
                          "magnitude_s", "stab_A", "stab_B", "d_A", "d_B", "g_A", "g_B", "limit_A_s", "limit_B_s",
                          "predicted"])

    law_rows = []
    for l, c in laws_l:
        st = by_law[lawkey(l, c)]
        pts = sorted(st["points"], key=lambda p: 21 if p is None else p)
        mags = sorted(float(x) for x in st["mags"])
        tp = conf.get((st["law"], True, True), 0)
        fp = conf.get((st["law"], True, False), 0)
        fn = conf.get((st["law"], False, True), 0)
        tn = conf.get((st["law"], False, False), 0)
        law_rows.append(dict(
            law=st["law"], lattice_s=LATTICE[l], pairs=st["pairs"], reversing=st["reversing"],
            share=f6(Fraction(st["reversing"], st["pairs"])), multi_reversal=st["multi"], m7_pairs=st["m7_pairs"],
            m7_reversing=st["m7_reversing"], all_caps_tied=st["ties_all"],
            point_q1=_q(pts, 0.25), point_median=_q(pts, 0.5), point_q3=_q(pts, 0.75), point_max=_q(pts, 1.0),
            mag_median_s=f6(median(mags)) if mags else "", mag_max_s=f6(st["max_mag"]), mag_max_pair=st["max_pair"],
            mag_ge_0_05_s=st.get("mat_%s" % MATERIAL[0], 0), mag_ge_1_s=st.get("mat_%s" % MATERIAL[1], 0),
            pred_tp=tp, pred_fp=fp, pred_fn=fn, pred_tn=tn))
    REG.write_csv(os.path.join(out, "by_law.csv"), law_rows)

    # reversal-point histogram by law
    hist_rows = []
    for l, c in laws_l:
        st = by_law[lawkey(l, c)]
        cnt = {}
        for p in st["points"]:
            cnt[p] = cnt.get(p, 0) + 1
        for h in RV.CAPS:
            if h in cnt:
                hist_rows.append(dict(law=st["law"], point=RV.cap_label(h), count=cnt[h]))
    if hist_rows:
        REG.write_csv(os.path.join(out, "reversal_points.csv"), hist_rows)

    # ---------------------------------------------------------------- lattice dependence
    lat_rows = []
    lat_detail = []
    lat_agg = {f: dict(any=0, all=0) for f, _ in FAMILIES}
    have = set(laws_l)
    for fam, names in FAMILIES:
        if not all((n, "a") in have for n in names):
            continue
        cats = {}
        for i in range(len(menus)):
            for j in range(i + 1, len(menus)):
                A, B = menus[i], menus[j]
                infos = [rev_index[(n, "a", A, B)] for n in names]
                rv = tuple(int(x["n_changes"] > 0) for x in infos)
                lims = tuple(x["limit_sign"] for x in infos)
                same_signs = len(set(x["signs"] for x in infos)) == 1
                key = (rv, len(set(lims)) > 1, same_signs)
                cats[key] = cats.get(key, 0) + 1
                if any(rv) and not all(rv) and A in m7set and B in m7set:
                    lat_detail.append(dict(family=fam, A=RV.mstr(A), B=RV.mstr(B), signs_1s=infos[0]["signs"],
                                           signs_5s=infos[1]["signs"], signs_15s=infos[2]["signs"]))
                if any(rv):
                    lat_agg[fam]["any"] += 1
                    lat_agg[fam]["all"] += int(all(rv))
        for (rv, limdiff, same), n in sorted(cats.items()):
            lat_rows.append(dict(family=fam, reverses_on_1s=rv[0], reverses_on_5s=rv[1], reverses_on_15s=rv[2],
                                 limit_sign_differs=int(limdiff), identical_sign_strings=int(same), pairs=n))
    if lat_rows:
        REG.write_csv(os.path.join(out, "lattice.csv"), lat_rows)
    if lat_detail:
        REG.write_csv(os.path.join(out, "lattice_m7_detail.csv"), lat_detail)

    # ---------------------------------------------------------------- P4: Corollary 4
    crit_rows, crit = RV.criterion_check(menus, ADDS, n_h=cfg["crit_h"])
    REG.write_csv(os.path.join(out, REG.table_name("criterion")), crit_rows,
                  fields=["menu", "g", "A0", "c_seconds", "c", "d", "c1", "c2", "h", "W_lo", "W_hi", "tot_add_c_at_h",
                          "tot_cap_plus_1", "tot_base_h", "M_S2", "M_S2new", "omega", "eq_new_h", "eq_old_h1",
                          "eq_old_h", "predicted_sign", "computed_sign", "identity_ok", "sign_ok"])
    fam = [dict(menu=RV.mstr(m), h=h, Tot=RV.family_tot(m, h))
           for m in [(15, 30, 60), (5, 15, 30), (10, 15, 30), (6, 15, 30)] for h in range(1, 7)]
    REG.write_csv(os.path.join(out, "family_tot.csv"), fam)
    t_a = time.time() - t0

    # ---------------------------------------------------------------- part B: demand limited
    t1 = time.time()
    dres = {m: dem_decode(e) for m, e in zip(REG.M7, REG.iter_units("x4dem", udm, dem_unit, raw=True, n_jobs=a.jobs))}
    dem_rows = []
    dem_sum = {}
    pruned_max = 0.0
    for m in REG.M7:
        for l, c in cfg["dem_laws"]:
            pruned_max = max([pruned_max] + dres[m][(l, c, "pruned")])
    M7 = list(REG.M7)
    for l, c in cfg["dem_laws"]:
        lk = lawkey(l, c)
        unl = {m: [res[m][(l, c)]["vals"][h] for h in DEM_CAPS] for m in M7}
        for si, (lam, sc) in enumerate(cfg["dem_scen"]):
            k = (lk, lam, sc)
            s = dem_sum.setdefault(k, dict(pairs=0, rev_unl=0, rev_dem=0, both=0, unl_only=0, dem_only=0,
                                           same_points=0, mags=[], mat=0, mat_u=0))
            for i in range(len(M7)):
                for j in range(i + 1, len(M7)):
                    A, B = M7[i], M7[j]
                    dd = [x - y for x, y in zip(dres[A][(l, c, si)], dres[B][(l, c, si)])]
                    du = [x - y for x, y in zip(unl[A], unl[B])]
                    iu = RV.reversal_info(DEM_CAPS, du)
                    idm = RV.reversal_info(DEM_CAPS, dd, tol=TOL_DEM)
                    ru, rd = iu["n_changes"] > 0, idm["n_changes"] > 0
                    s["pairs"] += 1
                    s["rev_unl"] += int(ru)
                    s["rev_dem"] += int(rd)
                    s["both"] += int(ru and rd)
                    s["unl_only"] += int(ru and not rd)
                    s["dem_only"] += int(rd and not ru)
                    s["same_points"] += int(ru and rd and iu["points"] == idm["points"])
                    if rd:
                        s["mags"].append(idm["magnitude"])
                        s["mat"] += int(idm["magnitude"] >= float(MATERIAL[0]))
                    if ru:
                        s["mat_u"] += int(iu["magnitude"] >= MATERIAL[0])
                    dem_rows.append(dict(law=l, conv=c, lam=lam, weights=sc, A=RV.mstr(A), B=RV.mstr(B),
                                         signs_unlimited=iu["signs"], signs_demand=idm["signs"],
                                         points_unlimited=" ".join(RV.cap_label(p) for p in iu["points"]),
                                         points_demand=" ".join(RV.cap_label(p) for p in idm["points"]),
                                         magnitude_unlimited_s=f6(iu["magnitude"]),
                                         magnitude_demand_s=f6(idm["magnitude"])))
    REG.write_csv(os.path.join(out, REG.table_name("demand_pairs")), dem_rows)
    dem_law_rows = []
    for (lk, lam, sc), s in dem_sum.items():
        mags = sorted(s["mags"])
        dem_law_rows.append(dict(law=lk, lam=lam, weights=sc, pairs=s["pairs"], reversing_unlimited=s["rev_unl"],
                                 reversing_demand=s["rev_dem"], both=s["both"], unlimited_only=s["unl_only"],
                                 demand_only=s["dem_only"], same_points=s["same_points"],
                                 reversing_unlimited_ge_0_05_s=s["mat_u"], reversing_demand_ge_0_05_s=s["mat"],
                                 mag_median_demand_s=f6(median(mags)) if mags else "",
                                 mag_max_demand_s=f6(mags[-1]) if mags else ""))
    REG.write_csv(os.path.join(out, "demand_by_law.csv"), dem_law_rows)
    t_b = time.time() - t1

    # ---------------------------------------------------------------- summary json and md
    tot_pairs = xsum(s["pairs"] for s in by_law.values())
    tot_rev = xsum(s["reversing"] for s in by_law.values())
    tp = xsum(v for (lk, p, o), v in conf.items() if p and o)
    fp = xsum(v for (lk, p, o), v in conf.items() if p and not o)
    fn = xsum(v for (lk, p, o), v in conf.items() if o and not p)
    tn = xsum(v for (lk, p, o), v in conf.items() if not o and not p)
    summ = dict(tier=a.tier, menus=len(menus), unordered_pairs_per_law=len(menus) * (len(menus) - 1) // 2,
                laws=[lawkey(l, c) for l, c in laws_l], caps=[RV.cap_label(h) for h in RV.CAPS],
                pair_law_cells=tot_pairs, reversing_cells=tot_rev,
                p1=dict(stable_cap_checks=p1_checked, empirical_ne_theoretical=p1_bad, reversals_above_bound=p1_above),
                p2=dict(checked=p2_checked, mismatches=p2_bad), lattice_rule=lat_rule,
                p3=dict(tp=tp, fp=fp, fn=fn, tn=tn, reasons={"%s: %s" % k: v for k, v in sorted(miss.items())},
                        defined=dict(tp=conf_def.get((True, True), 0), fp=conf_def.get((True, False), 0),
                                     fn=conf_def.get((False, True), 0), tn=conf_def.get((False, False), 0))),
                lattice_dependence={f: v for f, v in lat_agg.items()}, p4=crit, demand=dict(scenarios=[list(x) for x in cfg["dem_scen"]],
                laws=[lawkey(l, c) for l, c in cfg["dem_laws"]], caps=[RV.cap_label(h) for h in DEM_CAPS],
                pruned_mass_max=pruned_max, tol_s=TOL_DEM))
    REG.write_json(os.path.join(out, "x4_summary.json"), summ)
    if lat_rule_rows:
        REG.write_csv(os.path.join(out, "lattice_rule_disagree.csv"), lat_rule_rows)
    write_md(out, a.tier, menus, laws_l, law_rows, lat_rows, lat_detail, crit, summ, dem_law_rows, cfg, res)
    wall = time.time() - t0
    REG.write_timing(out, "x4_wall_s", wall)
    REG.write_timing(out, "x4_floor_s", t_floor)
    REG.write_timing(out, "x4_partA_s", t_a)
    REG.write_timing(out, "x4_partB_s", t_b)
    print("x4 done: %d menus, %d pair-law cells, %d reversing; P1 %d/%d, P2 %d, P4 sign mismatches %d; wall %.1f s"
          % (len(menus), tot_pairs, tot_rev, p1_bad, p1_above, p2_bad, crit["sign_mismatch"], wall))
    if p1_bad or p1_above or p2_bad or crit["sign_mismatch"] or crit["identity_mismatch"] or crit["base_identity_mismatch"]:
        print("X4 CHECK FAILED")
        return 1
    return 0


def _q(xs, q):
    if not xs:
        return ""
    xs = [21 if x is None else x for x in xs]
    v = xs[min(len(xs) - 1, int(q * (len(xs) - 1) + 0.5))]
    return "unc" if v == 21 else v


def write_md(out, tier, menus, laws_l, law_rows, lat_rows, lat_detail, crit, summ, dem_law_rows, cfg, res):
    L = []
    L.append("# X4: menu-ranking reversal map")
    L.append("")
    L.append("Tier %s. Exact. Regenerate: `python3 code/run_x4.py --tier %s --jobs 2`." % (tier, tier))
    L.append("")
    L.append("**Designed consequence, disclosed as such.** That the better of two menus can change with the cap h is "
             "built into the arithmetic of the structural floor (undershoot companion; Proposition 1(c), "
             "Proposition 2 and Proposition 1(b, e) of Appendix A of the paper): at low caps the menu with the longer longest part packs more "
             "seconds per ad, and at stable caps the lattice of the menu (its gcd) and its gaps decide. The "
             "simulation does not discover that reversals exist; it measures where they occur, how often and how "
             "large they are, on the study's break-length laws.")
    L.append("")
    L.append("Quantity: the exact structural floor E[D_h(A;T)] in seconds per break (demand unlimited, readiness 1), "
             "caps 1 to 20 and uncapped, for %d menus (%s, %d unordered pairs per law). Sign of E[D_h(A)] - E[D_h(A')] along the caps; a reversal is a change of strict sign (ties "
             "skipped), its point the first cap with the new sign; the magnitude of a reversing pair is the smaller "
             "of the two menus' largest leads, in seconds per break. Ordered pairs mirror the unordered ones, so "
             "ordered counts are twice those below." % (len(menus), "the seven study menus" if len(menus) == 7 else
                                                        "the seven study menus plus the 85-menu grid",
                                                        len(menus) * (len(menus) - 1) // 2))
    L.append("")
    L.append("## Reversing pairs by law")
    L.append("")
    L.append("| law | lattice (s) | pairs | reversing | share | magnitude >= 0.05 s / >= 1 s | 2+ reversals | M7 pairs reversing (of 21) | reversal cap q1 / median / q3 / max | magnitude median / max (s per break) | largest |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in law_rows:
        L.append("| %s | %s | %d | %d | %.3f | %d / %d | %d | %d | %s / %s / %s / %s | %s / %s | %s |" % (
            r["law"], r["lattice_s"], r["pairs"], r["reversing"], float(r["share"]), r["mag_ge_0_05_s"],
            r["mag_ge_1_s"], r["multi_reversal"],
            r["m7_reversing"], r["point_q1"], r["point_median"], r["point_q3"], r["point_max"],
            _fmt(r["mag_median_s"]), _fmt(r["mag_max_s"]), r["mag_max_pair"] or "none"))
    L.append("")
    L.append("Laws: L1 grid {60, 90, ..., 240}; L2a and L2b hybrid remainders T = B - S, S uniform on {5, 10, 15, 20, "
             "45} (always present), cap conventions a (maxseq on the dynamic portion) and b (K - 1); L3u uniform "
             "integers [60, 240]; L3s discretized Beta(2, 5) on [60, 240] (synthetic); L4 the same restricted to 5 s "
             "and 15 s lattices; L5 FreeWheel Q1 2023 mid-roll bins (shares sourced, bin edges modeling choices); L6 "
             "uniform [15, 60] and L7 uniform [240, 360] (synthetic). Full floors: `floors.csv`; every reversing "
             "pair with its sign string over caps 1..20, unc: `reversals.csv`; point histogram: "
             "`reversal_points.csv`.")
    L.append("")
    L.append("## Seven study menus: sign strings on L3u, L4u5, L4u15 and L2a")
    L.append("")
    names = [n for n in ("L3u", "L4u5", "L4u15", "L2") if (n, "a") in laws_l]
    L.append("Each character is the sign of E[D_h(A)] - E[D_h(A')] at h = 1..20, unc ('+' means A' leaves fewer "
             "seconds unfilled). Only pairs that reverse on at least one of these laws are listed.")
    L.append("")
    L.append("| A | A' | " + " | ".join(n + ("a" if n == "L2" else "") for n in names) + " |")
    L.append("| --- | --- | " + " | ".join("---" for _ in names) + " |")
    M7 = list(REG.M7)
    for i in range(len(M7)):
        for j in range(i + 1, len(M7)):
            A, B = M7[i], M7[j]
            ss = []
            anyrev = False
            for n in names:
                diffs = [res[A][(n, "a")]["vals"][h] - res[B][(n, "a")]["vals"][h] for h in RV.CAPS]
                info = RV.reversal_info(RV.CAPS, diffs)
                anyrev = anyrev or info["n_changes"] > 0
                ss.append("`%s`%s" % (info["signs"], " (at %s)" % ",".join(RV.cap_label(p) for p in info["points"])
                                       if info["points"] else ""))
            if anyrev:
                L.append("| %s | %s | %s |" % (RV.mstr(A), RV.mstr(B), " | ".join(ss)))
    L.append("")
    if lat_rows:
        L.append("## Does a reversal depend on the lattice of the law?")
        L.append("")
        L.append("Same base law restricted to integer, 5 s and 15 s lattices; each unordered pair classified by "
                 "where it reverses and whether its limit (uncapped) sign changes with the lattice.")
        L.append("")
        L.append("| family | reverses on 1 s / 5 s / 15 s | limit sign changes with lattice | identical sign strings | pairs |")
        L.append("| --- | --- | --- | --- | --- |")
        for r in lat_rows:
            L.append("| %s | %d / %d / %d | %s | %s | %d |" % (r["family"], r["reverses_on_1s"], r["reverses_on_5s"],
                                                           r["reverses_on_15s"],
                                                           "yes" if r["limit_sign_differs"] else "no",
                                                           "yes" if r["identical_sign_strings"] else "no", r["pairs"]))
        L.append("")
        for f, v in sorted(summ["lattice_dependence"].items()):
            if v["any"]:
                L.append("- %s family: %d pairs reverse on at least one of the three lattices; %d (%.0f%%) on all "
                         "three, so whether a pair reverses depends on the lattice for %d (%.0f%%)." % (
                             f, v["any"], v["all"], 100.0 * v["all"] / v["any"], v["any"] - v["all"],
                             100.0 * (v["any"] - v["all"]) / v["any"]))
        L.append("")
        lr = summ["lattice_rule"]
        L.append("Lattice ranking rule (Proposition 1(b, e), complete periods: filled menus rank by g - gcd(g, l)) on "
                 "the L4 laws, pairs where both menus fill every target: agrees with the exact limit sign in %d of %d. "
                 "In the %d disagreements (%d of them with the rule predicting a tie) the exact remainders over an "
                 "incomplete period break the tie (the L4 supports in [60, 240] are not whole periods of every gcd, "
                 "as Appendix A of the paper notes); listed in `lattice_rule_disagree.csv` (first 200)." % (
                     lr["agree"], lr["checked"], lr["disagree"], lr["rule_tie_disagree"]))
        L.append("")
    L.append("## Checks against Appendix A of the paper (P1 to P4 name checks here, not pod policies)")
    L.append("")
    p1, p2, p3 = summ["p1"], summ["p2"], summ["p3"]
    L.append("- (P1) Proposition 2. The least cap at which each menu's mean equals its uncapped value equals "
             "max_T l(p(T)) computed independently (engine E-C membership, least-parts DP; +1 for structured targets "
             "under convention b) in %d of %d (menu, law) cells (mismatches %d; a bound above 20 counts as a match "
             "when the mean has not stabilized by 20). Reversal points above the larger of the two menus' bounds: %d."
             % (p1["stable_cap_checks"] - p1["empirical_ne_theoretical"], p1["stable_cap_checks"],
                p1["empirical_ne_theoretical"], p1["reversals_above_bound"]))
    L.append("- (P2) Proposition 1(b, e). Where both menus fill every target of the law, the limit sign equals the sign "
             "of the difference of exact lattice floors sum_T w(T) (T mod g): %d pair-law cells, %d mismatches."
             % (p2["checked"], p2["mismatches"]))
    L.append("- (P4) Corollary 4 on exact window totals (reduced units, W = [c1, hd], the %d least caps with "
             "hd >= c1 + c2, c in {5, 6, 10, 15, 20, 30, 45} s with g | c, c < d and c not in the menu): %d cases; "
             "%d with A0' at h and A0 at h + 1 both at equality levels, where the identities sum_W D'_h = M(S2') and "
             "sum_W D_{h+1} = M(S2) - omega failed %d times and the predicted sign (adding c beats raising the cap "
             "iff M(S2') < M(S2) - omega) differed from the computed sign %d times; %d cases off equality levels "
             "(corrections Psi not implemented; not compared). sum_W D_h = M(S2) at equality levels: "
             "%d checks, %d mismatches. Among %d (menu, c) pairs, the winner at equality levels is the added "
             "duration in %d, the cap in %d, tied in %d, and changes with h in %d (it cannot, by the corollary)."
             % (cfg["crit_h"], crit["cases"], crit["at_equality"], crit["identity_mismatch"], crit["sign_mismatch"],
                crit["off_equality"], crit["base_identity_checks"], crit["base_identity_mismatch"], crit["pairs"],
                crit["add_c_wins"], crit["cap_wins"], crit["ties"], crit["h_dependent_pairs"]))
    L.append("- Example 6: Tot(h) reproduced in `family_tot.csv` (checked in tests/test_x4.py).")
    L.append("")
    L.append("## Reversal check: reversals where the undershoot theory predicts")
    L.append("")
    tot = p3["tp"] + p3["fp"] + p3["fn"] + p3["tn"]
    obs = p3["tp"] + p3["fn"]
    pred = p3["tp"] + p3["fp"]
    L.append("Two-regime predictor (P3): at h = 1 the menu with the longer longest part leaves fewer seconds "
             "(Proposition 1(c), D_h(T) = T - hd for T > hd); at the limit the exact lattice floor decides "
             "(Proposition 1(b, e), ignoring gaps); a reversal is predicted when the two signs are strict and opposite. "
             "Over %d pair-law cells: %d reversals observed, %d predicted; predicted and observed %d, predicted only "
             "%d, observed only %d, neither %d (precision %s, recall %s)."
             % (tot, obs, pred, p3["tp"], p3["fp"], p3["fn"], p3["tn"], _ratio(p3["tp"], pred), _ratio(p3["tp"], obs)))
    L.append("")
    dfn = p3["defined"]
    L.append("Restricted to cells where the predictor is defined (different longest parts and different lattice "
             "floors; %d cells): predicted and observed %d, predicted only %d, observed only %d, neither %d "
             "(precision %s, recall %s). Pairs with equal longest parts (most of the misses) are outside the "
             "predictor: their low-cap ranking is decided by targets below hd, where Proposition 1(c) gives no sign."
             % (xsum(dfn.values()), dfn["tp"], dfn["fp"], dfn["fn"], dfn["tn"], _ratio(dfn["tp"], dfn["tp"] + dfn["fp"]),
                _ratio(dfn["tp"], dfn["tp"] + dfn["fn"])))
    L.append("")
    L.append(reversal_check(summ))
    L.append("")
    L.append("## Demand-limited slice (seven study menus)")
    L.append("")
    L.append("Exact expectations over truncated Poisson creative counts (exact.py; double precision, pruned mass at "
             "most %.1e), caps 1..14 and uncapped, sign tolerance %.0e s. Do reversals at demand unlimited survive "
             "finite demand?" % (summ["demand"]["pruned_mass_max"], TOL_DEM))
    L.append("")
    L.append("Columns: reversing pairs at demand unlimited and at this demand (any strict sign change, then with "
             "magnitude at least 0.05 s per break); both, unlimited only, demand only, and same reversal points "
             "refer to any strict sign change.")
    L.append("")
    L.append("| law | lambda | weights | pairs | reversing unlimited (>= 0.05 s) | reversing demand (>= 0.05 s) | both | unlimited only | demand only | same points | magnitude median / max (s) |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in dem_law_rows:
        L.append("| %s | %d | %s | %d | %d (%d) | %d (%d) | %d | %d | %d | %d | %s / %s |" % (
            r["law"], r["lam"], pools.SCHEME_LABEL[r["weights"]], r["pairs"], r["reversing_unlimited"],
            r["reversing_unlimited_ge_0_05_s"], r["reversing_demand"], r["reversing_demand_ge_0_05_s"], r["both"], r["unlimited_only"], r["demand_only"], r["same_points"],
            _fmt(r["mag_median_demand_s"]), _fmt(r["mag_max_demand_s"])))
    L.append("")
    L.append("Per-pair sign strings: `demand_pairs.csv`. Weights and lambda values are synthetic sweeps (pools.py).")
    L.append("")
    L.append("Tables: `by_law.csv`, `reversals.csv`, `floors.csv`, `reversal_points.csv`, `lattice.csv`, "
             "`lattice_m7_detail.csv`, `criterion.csv`, `family_tot.csv`, `demand_by_law.csv`, `demand_pairs.csv`, "
             "`x4_summary.json`.")
    REG.write_text(os.path.join(out, "summary.md"), "\n".join(L) + "\n")


def reversal_check(summ):
    p1, p2, p3, p4 = summ["p1"], summ["p2"], summ["p3"], summ["p4"]
    exact_ok = (p1["empirical_ne_theoretical"] == 0 and p1["reversals_above_bound"] == 0 and p2["mismatches"] == 0
                and p4["sign_mismatch"] == 0 and p4["identity_mismatch"] == 0)
    obs = p3["tp"] + p3["fn"]
    pred = p3["tp"] + p3["fp"]
    rec = p3["tp"] / obs if obs else 1.0
    prec = p3["tp"] / pred if pred else 1.0
    head = ("**Reversal check: %s.** " % ("every exact statement of the theory holds; the coarse two-regime "
                                         "predictor is %s" % ("good" if min(rec, prec) >= 0.8 else "only partial")
                                         if exact_ok else "an exact check has a mismatch"))
    return head + ("Exact statements (P1, P2, P4) hold with zero mismatches: every reversal lies inside the cap "
                   "regime bounded by Proposition 2, every filled limit ranks by the lattice floor, and "
                   "Corollary 4 predicts the add-a-duration versus raise-the-cap sign exactly at equality levels. "
                   "The two-regime predictor has precision %.2f and recall %.2f. Misses by cause (a cell can have two "
                   "causes; FN = observed, not predicted; FP = predicted, not observed): %s." % (
                       prec, rec, "; ".join("%s %d" % (k, v) for k, v in sorted(p3["reasons"].items())) or "none")
                   if exact_ok else "See the checks above.")


def _ratio(a, b):
    return "%.2f" % (a / b) if b else "n/a"


def _fmt(x):
    if x == "" or x is None:
        return "none"
    return "%.2f" % float(x)


if __name__ == "__main__":
    sys.exit(main())
