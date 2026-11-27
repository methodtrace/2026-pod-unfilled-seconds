"""X5: clutter-cost sweep and the frontier of unfilled seconds against ads per break, with the
knapsack companion's necessary conditions checked on every simulated (full break, remainder) pair of hulls.

Usage: python3 run_x5.py [--tier quick|narrow] [--n N] [--jobs J] [--out DIR]

Grid (narrow): laws L2 (hybrid remainder T = B - S, B uniform on {60, 90, ..., 240}, S uniform on
{5, 10, 15, 20, 45}, always present) under cap conventions a and b, and L3u (uniform integers [60, 240]);
menus {15,30}, {10,15,30}, {6,15,30}, {15,30,60}, {10,15,20,30}; nominal caps 6, 8, 12 (and 7, 9, 13 for the
h + 1 comparisons); lambda 16 and 64; weights balanced and 15/30-dominant; clutter cost c from 0 to 2000 cents
of CPM per ad (the median bid of a 30 s ad under value law V1) in 12 steps; three clutter-cost shapes:
  base   c per ad (knapsack-companion envelope max_n H_T(n) - c n)
  A1     SYNTHETIC anchor for "intrusiveness doubles at three minutes" (FreeWheel/MediaScience, Designing a Better
         Ad Pod, January 2024): per-ad cost 2c when the pod's filled seconds exceed 180
  A2     SYNTHETIC anchor for "pods mixing :15 and :30 seemed longer" (same study): per-ad cost 1.5c when the pod
         holds both a 15 s and a 30 s creative
The anchors are qualitative; the multipliers 2 and 1.5 and the 180 s threshold reading are modeling choices.

Randomness: master seed "pods-x5-v1". Break targets from "<master>|break|<law>|<i>"; creative pools from
pools.duration_stream("<master>", i, a, ...), so every menu, cap, convention, c and anchor sees the same breaks
and creatives (common random numbers), and L2 and L3u share pools by break index. All per-break quantities are
integers (seconds, ads, cents of CPM, net value scaled by 2 * 12), and sums are exact integers, so outputs do not
depend on --jobs or chunking. Paired standard errors for contrasts come from per-break differences.
Writes data/results/x5/ (timing in timing.json only).
"""
import argparse
import math
import os
import random
import sys
import time
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from podsim import pools, laws, clutter, hullchecks  # noqa: E402
from podsim import registry as REG  # noqa: E402
from podsim.pod import Creative, select_menu  # noqa: E402
from podsim.numeric import xsum  # noqa: E402

MASTER = "pods-x5-v1"
ANCHORS = ("base", "A1", "A2")
MULT2 = {"base": (2, 2, 2, 2), "A1": (2, 4, 2, 4), "A2": (2, 2, 3, 3)}  # 2 x multiplier by class
KS = list(range(clutter.K_STEPS + 1))
SCALE = 2 * clutter.K_STEPS                 # net value scale: net_scaled = SCALE * rev - k * CMAX * n * mult2
L1PTS = [t for t, _ in laws.L1()]
SSET = laws.S_SPOTS
ONE_SPOT_SETS = dict([("L2", laws.S_SPOTS)] + sorted(laws.H2_SETS.items()))
TOL = 0

NARROW_GRID = dict(menus=[(15, 30), (10, 15, 30), (6, 15, 30), (15, 30, 60), (10, 15, 20, 30)],
                   hs=(6, 8, 12), lams=(16, 64), schemes=("balanced", "d1530"),
                   variants=(("L2", "a"), ("L2", "b"), ("L3u", "a")))
# full: the 31-menu sample, every built law with breaks up to 360 s, caps 3 to 12 and uncapped (h + 1 up to 13)
FULL_GRID = dict(menus=None, hs=tuple(range(3, 13)) + (None,), lams=(16, 64), schemes=("balanced", "d1530"),
                 variants=tuple(REG.FULL_LAWS))
# quick: the narrow grid plus one H2 set and the two-spot law (so the quick tier exercises the new laws)
QUICK_GRID = dict(NARROW_GRID, variants=NARROW_GRID["variants"] + (("L2s60", "a"), ("L2two", "b")))
TIERS = {"quick": dict(n=200, chunk=100, grid=QUICK_GRID), "narrow": dict(n=4000, chunk=250, grid=NARROW_GRID),
         "full": dict(n=2000, chunk=500, grid=FULL_GRID),
         "fullsmoke": dict(n=6, chunk=3, grid=dict(FULL_GRID, menus=[(15, 30), (6, 15, 30)], hs=(3, None),
                                                   lams=(16,), schemes=("d1530",)))}


def configure(tier):
    """Set the module grid for a tier. Called at import from PODSIM_TIER, so worker processes started with
    either fork or spawn see the same grid as the parent (run_tier.py and main() set PODSIM_TIER)."""
    global GRID_TIER, MENUS, BASE, HS, CAPS_ALL, LAMS, SCHEMES, VARIANTS, LAWS, DURS, KPOOL, CONTRASTS, HULL_CAPS
    if tier not in TIERS:
        raise SystemExit("unknown tier %r (expected one of: %s)" % (tier, ", ".join(sorted(TIERS))))
    g = TIERS[tier]["grid"]
    GRID_TIER = tier
    MENUS = list(g["menus"]) if g["menus"] is not None else [tuple(m) for m in REG.menu_sample()]
    BASE = (15, 30)
    if BASE not in MENUS:
        raise ValueError("X5 needs the base menu {15,30} in its grid")
    HS = tuple(g["hs"])
    ints = [h for h in HS if h is not None]
    CAPS_ALL = tuple(sorted(set(ints) | {h + 1 for h in ints})) + ((None,) if None in HS else ())
    HULL_CAPS = tuple(h for h in CAPS_ALL if h is not None)
    LAMS = tuple(g["lams"])
    SCHEMES = tuple(g["schemes"])
    VARIANTS = tuple(tuple(v) for v in g["variants"])
    LAWS = tuple(sorted({l for l, _ in VARIANTS}, key=lambda l: [x for x, _ in VARIANTS].index(l)))
    DURS = sorted(set(a for m in MENUS for a in m))
    from podsim.exact import TMAX
    KPOOL = max(48, TMAX // 5)  # top creatives kept per duration: no pod can use more (exact)
    CONTRASTS = contrast_defs()


def dyn_cap(h, conv, structured):
    return laws.dynamic_cap(h, structured, conv)


_LAWOBJ = {}


def draw_target(law, i):
    """(B, T, structured). One-spot hybrid laws (L2 and the H2 sets): B and S from their own stream (same law as
    laws.named). L3u: uniform integers [60, 240] from its own stream. Other laws: laws.named(law).sample on the
    same seed string; B is reported equal to T except for the two-spot law (structured = 2), whose B is not
    used (no hull-pair check for two spots)."""
    rng = random.Random("%s|break|%s|%d" % (MASTER, law, i))
    if law in ONE_SPOT_SETS:
        sset = ONE_SPOT_SETS[law]
        B = L1PTS[rng.randrange(len(L1PTS))]
        S = sset[rng.randrange(len(sset))]
        return B, B - S, True
    if law == "L3u":
        T = 60 + rng.randrange(181)
        return T, T, False
    lo = _LAWOBJ.get(law)
    if lo is None:
        lo = laws.named(law)
        _LAWOBJ[law] = lo
    T, st = lo.sample(rng)
    return T, T, st


def enumerate_classes(bids, caps_C):
    """{C: {(n, cls): (rev, sec)}} over count vectors; cls bit0: filled seconds > 180, bit1: has 15 s and 30 s.
    Best (rev, sec) per (n, cls); counts of distinct creatives limited by availability and capacity only."""
    durs = sorted(bids)
    Cmax = max(caps_C)
    caps_sorted = sorted(set(caps_C))
    pref = []
    for a in durs:
        p = [0]
        for x in bids[a]:
            p.append(p[-1] + x)
        pref.append(p)
    i15 = durs.index(15) if 15 in durs else -1
    i30 = durs.index(30) if 30 in durs else -1
    best = {C: {} for C in caps_sorted}
    counts = [0] * len(durs)
    L = len(durs)

    def rec(j, sec, n, rev):
        if j == L:
            cls = (1 if sec > 180 else 0) | (2 if (i15 >= 0 and i30 >= 0 and counts[i15] and counts[i30]) else 0)
            key = (rev, sec)
            for C in caps_sorted:
                if sec <= C:
                    d = best[C]
                    cur = d.get((n, cls))
                    if cur is None or key > cur:
                        d[(n, cls)] = key
            return
        a = durs[j]
        top = min(len(bids[a]), (Cmax - sec) // a)
        p = pref[j]
        for c in range(top + 1):
            counts[j] = c
            rec(j + 1, sec + c * a, n + c, rev + p[c])
        counts[j] = 0

    rec(0, 0, 0, 0)
    return best


def by_count(d):
    """best (rev, sec) per n over classes, as a list n = 0..max."""
    out = {}
    for (n, cls), v in d.items():
        if n not in out or v > out[n]:
            out[n] = v
    return [out[n] for n in range(len(out))]


def scen_list():
    return [(law, lam, sc) for law in LAWS for lam in LAMS for sc in SCHEMES]


def config_keys():
    keys = []
    for law, conv in VARIANTS:
        for menu in MENUS:
            for h in CAPS_ALL:
                for an in ANCHORS:
                    for k in KS:
                        keys.append((law + conv, menu, h, an, k))
    return keys


def contrast_defs():
    """(name, x key-part, y key-part): x - y, per variant, anchor, k. key-part = (menu, cap). h + 1 contrasts
    do not exist uncapped."""
    out = []
    for h in HS:
        for M in MENUS:
            if M == BASE:
                if h is not None:
                    out.append(("cap_plus_one", h, (BASE, h + 1), (BASE, h)))
                continue
            out.append(("menu_vs_base_same_h", h, (M, h), (BASE, h)))
            if h is not None:
                out.append(("menu_vs_base_h_plus_one", h, (M, h), (BASE, h + 1)))
    return out


configure(os.environ.get("PODSIM_TIER", "narrow"))


def work(args):
    """One chunk of breaks for one scenario. Returns integer sums."""
    law, lam, sc, start, n = args
    w = pools.weights(sc)
    vl = pools.ValueLaw()
    variants = [v for v in VARIANTS if v[0] == law]
    acc = {}
    cacc = {}
    hc = {}  # hull checks: form -> count
    t0 = time.time()
    for i in range(start, start + n):
        B, T, structured = draw_target(law, i)
        pool = {a: pools.duration_stream(MASTER, i, a, lam * w[a], KPOOL, vl)[0] for a in DURS}
        res = {}
        for menu in MENUS:
            bids = {a: [c.bid for c in pool[a]] for a in menu if a <= B and pool[a]}
            capsC = (B, T) if structured is True else (T,)
            if not bids:
                best = {C: {(0, 0): (0, 0)} for C in capsC}
            else:
                best = enumerate_classes(bids, capsC)
            bcT = by_count(best[T])
            if i - start < 3 and start < 2 * TIERS["narrow"]["chunk"]:
                _crosscheck(T, menu, pool, bcT)
            if structured is True:
                bcB = by_count(best[B])
                _hullchecks(bcB, bcT, menu, hc, (law, lam, sc, i))
            for lawv, conv in variants:
                for h in CAPS_ALL:
                    cap = dyn_cap(h, conv, structured)
                    bt = bcT if cap is None else bcT[:cap + 1]
                    vals = [x[0] for x in bt]
                    b, verts = clutter.hull_vertices(vals)
                    classes = [(nn, cls, rv) for (nn, cls), rv in best[T].items() if cap is None or nn <= cap]
                    classes.sort()
                    for k in KS:
                        nstar = clutter.seller_choice(bt, verts, k)
                        # envelope over the hull equals the brute maximum over all counts (knapsack companion, Section 2)
                        bv = max(clutter.K_STEPS * bt[nn][0] - k * clutter.CMAX * nn for nn in range(len(bt)))
                        if clutter.K_STEPS * bt[nstar][0] - k * clutter.CMAX * nstar != bv:
                            raise AssertionError("envelope mismatch")
                        rev, sec = bt[nstar]
                        res[(lawv + conv, menu, h, "base", k)] = (T - sec, nstar, SCALE * rev - k * clutter.CMAX * nstar * 2, rev)
                        for an in ("A1", "A2"):
                            mm = MULT2[an]
                            bestv = None
                            for nn, cls, (rv, sc_) in classes:
                                val = SCALE * rv - k * clutter.CMAX * nn * mm[cls]
                                if bestv is None or val > bestv[0]:
                                    bestv = (val, nn, sc_, rv)
                            res[(lawv + conv, menu, h, an, k)] = (T - bestv[2], bestv[1], bestv[0], bestv[3])
        for key, (u, a, net, rev) in res.items():
            s = acc.get(key)
            if s is None:
                s = [0] * 9
                acc[key] = s
            s[0] += u
            s[1] += u * u
            s[2] += a
            s[3] += a * a
            s[4] += net
            s[5] += net * net
            s[6] += rev
            s[7] += 1 if u > 0 else 0
            s[8] += 1
        for lawv, conv in variants:
            for an in ANCHORS:
                for k in KS:
                    for cname, h, (mx, hx), (my, hy) in CONTRASTS:
                        x = res[(lawv + conv, mx, hx, an, k)]
                        y = res[(lawv + conv, my, hy, an, k)]
                        ck = (lawv + conv, cname, h, mx, an, k)
                        s = cacc.get(ck)
                        if s is None:
                            s = [0] * 6
                            cacc[ck] = s
                        du, da, dn = x[0] - y[0], x[1] - y[1], x[2] - y[2]
                        s[0] += du
                        s[1] += du * du
                        s[2] += da
                        s[3] += da * da
                        s[4] += dn
                        s[5] += dn * dn
    return (law, lam, sc), acc, cacc, hc, time.time() - t0


def units(n, chunk):
    out = []
    for law, lam, sc in scen_list():
        for st in range(0, n, chunk):
            out.append(("%s_l%d_%s_s%d_n%d" % (law, lam, sc, st, min(chunk, n - st)), (law, lam, sc, st, min(chunk, n - st))))
    return out


def _enc_key(k):
    return [list(x) if isinstance(x, tuple) else x for x in k]


def _dec_key(k):
    return tuple(tuple(x) if isinstance(x, list) else x for x in k)


def work_unit(args):
    """work() with JSON-safe keys (integer sums only, so the cache round trip is exact)."""
    scen, acc, cacc, hc, dt = work(tuple(args))
    return dict(scen=list(scen), acc=[[_enc_key(k), v] for k, v in sorted(acc.items(), key=lambda kv: repr(kv[0]))],
                cacc=[[_enc_key(k), v] for k, v in sorted(cacc.items(), key=lambda kv: repr(kv[0]))],
                hc=hc, seconds=round(dt, 3))


def decode_unit(r):
    return (tuple(r["scen"]), {_dec_key(k): v for k, v in r["acc"]}, {_dec_key(k): v for k, v in r["cacc"]},
            r["hc"], r["seconds"])


def _crosscheck(T, menu, pool, bcT):
    """Brute checks on a few breaks per scenario: best_by_count (clutter.py) agrees with this enumeration, and
    the uncapped revenue optimum agrees with pod.select_menu's revenue policy."""
    bids = {a: [c.bid for c in pool[a]] for a in menu if a <= T and pool[a]}
    if not bids:
        return
    b2, _ = clutter.best_by_count(bids, [T])
    if [(x[0], x[1]) for x in b2[T]] != bcT:
        raise AssertionError("best_by_count mismatch")
    by = {a: list(pool[a]) for a in menu if pool[a]}
    _, prev = select_menu(T, None, by)
    if prev.revenue != max(x[0] for x in bcT):
        raise AssertionError("revenue optimum mismatch with select_menu")


def _hullchecks(bcB, bcT, menu, hc, ctx):
    for form in hullchecks.PAIR_FORMS:
        hs = (None,) if form == "unc" else HULL_CAPS
        for h in hs:
            cB, cT = hullchecks.pair_caps(h, form) if h is not None else (None, None)
            wv = [x[0] for x in (bcB if cB is None else bcB[:cB + 1])]
            rv = [x[0] for x in (bcT if cT is None else bcT[:cT + 1])]
            _, Hw, _ = clutter.hull(wv)
            _, Hr, _ = clutter.hull(rv)
            hullchecks.check_pair(Hw, Hr, cB, cT, context=(ctx, menu, form, h))
            hc[form] = hc.get(form, 0) + 1


# --------------------------------------------------------------------------------------------- reporting

def mean_se(s1, s2, n):
    m = s1 / n
    var = (s2 - s1 * s1 / n) / (n - 1) if n > 1 else 0.0
    return m, math.sqrt(max(var, 0.0) / n)


def wilson(x, n, z=1.959963984540054):
    p = x / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - hw, c + hw


def mstr(m):
    return "{" + ",".join(map(str, m)) + "}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier", default=os.environ.get("PODSIM_TIER", "narrow"), choices=sorted(TIERS))
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--jobs", type=int, default=REG.jobs())
    ap.add_argument("--out", default=None)
    ap.add_argument("--report-only", action="store_true", help="rebuild summary.md from the tables in --out")
    a = ap.parse_args()
    os.environ["PODSIM_TIER"] = a.tier  # unit cache folder follows the tier actually run
    if a.out:
        os.environ["PODSIM_OUT"] = os.path.abspath(a.out)  # --out is this experiment's folder; its cache goes inside
    if a.tier != GRID_TIER:
        configure(a.tier)
    n = a.n or TIERS[a.tier]["n"]
    chunk = min(TIERS[a.tier]["chunk"], n)
    us = units(n, chunk)
    if not a.report_only and REG.units_only([("x5", us, work_unit, False)]):
        return
    out = a.out or os.path.join(REG.out_root(), "x5")
    os.makedirs(out, exist_ok=True)
    if a.report_only:
        import json
        rows = REG.read_csv(os.path.join(out, REG.table_name("frontier")))
        crows = REG.read_csv(os.path.join(out, REG.table_name("contrasts")))
        mrows = REG.read_csv(os.path.join(out, REG.table_name("matched_ads")))
        vp = os.path.join(out, "matched_cells.json")
        if os.path.exists(vp):
            with open(vp) as f:
                matched = json.load(f)
        else:
            import gzip
            with gzip.open(vp + ".gz", "rt", encoding="utf-8") as f:
                matched = json.load(f)
        hcj = json.load(open(os.path.join(out, "hullchecks.json")))
        write_summary(out, rows, crows, mrows, matched, hcj, hcj["n_per_scenario"])
        return
    t0 = time.time()
    # one law at a time, laws in sorted order (the tables are sorted by law first), so memory holds one law's sums
    hc = {}
    cpu = 0.0
    matched = {}
    streams = {nm: REG.CsvStream(os.path.join(out, REG.table_name(nm))) for nm in ("frontier", "contrasts",
                                                                                   "matched_ads")}
    keep = not REG.big(GRID_TIER)
    rows, crows, mrows = [], [], []
    for law in sorted(LAWS):
        acc, cacc = {}, {}
        lu = [u for u in us if u[1][0] == law]
        for res in REG.iter_units("x5", lu, work_unit, n_jobs=a.jobs):
            scen, ac, cc, h, dt = decode_unit(res)
            cpu += dt
            for k, v in ac.items():
                kk = scen + k
                cur = acc.setdefault(kk, [0] * len(v))
                for j in range(len(v)):
                    cur[j] += v[j]
            for k, v in cc.items():
                kk = scen + k
                cur = cacc.setdefault(kk, [0] * len(v))
                for j in range(len(v)):
                    cur[j] += v[j]
            for f, c in h.items():
                hc[f] = hc.get(f, 0) + c
        fr = frontier_rows(acc)
        del acc
        cr = contrast_rows(cacc, n)
        del cacc
        mr = matched_rows(fr)
        streams["frontier"].write(fr)
        streams["contrasts"].write(cr)
        streams["matched_ads"].write(mr)
        matched.update(matched_cells(cr, mr))
        if keep:
            rows.extend(fr)
            crows.extend(cr)
            mrows.extend(mr)
    for st in streams.values():
        st.close()
    REG.write_json(os.path.join(out, "matched_cells.json.gz" if REG.big() else "matched_cells.json"), matched)
    hcj = dict(pairs_checked=hc, total=xsum(hc.values()), violations=0,
               forms={"a": "B at h, T at h (maxseq on the dynamic portion; Kr = K)",
                      "a_k1": "B at h + 1, T at h (companion form, K = h + 1)",
                      "b": "B at h, T at h - 1 (companion form, K = h)", "unc": "uncapped"},
               caps=list(HULL_CAPS), menus=[list(m) for m in MENUS],
               law=("L2" if not REG.big(GRID_TIER) else "one-spot hybrid laws (L2 and H2 sets)"), n_per_scenario=n)
    REG.write_json(os.path.join(out, "hullchecks.json"), hcj)
    meta = dict(master=MASTER, tier=a.tier, n=n, chunk=chunk, menus=[list(m) for m in MENUS], caps=[_hl(h) for h in CAPS_ALL],
                h=[_hl(h) for h in HS], lams=list(LAMS), schemes=list(SCHEMES), variants=[list(v) for v in VARIANTS],
                anchors={"base": "c per ad", "A1": "2c per ad if filled seconds > 180 (synthetic)",
                         "A2": "1.5c per ad if the pod has both 15 s and 30 s (synthetic)"},
                c_grid_dollars=[float(c) / 100 for c in clutter.c_grid()], kpool=KPOOL,
                value_law="V1 " + pools.ValueLaw().key())
    REG.write_json(os.path.join(out, "x5_meta.json"), meta)
    if not REG.big(GRID_TIER):
        write_summary(out, rows, crows, mrows, matched, hcj, n)
    wall = time.time() - t0
    REG.write_timing(out, "x5_wall_s", wall)
    REG.write_timing(out, "x5_cpu_s", cpu)
    print("x5 done: n=%d per scenario, %d hull pairs checked, wall %.1f s, cpu %.1f s" % (n, hcj["total"], wall, cpu))


def _hk(h):
    """Sort key for caps with None (uncapped) last; same order as the plain integers when no cap is None."""
    return (h is None, h or 0)


def _hl(h):
    return "none" if h is None else h


def frontier_rows(acc):
    rows = []
    for key in sorted(acc, key=lambda k: (k[0], k[1], k[2], k[3], MENUS.index(k[4]), _hk(k[5]), ANCHORS.index(k[6]), k[7])):
        law, lam, sc, lv, menu, h, an, k = key
        s = acc[key]
        N = s[8]
        mu, seu = mean_se(s[0], s[1], N)
        ma, sea = mean_se(s[2], s[3], N)
        mn, sen = mean_se(s[4], s[5], N)
        lo, hi = wilson(s[7], N)
        conv = lv[-1]
        rows.append(dict(law=lv[:-1], conv=conv, lam=lam, scheme=sc, menu=mstr(menu), h=_hl(h), anchor=an, k=k,
                         c_dollars=float(clutter.c_grid()[k]) / 100, n=N, unfilled_s=mu, unfilled_se=seu,
                         ads=ma, ads_se=sea, revenue_dollars=s[6] / N / 100.0,
                         net_dollars=mn / (SCALE * 100.0), net_se=sen / (SCALE * 100.0),
                         p_unfilled=s[7] / N, p_lo=lo, p_hi=hi))
    return rows


def contrast_rows(cacc, n):
    rows = []
    for key in sorted(cacc, key=lambda k: (k[0], k[1], k[2], k[3], k[4], _hk(k[5]), MENUS.index(k[6]), ANCHORS.index(k[7]), k[8])):
        law, lam, sc, lv, cname, h, mx, an, k = key
        s = cacc[key]
        du, sdu = mean_se(s[0], s[1], n)
        da, sda = mean_se(s[2], s[3], n)
        dn, sdn = mean_se(s[4], s[5], n)
        rows.append(dict(law=lv[:-1], conv=lv[-1], lam=lam, scheme=sc, contrast=cname, h=_hl(h), menu=mstr(mx), anchor=an,
                         k=k, c_dollars=float(clutter.c_grid()[k]) / 100, d_unfilled=du, d_unfilled_se=sdu,
                         d_ads=da, d_ads_se=sda, d_net_dollars=dn / (SCALE * 100.0),
                         d_net_se=sdn / (SCALE * 100.0)))
    return rows


def _interp(pts, A):
    """Piecewise-linear U at ads A on a frontier [(ads, U)] (any order); None outside the ads range."""
    pts = sorted(set(pts))
    if A < pts[0][0] - 1e-12 or A > pts[-1][0] + 1e-12:
        return None
    for (a1, u1), (a2, u2) in zip(pts, pts[1:]):
        if a1 - 1e-12 <= A <= a2 + 1e-12:
            if a2 - a1 < 1e-12:
                return min(u1, u2)
            return u1 + (u2 - u1) * (A - a1) / (a2 - a1)
    return pts[-1][1]


def matched_rows(rows):
    """Frontier comparison at matched ads per break: for menu M at cap h and each c point (ads, U), the {15,30}
    frontier at cap h + 1 interpolated at the same mean ads. Negative d_unfilled: M fills more per ad."""
    idx = {}
    for r in rows:
        idx.setdefault((r["law"], r["conv"], r["lam"], r["scheme"], r["menu"], r["h"], r["anchor"]), []).append(r)
    out = []
    for (law, conv, lam, sc, menu, h, an), rs in sorted(idx.items(), key=lambda kv: kv[0][:5] + ((kv[0][5] == "none",
                                                                                                    kv[0][5] if kv[0][5] != "none" else 0),) + kv[0][6:]):
        if menu == mstr(BASE) or (None if h == "none" else h) not in HS:
            continue
        refs = ((h, "base_same_h"),) if h == "none" else ((h + 1, "base_h_plus_one"), (h, "base_same_h"))
        for ref_h, tag in refs:
            ref = idx.get((law, conv, lam, sc, mstr(BASE), ref_h, an))
            pts = [(x["ads"], x["unfilled_s"]) for x in ref]
            for r in sorted(rs, key=lambda x: x["k"]):
                u = _interp(pts, r["ads"])
                out.append(dict(law=law, conv=conv, lam=lam, scheme=sc, menu=menu, h=h, anchor=an, ref=tag, k=r["k"],
                                ads=r["ads"], unfilled_s=r["unfilled_s"], ref_unfilled_at_ads=u,
                                d_unfilled=None if u is None else r["unfilled_s"] - u))
    return out


def matched_cells(crows, mrows):
    """Shorter-duration menu M at cap h against {15,30} at cap h + 1, per (law, conv, lam, scheme, menu, h,
    anchor), written to matched_cells.json: over the 13 c points, in how many
    does M at h have (i) higher seller net value than {15,30} at h + 1 by more than 2 paired SE, (ii) lower by
    more than 2 SE, and (iii) fewer unfilled seconds at matched ads (frontier below)."""
    out = {}
    for r in crows:
        if r["contrast"] != "menu_vs_base_h_plus_one":
            continue
        key = "|".join(str(x) for x in (r["law"] + r["conv"], r["lam"], r["scheme"], r["menu"], r["h"], r["anchor"]))
        d = out.setdefault(key, dict(net_win=0, net_loss=0, net_tie=0, fill_win=0, fill_loss=0, frontier_below=0,
                                     frontier_above=0, frontier_na=0, k_points=0))
        d["k_points"] += 1
        se = r["d_net_se"]
        if r["d_net_dollars"] > 2 * se and r["d_net_dollars"] > 1e-12:
            d["net_win"] += 1
        elif r["d_net_dollars"] < -2 * se and r["d_net_dollars"] < -1e-12:
            d["net_loss"] += 1
        else:
            d["net_tie"] += 1
        if r["d_unfilled"] < -2 * r["d_unfilled_se"] and r["d_unfilled"] < -1e-12:
            d["fill_win"] += 1
        elif r["d_unfilled"] > 2 * r["d_unfilled_se"] and r["d_unfilled"] > 1e-12:
            d["fill_loss"] += 1
    for r in mrows:
        if r["ref"] != "base_h_plus_one":
            continue
        key = "|".join(str(x) for x in (r["law"] + r["conv"], r["lam"], r["scheme"], r["menu"], r["h"], r["anchor"]))
        d = out[key]
        if r["d_unfilled"] is None:
            d["frontier_na"] += 1
        elif r["d_unfilled"] < -1e-9:
            d["frontier_below"] += 1
        elif r["d_unfilled"] > 1e-9:
            d["frontier_above"] += 1
    return out


def _f(x, d=2):
    return "n/a" if x is None or x == "" else ("%." + str(d) + "f") % x


def write_summary(out, rows, crows, mrows, matched, hcj, n):
    F = {}
    for r in rows:
        F[(r["law"], r["conv"], r["lam"], r["scheme"], r["menu"], r["h"], r["anchor"], r["k"])] = r
    C = {}
    for r in crows:
        C[(r["law"], r["conv"], r["lam"], r["scheme"], r["contrast"], r["h"], r["menu"], r["anchor"], r["k"])] = r
    L = []
    L.append("# X5: clutter frontier of unfilled seconds against ads per break")
    L.append("")
    L.append("Regenerate: `python3 code/run_x5.py --tier narrow --jobs 2` (master seed `%s`, %d breaks per scenario, "
             "common random numbers across every menu, cap, convention, clutter cost and anchor). Tables in this "
             "folder: `frontier.csv` (one row per scenario, menu, cap, anchor and cost), `contrasts.csv` (paired "
             "differences with paired standard errors), `matched_ads.csv` (frontiers compared at equal ads per "
             "break), `matched_cells.json`, `hullchecks.json`, `x5_meta.json`. Everything here is SYNTHETIC: Poisson "
             "pools, value law V1 (lognormal per-second value, median 30 s CPM $20), and the clutter cost and "
             "anchors are modeling choices." % (MASTER, n))
    L.append("")
    L.append("Model. For each break, V_T(n) is the best revenue of exactly n distinct creatives fitting T seconds "
             "(at most the dynamic cap), H_T its concave hull (knapsack companion, Section 2), and the seller picks "
             "argmax_n H_T(n) - c n, attained at a hull vertex (ties to fewer ads). c runs from $0 to $20 of CPM per "
             "ad (the median bid of a 30 s ad) in 12 steps. Ads per break is an outcome of pod construction; no "
             "result conditions on it (DAI timing companion, Section IV-B). Laws: L2 (T = B - S, B on the 30 s grid 60 to 240, S "
             "uniform on {5, 10, 15, 20, 45}) under conventions a (maxseq on the dynamic portion) and b (structured "
             "spot counts toward maxseq, remainder gets h - 1), and L3u (uniform integers 60 to 240).")
    L.append("")
    L.append("Anchors (qualitative, FreeWheel Viewer Experience Lab with MediaScience, Designing a Better Ad Pod, "
             "January 2024): A1 doubles the per-ad cost when the pod runs past "
             "180 s (\"intrusiveness doubles at three minutes\"); A2 raises it by half when a pod mixes 15 s and 30 s "
             "creatives (\"mixed pods seemed longer to over half\"). Both multipliers are SYNTHETIC readings of "
             "qualitative findings.")
    L.append("")
    # headline frontier table
    for law, conv in VARIANTS:
        for lam, sc in ((64, "balanced"), (16, "d1530")):
            L.append("## Frontier, %s%s, lambda %d, %s, cap h = 8, base clutter cost"
                     % (law, " convention " + conv if law == "L2" else "", lam, pools.SCHEME_LABEL[sc]))
            L.append("")
            L.append("Each cell: mean unfilled seconds / mean ads per break at clutter cost c (dollars of CPM per ad).")
            L.append("")
            ks = (0, 3, 6, 9, 12)
            L.append("| Menu | " + " | ".join("c = $%s" % _f(float(clutter.c_grid()[k]) / 100, 2) for k in ks) + " |")
            L.append("| --- |" + " --- |" * len(ks))
            for m in MENUS:
                cells = []
                for k in ks:
                    r = F[(law, conv, lam, sc, mstr(m), 8, "base", k)]
                    cells.append("%s / %s" % (_f(r["unfilled_s"], 1), _f(r["ads"], 2)))
                L.append("| %s | %s |" % (mstr(m), " | ".join(cells)))
            r9 = [F[(law, conv, lam, sc, mstr(BASE), 9, "base", k)] for k in ks]
            L.append("| {15,30} at h = 9 | %s |" % " | ".join("%s / %s" % (_f(r["unfilled_s"], 1), _f(r["ads"], 2)) for r in r9))
            L.append("")
    # shorter duration at h against {15,30} at h + 1
    L.append("## A shorter duration at cap h against {15,30} at cap h + 1")
    L.append("")
    L.append("Per cell, over the 13 clutter costs: number of costs at which the menu at h earns more seller net "
             "value (revenue minus clutter cost) than {15,30} at h + 1 by more than two paired standard errors, "
             "the number where it earns less, then the number where its frontier lies below the {15,30}, h + 1 "
             "frontier at matched ads (fewer unfilled seconds for the same ads per break; n/a points outside the "
             "reference's ads range are not counted). Format: net wins-losses; frontier below-above.")
    L.append("")
    for an in ANCHORS:
        L.append("### Anchor %s" % an)
        L.append("")
        hdr = ["Law", "lambda", "weights", "h"] + [mstr(m) for m in MENUS if m != BASE]
        L.append("| " + " | ".join(hdr) + " |")
        L.append("|" + " --- |" * len(hdr))
        for law, conv in VARIANTS:
            for lam in LAMS:
                for sc in SCHEMES:
                    for h in HS:
                        cells = []
                        for m in MENUS:
                            if m == BASE:
                                continue
                            key = "|".join(str(x) for x in (law + conv, lam, sc, mstr(m), h, an))
                            d = matched[key]
                            cells.append("%d-%d; %d-%d" % (d["net_win"], d["net_loss"], d["frontier_below"],
                                                           d["frontier_above"]))
                        L.append("| %s | %d | %s | %d | %s |" % (law + conv, lam, pools.SCHEME_LABEL[sc], h,
                                                                  " | ".join(cells)))
        L.append("")
    # aggregate counts of that comparison
    tot = {}
    for key, d in matched.items():
        parts = key.split("|")
        an = parts[5]
        t = tot.setdefault(an, [0, 0, 0, 0, 0])
        t[0] += 1
        t[1] += 1 if d["net_win"] > 0 else 0
        t[2] += 1 if d["net_loss"] == 0 and d["net_win"] > 0 else 0
        t[3] += 1 if d["frontier_below"] > 0 else 0
        t[4] += 1 if d["net_win"] == 0 else 0
    L.append("### Counts over cells (law, lambda, weights, h, menu)")
    L.append("")
    L.append("| Anchor | Cells | Wins at some c | Wins at some c, never loses | Frontier below at some c | Never wins |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for an in ANCHORS:
        t = tot[an]
        L.append("| %s | %d | %d | %d | %d | %d |" % (an, t[0], t[1], t[2], t[3], t[4]))
    L.append("")
    # cap +1 for base
    L.append("## Value of h + 1 for {15,30} (paired, base cost)")
    L.append("")
    L.append("Paired difference {15,30} at h + 1 minus at h: unfilled seconds (SE), ads, seller net value in dollars "
             "of CPM (SE), at c = $0 and c = $10.")
    L.append("")
    L.append("| Law | lambda | weights | h | dU c=0 | dNet c=0 | dU c=$10 | dNet c=$10 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for law, conv in VARIANTS:
        for lam in LAMS:
            for sc in SCHEMES:
                for h in HS:
                    a0 = C[(law, conv, lam, sc, "cap_plus_one", h, mstr(BASE), "base", 0)]
                    a6 = C[(law, conv, lam, sc, "cap_plus_one", h, mstr(BASE), "base", 6)]
                    L.append("| %s | %d | %s | %d | %s (%s) | %s (%s) | %s (%s) | %s (%s) |" % (
                        law + conv, lam, pools.SCHEME_LABEL[sc], h, _f(a0["d_unfilled"]), _f(a0["d_unfilled_se"]),
                        _f(a0["d_net_dollars"]), _f(a0["d_net_se"]), _f(a6["d_unfilled"]), _f(a6["d_unfilled_se"]),
                        _f(a6["d_net_dollars"]), _f(a6["d_net_se"])))
    L.append("")
    # regime tallies for short-duration menus (exclude {15,30,60}, which adds a longer part)
    L.append("### Short-duration menus by weight scheme ({10,15,30}, {6,15,30}, {10,15,20,30})")
    L.append("")
    L.append("Cells where the short-duration menu at h lies below the {15,30}, h + 1 frontier at matched ads for "
             "more clutter costs than it lies above, and cells where it earns more net value at some cost.")
    L.append("")
    L.append("| Anchor | Weights | Cells | Frontier below at most costs | Frontier below at some cost | Net win at some cost |")
    L.append("| --- | --- | --- | --- | --- | --- |")
    for an in ANCHORS:
        for sc in SCHEMES:
            c = [0, 0, 0, 0]
            for key, d in matched.items():
                p = key.split("|")
                if p[5] != an or p[2] != sc or p[3] == mstr((15, 30, 60)):
                    continue
                c[0] += 1
                c[1] += 1 if d["frontier_below"] > d["frontier_above"] else 0
                c[2] += 1 if d["frontier_below"] > 0 else 0
                c[3] += 1 if d["net_win"] > 0 else 0
            L.append("| %s | %s | %d | %d | %d | %d |" % (an, pools.SCHEME_LABEL[sc], c[0], c[1], c[2], c[3]))
    L.append("")
    L.append("Reading. The net-value contrast is not a pure arithmetic effect: lambda counts creatives over all eight "
             "durations, so under balanced weights a menu with an extra duration also sees more creatives (more "
             "demand). The matched-ads frontier comparison is the cleaner comparison: it asks whether, for the same "
             "clutter (ads per break), the shorter duration leaves fewer seconds unsold than one more slot does. "
             "Under the 15/30-dominant weights the extra duration adds few creatives, so that comparison is close "
             "to arithmetic alone.")
    L.append("")
    L.append("Tier note: the full tier runs 31 menus (the study menus and a fixed-seed sample), every built "
             "law, caps 3 to 12 and uncapped, at 2,000 breaks per cell; the narrow and quick tiers run smaller grids.")
    L.append("")
    L.append("## Hull-pair consistency checks (knapsack companion)")
    L.append("")
    pc = hcj["pairs_checked"]
    L.append("Every L2 break gives one pool at two capacities, the full break B and the remainder T = B - S. For "
             "each menu and nominal cap in %s, the hull pair (H_B, H_T) was checked against the knapsack companion's necessary "
             "conditions (dimension, dominance, (1), (2), (3) with their antecedents; capped rows in the form of "
             "the companion's exact obstruction checker) in four forms: b (B at h, T at h - 1, the companion's convention), a_k1 "
             "(B at h + 1, T at h: convention a as a companion instance with K = h + 1), a (B and T both at h), and "
             "uncapped. Pairs checked: %s; total %d; violations %d. A violation would stop the run. The checker "
             "re-implements the conditions from their statements and imports no companion code; it agrees with the "
             "companion's own `linear_violations` (uncapped) and `obstruction` (capped) on 40,000 random integer target "
             "pairs (a comparison that needs the companion's code and is not part of this release)."
             % (", ".join(str(h) for h in hcj["caps"]), ", ".join("%s %d" % (k, pc[k]) for k in sorted(pc)),
                hcj["total"], hcj["violations"]))
    L.append("")
    REG.write_text(os.path.join(out, "summary.md"), "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
