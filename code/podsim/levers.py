"""X2 levers: exact seconds recovered per break by one lever at a time, from every X1 baseline.

Exactness (as in exact.py): under the seconds-max policy filled seconds depend only on T, the cap and
per-duration counts; counts are independent Poisson with means fixed per duration over the union of
durations (DESIGN.md, common random numbers across menus), so a menu with an added duration has the same counts for the old durations plus
an independent count for the new one. Every lever's gain is a difference of two exact expectations over
the same joint law, which is the exact paired contrast (common random numbers in the limit).

Readiness enters as E[U] = (1 - rho) E[T] + rho E[U at rho = 1] (readiness drawn after selection).
"""
from fractions import Fraction
from operator import mul

from . import structural
from .exact import TMAX, last_below, profile_dist
from .laws import dynamic_cap
from .numeric import xsum

CAPS = list(range(2, 15))  # 2 for convention b at h = 3, up to 14 for h + 2 at h = 12


def law_parts(law):
    """Dense weights over T = 0..TMAX for breaks without (wu) and with (ws) a structured portion. Laws with
    two structured spots (H3) need law_parts_by_count; this function refuses them."""
    pc = law_parts_by_count(law)
    if any(n > 1 for n in pc):
        raise ValueError("law %s has breaks with two structured spots; use law_parts_by_count" % law.name)
    z = [0.0] * (TMAX + 1)
    return pc.get(0, z), pc.get(1, list(z))


def law_parts_by_count(law):
    """{number of structured spots: dense weights over T = 0..TMAX}."""
    out = {}
    for (T, st), w in law.support:
        if T > TMAX:
            raise ValueError("law %s reaches %d s > TMAX %d; set PODSIM_TMAX" % (law.name, T, TMAX))
        v = out.setdefault(int(st), [0.0] * (TMAX + 1))
        v[T] += float(w)
    return out


def nominal_caps(h, conv):
    """(cap for unstructured breaks, cap for structured breaks) at nominal maxseq h."""
    return dynamic_cap(h, False, conv), dynamic_cap(h, True, conv)


class MenuExpect(object):
    """Per menu: for each law, number of structured spots n, cap k (or None) and demand scenario s, the
    expectation P[law][n][k][s] = E[sum_T w_n(T) D_k(T)] under random counts, w_n the law's weight on breaks
    with n structured spots."""

    def __init__(self, menu, means_list, laws_dict, caps=None):
        self.menu = tuple(sorted(menu))
        S = len(means_list)
        self.S = S
        caps = sorted(set(CAPS if caps is None else [c for c in caps if c is not None]))
        self.caps = caps
        keys, probs, pruned = profile_dist(self.menu, means_list, H=max(caps))
        self.pruned = pruned
        marg = {k: {} for k in caps + [None]}
        for (C, Ua), pr in zip(keys, probs):
            for k in caps + [None]:
                b = Ua if k is None else C[k]
                row = marg[k].get(b)
                if row is None:
                    marg[k][b] = list(pr)
                else:
                    for s in range(S):
                        row[s] += pr[s]
        parts = {name: law_parts_by_count(law) for name, law in laws_dict.items()}
        self.P = {name: {n: {} for n in pc} for name, pc in parts.items()}
        lbcache = {}
        for k, dist in marg.items():
            acc = {name: {n: [0.0] * S for n in pc} for name, pc in parts.items()}
            for b, pr in dist.items():
                lb = lbcache.get(b)
                if lb is None:
                    lb = last_below(b)
                    lbcache[b] = lb
                for name, pc in parts.items():
                    for n, wv in pc.items():
                        x = xsum(map(mul, wv, lb))
                        ra = acc[name][n]
                        for s in range(S):
                            ra[s] += pr[s] * x
            for name, pc in parts.items():
                for n in pc:
                    self.P[name][n][k] = acc[name][n]

    def U(self, lawname, conv, h, s):
        return xsum(self.P[lawname][n][dynamic_cap(h, n, conv)][s] for n in self.P[lawname])


def struct_expect(menu, law, conv, h):
    """Exact E[D_h(A;T)] (Fraction), demand unlimited."""
    return xsum((w * structural.D(tuple(menu), dynamic_cap(h, st, conv), T) for (T, st), w in law.support),
               Fraction(0))


from functools import lru_cache as _lru


@_lru(maxsize=None)
def predecessor_table(menu, N=TMAX):
    """p_A(x) = largest element of <A> not above x, by membership from engine E-C gap sets, and the
    least-parts table l_A (direct DP) for the stability check."""
    from .checks import semigroup_member
    inside = semigroup_member(tuple(menu))
    p = []
    last = None
    for x in range(N + 1):
        if inside(x):
            last = x
        p.append(last)
    return p, inside, structural.min_parts(tuple(sorted(menu)), N)


def stability_assert(menu, c, law, conv, h):
    """Proposition 2 at stable caps, pointwise, demand unlimited: for every target T of the law with
    dynamic cap k >= l_A(p_A(T)) and k >= l_A'(p_A'(T)) (A' = A u {c}), the undershoot drops on adding c
    if and only if <A'> has an element in (p_A(T), T]. Raises on violation. Returns (n_stable_targets,
    n_targets, all_stable, n_gain_targets)."""
    A = tuple(sorted(menu))
    A2 = tuple(sorted(menu + (c,)))
    pA, inA, lA = predecessor_table(A)
    pB, inB, lB = predecessor_table(A2)
    ns = nt = ng = 0
    for (T, st), w in law.support:
        k = dynamic_cap(h, st, conv)
        nt += 1
        if pA[T] is None:
            continue
        kk = 10 ** 9 if k is None else k
        if kk >= lA[pA[T]] and kk >= lB[pB[T]]:
            ns += 1
            d1 = structural.D(A, k, T)
            d2 = structural.D(A2, k, T)
            new = any(inB(x) for x in range(pA[T] + 1, T + 1))
            if (d2 < d1) != new:
                raise AssertionError("Proposition 2 fails: %s + %d, h %s, T %d" % (A, c, h, T))
            if d2 < d1:
                ng += 1
    return ns, nt, ns == nt, ng


def per_T_expect(menu, means, caps):
    """{cap: [E[D_cap(T)] for T = 0..TMAX]} under random counts (means dict) or demand unlimited (None,
    exact Fractions). cap None = uncapped."""
    menu = tuple(sorted(menu))
    if means is None:
        return {k: [Fraction(x) for x in structural.undershoot_table(menu, k, TMAX)] for k in caps}
    keys, probs, pruned = profile_dist(menu, [means], H=max(c for c in caps if c is not None))
    out = {k: [0.0] * (TMAX + 1) for k in caps}
    for (C, Ua), pr in zip(keys, probs):
        p = pr[0]
        for k in caps:
            lb = last_below(Ua if k is None else C[k])
            row = out[k]
            for T in range(TMAX + 1):
                row[T] += p * lb[T]
    return out
