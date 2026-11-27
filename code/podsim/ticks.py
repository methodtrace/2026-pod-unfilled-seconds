"""X7: integer seconds versus 90 kHz ticks.

Units: 1 s = 90,000 ticks (SCTE-35 / MPEG-TS presentation clock). A creative of nominal duration a s has
true duration 90,000 a + delta ticks. The break's dynamic target is T_ticks = 90,000 T + o with T from
the integer law and o uniform on {0, ..., 89,999} (a sub-second offset). A pod is accepted when its true
total is at most T_ticks + tol. Unfilled seconds U_tick = (T_ticks - filled ticks) / 90,000.

Perturbation models:
  sys+     systematic: every creative of every duration overruns by eps ticks (delta_a = +eps)
  sys-     systematic underrun (delta_a = -eps)
  ntsc     systematic, DERIVED (not sourced): a creative of nominal a s authored at 30 fps and played at
           30000/1001 fps (29.97) lasts a * 1001/1000 s, so delta_a = 90 a ticks (15 s -> 15.015 s,
           1,351,350 ticks; 30 s -> 30.03 s). For a = 45, 60 this exceeds one frame (3003 ticks).
  indep    independent per creative, delta uniform on the integers in [-eps, eps]
Pod construction: the seller maximizes true filled ticks; within a duration creatives are taken in bid
order (as in the integer model), so the perturbation does not steer which creative of a duration runs
(a modeling choice; DESIGN.md). Under the arithmetic relaxation an elastic creative running r s has
true length 90,000 r + its delta (for ntsc, 90,090 r).

Comparison with the integer model at the same break: Delta = U_tick - (U_int + o / 90,000), where U_int is
the integer-model unfilled seconds of the same pools; Delta isolates the effect of duration perturbation
and tolerance from the sub-second offset itself.
"""
import random
from fractions import Fraction

from . import structural
from .exact import TMAX as _TMAX

TPS = 90000


def delta_sys(model, eps, a):
    if model == "sys+":
        return eps
    if model == "sys-":
        return -eps
    if model == "ntsc":
        return 90 * a
    raise ValueError(model)


# ------------------------------------------------------------- exact, systematic, demand unlimited

def nmax_ads(amin, eps_neg, tol):
    """Largest number of creatives of length >= amin s (true length >= 90000 amin - eps_neg) that fit in
    the largest possible target 90000 * 241 + tol ticks."""
    return (TPS * (_TMAX + 1) + tol) // (TPS * amin - eps_neg)


def candidates_menu(menu, model, eps, tol):
    """{true filled ticks: least number of creatives} over all count vectors of the menu (demand unlimited,
    systematic model)."""
    durs = sorted(menu)
    dl = [delta_sys(model, eps, a) for a in durs]
    lim = TPS * (_TMAX + 1) + tol
    nmax = nmax_ads(durs[0], max(0, -min(dl)), tol)
    best = {}

    def rec(j, f, n):
        if j == len(durs):
            if best.get(f, 10 ** 9) > n:
                best[f] = n
            return
        step = TPS * durs[j] + dl[j]
        c = 0
        while f + c * step <= lim and n + c <= nmax:
            rec(j + 1, f + c * step, n + c)
            c += 1
    rec(0, 0, 0)
    return best


def candidates_elastic(menu, model, eps, tol):
    """Same for the arithmetic relaxation: k creatives, total r s in [k m, k M], true 90000 r + k delta
    (sys+/sys-) or 90090 r (ntsc)."""
    m, M = min(menu), max(menu)
    lim = TPS * (_TMAX + 1) + tol
    best = {}
    d = 0 if model == "ntsc" else delta_sys(model, eps, 0)
    nmax = nmax_ads(m, max(0, -d), tol)
    best[0] = 0
    for k in range(1, nmax + 1):
        for r in range(k * m, k * M + 1):
            f = (TPS + 90) * r if model == "ntsc" else TPS * r + k * d
            if f > lim:
                break
            if best.get(f, 10 ** 9) > k:
                best[f] = k
    return best


def exact_sys_unlimited(menu, model, eps, tol, law, caps, conv, arith=False, offset0=False):
    """Exact (E[U_tick], E[overrun]) in seconds (Fractions), demand unlimited, systematic model, for each
    nominal cap in caps (None = uncapped): average over the law's support and the uniform offset o, or, with
    offset0, at o = 0 (a break that is an exact whole number of seconds, as on a scheduled grid)."""
    from .laws import dynamic_cap
    best = candidates_elastic(menu, model, eps, tol) if arith else candidates_menu(menu, model, eps, tol)
    items = sorted(best.items())
    out = {}
    cache = {}
    for h in caps:
        tu = to = Fraction(0)
        for (T, st), w in law.support:
            k = dynamic_cap(h, st, conv)
            key = (T, k)
            if key not in cache:
                fs = [f for f, n in items if k is None or n <= k]
                cache[key] = unfilled_at_offset0(T, fs, tol) if offset0 else mean_unfilled_over_offset(T, fs, tol)
            tu += w * cache[key][0]
            to += w * cache[key][1]
        out[h] = (tu, to)
    return out


def unfilled_at_offset0(T, fs, tol):
    """(U, overrun) in seconds for a break of exactly 90000 T ticks: g = max{f in fs: f <= 90000 T + tol}."""
    import bisect
    base = TPS * T
    g = fs[bisect.bisect_right(fs, base + tol) - 1]
    return Fraction(max(0, base - g), TPS), Fraction(max(0, g - base), TPS)


def mean_unfilled_over_offset(T, fs, tol):
    """(E[U], E[overrun]) in seconds over o uniform in {0..89999}: U = max(0, 90000 T + o - g(o)) / 90000 and
    overrun = max(0, g(o) - 90000 T - o) / 90000, g(o) = max{f in fs: f <= 90000 T + o + tol}; fs sorted,
    contains 0. Overrun is positive only when tol > 0 (the pod runs past the break, inside the tolerance)."""
    import bisect
    base = TPS * T + tol
    i0 = bisect.bisect_right(fs, base) - 1
    cur = fs[i0]
    tu = to = 0
    o_prev = 0
    j = i0 + 1
    while j < len(fs) and fs[j] <= base + TPS - 1:
        o_f = fs[j] - base
        a, b = _sums(TPS * T - cur, o_prev, o_f - 1)
        tu += a
        to += b
        cur = fs[j]
        o_prev = o_f
        j += 1
    a, b = _sums(TPS * T - cur, o_prev, TPS - 1)
    tu += a
    to += b
    return Fraction(tu, TPS * TPS), Fraction(to, TPS * TPS)


def _ar(lo, hi, c):
    """sum_{o=lo}^{hi} (c + o)."""
    if hi < lo:
        return 0
    n = hi - lo + 1
    return n * c + (lo + hi) * n // 2


def _sums(c, o1, o2):
    """(sum max(0, c + o), sum max(0, -(c + o))) over o in [o1, o2]."""
    if o2 < o1:
        return 0, 0
    lo = max(o1, -c)
    pos = _ar(lo, o2, c)
    neg = -_ar(o1, min(o2, -c - 1), c)
    return pos, neg


# ------------------------------------------------------------------- Monte Carlo selection in ticks

def select_ticks(Tt, cap, by, durs):
    """Max true filled ticks. by: dict a -> list of true tick lengths in bid order (top creatives first).
    Enumerates count vectors over all but the smallest duration; for the smallest takes the largest
    feasible count (true lengths are positive, so filled ticks increase with it)."""
    durs = sorted((a for a in durs if by.get(a)), reverse=True)
    hcap = 10 ** 9 if cap is None else cap
    if not durs or hcap <= 0:
        return 0
    pre = {}
    for a in durs:
        p = [0]
        for x in by[a][:min(len(by[a]), hcap)]:
            p.append(p[-1] + x)
        pre[a] = p
    last = durs[-1]
    head = durs[:-1]
    lp = pre[last]
    best = 0
    stack = [(0, 0, 0)]

    def rec(i, t, n):
        nonlocal best
        if i == len(head):
            rem = Tt - t
            kmax = min(len(lp) - 1, hcap - n)
            # largest c with lp[c] <= rem (lp increasing)
            lo, hi = 0, kmax
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if lp[mid] <= rem:
                    lo = mid
                else:
                    hi = mid - 1
            v = t + lp[lo]
            if v > best:
                best = v
            return
        a = head[i]
        p = pre[a]
        top = min(len(p) - 1, hcap - n)
        for c in range(top, -1, -1):
            if t + p[c] > Tt:
                continue
            rec(i + 1, t + p[c], n + c)

    rec(0, 0, 0)
    return best


def select_ticks_elastic(Tt, cap, deltas, m, M, ntsc=False):
    """Elastic creatives (arithmetic relaxation) in ticks. deltas: per-creative deltas in value order.
    k creatives running total r seconds (k m <= r <= k M) have true length 90000 r + D_k (ntsc: 90090 r)."""
    K = len(deltas) if cap is None else min(cap, len(deltas))
    best = 0
    D = 0
    for k in range(1, K + 1):
        D += deltas[k - 1]
        if ntsc:
            r = min(k * M, Tt // (TPS + 90))
            f = (TPS + 90) * r
        else:
            r = min(k * M, (Tt - D) // TPS)
            f = TPS * r + D
        if r < k * m:
            continue
        if f > best:
            best = f
    return best


def tick_rng(master, i, a):
    return random.Random("%s|tick|%d|%d" % (master, i, a))
