"""Creative supply per break, with common random numbers.

For break i, each duration a has its own random stream, seeded by the string "<master>|pool|<i>|<a>"
only (random.Random string seeding is SHA-512 based and identical across platforms and
Python 3 versions). The Poisson mean of duration a is lambda * w_a with w a weight over the UNION of
durations {5, 6, 10, 15, 20, 30, 45, 60}, so it does not depend on the menu. The break length T has its
own stream "<master>|break|<law>|<i>". Consequences: every relaxation combo, cap h, readiness level rho
and menu sees the same creatives for each duration; adding a duration to a menu leaves the other
durations' pools identical; different lambda or weights are coupled through the same uniforms.

Per duration a the stream draws, in order:
  1. n_a ~ Poisson(lambda * w_a), exact (sum of Poisson chunks of mean <= 20, each by inversion);
  2. the top K = min(n_a, kneed) per-second values among n_a i.i.d. draws, as descending uniform order
     statistics U_(n) = V_1^(1/n), U_(n-j) = U_(n-j+1) V_(j+1)^(1/(n-j)), mapped through the value law;
     only the top K can ever be selected (kneed = floor(Tmax / 5) bounds the number of ads of any pod,
     including elastic pods under the arithmetic relaxation, since every duration is at least 5 s);
  3. one readiness uniform per creative (ready at the deadline iff u < rho);
  4. extra creatives for the demand relaxation (n_a unbounded), drawn after the pool so the pool itself
     does not depend on whether the relaxation is used: kneed fresh i.i.d. creatives conditioned to clear
     the floor. The relaxed pool is the real pool plus these extras (a superset).

Value law (SYNTHETIC, no source): per-second value in cents of CPM per second,
  v = max(1, round(100 * exp(mu + sigma Z) * (a / 30) ** beta)), Z standard normal,
defaults mu = ln(20 / 30) (median 30-second CPM of $20), sigma = 0.5, beta = 0 (flat bid density).
Floor (OpenRTB mincpmpersec, in the same cents-per-second unit): a creative with v < floor is dropped
before pod construction. Default floor 0 (off).
"""
import math
import random
from statistics import NormalDist

from .pod import Creative
from .numeric import xsum

_N = NormalDist()


def poisson(rng, lam):
    if lam <= 0:
        return 0
    n = 0
    chunks = int(math.ceil(lam / 20.0))
    mu = lam / chunks
    emu = math.exp(-mu)
    for _ in range(chunks):
        # inversion by sequential search
        u = rng.random()
        k, p = 0, emu
        c = p
        while u > c:
            k += 1
            p *= mu / k
            c += p
            if k > 10 * mu + 100:
                break
        n += k
    return n


class ValueLaw(object):
    def __init__(self, mu=math.log(20.0 / 30.0), sigma=0.5, beta=0.0, floor=0):
        self.mu, self.sigma, self.beta, self.floor = mu, sigma, beta, floor

    def value(self, a, q):
        q = min(max(q, 1e-15), 1 - 1e-15)
        x = math.exp(self.mu + self.sigma * _N.inv_cdf(q)) * (a / 30.0) ** self.beta
        return max(1, int(round(100 * x)))

    def q_floor(self, a):
        """Smallest uniform level whose value clears the floor (conservative; checked after mapping)."""
        if self.floor <= 1:
            return 0.0
        x = (self.floor - 0.5) / 100.0 / (a / 30.0) ** self.beta
        return _N.cdf((math.log(x) - self.mu) / self.sigma)

    def key(self):
        return "mu%.6f_s%.4f_b%.4f_f%d" % (self.mu, self.sigma, self.beta, self.floor)


MIN_DUR = 5  # smallest duration in any menu used; kneed = Tmax // MIN_DUR bounds the ads of any pod


TMAX_ALL = 240  # every law with targets up to 240 s gets the same number of creatives per duration


def kneed_for(Tmax=TMAX_ALL):
    """Creatives generated per duration: max(Tmax, 240) // 5. For every law with targets up to 240 s this is
    48, so a break index draws the same stream whatever the law (no pod on a target <= 240 s can use more than
    48 ads); laws with longer targets (L7, up to 360 s) get Tmax // 5."""
    return max(Tmax, TMAX_ALL) // MIN_DUR


def duration_stream(master, i, a, n_mean, kneed, vlaw):
    """Return (pool, extras) for one duration of one break: lists of Creative sorted by v descending
    (pool) and in draw order (extras). Seeded by (master, break, duration) only."""
    rng = random.Random("%s|pool|%d|%d" % (master, i, a))
    n = poisson(rng, n_mean)
    K = min(n, kneed)
    vals = []
    q = 1.0
    for j in range(K):
        q *= (1.0 - rng.random()) ** (1.0 / (n - j))
        vals.append(q)
    us = [rng.random() for _ in range(K)]
    pool = []
    for j in range(K):
        v = vlaw.value(a, vals[j])
        if v >= vlaw.floor:
            pool.append(Creative(a, v, us[j], (a, "p", j)))
    qf = vlaw.q_floor(a)
    extras = []
    for j in range(kneed):
        qq = qf + (1.0 - qf) * rng.random()
        v = vlaw.value(a, qq)
        if v < vlaw.floor:
            v = vlaw.floor
        extras.append(Creative(a, v, rng.random(), (a, "x", j)))
    return pool, extras


def break_target(master, law_obj, i):
    rng = random.Random("%s|break|%s|%d" % (master, law_obj.name, i))
    return law_obj.sample(rng)


UNION = (5, 6, 10, 15, 20, 30, 45, 60)
SCHEMES = ("balanced", "w30", "w15", "short", "d1530")
SCHEME_LABEL = {"balanced": "balanced", "w30": "30-heavy", "w15": "15-heavy", "short": "short-scarce",
                "d1530": "15/30-dominant"}


def weights(scheme="balanced"):
    """w_a over the union of durations, summing to 1, so lambda is the expected total number of distinct
    creatives per break over all eight durations (a menu sees only its own durations). Schemes, all
    SYNTHETIC values: balanced (1/8 each); w30 (30 s gets 1/2, the other seven share 1/2); w15 (same with
    15 s); short (durations below 15 s get weight 1/4 relative to 1 for the others, renormalized); d1530
    (15/30-dominant: 0.6 on 30 s, 0.4 on 15 s, 0.02 on each of the other six, renormalized by 1.12;
    informed by a public Wurl 2021 statement that 15 s and 30 s creatives dominate, values synthetic)."""
    k = len(UNION)
    if scheme == "balanced":
        return {a: 1.0 / k for a in UNION}
    if scheme in ("w30", "w15"):
        tgt = 30 if scheme == "w30" else 15
        return {a: (0.5 if a == tgt else 0.5 / (k - 1)) for a in UNION}
    if scheme == "short":
        raw = {a: (0.25 if a < 15 else 1.0) for a in UNION}
    elif scheme == "d1530":
        raw = {a: (0.6 if a == 30 else 0.4 if a == 15 else 0.02) for a in UNION}
    else:
        raise KeyError(scheme)
    s = xsum(raw.values())
    return {a: raw[a] / s for a in UNION}
