"""Demand and readiness sweeps: catalog axes D3 (fine lambda grid), D4 (negative binomial pools) and R2
(readiness by creative age).

D3. lambda on the log2 grid 1, 2, 4, ..., 256 for every weight scheme, Poisson counts (pools.py convention:
lambda is the expected number of distinct creatives per break over the union of eight durations).

D4. Negative binomial counts with the same per-duration means and dispersion k in {1, 4} (variance
mean + mean^2 / k), independent across durations. Exact by the same argument as the Poisson case: the
seconds-max fill depends only on the per-duration counts, so every expectation is a finite sum over the
truncated count laws (exact.nb_trunc, exact.total_trunc). Only the count law changes; nothing else does.

R2. Each creative is new with probability s, independently of its duration, value and everything the seller
sees; a new creative is ready at the deadline with probability rho_new, an older one with rho_old >= rho_new.
Readiness is drawn after selection and the seller does not see age (as in R1). Then each selected creative is
ready independently with probability rho_eff = s rho_new + (1 - s) rho_old, so
E[U | T, pool] = T - rho_eff F, and every R2 quantity is the R1 closed form at rho = rho_eff: EXACT, no
sampling. This rests on independence of age from selection. If the new share depended on duration, or if the
seller saw age and preferred older creatives (catalog R3, registered as an extension), the closed form would not hold; neither
variant is built. sampled_check() verifies the closed form against an explicit per-creative age and readiness
draw (used by the tests).
"""
import random

from .exact import NegBinMeans
from . import pools

D3_LAMS = (1, 2, 4, 8, 16, 32, 64, 128, 256)
D4_KS = (1, 4)
# R2 grid (synthetic sweep values, no source): share of new creatives, readiness of new and of older creatives
R2_SHARES = (0.1, 0.25, 0.5)
R2_RHO_NEW = (0.5, 0.8)
R2_RHO_OLD = (1.0, 0.99)


def scenarios(schemes=pools.SCHEMES, lams=D3_LAMS, ks=D4_KS):
    """[(label, scheme, lam, count_law, means)]: Poisson for every (scheme, lam), then negative binomial for
    every (k, scheme, lam). count_law is 'poisson' or 'nb<k>'."""
    out = []
    for sc in schemes:
        w = pools.weights(sc)
        for lam in lams:
            out.append(("poisson|%s|%s" % (sc, lam), sc, lam, "poisson", {a: lam * w[a] for a in pools.UNION}))
    for k in ks:
        for sc in schemes:
            w = pools.weights(sc)
            for lam in lams:
                out.append(("nb%d|%s|%s" % (k, sc, lam), sc, lam, "nb%d" % k,
                            NegBinMeans({a: lam * w[a] for a in pools.UNION}, k)))
    return out


def rho_eff(share_new, rho_new, rho_old):
    """Effective per-creative readiness under R2 (exact when age is independent of selection)."""
    for x, nm in ((share_new, "share_new"), (rho_new, "rho_new"), (rho_old, "rho_old")):
        if not 0.0 <= x <= 1.0:
            raise ValueError("%s must be in [0, 1], got %r" % (nm, x))
    if rho_new > rho_old:
        raise ValueError("R2 assumes rho_new <= rho_old (got %r > %r)" % (rho_new, rho_old))
    return share_new * rho_new + (1.0 - share_new) * rho_old


def r2_configs(shares=R2_SHARES, rho_new=R2_RHO_NEW, rho_old=R2_RHO_OLD):
    out = []
    for s in shares:
        for rn in rho_new:
            for ro in rho_old:
                out.append((s, rn, ro, rho_eff(s, rn, ro)))
    return out


def sampled_check(pod_items, T, share_new, rho_new, rho_old, n, seed="r2-check"):
    """Monte Carlo mean of unfilled seconds T - (ready seconds) over n independent age and readiness draws for a
    fixed selected pod (list of durations), to compare with the closed form T - rho_eff * sum(durations)."""
    rng = random.Random(seed)
    tot = 0.0
    for _ in range(n):
        filled = 0
        for d in pod_items:
            new = rng.random() < share_new
            if rng.random() < (rho_new if new else rho_old):
                filled += d
        tot += T - filled
    return tot / n
