"""X5 clutter envelope (knapsack companion, Section 2): value-cardinality hulls of one creative pool and the
seller's optimum under a per-ad clutter cost.

Definitions (knapsack companion, hull notation, read for a pod):
  V_C(n)  best revenue of a set of exactly n distinct creatives whose durations sum to at most C seconds
          (undefined when no n-set fits; feasible counts are downward closed). Ties among n-sets of equal
          revenue are broken by more filled seconds, then by enumeration order.
  b       the first count maximizing V_C (with a cap h, over n <= h).
  H_C     the least concave majorant of (n, V_C(n)) on 0..b; strictly increasing, H_C(0) = 0, exact
          Fractions between vertices. Vertices are the counts where the slope changes, plus b
          (the knapsack companion's positive vertices).
  Seller optimum for a per-ad clutter cost c >= 0: max_n H_C(n) - c n. The maximum is attained at a hull
  vertex, where H_C = V_C and an attaining pod exists; for c >= 0 it equals max_n V_C(n) - c n over every
  feasible n <= h, because counts above b are dominated. Ties in net value (c equal to a hull slope) go to
  the smaller count: the seller adds no clutter for zero net gain.

Units: revenue in cents of CPM per pod (pod.py); c in cents of CPM per ad. The c grid is
c_k = k * CMAX / K_STEPS, k = 0..K_STEPS, with CMAX the median 30-second CPM of value law V1 ($20 = 2000
cents). Net values are compared exactly as K_STEPS * V(n) - k * CMAX * n (integers).

Reduction used by best_by_count(): for a fixed count vector (c_a) the best set takes the c_a highest bids of
each duration (same argument as pod.select_menu), so it suffices to enumerate count vectors with
c_a <= n_a and sum c_a a <= C. One enumeration serves several capacities (the full break B and the
remainder T = B - S share the pool). Checked against subset enumeration in tests/test_x5.py.
"""
from fractions import Fraction

CMAX = 2000          # cents of CPM per ad: median 30 s CPM of V1 (pools.ValueLaw defaults)
K_STEPS = 12         # c from 0 to CMAX in 12 equal steps (13 grid points)


def c_grid():
    return [Fraction(k * CMAX, K_STEPS) for k in range(K_STEPS + 1)]


def by_duration(pool, menu, C):
    """{a: [bids sorted descending]} for durations in the menu that fit in C seconds."""
    out = {}
    for cr in pool:
        if cr.dur in menu and cr.dur <= C:
            out.setdefault(cr.dur, []).append(cr.bid)
    for a in out:
        out[a].sort(reverse=True)
    return out


def best_by_count(bids, caps_C, nmax=None):
    """For each capacity C in caps_C (seconds): list best[n] = (revenue, seconds, counts) of the best n-set
    with total duration <= C, n = 0..(largest feasible count, at most nmax); counts is a tuple aligned with
    sorted(bids). bids: {duration: bids sorted descending}. Returns {C: list}."""
    durs = sorted(bids)
    Cmax = max(caps_C)
    caps_sorted = sorted(set(caps_C))
    pref = []
    tops = []
    for a in durs:
        p = [0]
        for x in bids[a]:
            p.append(p[-1] + x)
        pref.append(p)
        tops.append(len(bids[a]))
    best = {C: {} for C in caps_sorted}
    nlim = 10 ** 9 if nmax is None else nmax
    counts = [0] * len(durs)
    L = len(durs)

    def leaf(sec, n, rev):
        key = (rev, sec)
        for C in caps_sorted:
            if sec <= C:
                cur = best[C].get(n)
                if cur is None or key > cur[:2]:
                    best[C][n] = (rev, sec, tuple(counts))

    def rec(j, sec, n, rev):
        if j == L:
            leaf(sec, n, rev)
            return
        a = durs[j]
        top = min(tops[j], (Cmax - sec) // a, nlim - n)
        p = pref[j]
        for c in range(top + 1):
            counts[j] = c
            rec(j + 1, sec + c * a, n + c, rev + p[c])
        counts[j] = 0

    rec(0, 0, 0, 0)
    out = {}
    for C in caps_sorted:
        d = best[C]
        k = 0
        lst = []
        while k in d:
            lst.append(d[k])
            k += 1
        out[C] = lst
    return out, durs


def truncate(best, cap):
    """best[n] for n <= cap (cap None: all)."""
    return best if cap is None else best[:cap + 1]


def hull(values):
    """Concave hull of V(0..N) (integers or Fractions, V(0) = 0) in the knapsack companion's convention.
    Returns (b, H, verts): b the first maximizing count, H the tuple H(0..b) of Fractions, verts the
    positive vertices (slope changes and b), increasing."""
    M = max(values)
    b = values.index(M)
    pts = [(n, values[n]) for n in range(b + 1)]
    st = []
    for p in pts:
        while len(st) >= 2:
            (x1, y1), (x2, y2) = st[-2], st[-1]
            # remove st[-1] if it lies on or below the chord from st[-2] to p
            if (y2 - y1) * (p[0] - x1) <= (p[1] - y1) * (x2 - x1):
                st.pop()
            else:
                break
        st.append(p)
    H = [Fraction(0)] * (b + 1)
    for (x1, y1), (x2, y2) in zip(st, st[1:]):
        for n in range(x1, x2 + 1):
            H[n] = Fraction(y1) + Fraction(y2 - y1, x2 - x1) * (n - x1)
    if b == 0:
        H = [Fraction(values[0])]
    verts = [x for x, _ in st if x > 0]
    return b, tuple(H), verts


def hull_vertices(values):
    """Integer-only fast path of hull(): (b, verts) without building H (same chain, same vertices)."""
    M = max(values)
    b = values.index(M)
    st = []
    for x in range(b + 1):
        y = values[x]
        while len(st) >= 2:
            (x1, y1), (x2, y2) = st[-2], st[-1]
            if (y2 - y1) * (x - x1) <= (y - y1) * (x2 - x1):
                st.pop()
            else:
                break
        st.append((x, y))
    return b, [x for x, _ in st if x > 0]


def hull_verts(H):
    """Knapsack companion verts(): j >= 1 where the slope changes, or j = b (verify_certificates.verts)."""
    return [j for j in range(1, len(H)) if j == len(H) - 1 or H[j] - H[j - 1] != H[j + 1] - H[j]]


def seller_choice(best, verts, k):
    """Index n* of the seller optimum at c = c_k among hull vertices (and 0), ties to the smaller count."""
    bestn = 0
    bestv = 0
    for n in verts:
        v = K_STEPS * best[n][0] - k * CMAX * n
        if v > bestv:
            bestn, bestv = n, v
    return bestn


def frontier_points(best, cap, T):
    """For one target T and cap: per k in 0..K_STEPS, (unfilled seconds, ads, revenue, scaled net
    K_STEPS*rev - k*CMAX*ads, counts of the chosen pod). Also returns the hull (b, H, verts)."""
    bt = truncate(best, cap)
    vals = [x[0] for x in bt]
    b, H, verts = hull(vals)
    out = []
    for k in range(K_STEPS + 1):
        n = seller_choice(bt, verts, k)
        rev, sec, cnt = bt[n]
        out.append((T - sec, n, rev, K_STEPS * rev - k * CMAX * n, cnt))
    return out, (b, H, verts)
