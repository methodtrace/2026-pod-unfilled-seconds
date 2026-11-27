"""Exact pod construction for a finite pool of distinct creatives.

Units and value law:
- A creative has an integer duration (seconds), an integer per-second value v in hundredths of a dollar
  of CPM per second (the unit of OpenRTB mincpmpersec, scaled by 100 so all arithmetic is exact), and a
  readiness uniform u in [0, 1) used only after selection.
- Its bid (CPM, in hundredths of a dollar) is v * duration. Pod revenue is the sum of bids of the
  selected creatives (per thousand pod impressions). Equivalently a 30-second-equivalent CPM of 30 v.
- Floor: a creative with v below mincpmpersec is removed before pod construction (pools.py).

Problem: choose distinct creatives, at most `cap` of them (None = no cap), total duration <= T.
Policies: "seconds" maximizes filled seconds, ties broken by revenue; "revenue" maximizes revenue,
ties broken by filled seconds. Further ties are broken deterministically by enumeration order.

Methods. dp_select() is the exact dynamic program over (seconds used, ads used) on distinct
creatives that defines the pod problem; it is the reference. select_menu() is a faster exact method used in
production runs, checked against dp_select() and against subset enumeration in the tests:
for any objective that is increasing in revenue for fixed counts, the best pod with
c_a creatives of duration a uses the c_a highest bids of that duration. So it suffices to enumerate
count vectors (c_a). Moreover, given the counts of all durations but the smallest, raising the count
of the smallest duration as far as feasible increases both seconds and revenue (bids are positive),
so only that maximal value is enumerated. pod_oracle() checks this against subset enumeration.

Arithmetic relaxation ("elastic" pool): every creative of the pool may run at any integer duration in
[m, M] = [min A, max A], with bid v * (chosen duration). This is a modeling choice used by the pod checks and
the tick study (DESIGN.md); the structural split uses the range of lengths at unlimited demand instead.
"""
from itertools import combinations, product
from .numeric import xsum


class Creative(object):
    __slots__ = ("dur", "v", "u", "ident")

    def __init__(self, dur, v, u=0.0, ident=None):
        self.dur, self.v, self.u, self.ident = dur, v, u, ident

    @property
    def bid(self):
        return self.v * self.dur

    def __repr__(self):
        return "Creative(%d, %d, %.3f, %r)" % (self.dur, self.v, self.u, self.ident)


class Pod(object):
    """Selected creatives with the duration each runs at (equal to its own except in elastic pools)."""
    __slots__ = ("seconds", "revenue", "items")

    def __init__(self, seconds, revenue, items):
        self.seconds, self.revenue, self.items = seconds, revenue, items  # items: [(creative, run_dur)]

    def ready_seconds(self, rho):
        if rho >= 1:
            return self.seconds
        return xsum(d for c, d in self.items if c.u < rho)

    def ready_revenue(self, rho):
        if rho >= 1:
            return self.revenue
        return xsum(c.v * d for c, d in self.items if c.u < rho)

    @property
    def n_ads(self):
        return len(self.items)


def _pools_by_duration(pool):
    by = {}
    for c in pool:
        by.setdefault(c.dur, []).append(c)
    for a in by:
        by[a].sort(key=lambda c: -c.bid)  # stable: equal bids keep pool order
    return by


def select_menu(T, cap, pool, menu=None):
    """Both policies on a menu pool. pool: list of Creative (durations in the menu), or a dict
    {duration: list sorted by bid descending}. Returns (pod_seconds_policy, pod_revenue_policy)."""
    by = pool if isinstance(pool, dict) else _pools_by_duration(pool)
    durs = sorted((a for a in by if by[a] and a <= T), reverse=True)
    hcap = 10 ** 9 if cap is None else cap
    if not durs or hcap <= 0 or T <= 0:
        return Pod(0, 0, []), Pod(0, 0, [])
    pref = {}
    kmax = {}
    for a in durs:
        k = min(len(by[a]), T // a, hcap)
        kmax[a] = k
        p = [0]
        for c in by[a][:k]:
            p.append(p[-1] + c.bid)
        pref[a] = p
    last = durs[-1]
    head = durs[:-1]
    best_s = None  # (seconds, revenue, counts)
    best_r = None
    counts = [0] * len(head)

    def rec(i, sec, n, rev):
        nonlocal best_s, best_r
        if i == len(head):
            c = min(kmax[last], (T - sec) // last, hcap - n)
            s2 = sec + c * last
            r2 = rev + pref[last][c]
            key_s = (s2, r2)
            key_r = (r2, s2)
            if best_s is None or key_s > best_s[0]:
                best_s = (key_s, tuple(counts) + (c,))
            if best_r is None or key_r > best_r[0]:
                best_r = (key_r, tuple(counts) + (c,))
            return
        a = head[i]
        top = min(kmax[a], (T - sec) // a, hcap - n)
        for c in range(top, -1, -1):
            counts[i] = c
            rec(i + 1, sec + c * a, n + c, rev + pref[a][c])
        counts[i] = 0

    rec(0, 0, 0, 0)

    def build(entry):
        (k1, k2), cs = entry
        items = []
        for a, c in zip(durs, cs):
            items.extend((cr, a) for cr in by[a][:c])
        sec = xsum(d for _, d in items)
        rev = xsum(cr.bid for cr, _ in items)
        return Pod(sec, rev, items)

    return build(best_s), build(best_r)


def select_elastic(T, cap, pool, m, M):
    """Both policies when each creative may run at any integer duration in [m, M] (arithmetic
    relaxation). pool: list of Creative (their own durations are ignored), or a list already sorted by
    v descending. Returns (pod_seconds_policy, pod_revenue_policy)."""
    cr = sorted(pool, key=lambda c: -c.v)
    K = len(cr) if cap is None else min(cap, len(cr))
    K = min(K, T // m) if m > 0 else K
    span = M - m
    pv = [0]
    for c in cr[:K]:
        pv.append(pv[-1] + c.v)
    best_s = (0, 0, 0)  # (seconds, revenue, k)
    best_r = (0, 0, 0)
    for k in range(1, K + 1):
        s = min(T, k * M)
        if s < k * m:
            break
        extra = s - k * m
        full = extra // span if span else 0
        rem = extra - full * span if span else 0
        rev = m * pv[k] + span * pv[full] + (rem * cr[full].v if rem else 0)
        if (s, rev) > best_s[:2]:
            best_s = (s, rev, k)
        if (rev, s) > (best_r[1], best_r[0]):
            best_r = (s, rev, k)

    def build(entry):
        s, rev, k = entry
        if k == 0:
            return Pod(0, 0, [])
        extra = s - k * m
        items = []
        for c in cr[:k]:
            add = min(span, extra)
            extra -= add
            items.append((c, m + add))
        return Pod(s, rev, items)

    return build(best_s), build(best_r)


# ------------------------------------------------------------------------------- reference DP

NEG = float("-inf")


def dp_select(T, cap, pool, elastic=None):
    """Exact DP over (seconds used, ads used): R[k][s] = best revenue of a set of exactly k distinct
    creatives with total duration exactly s. elastic=(m, M) lets each creative take any integer
    duration in [m, M] (arithmetic relaxation). Returns ((s, r) seconds policy, (r, s) revenue policy).
    No pool reduction: every creative is an item, so this is also a check of the reduction used by
    select_menu()."""
    K = len(pool) if cap is None else min(cap, len(pool))
    R = [[NEG] * (T + 1) for _ in range(K + 1)]
    R[0][0] = 0
    for c in pool:
        opts = [c.dur] if elastic is None else list(range(elastic[0], elastic[1] + 1))
        for k in range(K - 1, -1, -1):
            row, nxt = R[k], R[k + 1]
            for s in range(T, -1, -1):
                base = row[s]
                if base == NEG:
                    continue
                for d in opts:
                    s2 = s + d
                    if s2 <= T:
                        v = base + c.v * d
                        if v > nxt[s2]:
                            nxt[s2] = v
    best_s = (0, 0)
    best_r = (0, 0)
    for k in range(K + 1):
        for s in range(T + 1):
            r = R[k][s]
            if r == NEG:
                continue
            best_s = max(best_s, (s, r))
            best_r = max(best_r, (r, s))
    return best_s, best_r


# ---------------------------------------------------------------------------------------- oracles

def pod_oracle(T, cap, pool):
    """Brute force over all subsets of distinct creatives. Returns ((s, r) best for seconds policy,
    (r, s) best for revenue policy)."""
    hcap = len(pool) if cap is None else cap
    best_s = (0, 0)
    best_r = (0, 0)
    n = len(pool)
    for k in range(0, min(n, hcap) + 1):
        for sub in combinations(pool, k):
            s = xsum(c.dur for c in sub)
            if s > T:
                continue
            r = xsum(c.bid for c in sub)
            best_s = max(best_s, (s, r))
            best_r = max(best_r, (r, s))
    return best_s, best_r


def elastic_oracle(T, cap, pool, m, M):
    """Brute force for the elastic pool: every subset and every duration assignment in [m, M]."""
    hcap = len(pool) if cap is None else cap
    best_s = (0, 0)
    best_r = (0, 0)
    for k in range(0, min(len(pool), hcap) + 1):
        for sub in combinations(pool, k):
            for ds in product(range(m, M + 1), repeat=k):
                s = xsum(ds)
                if s > T:
                    continue
                r = xsum(c.v * d for c, d in zip(sub, ds))
                best_s = max(best_s, (s, r))
                best_r = max(best_r, (r, s))
    return best_s, best_r
