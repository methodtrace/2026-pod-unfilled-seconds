"""X6 revenue layer: value laws, floors, buyer-side filtering, and both exact pod policies on one pool.

Units (as in pod.py and pools.py): a creative's per-second value v is an integer in cents of CPM per second
(the unit of OpenRTB mincpmpersec, times 100); its bid is v * duration cents of CPM; pod revenue is the sum
of the selected bids (pay-as-bid), in cents of CPM per pod, that is per thousand pod impressions. Reports
divide by 100 to give dollars of CPM per pod.

Value laws (both SYNTHETIC, no source):
  V1  flat per-second value: pools.ValueLaw() defaults, v = round(100 exp(mu + sigma Z)), mu = ln(20/30),
      sigma = 0.5 (median 30-second CPM $20), the same law as pools.py and every other experiment.
  V2  duration premium: v = round(100 exp(mu + sigma Z) (a / 30) ** beta) with beta = V2_BETA = -0.3, so a
      creative's per-second value is anchored at 30 s and rises for shorter ads (15 s: x1.23, 10 s: x1.39,
      6 s: x1.62, 5 s: x1.71) and falls for longer ones (45 s: x0.89, 60 s: x0.81).
  Both laws map the SAME uniform order statistic of each creative (common random numbers across V1 and V2).

Floors (mechanisms from OpenRTB 2.6, levels SYNTHETIC):
  none          no floor.
  mincpmpersec  a scalar floor f on the per-second CPM; a creative bids iff v >= f.
  durfloors     a CPM floor per duration range (the spec's example ranges 1-15, 16-30, 31+ s); a creative of
                duration a bids iff its bid v * a is at least the floor of its range (the largest floor
                among matching ranges if ranges overlap; a duration outside every range has no floor, the
                spec's fallback to Imp.bidfloor, which is unset here).
  Filtering is buyer-side and happens before pod construction (OpenRTB 7.6: buyers use mincpmpersec when it
  is present), so every policy sees the same filtered pool.

Pool draws. stream_draw() reproduces the first part of pools.duration_stream() exactly (same seed string
"<master>|pool|<i>|<a>", same Poisson draw, same descending uniform order statistics), but draws all n_a
order statistics instead of the top min(n_a, kneed) (pools.kneed_for: 48 for targets up to 240 s), because
first-come construction (P4) can pick a creative that is not among the top bids. The top min(n_a, kneed)
values are therefore identical to the pools.py
simulator's pools (tested). Arrival times for P4 come from a separate stream "<master>|arrive|<i>|<a>"
(independent of value), so they do not disturb the pool.

Policies on one filtered pool (pod.select_menu, exact; checked against pod.dp_select and pod.pod_oracle in
the tests): P1 seconds-max (ties by revenue), P2 revenue-max (ties by seconds). Greedy baselines P3, P3d
and P4 are in greedy.py.
"""
import math
import random
from statistics import NormalDist

from . import pools as P
from .pod import Creative, select_menu
from . import greedy

V2_BETA = -0.3
_N = NormalDist()


def value_law(name):
    if name == "V1":
        return P.ValueLaw()
    if name == "V2":
        return P.ValueLaw(beta=V2_BETA)
    raise KeyError(name)


VALUE_LAWS = ("V1", "V2")


class Floor(object):
    """A buyer-side floor. kind 'none', 'ps' (mincpmpersec, cents of CPM per second) or 'dur' (durfloors:
    list of (lo, hi, cents of CPM), hi None for open-ended)."""

    def __init__(self, name, kind, ps=0, ranges=()):
        self.name, self.kind, self.ps, self.ranges = name, kind, ps, tuple(ranges)

    def min_v(self, a):
        """Least integer per-second value v that bids at duration a (1 means no constraint)."""
        if self.kind == "none":
            return 1
        if self.kind == "ps":
            return max(1, self.ps)
        if self.kind == "dur":
            fl = [f for lo, hi, f in self.ranges if a >= lo and (hi is None or a <= hi)]
            if not fl:
                return 1
            F = max(fl)
            return max(1, -(-F // a))  # ceil(F / a): v * a >= F
        raise ValueError(self.kind)

    def passes(self, a, v):
        return v >= self.min_v(a)

    def describe(self):
        if self.kind == "none":
            return "no floor"
        if self.kind == "ps":
            return "mincpmpersec $%.2f per second (30-s equivalent $%.2f CPM)" % (self.ps / 100.0, 0.3 * self.ps)
        parts = []
        for lo, hi, f in self.ranges:
            rng = ("%d+ s" % lo) if hi is None else ("%d-%d s" % (lo, hi))
            parts.append("%s: $%.2f CPM" % (rng, f / 100.0))
        return "durfloors " + "; ".join(parts)


# Narrow-tier floors (levels SYNTHETIC). Per-second levels expressed as 30-second-equivalent CPMs of
# $15, $20 and $30; under V1 they sit at the 28th, 50th and 79th percentiles of the per-second value.
# The durfloors schedule uses the spec's example ranges with floors $10 / $20 / $40 CPM: equal to the
# median V1 value at the top of the 1-15 and 16-30 ranges, so it binds hardest on the short end of each
# range (a 6-s ad needs $1.67 per second, a 10-s ad $1.00, a 15-s ad $0.67).
FLOORS_NARROW = (
    Floor("none", "none"),
    Floor("ps50", "ps", ps=50),
    Floor("ps67", "ps", ps=67),
    Floor("ps100", "ps", ps=100),
    Floor("dfA", "dur", ranges=((1, 15, 1000), (16, 30, 2000), (31, None, 4000))),
)


def pass_prob(vlaw, a, fl):
    """Exact probability that one creative of duration a clears floor fl under value law vlaw
    (accounts for the integer rounding of v and the max(1, .) guard)."""
    m = fl.min_v(a)
    if m <= 1:
        return 1.0
    # v >= m  <=>  round(100 x) >= m  <=>  100 x >= m - 0.5 (round half to even only matters on a null set)
    x = (m - 0.5) / 100.0 / (a / 30.0) ** vlaw.beta
    return 1.0 - _N.cdf((math.log(x) - vlaw.mu) / vlaw.sigma)


# ------------------------------------------------------------------------------------------ draws

def stream_draw(master, i, a, n_mean):
    """(n, qs): Poisson count and ALL n descending uniform order statistics for duration a of break i.
    The first min(n, kneed) equal pools.duration_stream()'s, draw for draw (pools.kneed_for)."""
    rng = random.Random("%s|pool|%d|%d" % (master, i, a))
    n = P.poisson(rng, n_mean)
    qs = []
    q = 1.0
    for j in range(n):
        q *= (1.0 - rng.random()) ** (1.0 / (n - j))
        qs.append(q)
    return n, qs


def arrival_draw(master, i, a, n):
    rng = random.Random("%s|arrive|%d|%d" % (master, i, a))
    return [rng.random() for _ in range(n)]


class BreakDraw(object):
    """All random inputs of one break for one (law, menu, lambda, weights): T, structured flag, and per
    duration the order statistics and arrival times. Value laws and floors are applied later, so every
    (cap, floor, value law, policy) condition shares these draws."""
    __slots__ = ("T", "structured", "q", "arr")

    def __init__(self, master, law, i, menu, lam, w):
        self.T, self.structured = P.break_target(master, law, i)
        self.q, self.arr = {}, {}
        for a in menu:
            n, qs = stream_draw(master, i, a, lam * w[a])
            self.q[a] = qs
            self.arr[a] = arrival_draw(master, i, a, n)

    def values(self, vlaw):
        """{a: [v_j]} descending per duration (the value map is increasing in q)."""
        return {a: [vlaw.value(a, q) for q in qs] for a, qs in self.q.items()}


def build_pool(draw, vals, fl):
    """Filtered pool. Returns (by_dur, arrival_list, n_total, n_kept): by_dur {a: creatives sorted by bid
    descending} for the exact DP and greedy P3; arrival_list all kept creatives in arrival order for P4."""
    by = {}
    arr = []
    n_tot = 0
    for a in sorted(vals):
        m = fl.min_v(a)
        vs = vals[a]
        n_tot += len(vs)
        lst = []
        ar = draw.arr[a]
        for j, v in enumerate(vs):
            if v < m:
                break  # descending: every later value is below the floor too
            c = Creative(a, v, 0.0, (a, j))
            lst.append(c)
            arr.append((ar[j], a, j, c))
        by[a] = lst
    arr.sort(key=lambda t: (t[0], t[1], t[2]))
    return by, [t[3] for t in arr], n_tot, len(arr)


POLICIES = ("P1", "P2", "P3", "P3d", "P4")


def all_policies(T, cap, by, arrival):
    """{policy: Pod} on one pool. P1 seconds-max and P2 revenue-max exact; greedy baselines from greedy.py.
    Asserts that the exact DP weakly dominates every other policy in its own objective."""
    p1, p2 = select_menu(T, cap, by)
    pods = {"P1": p1, "P2": p2,
            "P3": greedy.greedy_price(T, cap, by),
            "P3d": greedy.greedy_duration(T, cap, by),
            "P4": greedy.first_come(T, cap, arrival)}
    greedy.assert_dominance(pods, T, cap)
    return pods
