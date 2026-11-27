"""The knapsack companion's necessary conditions on a pair of value-cardinality hulls of one pool at two capacities, used as a
consistency oracle on every simulated (full break B, remainder T = B - S) pair.

Reading (the companion's reservation interpretation): a structured spot of S seconds is a mandatory item
of size D - R, so the full break is capacity D = B and the dynamic remainder is capacity R = T = B - S, for the
same creative pool. H_w is the hull at B, H_r the hull at T (clutter.hull; the companion's hull notation).

Caps (the companion's uncapped default; at most K items at D and K - 1 at R):
  convention b (the companion's): the structured spot counts toward a total of K = h; the pair is (B at cap h, T at h - 1).
  convention a (OpenRTB signaling, maxseq on the dynamic portion only): the remainder gets h, and a full break
               with no structured spot also gets h; checked as (B at h, T at h) and in the companion's exact form
               (B at h + 1, T at h, K = h + 1). See PAIR_FORMS.
  uncapped:    (B, T), no cap.

Conditions, re-implemented here from the statements (no companion code is imported; the companion's own checker,
verify_certificates.py, is not needed to run this one):
  dimension   b_w <= K and b_r <= K - 1 (capped only).
  dominance   H_r(m) <= bar H_w(m) for 0 <= m <= b_r, with bar H(k) = H(min{k, b}).
  (1)         at a w-vertex n with h_n > rho_1: bar H_w(n - 1 + m) >= ((n - 1)/n) H_w(n) + H_r(m)
              (companion Corollary 3.4).
  (2)         same antecedent and n >= 3: bar H_w(m + 1) >= H_w(n)/n + H_r(m) (Corollary 3.4).
  (3)         n >= 3 a w-vertex with bar H_r(2) < H_w(n) - (n - 2) H_w(1):
              bar H_w(m + 1) >= H_r(m) + min{H/n, (H - rho_1)/(n - 1)}, H = H_w(n) (Corollary 3.5).
  Uncapped (the linear closure L of the companion): m ranges over 0..b_r.
  Capped: the companion gives the scalar rows uncapped; with a cap only the forms its exact obstruction checker
  uses are applied (verify_certificates.obstruction): (1) for every remainder vertex m and every top-q subset of
  its attaining set, bar H_w(n - 1 + q) >= ((n - 1)/n) H + (q/m) H_r(m) when n - 1 + q <= K; (2) and (3) for m in
  the remainder vertices and 0 with m + 1 <= K. (Interpolating H_r between vertices across an omitted over-cap
  row is not valid, per the companion's checker.)
A violation raises HullCheckError: for hulls computed from one pool it can only be a simulator bug.
"""
from fractions import Fraction as Q


class HullCheckError(AssertionError):
    pass


def verts(H):
    return [j for j in range(1, len(H)) if j == len(H) - 1 or H[j] - H[j - 1] != H[j + 1] - H[j]]


def _bar(H, k):
    return H[min(k, len(H) - 1)]


def well_formed(H):
    """H(0) = 0, strictly increasing, concave (problems here are bugs in the hull, reported separately)."""
    out = []
    if H[0] != 0:
        out.append({"equation": "H(0)"})
    for j in range(1, len(H)):
        if not H[j] > H[j - 1]:
            out.append({"equation": "increasing", "n": j})
        if j + 1 < len(H) and H[j + 1] - H[j] > H[j] - H[j - 1]:
            out.append({"equation": "concave", "n": j})
    return out


def violations(w, r, K=None, Kr=None):
    """All violated conditions for the target pair (w, r). K is the cap at the full break (None = uncapped);
    Kr the cap at the remainder, default K - 1 (the companion's convention). Empty list = consistent."""
    w = tuple(Q(x) for x in w)
    r = tuple(Q(x) for x in r)
    bw, br = len(w) - 1, len(r) - 1
    out = []
    for nm, H in (("w", w), ("r", r)):
        for v in well_formed(H):
            v["hull"] = nm
            out.append(v)
    if K is not None and Kr is None:
        Kr = K - 1
    if K is not None and (bw > K or br > Kr):
        out.append({"equation": "dimension", "bw": bw, "br": br, "K": K, "Kr": Kr})
        return out
    for m in range(br + 1):
        if r[m] > _bar(w, m):
            out.append({"equation": "dominance", "m": m, "lhs": str(_bar(w, m)), "rhs": str(r[m])})
    rho = r[1] if br else Q(0)
    vr = verts(r)
    for n in verts(w):
        H = w[n]
        long_vertex = w[n] - w[n - 1] > rho
        if K is None:
            if long_vertex:
                for m in range(br + 1):
                    lhs, rhs = _bar(w, n - 1 + m), Q(n - 1, n) * H + r[m]
                    if lhs < rhs:
                        out.append({"equation": "(1)", "n": n, "m": m, "lhs": str(lhs), "rhs": str(rhs)})
                    if n >= 3:
                        lhs, rhs = _bar(w, m + 1), H / n + r[m]
                        if lhs < rhs:
                            out.append({"equation": "(2)", "n": n, "m": m, "lhs": str(lhs), "rhs": str(rhs)})
            if n >= 3 and _bar(r, 2) < H - (n - 2) * w[1]:
                beta = min(H / n, (H - rho) / (n - 1))
                for m in range(br + 1):
                    lhs, rhs = _bar(w, m + 1), r[m] + beta
                    if lhs < rhs:
                        out.append({"equation": "(3)", "n": n, "m": m, "lhs": str(lhs), "rhs": str(rhs)})
        else:
            if long_vertex:
                for m in vr:
                    for q in range(1, m + 1):
                        if n - 1 + q > K:
                            continue
                        lhs, rhs = _bar(w, n - 1 + q), Q(n - 1, n) * H + Q(q, m) * r[m]
                        if lhs < rhs:
                            out.append({"equation": "(1)", "n": n, "m": m, "q": q, "lhs": str(lhs), "rhs": str(rhs)})
                if n >= 3:
                    for m in vr + [0]:
                        if m + 1 > K:
                            continue
                        lhs, rhs = _bar(w, m + 1), H / n + r[m]
                        if lhs < rhs:
                            out.append({"equation": "(2)", "n": n, "m": m, "lhs": str(lhs), "rhs": str(rhs)})
            if n >= 3 and _bar(r, 2) < H - (n - 2) * w[1]:
                beta = min(H / n, (H - rho) / (n - 1))
                for m in vr + [0]:
                    if m + 1 > K:
                        continue
                    lhs, rhs = _bar(w, m + 1), r[m] + beta
                    if lhs < rhs:
                        out.append({"equation": "(3)", "n": n, "m": m, "lhs": str(lhs), "rhs": str(rhs)})
    return out


def check_pair(w, r, K=None, Kr=None, context=None):
    """Raise HullCheckError on any violation; return 1 (for counting)."""
    v = violations(w, r, K, Kr)
    if v:
        raise HullCheckError("hull-pair condition violated %s: %s; Hw=%s Hr=%s K=%s Kr=%s"
                             % (context or "", v[:3], [str(x) for x in w], [str(x) for x in r], K, Kr))
    return 1


# Pair forms checked for nominal cap h: name -> (cap at B, cap at T). K = cap at B, Kr = cap at T.
#   b      companion convention: structured spot counts toward K = h; remainder h - 1.      companion exact form.
#   a      OpenRTB signaling: the full break and the remainder are both capped at maxseq = h. Kr = K: the
#          capped rows' witnesses (X minus x plus Z, {y} plus Z, top-q subsets of Z) are still fit-feasible and
#          are applied only when their count is within K, so the derivation carries over (stated, not the companion's).
#   a_k1   convention a in the companion's exact form: remainder at h is the R side of an instance with K = h + 1.
#   unc    uncapped pair.
PAIR_FORMS = ("a", "a_k1", "b", "unc")


def pair_caps(h, form):
    """(cap at B, cap at T) for nominal cap h."""
    if form == "b":
        return h, h - 1
    if form == "a":
        return h, h
    if form == "a_k1":
        return h + 1, h
    if form == "unc":
        return None, None
    raise ValueError(form)
