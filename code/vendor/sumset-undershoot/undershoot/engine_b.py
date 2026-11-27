"""Engine E-B (Apery). Minimum factorization length m(n) by dynamic programming over the given
generators, the Apery set of the homogenized semigroup S_A = <(1,a): a in A0> with respect to
(1,0) and (1,d), then hA0 and undershoot from the brief's Section 3 formulas.
Shares no code with engine_a or engine_c.

Bound used: every minimum-length representation of n uses at most d-1 parts other than d
(pigeonhole on prefix sums mod d: d such parts contain a subset summing to t*d with t < size,
and replacing it by t copies of d shortens the representation). So n >= (d-1)*a_{k-1} + d
forces a d in every minimum representation, m(n-d) = m(n) - 1, and n is not Apery.
"""

INF = float("inf")


def min_lengths(A0, N):
    gens = [a for a in A0 if a > 0]
    m = [INF] * (N + 1)
    m[0] = 0
    for n in range(1, N + 1):
        best = INF
        for a in gens:
            if a <= n:
                v = m[n - a]
                if v < best:
                    best = v
        m[n] = best + 1
    return m


def apery_bound(A0):
    gens = sorted(a for a in A0 if a > 0)
    d = gens[-1]
    second = gens[-2] if len(gens) > 1 else 0
    return (d - 1) * second + d - 1


def apery(A0):
    """Apery set as sorted list of (h, n)."""
    d = max(A0)
    N = apery_bound(A0)
    m = min_lengths(A0, N)
    ap = []
    for n in range(N + 1):
        if m[n] == INF:
            continue
        if n < d or m[n - d] == INF or m[n - d] >= m[n]:
            ap.append((m[n], n))
    return sorted(ap)


def is_cm(A0, ap=None):
    ap = apery(A0) if ap is None else ap
    return len(ap) == max(A0)


def sumset_series_from_apery(A0, H, ap=None):
    """Bitsets of hA0 for h = 0..H from hA0 = U_{(h',n') in Ap, h'<=h} {n' + j d: 0 <= j <= h-h'}."""
    d = max(A0)
    ap = apery(A0) if ap is None else ap
    by_h = {}
    for hh, n in ap:
        by_h.setdefault(hh, []).append(n)
    out = []
    cur = 0
    for h in range(H + 1):
        cur = cur | (cur << d)
        for n in by_h.get(h, []):
            cur |= 1 << n
        out.append(cur)
    return out


def undershoot_formula(A0, h, T, ap=None):
    """D_h(T) = T - max over Apery (h',n') with h'<=h, n'<=T of n' + d*min(h-h', floor((T-n')/d))."""
    d = max(A0)
    ap = apery(A0) if ap is None else ap
    best = -1
    for hh, n in ap:
        if hh <= h and n <= T:
            v = n + d * min(h - hh, (T - n) // d)
            if v > best:
                best = v
    return T - best
