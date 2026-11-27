"""Break-length laws. Every law is an exact pmf with Fraction weights, so exact
means of the structural floor need no sampling; sample() draws from the same pmf.

A law yields (T, structured) pairs: T is the dynamic target (poddur) and structured is True when a
structured portion was carved out of the break (hybrid pod), which matters for cap convention (b).

L1  grid:              T uniform on {60, 90, ..., 240}                       (model choice)
L2  hybrid remainder:  B from L1, S uniform on a set, present with prob p,   (model choice; S set and p
                       T = B - S if present else B                             are parameters)
L3u irregular live:    T uniform on integers [60, 240]                        (model choice)
L3s right-skewed:      T on integers [60, 240], weight x (1 - x)^4 with       (SYNTHETIC choice: a
                       x = (2 (T - 60) + 1) / 362 (discretized Beta(2, 5)      discretized Beta(2,5);
                       at bin midpoints), mean about 111 s, mode about 96 s    no source)
L4  lattice variants:  L3u or L3s restricted to multiples of 5 or 15 s,       (model choice)
                       renormalized
L8  bimodal live:      with probability 1 - q a scheduled break from L1, with  (SYNTHETIC: the stoppage
                       probability q an irregular stoppage break, uniform      range and q are sweep
                       integers [30, 120]; q in {0.25, 0.5, 0.75}              values, no source)
L5  minute bins:       FreeWheel Q1 2023 mid-roll shares, uniform seconds      (shares sourced; bin
                       inside each bin (L5 below)                              edges modeling choices)
L6, L7 short and long: uniform integers [15, 60] and [240, 360]               (SYNTHETIC)
H2  hybrid S sets:     as L2 with S uniform on {15, 30}, {5, 10}, {7, 8, 12}   (catalog family H2; sets
                       or {60}; laws L2s1530, L2s510, L2s7812, L2s60            synthetic)
H3  two spots:         law L2two: B from L1, an opening spot S1 and a closing  (catalog family H3;
                       spot S2, each uniform on {5, 10, 15, 20, 45},           conditioning on
                       independent, conditioned per B on S1 + S2 <= B;         S1 + S2 <= B is a
                       T = B - S1 - S2                                         modeling choice)

The structured flag of a support point is a count of structured spots: False/0 (none), True/1 (one spot) or
2 (H3). True == 1 in Python, so a one-spot flag and a count of one are the same value.
"""
from fractions import Fraction
import bisect
from .numeric import xsum


def uniform(points):
    pts = sorted(set(points))
    w = Fraction(1, len(pts))
    return [(t, w) for t in pts]


def normalize(pairs):
    tot = xsum(w for _, w in pairs)
    return [(t, Fraction(w) / tot) for t, w in pairs]


def L1(lo=60, hi=240, step=30):
    return uniform(range(lo, hi + 1, step))


def L3u(lo=60, hi=240):
    return uniform(range(lo, hi + 1))


def L3s(lo=60, hi=240):
    n = hi - lo + 1
    out = []
    for T in range(lo, hi + 1):
        x = Fraction(2 * (T - lo) + 1, 2 * n)
        out.append((T, x * (1 - x) ** 4))
    return normalize(out)


def L5():
    """FreeWheel Q1 2023 mid-roll break-length shape (minute bins 8/32/26/10/24% for < 1, 1-2, 2-3, 3-4 and
    4 or more minutes; FreeWheel, The State of TV Advertising Viewer Experience, 2023), integer seconds uniform inside each bin:
    [1, 59], [60, 119], [120, 179], [180, 239], and the open top bin cut to [240, 300] s. The bin edges and the
    cut are modeling choices; only the five shares are sourced."""
    bins = [((1, 59), Fraction(8, 100)), ((60, 119), Fraction(32, 100)), ((120, 179), Fraction(26, 100)),
            ((180, 239), Fraction(10, 100)), ((240, 300), Fraction(24, 100))]
    out = []
    for (lo, hi), share in bins:
        n = hi - lo + 1
        out.extend((t, share / n) for t in range(lo, hi + 1))
    return out


def L6():
    """Short breaks: uniform integers [15, 60] s (synthetic)."""
    return uniform(range(15, 61))


def L7():
    """Long breaks: uniform integers [240, 360] s (synthetic)."""
    return uniform(range(240, 361))


def L8(q, stop_lo=30, stop_hi=120):
    """Bimodal live breaks: L1 grid with probability 1 - q, irregular stoppage breaks uniform on integers
    [stop_lo, stop_hi] with probability q (synthetic)."""
    q = Fraction(q)
    acc = {}
    for t, w in L1():
        acc[t] = acc.get(t, Fraction(0)) + (1 - q) * w
    for t, w in uniform(range(stop_lo, stop_hi + 1)):
        acc[t] = acc.get(t, Fraction(0)) + q * w
    return sorted(acc.items())


def L4(base, step):
    return normalize([(t, w) for t, w in base if t % step == 0])


class Law(object):
    """A pmf over (T, structured) with exact weights."""

    def __init__(self, name, pairs):
        # pairs: [((T, structured), weight)]
        acc = {}
        for k, w in pairs:
            acc[k] = acc.get(k, Fraction(0)) + Fraction(w)
        tot = xsum(acc.values())
        if tot != 1:
            raise ValueError("law %s weights sum to %s" % (name, tot))
        self.name = name
        self.support = sorted(acc.items())
        cum = []
        c = Fraction(0)
        for _, w in self.support:
            c += w
            cum.append(float(c))
        cum[-1] = 1.0
        self._cum = cum

    @classmethod
    def plain(cls, name, pmf):
        return cls(name, [((t, False), w) for t, w in pmf])

    @classmethod
    def hybrid(cls, name, break_pmf, S_set, p=Fraction(1)):
        p = Fraction(p)
        S_pmf = uniform(S_set)
        pairs = []
        for b, wb in break_pmf:
            if p < 1:
                pairs.append(((b, False), wb * (1 - p)))
            if p > 0:
                for s, ws in S_pmf:
                    pairs.append(((b - s, True), wb * p * ws))
        return cls(name, pairs)

    @classmethod
    def two_spots(cls, name, break_pmf, S_set):
        """H3: opening and closing structured spots, each uniform on S_set and independent, conditioned per
        break length B on S1 + S2 <= B (the pairs that fit); T = B - S1 - S2, structured count 2."""
        pairs = []
        for b, wb in break_pmf:
            ok = [(s1, s2) for s1 in S_set for s2 in S_set if s1 + s2 <= b]
            if not ok:
                raise ValueError("no pair of structured spots fits a %d s break" % b)
            for s1, s2 in ok:
                pairs.append(((b - s1 - s2, 2), wb / len(ok)))
        return cls(name, pairs)

    def sample(self, rng):
        i = bisect.bisect_right(self._cum, rng.random())
        return self.support[min(i, len(self.support) - 1)][0]

    @property
    def Tmax(self):
        return max(t for (t, _), _ in self.support)


# S set of L2, L2two, X0 and X3 (synthetic parameter): structured spot lengths in seconds
S_SPOTS = (5, 10, 15, 20, 45)
H2_SETS = {"L2s1530": (15, 30), "L2s510": (5, 10), "L2s7812": (7, 8, 12), "L2s60": (60,)}
L8_Q = {"L8q25": Fraction(1, 4), "L8q50": Fraction(1, 2), "L8q75": Fraction(3, 4)}
# every law name with its lattice (gcd of the support's targets); checked against the support in the tests
NEW_LAWS = tuple(sorted(L8_Q)) + tuple(sorted(H2_SETS)) + ("L2two",)


def named(name):
    """Laws used by the run scripts."""
    if name == "L1":
        return Law.plain("L1", L1())
    if name == "L2":
        return Law.hybrid("L2", L1(), S_SPOTS, 1)
    if name == "L3u":
        return Law.plain("L3u", L3u())
    if name == "L3s":
        return Law.plain("L3s", L3s())
    if name == "L4u5":
        return Law.plain("L4u5", L4(L3u(), 5))
    if name == "L4u15":
        return Law.plain("L4u15", L4(L3u(), 15))
    if name == "L4s5":
        return Law.plain("L4s5", L4(L3s(), 5))
    if name == "L4s15":
        return Law.plain("L4s15", L4(L3s(), 15))
    if name == "L5":
        return Law.plain("L5", L5())
    if name == "L6":
        return Law.plain("L6", L6())
    if name == "L7":
        return Law.plain("L7", L7())
    if name in L8_Q:
        return Law.plain(name, L8(L8_Q[name]))
    if name in H2_SETS:
        return Law.hybrid(name, L1(), H2_SETS[name], 1)
    if name == "L2two":
        return Law.two_spots("L2two", L1(), S_SPOTS)
    raise KeyError("unknown break-length law %r" % (name,))


def dynamic_cap(h, structured, convention):
    """Cap on the dynamic portion. convention 'a' (OpenRTB signaling): maxseq applies to the dynamic
    portion alone, so the cap is h. Convention 'b' (knapsack companion): the structured spots count toward a total K = h,
    so a remainder after n structured spots gets max(0, h - n) (n = 1 for True). h None (uncapped) stays
    None."""
    if convention not in ("a", "b"):
        raise ValueError("unknown cap convention %r" % (convention,))
    if h is None:
        return None
    if convention == "a" or not structured:
        return h
    return max(0, h - int(structured))
