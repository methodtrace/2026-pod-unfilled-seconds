"""Range lever at finite demand as eligibility: rqddurs -> minduration/maxduration = [min A, max A].

What the switch does in the auction. A creative is a file of fixed length. Listing the exact menu A in rqddurs
admits only creatives whose length is in A; a duration range admits every creative whose length lies in
[min A, max A]. Nothing stretches or shrinks. So the lever's gain at finite demand is the fill added by the
creatives of the other lengths in the range that already exist in buyers' inventories.

Supply of those creatives (declared scenario plus a sweep). Lengths in the union {5, 6, 10, 15, 20, 30, 45, 60}
keep their scheme means lambda w_a, the same creatives the added-duration lever admits one length at a time.
Every other integer length in [5, 60] (48 lengths) is a nonstandard creative with mean eps lambda / 48, the same
for every such length and for every menu, so the supply does not depend on the menu (common random numbers
across menus, as for the union). Wurl (2021) reports that lengths other than about 15 s and 30 s almost never
occur on its platform, so the declared
scenario is eps = 0.01 (one creative in a hundred is nonstandard, spread over 48 lengths); the sweep is
eps in {0, 0.01, 0.05, 0.2}. eps = 0 admits only the union lengths in the range. Synthetic values, no source
for the levels.

Method (sampled, standard errors). Under the seconds-max policy the fill depends only on the per-length counts,
so a sample is one count vector over all 56 lengths in [5, 60]; the expectation over the break law is exact for
each sample (reachable sets with at most k creatives, dotted with the law's weights). Count of length d in sample i
is the inverse CDF of one uniform u(i, d) from random.Random("pods-range-v1|<i>") drawn for d = 5, ..., 60 in
order: the same uniforms for every menu, demand scenario, eps and cap, so every gain is a paired contrast
(baseline and range from the same counts) and scenarios are coupled monotonically. Counts are truncated at
floor(TMAX / d) (more creatives of a length cannot change any fill up to TMAX), which is exact. Returned per
cell: mean gain, its standard error over samples, and the sampled baseline E[U], whose agreement with the exact
baseline (levers.MenuExpect) checks the sampler. Rankings that involve the sampled gain treat levers within two
standard errors of the top as tied (numeric.nondominated, used by run_x2.best, run_x2_split and run_xd.top_label).
"""
import math
import random
from bisect import bisect_right
from operator import mul

from .exact import TMAX, MASK, count_trunc, last_below_memo, NegBinMeans
from .laws import dynamic_cap
from .levers import law_parts_by_count
from .numeric import xsum
from . import pools

MASTER = "pods-range-v1"
LENGTHS = tuple(range(5, 61))
OFF_UNION = tuple(d for d in LENGTHS if d not in pools.UNION)
EPS_DECLARED = 0.01
EPS_SWEEP = (0.0, 0.01, 0.05, 0.2)


def length_means(means, eps):
    """Per-length means over all 56 lengths for a scenario (means over the union) and nonstandard share eps.
    Keeps the count law of the scenario (Poisson dict or NegBinMeans with its dispersion)."""
    lam = xsum(means[a] for a in pools.UNION)
    off = eps * lam / len(OFF_UNION)
    out = {d: (means[d] if d in pools.UNION else off) for d in LENGTHS}
    if isinstance(means, NegBinMeans):
        return NegBinMeans(out, means.k)
    return out


def cdf_table(means, d):
    """Cumulative probabilities [P(n <= 0), ..., P(n <= top - 1)], top = TMAX // d; n = top means "at least top"."""
    top = TMAX // d
    p = count_trunc(means, d, top)
    out = []
    acc = 0.0
    for x in p[:top]:
        acc += x
        out.append(acc)
    return out


def add_length(C, Ua, d, c, H):
    """Reachability state after adding c creatives of length d: C[k] = totals in [0, TMAX] reachable with at most k
    creatives, Ua the uncapped set."""
    if c <= 0:
        return C, Ua
    Cn = list(C)
    for j in range(1, c + 1):
        sh = j * d
        for k in range(H, j - 1, -1):
            Cn[k] |= (C[k - j] << sh) & MASK
    U = Ua
    for j in range(1, c + 1):
        U |= (Ua << (j * d)) & MASK
    return Cn, U


class _Values(object):
    """E[U] over the break law for a reachability state, for every (law, conv, h) key at once. The law dot products
    sum_T w_n(T) (T - last reachable <= T) are memoized per reachable set, for every (law, structured count)."""

    def __init__(self, laws_dict, lawconvs, caps):
        parts = {name: law_parts_by_count(law) for name, law in laws_dict.items()}
        self.cols = sorted((name, n) for name in parts for n in parts[name])
        self.vecs = [parts[name][n] for name, n in self.cols]
        col = {c: j for j, c in enumerate(self.cols)}
        self.keys = [(nm, cv, h) for nm, cv in lawconvs for h in caps]
        # per key: [(cap, column index)]
        self.plan = [[(dynamic_cap(h, n, cv), col[(nm, n)]) for n in sorted(parts[nm])] for nm, cv, h in self.keys]
        self.caps = sorted({c for pl in self.plan for c, _ in pl if c is not None})
        self.H = max([1] + self.caps)
        self.memo = {}
        self.vmemo = {}
        # memo sizes bounded by stored floats (about 4 million each, under 0.3 GB per worker); results do not depend
        # on them
        self.memo_max = max(1000, 4000000 // max(1, len(self.vecs)))
        self.vmemo_max = max(100, 4000000 // max(1, len(self.keys)))

    def dots(self, bits):
        v = self.memo.get(bits)
        if v is None:
            lb = last_below_memo(bits)
            v = [xsum(map(mul, w, lb)) for w in self.vecs]
            if len(self.memo) < self.memo_max:
                self.memo[bits] = v
        return v

    def __call__(self, C, Ua):
        key = tuple(C[c] for c in self.caps) + (Ua,)
        r = self.vmemo.get(key)
        if r is not None:
            return r
        d = {c: self.dots(C[c]) for c in self.caps}
        d[None] = self.dots(Ua)
        r = []
        for pl in self.plan:
            if len(pl) == 1:
                c, j = pl[0]
                r.append(d[c][j])
            elif len(pl) == 2:
                (c1, j1), (c2, j2) = pl
                r.append(d[c1][j1] + d[c2][j2])  # correctly rounded, equal to fsum of two terms
            else:
                r.append(xsum(d[c][j] for c, j in pl))
        if len(self.vmemo) < self.vmemo_max:
            self.vmemo[key] = r
        return r


def range_gains(menu, laws_dict, lawconvs, caps, means_list, eps_list, n_samples, master=MASTER):
    """Sampled range-lever gains. Returns {(law, conv, h, s, eps): (mean gain, se, sampled baseline E[U], se of the
    sampled baseline)} for every law-convention pair, nominal cap h in caps (None = uncapped), scenario index s of
    means_list and eps in eps_list; seconds per break at rho = 1. The paired mean over samples; its standard error
    understates the error in cells whose loss comes from shortfalls rarer than about 1 / n_samples (a sample that
    never sees such a shortfall cannot estimate it), which the baseline check in the callers' metadata measures."""
    menu = tuple(sorted(menu))
    if any(a not in pools.UNION for a in menu):
        raise ValueError("menu %s has lengths outside the union %s, whose supply is not defined" % (menu, pools.UNION))
    m, M = min(menu), max(menu)
    extra_union = sorted((d for d in pools.UNION if m <= d <= M and d not in menu), reverse=True)
    extra_off = sorted((d for d in OFF_UNION if m <= d <= M), reverse=True)
    V = _Values(laws_dict, lawconvs, caps)
    H = V.H
    nk = len(V.keys)
    cdfs = []
    for means in means_list:
        row = {}
        for e in eps_list:
            lm = length_means(means, e)
            row[e] = {d: cdf_table(lm, d) for d in LENGTHS if d in menu or d in extra_union or d in extra_off}
        cdfs.append(row)
    S = len(means_list)
    sg = {(s, e): [0.0] * nk for s in range(S) for e in eps_list}
    sgg = {(s, e): [0.0] * nk for s in range(S) for e in eps_list}
    sb = [[0.0] * nk for _ in range(S)]
    sbb = [[0.0] * nk for _ in range(S)]
    zero = [1] * (H + 1)
    menu_desc = sorted(menu, reverse=True)
    for i in range(n_samples):
        rng = random.Random("%s|%d" % (master, i))
        u = {d: rng.random() for d in LENGTHS}
        for s in range(S):
            cd0 = cdfs[s][eps_list[0]]

            def cnt(cd, d):
                t = cd[d]
                return min(bisect_right(t, u[d]), len(t))
            C, Ua = zero, 1
            for a in menu_desc:
                C, Ua = add_length(C, Ua, a, cnt(cd0, a), H)
            vb = V(C, Ua)
            rb, rbb = sb[s], sbb[s]
            for j, x in enumerate(vb):
                rb[j] += x
                rbb[j] += x * x
            C1, U1, added = C, Ua, False
            for d in extra_union:
                c = cnt(cd0, d)
                if c:
                    C1, U1 = add_length(C1, U1, d, c, H)
                    added = True
            v1 = V(C1, U1) if added else vb
            for e in eps_list:
                cd = cdfs[s][e]
                C2, U2, add2 = C1, U1, False
                for d in extra_off:
                    c = cnt(cd, d)
                    if c:
                        C2, U2 = add_length(C2, U2, d, c, H)
                        add2 = True
                v2 = V(C2, U2) if add2 else v1
                if v2 is vb:
                    continue
                rg, rgg = sg[(s, e)], sgg[(s, e)]
                for j in range(nk):
                    g = vb[j] - v2[j]
                    if g:
                        rg[j] += g
                        rgg[j] += g * g
    out = {}
    n = n_samples

    def mse(a, aa):
        mu = a / n
        var = max(aa / n - mu * mu, 0.0) * n / (n - 1) if n > 1 else 0.0
        return mu, math.sqrt(var / n)
    for s in range(S):
        for e in eps_list:
            for j, k in enumerate(V.keys):
                mg, seg = mse(sg[(s, e)][j], sgg[(s, e)][j])
                mb, seb = mse(sb[s][j], sbb[s][j])
                out[k + (s, e)] = (mg, seg, mb, seb)
    return out
