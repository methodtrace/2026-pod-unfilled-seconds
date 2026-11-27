"""Engine E-A (direct). hA0 by repeated shifted OR of a Python-int bitset; undershoot by scan.
Shares no code with engine_b or engine_c."""


def sumset_bits(A0, h):
    """Bitset of hA0 = {sum of exactly h elements of A0}; A0 must contain 0."""
    cur = 1
    for _ in range(h):
        nxt = 0
        for a in A0:
            nxt |= cur << a
        cur = nxt
    return cur


def sumset_series(A0, H):
    """List [bits(0A0), bits(1A0), ..., bits(HA0)]."""
    out = [1]
    cur = 1
    for _ in range(H):
        nxt = 0
        for a in A0:
            nxt |= cur << a
        cur = nxt
        out.append(cur)
    return out


def elements(bits):
    s = bin(bits)[:1:-1]
    return [i for i, c in enumerate(s) if c == "1"]


def undershoot_scan(bits, L, U):
    """[D(T) for T in L..U], D(T) = T - max{s in set: s <= T}. Requires an element <= L."""
    below = bits & ((1 << (L + 1)) - 1)
    if below == 0:
        raise ValueError("no element <= L")
    last = below.bit_length() - 1
    out = []
    for T in range(L, U + 1):
        if (bits >> T) & 1:
            last = T
        out.append(T - last)
    return out


def total_undershoot(bits, L, U):
    return sum(undershoot_scan(bits, L, U))
