"""Exact expectations for X1, X3 and the other exact tables (no Monte Carlo).

TMAX is the largest target in seconds (PODSIM_TMAX: 240 by default, 360 in the full tier).

Why this is exact. Under the seconds-max policy the filled seconds F of a pod depend only on the target T,
the cap and the per-duration counts n_a (capped at floor(TMAX / a), beyond which extra creatives cannot
change F for T <= TMAX); bids only break ties among pods with equal seconds. Readiness is drawn after
selection, independently with probability rho per selected creative, so E[U | T, pool] = T - rho F =
(1 - rho) T + rho (T - F). With n_a independent Poisson(lambda w_a), every expected unfilled-seconds quantity
and every part of the accounting identity (decompose.py, linear in these expectations) is an exact finite sum
over the truncated Poisson laws of the counts and the law of T.

Enumeration (MenuProfiles, the reference engine). For a menu, every count vector (c_a),
0 <= c_a <= floor(TMAX / a) (the top value meaning "at least"), is mapped to its reachability profile: for
each cap k in HS = 2..12 the bitset of totals in [0, TMAX] reachable with at most k distinct creatives under
the counts, and the uncapped bitset. Count vectors with the same profile are merged; each profile's
undershoot table is computed once. profile_dist() is the forward DP over durations used in runs; it takes
the largest cap H as an argument (HMAX2 = 14 by default), and callers pass larger values for larger caps.

Precision. The structural floor (demand unlimited) is exact in Fractions. Demand-limited expectations are
float sums of Poisson probabilities (double precision; truncation is exact by the "at least" top cell).
"""
import math
import os
from fractions import Fraction

from . import structural
from .laws import dynamic_cap
from .numeric import xsum

TMAX = int(os.environ.get("PODSIM_TMAX", "240"))
HS = tuple(range(2, 13))  # caps needed: 3..12, and 2 for convention b at h = 3
MASK = (1 << (TMAX + 1)) - 1


def poisson_trunc(mean, top):
    """[P(n = 0), ..., P(n = top - 1), P(n >= top)] for n ~ Poisson(mean). With top = 0 (a duration longer than the
    horizon) the single cell is "zero or more creatives" and carries mass one."""
    if top <= 0:
        return [1.0]
    if mean <= 0:
        return [1.0] + [0.0] * top
    p = [math.exp(-mean)]
    for k in range(1, top):
        p.append(p[-1] * mean / k)
    p.append(max(0.0, 1.0 - xsum(p)))
    return p


def nb_trunc(mean, k, top):
    """[P(n = 0), ..., P(n = top - 1), P(n >= top)] for n negative binomial with mean `mean` and dispersion k
    (variance mean + mean^2 / k; k -> infinity is Poisson): P(0) = p^k, P(n) = P(n - 1) (n - 1 + k) / n (1 - p),
    p = k / (k + mean)."""
    if k <= 0:
        raise ValueError("negative binomial dispersion must be positive, got %r" % (k,))
    if top <= 0:
        return [1.0]
    if mean <= 0:
        return [1.0] + [0.0] * top
    p = k / (k + mean)
    out = [p ** k]
    for n in range(1, top):
        out.append(out[-1] * (n - 1 + k) / n * (1 - p))
    out.append(max(0.0, 1.0 - xsum(out)))
    return out


class NegBinMeans(dict):
    """Per-duration means (a dict, as for Poisson pools) marked as negative binomial counts with dispersion
    k (catalog axis D4). A plain dict of means means Poisson counts; every exact routine accepts either."""

    def __init__(self, means, k):
        dict.__init__(self, means)
        if not k > 0:
            raise ValueError("negative binomial dispersion must be positive, got %r" % (k,))
        self.k = k

    def __reduce__(self):
        return (NegBinMeans, (dict(self), self.k))


def count_trunc(means, a, top):
    """Truncated count law of duration a under the demand scenario `means` (Poisson or NegBinMeans)."""
    if isinstance(means, NegBinMeans):
        return nb_trunc(means[a], means.k, top)
    return poisson_trunc(means[a], top)


def total_trunc(means, menu, top):
    """Truncated law of the total count sum_{a in menu} n_a (top cell: at least top). Poisson: the sum is
    Poisson. Negative binomial with unequal means: exact convolution of the per-duration laws, each truncated
    at top (a component at least top forces the total to at least top, so the truncation is exact)."""
    if not isinstance(means, NegBinMeans):
        return poisson_trunc(xsum(means[a] for a in menu), top)
    acc = [1.0] + [0.0] * top
    for a in menu:
        pa = nb_trunc(means[a], means.k, top)
        new = [0.0] * (top + 1)
        for i, x in enumerate(acc):
            if x == 0.0:
                continue
            for j, y in enumerate(pa):
                new[min(top, i + j)] += x * y
        acc = new
    return acc


def last_below(bits):
    """Undershoot table [T - max{s <= T in bits}] for T = 0..TMAX (bits contains 0)."""
    out = []
    last = 0
    for T in range(TMAX + 1):
        if (bits >> T) & 1:
            last = T
        out.append(T - last)
    return out


class MenuProfiles(object):
    def __init__(self, menu):
        self.menu = tuple(sorted(menu))
        self.tops = [TMAX // a for a in self.menu]
        self.profile_of = {}   # count vector -> profile index
        self.tables = []       # per profile: {cap: undershoot table}, cap None = uncapped
        keys = {}
        H = max(HS)
        durs = self.menu

        def rec(j, E, Ua, counts):
            if j == len(durs):
                C = []
                acc = 0
                for k in range(H + 1):
                    acc |= E[k]
                    C.append(acc)
                key = (tuple(C[min(HS):]), Ua)
                idx = keys.get(key)
                if idx is None:
                    idx = len(self.tables)
                    keys[key] = idx
                    tab = {h: last_below(C[h]) for h in HS}
                    tab[None] = last_below(Ua)
                    self.tables.append(tab)
                self.profile_of[tuple(counts)] = idx
                return
            a = durs[j]
            Ecur = list(E)
            Ucur = Ua
            for c in range(self.tops[j] + 1):
                if c > 0:
                    for k in range(H, c - 1, -1):
                        Ecur[k] |= (E[k - c] << (c * a)) & MASK
                    Ucur |= (Ua << (c * a)) & MASK
                rec(j + 1, list(Ecur), Ucur, counts + [c])

        rec(0, [1] + [0] * H, 1, [])

    def profile_probs(self, means):
        """Probability of each profile when the n_a are independent with the count law of `means` (Poisson, or
    negative binomial for NegBinMeans)."""
        pm = [count_trunc(means, a, top) for a, top in zip(self.menu, self.tops)]
        out = [0.0] * len(self.tables)
        for counts, idx in self.profile_of.items():
            p = 1.0
            for j, c in enumerate(counts):
                p *= pm[j][c]
                if p == 0.0:
                    break
            out[idx] += p
        return out


def elastic_U(T, K, m, M):
    """Unfilled seconds when at most K creatives each run any integer length in [m, M]: the structural floor of the
    range menu, D_K([m, M]; T) (unlimited supply at every length; used by the tests of pod.select_elastic)."""
    k = min(K, T // m)
    return T - (min(T, k * M) if k > 0 else 0)


def law_vector(law, h, conv):
    """[(T, weight, dynamic cap)] for a Law at nominal cap h under convention conv."""
    return [(T, w, dynamic_cap(h, st, conv)) for (T, st), w in law.support]


def combos_for(menu, law, conv, hs, means_list, prof=None):
    """Reference engine (per support point, enumeration of count vectors). For each nominal cap h in hs
    (None = uncapped) and each demand scenario in means_list (a dict duration -> Poisson mean, or None for
    demand unlimited): U[frozenset()] = E[U] of the actual pool at rho = 1 and the four structural values
    U[{dem}] = E[D_h(A)], U[{dem, cap}] = E[D_inf(A)], U[{arith, dem}] = E[D_h(R)], U[{arith, cap, dem}] =
    E[D_inf(R)] (R the range of lengths). Returns {(scenario index, h): dict(U=..., ET=E[T], P_struct_pos=...)}.
    Demand-unlimited values are exact Fractions; demand-limited ones are floats."""
    menu = tuple(sorted(menu))
    rng = structural.range_menu(menu)
    sup = law.support
    ET = xsum(w * T for (T, _), w in sup)

    def Dexp(A, h):
        return xsum((w * structural.D(A, dynamic_cap(h, st, conv), T) for (T, st), w in sup), Fraction(0))
    struct = {}
    for h in hs:
        struct[h] = dict(dem=Dexp(menu, h), demcap=Dexp(menu, None), ardem=Dexp(rng, h),
                         ardemcap=Dexp(rng, None), pos=_pos(menu, law, conv, h))
    need_dem = any(x is not None for x in means_list)
    avg = None
    if need_dem:
        prof = prof or MenuProfiles(menu)
        vecs = {h: [(T, float(w), c) for T, w, c in law_vector(law, h, conv)] for h in hs}
        # law-averaged undershoot per profile and cap, computed once per (menu, law, convention)
        avg = [{h: xsum(w * tab[c][T] for T, w, c in vecs[h]) for h in hs} for tab in prof.tables]
    out = {}
    for si, means in enumerate(means_list):
        if means is not None:
            pp = prof.profile_probs(means)
            live = [(i, p) for i, p in enumerate(pp) if p > 0.0]
        for h in hs:
            st = struct[h]
            d = {frozenset(["dem"]): st["dem"], frozenset(["dem", "cap"]): st["demcap"],
                 frozenset(["arith", "dem"]): st["ardem"], frozenset(["arith", "cap", "dem"]): st["ardemcap"]}
            d[frozenset()] = st["dem"] if means is None else xsum(p * avg[i][h] for i, p in live)
            out[(si, h)] = dict(U=d, ET=ET, P_struct_pos=st["pos"])
    return out


def _pos(menu, law, conv, h):
    """Exact P(U_struct > 0): probability that a break has any structural unfilled second."""
    return xsum((w for (T, st), w in law.support if structural.D(menu, dynamic_cap(h, st, conv), T) > 0),
               Fraction(0))


# ------------------------------------------------------------------ forward DP over durations (X2, X3b)

from operator import mul as _mul

HMAX2 = 14  # default largest cap of profile_dist: caps up to 12 plus 2 for the cap lever


def profile_dist(menu, means_list, H=HMAX2, prune=1e-15):
    """Distribution of reachability profiles under independent truncated counts (Poisson or negative
    binomial), for several demand scenarios at once, by a forward DP over durations that merges prefixes with
    identical state. State: (C_0..C_H, Ua) with C_k = totals in [0, TMAX] reachable with at most k distinct
    creatives and Ua the uncapped set. Returns (states, probs, pruned) where probs[i][s] is the probability of
    state i in scenario s and pruned[s] bounds the probability mass dropped (states whose probability is below
    `prune` in every scenario); the induced error on any expectation is at most TMAX * pruned[s] seconds."""
    menu = tuple(sorted(menu))
    S = len(means_list)
    start = (tuple([1] * (H + 1)), 1)
    states = {start: [1.0] * S}
    pruned = [0.0] * S
    for a in sorted(menu, reverse=True):
        top = TMAX // a
        pm = [count_trunc(means, a, top) for means in means_list]
        new = {}
        for (C, Ua), pr in states.items():
            Cc = list(C)
            Uc = Ua
            for c in range(top + 1):
                if c > 0:
                    sh = c * a
                    for k in range(H, c - 1, -1):
                        Cc[k] |= (C[k - c] << sh) & MASK
                    Uc |= (Ua << sh) & MASK
                key = (tuple(Cc), Uc)
                row = new.get(key)
                if row is None:
                    row = [0.0] * S
                    new[key] = row
                for s in range(S):
                    row[s] += pr[s] * pm[s][c]
        states = {}
        for k, row in new.items():
            if max(row) < prune:
                for s in range(S):
                    pruned[s] += row[s]
            else:
                states[k] = row
    keys = list(states)
    return keys, [states[k] for k in keys], pruned


_LB = {}


def last_below_memo(bits):
    t = _LB.get(bits)
    if t is None:
        t = last_below(bits)
        if len(_LB) < 400000:
            _LB[bits] = t
    return t


def law_weights(law, conv, h):
    """Dense weight vectors over T = 0..TMAX: (w by dynamic cap) as dict cap -> list."""
    out = {}
    for (T, st), w in law.support:
        c = dynamic_cap(h, st, conv)
        v = out.setdefault(c, [0.0] * (TMAX + 1))
        v[T] += float(w)
    return out


def expect_table(menu, law, conv, hs, means_list, keys_probs=None):
    """Fast equivalent of combos_for(...)[(s, h)]["U"][frozenset()] for demand-limited scenarios (means_list
    without None), caps hs (ints up to the H of the profile distribution, HMAX2 = 14 by default, or None).
    Returns dict (s, h) -> {'none': E[U]} at rho = 1, plus 'pruned'
    per scenario. Uncapped values use h = None."""
    menu = tuple(sorted(menu))
    keys, probs, pruned = keys_probs or profile_dist(menu, means_list)
    S = len(means_list)
    W = {h: law_weights(law, conv, h) for h in hs}
    out = {}
    acc = {(s, h): 0.0 for s in range(S) for h in hs}
    for (C, Ua), pr in zip(keys, probs):
        val = {}
        for h in hs:
            tot = 0.0
            for cap, wv in W[h].items():
                bits = Ua if cap is None else C[cap]
                tot += xsum(map(_mul, wv, last_below_memo(bits)))
            val[h] = tot
        for s in range(S):
            p = pr[s]
            if p:
                for h in hs:
                    acc[(s, h)] += p * val[h]
    for s in range(S):
        for h in hs:
            out[(s, h)] = {"none": acc[(s, h)]}
    out["pruned"] = pruned
    return out
