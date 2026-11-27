"""Practitioner-style greedy pod builders (scenario catalog policy axis: P3, P3d and P4), and the dominance check.

Every builder scans a list of distinct creatives once and adds a creative when it still fits: total
duration at most T and ad count at most the cap (None = no cap). A creative that does not fit is skipped and
the scan continues (a "fill while it fits" rule, not "stop at the first misfit").

  P3   greedy by bid price per second: creatives in descending per-second value v; ties broken by longer
       duration first, then by pool order. This is the reading of "greedy by price, longest first" used for
       the headline (price is the primary key, length the tie-break).
  P3d  the other reading, reported alongside: longest duration first, and by descending price within a
       duration (fill the long slots first, best bid first).
  P4   first-come: creatives in bid arrival order (arrival times drawn independently of value).

assert_dominance(): the exact seconds-max pod (P1) has at least the seconds of every other pod, and the
exact revenue-max pod (P2) has at least the revenue of every other pod, on the same pool. Raised as an
AssertionError so a violation stops the run.
"""
from .pod import Pod


def _scan(T, cap, order):
    hcap = 10 ** 9 if cap is None else cap
    sec = rev = 0
    items = []
    if T <= 0 or hcap <= 0:
        return Pod(0, 0, [])
    for c in order:
        if len(items) >= hcap:
            break
        if sec + c.dur <= T:
            sec += c.dur
            rev += c.bid
            items.append((c, c.dur))
            if sec == T:
                break
    return Pod(sec, rev, items)


def _flat(by):
    out = []
    for a in sorted(by):
        out.extend(by[a])
    return out


def greedy_price(T, cap, by):
    """P3. by: {duration: creatives}."""
    flat = _flat(by)
    order = sorted(range(len(flat)), key=lambda k: (-flat[k].v, -flat[k].dur, k))
    return _scan(T, cap, [flat[k] for k in order])


def greedy_duration(T, cap, by):
    """P3d. by: {duration: creatives}."""
    flat = _flat(by)
    order = sorted(range(len(flat)), key=lambda k: (-flat[k].dur, -flat[k].v, k))
    return _scan(T, cap, [flat[k] for k in order])


def first_come(T, cap, arrival):
    """P4. arrival: creatives already in arrival order."""
    return _scan(T, cap, arrival)


def assert_dominance(pods, T, cap):
    s1 = pods["P1"].seconds
    r2 = pods["P2"].revenue
    for k, p in pods.items():
        if p.seconds > T or (cap is not None and p.n_ads > cap):
            raise AssertionError("policy %s infeasible: %d s, %d ads, T %d, cap %s" % (k, p.seconds, p.n_ads, T, cap))
        if p.seconds > s1:
            raise AssertionError("policy %s fills %d s > seconds-max %d (T %d, cap %s)" % (k, p.seconds, s1, T, cap))
        if p.revenue > r2:
            raise AssertionError("policy %s earns %d > revenue-max %d (T %d, cap %s)" % (k, p.revenue, r2, T, cap))
