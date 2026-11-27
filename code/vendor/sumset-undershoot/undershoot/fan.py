"""Morales fan data for four-element sets A0 = {0, al, be, d} (Manuscript Setup before Lemma 7.9).
fan(): the fan of L = {(s, p): s b1 = p c1 mod d} (Bermejo, Gimenez and Morales 2006, Sec 2), with the indices
v, nu, mu. frob(): Frobenius numbers of S1 and S2 by Lemma 7.9 (Rodseth 1978, Thm 1, with Johnson's reduction).
reg_ideal(): reg(I(C_A)) by BGM Thm 2.8 for non-CM sets. Standard library only; shares no code with the engines
E-A, E-B, E-C or with engine_d/edsearch.c."""
from math import gcd


def inv(x, m):
    """Inverse of x modulo m (m >= 2, gcd(x, m) = 1); extended Euclid, Python 3.5 compatible."""
    a, b, u, v = x % m, m, 1, 0
    while b:
        t = a // b
        a, b, u, v = b, a - t * b, v, u - t * v
    return u % m


def fan(al, be, d):
    """Morales fan of L = {(s, p): s b1 = p c1 mod d}, oriented so that b1 (d - c1) <= (d - b1) c1."""
    if al * (d - be) <= (d - al) * be:
        b1, c1 = al, be
    else:
        b1, c1 = be, al
    b2, c2 = d - b1, d - c1
    g = gcd(b1, d); m = d // g
    s0 = 0 if m == 1 else (c1 % m) * inv(b1 // g, m) % m
    S, P, Q = [m, s0], [0, g], [None, None]
    while S[-1]:
        q = -(-S[-2] // S[-1])
        S.append(q * S[-1] - S[-2]); P.append(q * P[-1] - P[-2]); Q.append(q)
    R1 = []
    for s, p in zip(S, P):
        assert (s * b1 - p * c1) % d == 0
        R1.append((s * b1 - p * c1) // d)
    R2 = [s - p - r for s, p, r in zip(S, P, R1)]
    n = len(S)
    return dict(b1=b1, c1=c1, b2=b2, c2=c2, g=g, S=S, P=P, Q=Q, R1=R1, R2=R2, n=n,
                nu=max(k for k in range(n) if R1[k] >= 0 and R2[k] >= 0),
                nu_r=max(k for k in range(n) if R1[k] >= 0),
                mu=max(k for k in range(n) if R2[k] > 0),
                v=max(k for k in range(n) if R1[k] > 0))


def frob(F, j, d):
    """Lemma 7.9 (Rodseth's Theorem 1 with Johnson's reduction), for S1 (j = 1) or S2 (j = 2)."""
    S, P = F["S"], F["P"]
    b, c, i = (F["b1"], F["c1"], F["v"]) if j == 1 else (F["b2"], F["c2"], F["mu"])
    return -d + b * (S[i] - 1) + c * (P[i + 1] - 1) - min(b * S[i + 1], c * P[i])


def reg_ideal(F):
    """BGM Thm 2.8, curve case: reg(I) = max over nu < k <= mu of [deg G_k + max(D_k, D_(k-1))] - 2."""
    S, P, R1, R2, nu, mu = F["S"], F["P"], F["R1"], F["R2"], F["nu"], F["mu"]
    degG = lambda k: S[k] + (-R1[k] if R1[k] < 0 else 0) + (-R2[k] if R2[k] < 0 else 0)
    D = lambda k: S[k] - S[k + 1] + P[k + 1] - P[k]
    terms = [(degG(k) + max(D(k), D(k - 1)), k) for k in range(nu + 1, mu + 1)]
    return max(terms)[0] - 2, [k for t, k in terms if t == max(terms)[0]]


def is_family(al, be, d):
    """The equality family of Theorem 7.10: {0, b - 1, b + 1, 2b} with b even."""
    return d % 4 == 0 and al == d // 2 - 1 and be == d // 2 + 1
