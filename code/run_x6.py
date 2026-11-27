"""X6: seconds-max versus revenue-max pod construction under floors and two value laws, plus greedy baselines.

Scenario catalog axes: value (V1 to V4) and policy (P1 to P4).

Per block (law, convention, menu, lambda, weight scheme) the script draws N breaks once (podsim/revenue.py
BreakDraw: target, per-duration Poisson counts and value order statistics, arrival times) and evaluates every
(cap, value law, floor, policy) on those same draws (common random numbers). Readiness is fixed at rho = 1:
X6 is about pod choice, and readiness enters revenue and seconds linearly after selection (DESIGN.md,
implementation choice 15). Per condition it reports, with paired Monte Carlo standard errors across breaks:
  U_Px     expected unsold paid seconds (T minus filled seconds) under policy Px
  R_Px     expected pod revenue, dollars of CPM per pod (pay-as-bid)
  policy gap  E[S_P1 - S_P2] (columns gapS_P2, P_gapS_P2_pos): seconds the revenue-max pod leaves empty
           relative to the seconds-max pod on the same filtered pool, and P(gap > 0)
  revgap   E[R_P2 - R_P1]
  floor    paired contrasts with the no-floor condition on the same draws: dU_floor = U_P1(f) - U_P1(none)
           (seconds the seconds-max policy loses to floor filtering; revenue-max can lose a different number) and
           dR_floor = R_P2(f) - R_P2(none)
  greedy   for P3, P3d, P4: E[S_P1 - S_Px] and E[R_P2 - R_Px] with SEs, and the distribution of the relative
           revenue gap (R_P2 - R_Px) / R_P2 (P(zero gap), p50, p90, p99, max) from a 0.1%-bin histogram.
The exact DP's dominance in its own objective is asserted on every pool (greedy.assert_dominance), and P1/P2
are checked against the reference DP pod.dp_select on the first SPOT breaks of every block.

Usage: python3 run_x6.py [--tier quick|narrow|full] [--n N] [--jobs J] [--out DIR] [--estimate]
Defaults: tier from PODSIM_TIER (narrow), N from the tier, jobs from PODSIM_JOBS (2), out from PODSIM_OUT
(data/results). Writes OUT/x6/: summary.md, x6_aggregates.json (unrounded headline values), x6_conditions.csv, x6_conditions.json, x6_greedy_hist.json.gz,
x6_meta.json (full tier: x6_conditions.csv.gz and x6_greedy_hist.csv.gz instead of the CSV, JSON and JSON
histograms); timing in OUT/x6/timing.json only. Per-block results are cached in OUT/.cache/<tier>/x6/ with the
code hash (registry.cached), so a stopped run resumes; the unit key includes N and the master seed.
"""
import argparse
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import registry as REG  # noqa: E402
from podsim import pools as P  # noqa: E402
from podsim import revenue as RV  # noqa: E402
from podsim.laws import named, dynamic_cap  # noqa: E402
from podsim.pod import dp_select  # noqa: E402
from podsim.numeric import xsum  # noqa: E402

MASTER = "pods-x6-v1"
SPOT = 10
GREEDY = ("P3", "P3d", "P4")
HBINS = 1000  # relative revenue gap histogram: bin k holds gaps in [k/1000, (k+1)/1000); bin 1000 is gap 1

X6_TIERS = {
    "quick": dict(laws=[("L2", "a"), ("L3u", "a")], menus=[(15, 30), (6, 15, 30)], caps=[4, None],
                  lams=(8,), schemes=("balanced",), floors=("none", "ps67", "dfA"), vlaws=RV.VALUE_LAWS, n=500),
    "narrow": dict(laws=[("L2", "a"), ("L3u", "a")], menus=[(15, 30), (10, 15, 30), (6, 15, 30), (15, 30, 60)],
                   caps=[4, 6, 8, None], lams=(8, 64), schemes=("balanced", "d1530"),
                   floors=tuple(f.name for f in RV.FLOORS_NARROW), vlaws=RV.VALUE_LAWS, n=20000),
    # full: every built law with breaks up to 360 s, the 31-menu sample (registry.menu_sample), caps 3 to 12 and
    # uncapped; N, lambda and weights reduced so the tier stays an overnight run (registry.FULL_SKIPPED)
    "full": dict(laws=REG.FULL_LAWS, menus=REG.menu_sample(), caps=list(range(3, 13)) + [None], lams=(8, 64),
                 schemes=("balanced", "d1530"), floors=tuple(f.name for f in RV.FLOORS_NARROW), vlaws=RV.VALUE_LAWS,
                 n=4000),
}
X6_TIERS["fullsmoke"] = dict(X6_TIERS["full"], menus=[(15, 30)], caps=[3, None], lams=(8,), schemes=("d1530",), n=15)
FLOOR_BY_NAME = {f.name: f for f in RV.FLOORS_NARROW}


def capname(h):
    return "none" if h is None else str(h)


def menuname(m):
    return " ".join(map(str, m))


# ------------------------------------------------------------------------------------- accumulation

class Acc(object):
    """Sums and sums of squares per metric (paired SEs come from per-break differences)."""

    def __init__(self):
        self.n = 0
        self.s = {}
        self.q = {}
        self.cnt = {}
        self.hist = {g: {} for g in GREEDY}

    def add(self, vals, flags, gaps):
        self.n += 1
        for k, v in vals.items():
            self.s[k] = self.s.get(k, 0) + v
            self.q[k] = self.q.get(k, 0) + v * v
        for k, b in flags.items():
            if b:
                self.cnt[k] = self.cnt.get(k, 0) + 1
        for g, x in gaps.items():
            b = min(HBINS, int(x * HBINS + 1e-12))
            h = self.hist[g]
            h[b] = h.get(b, 0) + 1

    def to_json(self):
        return dict(n=self.n, s=self.s, q=self.q, cnt=self.cnt,
                    hist={g: {str(b): c for b, c in h.items()} for g, h in self.hist.items()})


def cond_key(h, vl, fl):
    return "%s|%s|%s" % (capname(h), vl, fl)


def run_block(args):
    """One block: (law, conv, menu, lam, scheme, n, cfg-subset). Returns {cond_key: Acc json} and timing."""
    lawname, conv, menu, lam, scheme, n, caps, vlaws, floors = args
    law = named(lawname)
    w = P.weights(scheme)
    vls = {v: RV.value_law(v) for v in vlaws}
    fls = [FLOOR_BY_NAME[f] for f in floors]
    accs = {cond_key(h, v, f.name): Acc() for h in caps for v in vlaws for f in fls}
    t0 = time.time()
    for i in range(n):
        d = RV.BreakDraw(MASTER, law, i, menu, lam, w)
        T = d.T
        for vn, vl in vls.items():
            vals = d.values(vl)
            base = {}
            for fl in fls:
                by, arr, ntot, nkept = RV.build_pool(d, vals, fl)
                for h in caps:
                    cap = dynamic_cap(h, d.structured, conv)
                    pods = RV.all_policies(T, cap, by, arr)
                    if i < SPOT and fl.name == "none":
                        flat = [c for a in sorted(by) for c in by[a]]
                        (ss, sr), (rr, rs) = dp_select(T, cap, flat)
                        p1, p2 = pods["P1"], pods["P2"]
                        if (ss, sr) != (p1.seconds, p1.revenue) or (rr, rs) != (p2.revenue, p2.seconds):
                            raise AssertionError("select_menu disagrees with dp_select at break %d" % i)
                    S = {k: p.seconds for k, p in pods.items()}
                    R = {k: p.revenue / 100.0 for k, p in pods.items()}
                    vals_ = {"T": T, "n_pool": ntot, "n_kept": nkept}
                    for k in RV.POLICIES:
                        vals_["U_" + k] = T - S[k]
                        vals_["R_" + k] = R[k]
                        vals_["ads_" + k] = pods[k].n_ads
                    vals_["gapS_P2"] = S["P1"] - S["P2"]
                    vals_["gapR_P2"] = R["P2"] - R["P1"]
                    for g in GREEDY:
                        vals_["gapS_" + g] = S["P1"] - S[g]
                        vals_["gapR_" + g] = R["P2"] - R[g]
                        vals_["gapSrev_" + g] = S["P2"] - S[g]
                    if fl.name == "none":
                        base[h] = (T - S["P1"], R["P2"], T - S["P2"], R["P1"])
                    b = base[h]
                    vals_["dU_floor_P1"] = (T - S["P1"]) - b[0]
                    vals_["dR_floor_P2"] = R["P2"] - b[1]
                    vals_["dU_floor_P2"] = (T - S["P2"]) - b[2]
                    vals_["dR_floor_P1"] = R["P1"] - b[3]
                    flags = {"gapS_P2_pos": S["P1"] > S["P2"], "gapR_P2_pos": R["P2"] > R["P1"],
                             "empty_P2": S["P2"] == 0}
                    gaps = {}
                    for g in GREEDY:
                        flags["gapR0_" + g] = R["P2"] == R[g]
                        flags["gapS0_" + g] = S["P1"] == S[g]
                        gaps[g] = (R["P2"] - R[g]) / R["P2"] if R["P2"] > 0 else 0.0
                    accs[cond_key(h, vn, fl.name)].add(vals_, flags, gaps)
    return {k: a.to_json() for k, a in accs.items()}, time.time() - t0


def block_list(cfg, n):
    out = []
    for lawname, conv in cfg["laws"]:
        for menu in cfg["menus"]:
            for lam in cfg["lams"]:
                for sc in cfg["schemes"]:
                    out.append((lawname, conv, tuple(menu), lam, sc, n, list(cfg["caps"]), tuple(cfg["vlaws"]),
                                tuple(cfg["floors"])))
    return out


def block_id(b):
    lawname, conv, menu, lam, sc, n = b[:6]
    return "%s-%s_m%s_l%d_%s_n%d" % (lawname, conv, "-".join(map(str, menu)), lam, sc, n)


def block_unit(b):
    res, dt = run_block(b)
    return dict(res=res, seconds=round(dt, 3))


def units(blocks):
    return [("%s__%s" % (MASTER, block_id(b)), b) for b in blocks]


# ------------------------------------------------------------------------------------------ reporting

def mean_se(acc, k):
    n = acc["n"]
    s = acc["s"].get(k, 0)
    q = acc["q"].get(k, 0)
    m = s / n
    var = max(0.0, (q - s * s / n) / (n - 1)) if n > 1 else 0.0
    return m, math.sqrt(var / n)


def hist_quant(h, n, p):
    """Upper edge of the bin holding the p-quantile of the relative gap."""
    tgt = p * n
    c = 0
    for b in sorted(int(x) for x in h):
        c += h[str(b)]
        if c >= tgt - 1e-9:
            return min(1.0, (b + 1) / HBINS) if b > 0 else 0.0
    return 1.0


def rows_for_block(b, res):
    lawname, conv, menu, lam, sc, n, caps, vlaws, floors = b
    rows = []
    hists = {}
    for h in caps:
        for v in vlaws:
            for fl in floors:
                a = res[cond_key(h, v, fl)]
                r = dict(law=lawname, conv=conv, menu=menuname(menu), lam=lam, scheme=sc, h=capname(h), vlaw=v,
                         floor=fl, N=a["n"])
                for k in ("T", "n_pool", "n_kept"):
                    r["E_" + k] = mean_se(a, k)[0]
                r["pass_rate"] = r["E_n_kept"] / r["E_n_pool"] if r["E_n_pool"] > 0 else 1.0
                for pol in RV.POLICIES:
                    for k in ("U_", "R_", "ads_"):
                        m, se = mean_se(a, k + pol)
                        r[k + pol] = m
                        if k != "ads_":
                            r[k + pol + "_se"] = se
                for k in ["gapS_P2", "gapR_P2", "dU_floor_P1", "dR_floor_P2", "dU_floor_P2", "dR_floor_P1"] + \
                        ["gap%s_%s" % (x, g) for g in GREEDY for x in ("S", "R", "Srev")]:
                    m, se = mean_se(a, k)
                    r[k] = m
                    r[k + "_se"] = se
                r["P_gapS_P2_pos"] = a["cnt"].get("gapS_P2_pos", 0) / a["n"]
                r["P_gapR_P2_pos"] = a["cnt"].get("gapR_P2_pos", 0) / a["n"]
                r["P_empty_P2"] = a["cnt"].get("empty_P2", 0) / a["n"]
                r["rel_revgap_P2"] = r["gapR_P2"] / r["R_P2"] if r["R_P2"] > 0 else 0.0
                for g in GREEDY:
                    hh = a["hist"][g]
                    r["P_gapR0_" + g] = a["cnt"].get("gapR0_" + g, 0) / a["n"]
                    r["P_gapS0_" + g] = a["cnt"].get("gapS0_" + g, 0) / a["n"]
                    r["relgapR_mean_" + g] = r["gapR_" + g] / r["R_P2"] if r["R_P2"] > 0 else 0.0
                    for p, lab in ((0.5, "p50"), (0.9, "p90"), (0.99, "p99")):
                        r["relgapR_%s_%s" % (lab, g)] = hist_quant(hh, a["n"], p)
                    r["relgapR_max_" + g] = hist_quant(hh, a["n"], 1.0)
                    hists["%s|%s|%s" % (block_id(b), cond_key(h, v, fl), g)] = hh
                rows.append(r)
    return rows, hists


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, c - hw), min(1.0, c + hw))


def f2(x):
    return "%.2f" % x


def f3(x):
    return "%.3f" % x


def pct(x):
    return "%.1f%%" % (100 * x)


SLIM = ["law", "conv", "menu", "lam", "scheme", "h", "vlaw", "floor", "gapS_P2", "gapS_P2_se", "P_gapS_P2_pos",
        "gapR_P2", "rel_revgap_P2", "dU_floor_P1", "dU_floor_P1_se", "dR_floor_P2"] + \
    ["%s_%s" % (x, g) for g in GREEDY for x in ("gapS", "relgapR_mean", "relgapR_max", "P_gapR0")]


class SlimRow(object):
    """The columns of one condition that the summary reads, in a compact form (the full tier holds a few hundred
    thousand conditions in memory while writing the summary). Indexable like the row dict."""
    __slots__ = tuple(f.replace("+", "_") for f in SLIM)

    def __init__(self, r):
        for f in SLIM:
            setattr(self, f, r[f])

    def __getitem__(self, k):
        return getattr(self, k)


def write_summary(path, rows, cfg, tier, n, nblocks, every_condition=True):
    L = []
    L.append("# X6: seconds-max versus revenue-max under floors, and greedy baselines (tier %s)" % tier)
    L.append("")
    L.append("Catalog axes: value (V1 to V4) and policy (P1 to P4). Every number is a Monte Carlo mean over "
             "N = %d breaks per block (%d blocks), common random numbers across caps, value laws, floors and "
             "policies (master seed `%s`; per-draw seed strings in podsim/revenue.py). Standard errors (SE) are "
             "across breaks; contrasts use paired per-break differences. Readiness rho = 1. Revenue is pay-as-bid, "
             "dollars of CPM per pod (per thousand pod impressions). All value laws, floor levels and weights are "
             "synthetic sweeps; the floor mechanisms (mincpmpersec, durfloors) are OpenRTB 2.6 (mincpmpersec "
             "and durfloors fields)." % (n, nblocks, MASTER))
    L.append("")
    L.append("Grid: laws %s; menus %s; caps %s; lambda %s; weights %s; value laws %s; floors:"
             % (", ".join("%s (convention %s)" % lc for lc in cfg["laws"]),
                "; ".join("{%s}" % ", ".join(map(str, m)) for m in cfg["menus"]),
                ", ".join(capname(h) for h in cfg["caps"]), ", ".join(map(str, cfg["lams"])),
                ", ".join(P.SCHEME_LABEL[s] for s in cfg["schemes"]), ", ".join(cfg["vlaws"])))
    L.append("")
    for fn in cfg["floors"]:
        fl = FLOOR_BY_NAME[fn]
        L.append("- `%s`: %s" % (fn, fl.describe()))
    L.append("")
    L.append("Value laws: V1 flat per-second value (pools.py, median 30-s CPM $20, sigma 0.5); V2 duration premium, "
             "per-second value times (a/30)^%.1f (15 s x%.2f, 6 s x%.2f, 60 s x%.2f). Both synthetic."
             % (RV.V2_BETA, 0.5 ** RV.V2_BETA, 0.2 ** RV.V2_BETA, 2.0 ** RV.V2_BETA))
    L.append("")
    L.append("Policies: P1 exact seconds-max (ties by revenue); P2 exact revenue-max (ties by seconds); P3 greedy by "
             "per-second price, longer first on ties; P3d greedy longest duration first, then price; P4 first-come "
             "in arrival order. Every greedy rule adds a creative whenever it still fits under T and the cap.")
    L.append("")

    # ---- headline aggregates
    N_all = len(rows)
    pos = [r for r in rows if r["gapS_P2"] > 0]
    sig = [r for r in rows if r["gapS_P2"] > 2 * r["gapS_P2_se"] + 1e-12]
    mx = max(rows, key=lambda r: r["gapS_P2"])
    L.append("## Headline")
    L.append("")
    L.append("- Conditions: %d. Revenue-max (P2) leaves seconds empty relative to seconds-max (P1) on the same pool "
             "in %d of them (mean gap above 2 SE in %d). Largest mean gap: %s s (SE %s) per break, %s, menu {%s}, "
             "h %s, lambda %d, %s, %s, floor %s; there P(gap > 0) = %s and the revenue gain is $%s CPM per pod "
             "(%s of P2 revenue)."
             % (N_all, len(pos), len(sig), f3(mx["gapS_P2"]), f3(mx["gapS_P2_se"]), mx["law"], ", ".join(mx["menu"].split()), mx["h"],
                mx["lam"], P.SCHEME_LABEL[mx["scheme"]], mx["vlaw"], mx["floor"], pct(mx["P_gapS_P2_pos"]),
                f3(mx["gapR_P2"]), pct(mx["rel_revgap_P2"])))
    for v in cfg["vlaws"]:
        sub = [r for r in rows if r["vlaw"] == v]
        L.append("- %s: mean over conditions of the policy gap %s s per break (range %s to %s); mean revenue gain of P2 "
                 "over P1 %s of P2 revenue (max %s)."
                 % (v, f3(xsum(r["gapS_P2"] for r in sub) / len(sub)), f3(min(r["gapS_P2"] for r in sub)),
                    f3(max(r["gapS_P2"] for r in sub)), pct(xsum(r["rel_revgap_P2"] for r in sub) / len(sub)),
                    pct(max(r["rel_revgap_P2"] for r in sub))))
    fe = [r for r in rows if r["floor"] != "none"]
    mxf = max(fe, key=lambda r: r["dU_floor_P1"])
    L.append("- Floors (bids below the floor do not clear): largest added unsold seconds %s s per break (SE %s), floor %s, %s, "
             "menu {%s}, h %s, lambda %d, %s, %s; revenue change there %s dollars CPM per pod. In this pay-as-bid model a "
             "floor only removes bids, so dR_floor is never positive (no bid response is modeled)."
             % (f3(mxf["dU_floor_P1"]), f3(mxf["dU_floor_P1_se"]), mxf["floor"], mxf["law"], ", ".join(mxf["menu"].split()), mxf["h"],
                mxf["lam"], P.SCHEME_LABEL[mxf["scheme"]], mxf["vlaw"], f3(mxf["dR_floor_P2"])))
    for g in GREEDY:
        L.append("- %s versus the exact DP: mean shortfall %s s against P1 (max %s s) and %s of revenue against P2 "
                 "(max condition mean %s; worst single pool %s); P(revenue gap = 0) from %s to %s across conditions."
                 % (g, f3(xsum(r["gapS_" + g] for r in rows) / N_all), f3(max(r["gapS_" + g] for r in rows)),
                    pct(xsum(r["relgapR_mean_" + g] for r in rows) / N_all),
                    pct(max(r["relgapR_mean_" + g] for r in rows)),
                    pct(max(r["relgapR_max_" + g] for r in rows)),
                    pct(min(r["P_gapR0_" + g] for r in rows)), pct(max(r["P_gapR0_" + g] for r in rows))))
    L.append("- The exact DP weakly dominated every other policy in its own objective on every pool (asserted per "
             "pool; %d conditions x %d breaks), and P1/P2 matched the reference DP (pod.dp_select) on the first %d "
             "breaks of every block with no floor." % (N_all, n, SPOT))
    L.append("")

    # ---- policy gap and floors
    L.append("## Policy gap and floors")
    L.append("")
    nofl = [r for r in rows if r["floor"] == "none"]
    with_fl = [r for r in rows if r["floor"] != "none"]

    def avg(rs, k):
        return xsum(r[k] for r in rs) / len(rs) if rs else 0.0

    L.append("Question: does revenue-max leave seconds empty when short creatives price below the floor?")
    L.append("")
    L.append("- Policy component (deliberate emptiness, same pool): mean E[S_P1 - S_P2] is %s s with no floor and %s s "
             "averaged over the floored conditions; it is positive with no floor at all, so revenue-max leaves seconds "
             "empty without any floor, by swapping several cheaper short ads for fewer high bids."
             % (f3(avg(nofl, "gapS_P2")), f3(avg(with_fl, "gapS_P2"))))
    L.append("- Floor component (seconds-max policy; filtering removes the same creatives from both policies' pools): "
             "mean E[U_P1(f) - U_P1(none)] "
             "is %s s over the floored conditions." % f3(avg(with_fl, "dU_floor_P1")))
    for v in cfg["vlaws"]:
        a0 = [r for r in nofl if r["vlaw"] == v]
        L.append("- %s, no floor: mean policy gap %s s; per floor: %s." % (
            v, f3(avg(a0, "gapS_P2")),
            "; ".join("%s %s s (floor adds %s s)" % (
                fn, f3(avg([r for r in rows if r["vlaw"] == v and r["floor"] == fn], "gapS_P2")),
                f3(avg([r for r in rows if r["vlaw"] == v and r["floor"] == fn], "dU_floor_P1")))
                      for fn in cfg["floors"] if fn != "none")))
    L.append("")
    L.append("POLICY_PLACEHOLDER")
    L.append("")

    # ---- full condition tables
    if not every_condition:
        L.append("Every condition (%d) is in x6_conditions.csv.gz; greedy revenue-gap histograms in "
                 "x6_greedy_hist.csv.gz (0.1%% bins). The per-condition tables are not repeated here at this size."
                 % len(rows))
        return L
    L.append("## Every condition")
    L.append("")
    L.append("Columns: U1, U2 unsold seconds per break under P1, P2 (SE); gap = E[S_P1 - S_P2] (SE), P(gap>0); "
             "R1, R2 revenue $CPM per pod; dR = E[R_P2 - R_P1] (SE); dUf = E[U_P1(f) - U_P1(none)] (SE); "
             "kept = share of creatives clearing the floor; P3, P3d, P4: seconds shortfall vs P1 / mean relative "
             "revenue shortfall vs P2.")
    L.append("")
    keyf = lambda r: (r["law"], r["conv"], r["menu"], r["lam"], r["scheme"], r["vlaw"],
                      cfg["caps"].index(None if r["h"] == "none" else int(r["h"])), cfg["floors"].index(r["floor"]))
    rows_s = sorted(rows, key=keyf)
    cur = None
    for r in rows_s:
        blk = (r["law"], r["conv"], r["menu"], r["lam"], r["scheme"], r["vlaw"])
        if blk != cur:
            cur = blk
            L.append("")
            L.append("### %s (conv %s), menu {%s}, lambda %d, %s, %s; E[T] = %s s"
                     % (r["law"], r["conv"], ", ".join(r["menu"].split()), r["lam"], P.SCHEME_LABEL[r["scheme"]],
                        r["vlaw"], f2(r["E_T"])))
            L.append("")
            L.append("| h | floor | kept | U1 (SE) | U2 (SE) | gap (SE) | P(gap>0) | R1 | R2 | dR (SE) | dUf (SE) | P3 | P3d | P4 |")
            L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        L.append("| %s | %s | %s | %s (%s) | %s (%s) | %s (%s) | %s | %s | %s | %s (%s) | %s (%s) | %s | %s | %s |" % (
            r["h"], r["floor"], pct(r["pass_rate"]), f2(r["U_P1"]), f3(r["U_P1_se"]), f2(r["U_P2"]), f3(r["U_P2_se"]),
            f3(r["gapS_P2"]), f3(r["gapS_P2_se"]), pct(r["P_gapS_P2_pos"]), f2(r["R_P1"]), f2(r["R_P2"]),
            f3(r["gapR_P2"]), f3(r["gapR_P2_se"]), f2(r["dU_floor_P1"]), f3(r["dU_floor_P1_se"]),
            *["%s / %s" % (f2(r["gapS_" + g]), pct(r["relgapR_mean_" + g])) for g in GREEDY]))
    L.append("")
    L.append("Files: x6_conditions.csv and x6_conditions.json (every column, every condition), x6_greedy_hist.json "
             "(relative revenue gap histograms, 0.1% bins, per condition and greedy policy), x6_meta.json (grid, "
             "seeds, N).")
    return L



def aggregates(rows, cfg):
    """Unrounded aggregates behind the summary's headline and policy lines, keyed as in manuscript_numbers.py
    (percent values in percent). The numbers script reads these, so a cited number is rounded once, at display."""
    def avg(rs, k):
        return xsum(r[k] for r in rs) / len(rs) if rs else 0.0
    nofl = [r for r in rows if r["floor"] == "none"]
    fl = [r for r in rows if r["floor"] != "none"]
    A = {"conditions": len(rows), "gap_nofloor_mean": avg(nofl, "gapS_P2"), "floor_added_mean": avg(fl, "dU_floor_P1"),
         "gap_max": max(r["gapS_P2"] for r in rows),
         "nofloor.gap_above_2se": "%d of %d" % (len([r for r in nofl if r["gapS_P2"] > 2 * r["gapS_P2_se"] + 1e-12]),
                                                len(nofl))}
    for g in GREEDY:
        A[g + ".short"] = avg(rows, "gapS_" + g)
        A[g + ".short_nofloor"] = avg(nofl, "gapS_" + g)
        A[g + ".short_floored"] = avg(fl, "gapS_" + g)
        for f in cfg["floors"]:
            A["%s.short_floor.%s" % (g, f)] = avg([r for r in rows if r["floor"] == f], "gapS_" + g)
        A[g + ".max"] = max(r["gapS_" + g] for r in rows)
        A[g + ".rev"] = 100 * avg(rows, "relgapR_mean_" + g)
        A[g + ".rev_max_condition"] = 100 * max(r["relgapR_mean_" + g] for r in rows)
    for v in cfg["vlaws"]:
        sub = [r for r in rows if r["vlaw"] == v]
        A[v + ".gap_mean"] = avg(sub, "gapS_P2")
        A[v + ".rev_gain"] = 100 * avg(sub, "rel_revgap_P2")
        A[v + ".nofloor_gap"] = avg([r for r in nofl if r["vlaw"] == v], "gapS_P2")
        for f in cfg["floors"]:
            if f != "none":
                A["%s.floor_adds.%s" % (v, f)] = avg([r for r in sub if r["floor"] == f], "dU_floor_P1")
    return A

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default=None, choices=sorted(X6_TIERS))
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--jobs", type=int, default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--estimate", action="store_true", help="time a few breaks per block and print an estimate")
    a = ap.parse_args()
    if a.out:
        os.environ["PODSIM_OUT"] = os.path.abspath(a.out)
    tier = a.tier or REG.tier_name()
    os.environ["PODSIM_TIER"] = tier
    cfg = X6_TIERS[tier]
    n = a.n or cfg["n"]
    jobs = a.jobs or REG.jobs()
    blocks = block_list(cfg, n)
    us = units(blocks)
    if REG.units_only([("x6", us, block_unit, True)]):
        return 0
    if a.estimate:
        probe = 200
        tot = 0.0
        for b in block_list(cfg, probe)[:: max(1, len(blocks) // 16)]:
            _, dt = run_block(b)
            tot += dt / probe
        per = tot / len(block_list(cfg, probe)[:: max(1, len(blocks) // 16)])
        cpu = per * n * len(blocks)
        print("x6 %s: %d blocks x %d breaks; about %.2f ms per break per block on this machine; %.0f CPU s total"
              % (tier, len(blocks), n, per * 1000, cpu))
        return 0
    out = REG.out_dir("x6")
    t0 = time.time()
    block_secs = {}
    if not REG.big(tier):
        res = REG.map_units("x6", us, block_unit, raw=True, n_jobs=jobs)
        rows, hists = [], {}
        for b, r in zip(blocks, res):
            rr, hh = rows_for_block(b, r["res"])
            rows.extend(rr)
            hists.update(hh)
            block_secs[block_id(b)] = r["seconds"]
        REG.write_csv(os.path.join(out, "x6_conditions.csv"), rows)
        REG.write_json(os.path.join(out, "x6_conditions.json"), rows)
        REG.write_json(os.path.join(out, "x6_greedy_hist.json.gz"), hists)
    else:
        # full tier: stream every condition to gzipped CSVs (the conditions JSON duplicate is not written) and
        # keep only the columns the summary needs in memory
        rows = []
        sc = REG.CsvStream(os.path.join(out, "x6_conditions.csv.gz"))
        sh = REG.CsvStream(os.path.join(out, "x6_greedy_hist.csv.gz"), fields=["condition", "policy", "bin", "count"])
        for b, r in zip(blocks, REG.iter_units("x6", us, block_unit, raw=True, n_jobs=jobs)):
            rr, hh = rows_for_block(b, r["res"])
            sc.write(rr)
            hrows = []
            for k in sorted(hh):
                cond, g = k.rsplit("|", 1)
                for bn in sorted(hh[k], key=int):
                    hrows.append(dict(condition=cond, policy=g, bin=int(bn), count=hh[k][bn]))
            sh.write(hrows)
            rows.extend(SlimRow(x) for x in rr)
            block_secs[block_id(b)] = r["seconds"]
        sc.close()
        sh.close()
    meta = dict(tier=tier, master=MASTER, n=n, blocks=len(blocks), conditions=len(rows), spot_dp_breaks=SPOT,
                laws=[list(x) for x in cfg["laws"]], menus=[list(m) for m in cfg["menus"]],
                caps=[capname(h) for h in cfg["caps"]], lams=list(cfg["lams"]), schemes=list(cfg["schemes"]),
                vlaws=list(cfg["vlaws"]), v2_beta=RV.V2_BETA,
                floors={f: FLOOR_BY_NAME[f].describe() for f in cfg["floors"]}, rho=1.0,
                seeds=dict(pool="<master>|pool|<break>|<duration>", arrival="<master>|arrive|<break>|<duration>",
                           target="<master>|break|<law>|<break>"))
    REG.write_json(os.path.join(out, "x6_meta.json"), meta)
    REG.write_json(os.path.join(out, "x6_aggregates.json"), aggregates(rows, cfg))
    L = write_summary(None, rows, cfg, tier, n, len(blocks), every_condition=not REG.big(tier))
    txt = "\n".join(L) + "\n"
    policy = policy_text(rows, cfg)
    txt = txt.replace("POLICY_PLACEHOLDER", policy)
    REG.write_text(os.path.join(out, "summary.md"), txt)
    dt = time.time() - t0
    REG.write_timing(out, "x6_" + tier, dt)
    REG.write_timing(out, "x6_%s_block_cpu_total" % tier, xsum(block_secs.values()))
    print("x6 %s: %d blocks, %d conditions, N = %d, %.1f s wall (%.1f CPU s in blocks)"
          % (tier, len(blocks), len(rows), n, dt, xsum(block_secs.values())))
    return 0


def policy_text(rows, cfg):
    """Rule-based summary paragraph of the policy gap and floors section (fixed rules, computed from the table)."""
    nofl = [r for r in rows if r["floor"] == "none"]
    fl = [r for r in rows if r["floor"] != "none"]
    g0 = xsum(r["gapS_P2"] for r in nofl) / len(nofl)
    gf = xsum(r["gapS_P2"] for r in fl) / len(fl)
    du = xsum(r["dU_floor_P1"] for r in fl) / len(fl)
    pos0 = xsum(1 for r in nofl if r["gapS_P2"] > 2 * r["gapS_P2_se"] + 1e-12)
    return ("**Policy gap and floors.** Revenue-max leaves "
            "seconds empty relative to seconds-max on the same pool (mean %s s per break with no floor, above 2 SE in "
            "%d of %d no-floor conditions), so the policy gap exists without any floor. A bid below the floor "
            "(mincpmpersec or a durfloors range floor) does not clear, whether the buyer withholds it or the "
            "exchange rejects it, so the creatives that price below it never enter the pool. For the seconds-max "
            "policy the floors add a mean of %s s per break over the floored conditions; revenue-max can lose a "
            "different number to the same floor, because filtering also changes which pod it prefers. With floors "
            "the policy gap averages %s s. The two components are reported separately: floor-induced unsold "
            "seconds (a pool effect) and the revenue-max policy gap (a choice effect)." % (f3(g0), pos0, len(nofl),
                                                                                          f3(du), f3(gf)))


if __name__ == "__main__":
    sys.exit(main())
