"""X4: menu-ranking reversal map. Exact arithmetic throughout the demand-unlimited part.

Quantities (results of the paper's Appendix A: Proposition 1(c), Proposition 2,
Proposition 1(b, e), Corollary 4, Example 6):
  floor value   E[D_h(A;T)], the exact structural floor at demand unlimited, for a law of T, a cap h
                (1..20 or None = uncapped) and a cap convention (laws.dynamic_cap). Computed with
                structural.D, scaled to integers by the law's common denominator so pair differences are exact.
  pair sign     sign of E[D_h(A)] - E[D_h(A')] as h runs over CAPS (uncapped last). Positive means A leaves more
                seconds unfilled, so A' is the better menu at that cap.
  reversal      a change of the strict sign along CAPS (ties skipped); the reversal point is the first cap at
                which the new sign appears.
  magnitude     for a reversing pair, min(largest lead of A, largest lead of A') in seconds per break: the
                reversal is as large as its smaller side.
  stable cap    least h in 1..20 with E[D_h] equal to its uncapped value (Proposition 2: the mean equals its
                limit exactly from max_T l(p(T)) on); None if above 20.

Checks of the reversal map (labels P1 to P4 here name checks, not pod policies; x4_summary.json keys p1 to p4):
  (P1) every reversal point lies at or below max(stable cap of A, stable cap of A') (Proposition 2).
  (P2) limit sign from the lattice floor: when every target of the law has uncapped undershoot T mod g for both
       menus ("filled"), the limit mean is sum_T w(T) (T mod g) (Proposition 1(b, e); exact remainders averaged
       for incomplete periods).
  (P3) a coarse reversal predictor: at low caps the menu with the larger longest part wins (cap regime,
       D_h(T) = T - h d for T > h d, Proposition 1(c)), at the limit the lattice floor decides (P2); a reversal is
       predicted when the two disagree. This one can fail and is reported as a confusion matrix.
  (P4) Corollary 4 on exact window totals in reduced units, where its hypotheses hold and both sets are at
       equality levels (criterion_check).
"""
from fractions import Fraction
from math import gcd
from functools import reduce

from . import structural
from . import engines as E
from .laws import dynamic_cap
from .numeric import xsum

CAPS = tuple(range(1, 21)) + (None,)


def cap_label(h):
    return "unc" if h is None else str(h)


def mstr(m):
    return "{" + ",".join(str(a) for a in m) + "}"


def law_denominator(law):
    return reduce(lambda x, y: x * y // gcd(x, y), [w.denominator for _, w in law.support], 1)


def floor_values(menu, law, conv, caps=CAPS):
    """{h: Fraction E[D_h(menu;T)]} exactly."""
    A = tuple(sorted(menu))
    out = {}
    for h in caps:
        out[h] = xsum((w * structural.D(A, dynamic_cap(h, st, conv), T) for (T, st), w in law.support),
                     Fraction(0))
    return out


def stable_cap(vals, caps=CAPS):
    lim = vals[None]
    for h in caps:
        if h is not None and vals[h] == lim:
            return h
    return None


def lattice_floor(menu, law):
    """sum_T w(T) (T mod g): the limit mean when every target is filled to T mod g (Proposition 1(b, e))."""
    g = structural.menu_gcd(menu)
    return xsum((w * (T % g) for (T, st), w in law.support), Fraction(0))


def filled(menu, law, conv):
    """True if every target of the law has uncapped undershoot T mod g."""
    g = structural.menu_gcd(menu)
    A = tuple(sorted(menu))
    return all(structural.D(A, dynamic_cap(None, st, conv), T) == T % g for (T, st), _ in law.support)


def sgn(x, tol=0):
    if x > tol:
        return 1
    if x < -tol:
        return -1
    return 0


def reversal_info(caps, diffs, tol=0):
    """diffs[i] = E_A - E_A' at caps[i]. Returns dict with the sign string, reversal points, number of changes,
    leads (largest amount by which A beats A', and A' beats A) and magnitude (0 if no reversal)."""
    signs = [sgn(x, tol) for x in diffs]
    points = []
    last = 0
    for h, s in zip(caps, signs):
        if s != 0:
            if last != 0 and s != last:
                points.append(h)
            last = s
    lead_a = max([-x for x in diffs if -x > tol] or [0])
    lead_b = max([x for x in diffs if x > tol] or [0])
    first = next((s for s in signs if s), 0)
    return dict(signs="".join("+" if s > 0 else "-" if s < 0 else "0" for s in signs), points=points,
                n_changes=len(points), lead_a=lead_a, lead_b=lead_b,
                magnitude=min(lead_a, lead_b) if points else 0, first_sign=first, limit_sign=signs[-1])


def lattice_rule_sign(mA, mB, ell):
    """Sign predicted by 'menus on one unshifted lattice rank by g - gcd(g, l)' (complete periods)."""
    gA, gB = structural.menu_gcd(mA), structural.menu_gcd(mB)
    return sgn((gA - gcd(gA, ell)) - (gB - gcd(gB, ell)))


# --------------------------------------------------------------------------- Corollary 4 check

def _semigroup(gens):
    """(gap set, conductor) of the numerical semigroup generated by gens (gcd 1), via engine E-C."""
    gp = E.engine_c.gaps(sorted(set(gens)))
    return set(gp), (max(gp) + 1 if gp else 0)


def _up_dist(gapset, y):
    j = 0
    while (y + j) in gapset:
        j += 1
    return j


def mass(gapset):
    """M(S) = sum over gaps y of o(y) = min{j >= 0: y + j in S} (equals the downward mass by run symmetry)."""
    return xsum(_up_dist(gapset, y) for y in gapset)


def reduced(menu):
    g, A0 = E.common.normalize(menu)
    return g, tuple(A0)


def _sumset_bits(A0, h, N):
    """Set of n in [0, N] that are sums of at most h parts of A0 \\ {0} (i.e. hA0 with 0 in A0)."""
    m = structural.min_parts(tuple(a for a in A0 if a > 0), N)
    return [m[n] <= h for n in range(N + 1)]


def _I_h(S1gaps, S2gaps, h, d):
    N = h * d
    return [(n not in S1gaps) and ((N - n) not in S2gaps) for n in range(N + 1)]


def _window_total(A0, h, lo, hi):
    """sum_{n=lo}^{hi} D_h(A0; n) in reduced units."""
    m = structural.min_parts(tuple(a for a in A0 if a > 0), hi)
    last = 0
    tot = 0
    for n in range(hi + 1):
        if m[n] <= h:
            last = n
        if n >= lo:
            tot += n - last
    return tot


def criterion_case(A0, c, h):
    """One (A0, c, h) case of Corollary 4 in reduced units. Returns a dict with the hypotheses, the three
    window totals, the predicted values at equality levels and the signs; None if hd < c1 + c2."""
    d = max(A0)
    S1g, c1 = _semigroup([a for a in A0 if a > 0])
    S2gens = [d - a for a in A0 if a != d]
    S2g, c2 = _semigroup(S2gens)
    if h * d < c1 + c2:
        return None
    A1 = tuple(sorted(set(A0) | {c}))
    S1g1, _ = _semigroup([a for a in A1 if a > 0])
    S2g1, _ = _semigroup(S2gens + [d - c])
    lo, hi = c1, h * d
    tot_new_h = _window_total(A1, h, lo, hi)
    tot_old_h1 = _window_total(A0, h + 1, lo, hi)
    tot_old_h = _window_total(A0, h, lo, hi)
    eq_new_h = _sumset_bits(A1, h, h * d) == _I_h(S1g1, S2g1, h, d)
    eq_old_h1 = _sumset_bits(A0, h + 1, (h + 1) * d) == _I_h(S1g, S2g, h + 1, d)
    eq_old_h = _sumset_bits(A0, h, h * d) == _I_h(S1g, S2g, h, d)
    M2, M2n = mass(S2g), mass(S2g1)
    omega = xsum(_up_dist(S2g, y) for y in range(d))
    return dict(d=d, c1=c1, c2=c2, h=h, W_lo=lo, W_hi=hi, tot_add_c_at_h=tot_new_h, tot_cap_plus_1=tot_old_h1,
                tot_base_h=tot_old_h, M_S2=M2, M_S2new=M2n, omega=omega, eq_new_h=eq_new_h, eq_old_h1=eq_old_h1,
                eq_old_h=eq_old_h, predicted_sign=sgn(M2n - (M2 - omega)),
                computed_sign=sgn(tot_new_h - tot_old_h1))


def criterion_check(menus, adds, n_h=4):
    """For each physical menu, each added duration c in adds with g | c, c < max(menu), c not in menu (so the
    gcd is unchanged and 0 < c/g < d), and the n_h least caps with h d >= c1 + c2: compare exact window totals
    with the corollary. Returns (rows, stats). At equality levels for A0' at h and A0 at h + 1 the identities
    sum_W D'_h = M(S2'), sum_W D_{h+1} = M(S2) - omega must hold and the computed sign must equal the predicted
    sign; sum_W D_h = M(S2) is checked where A0 is at an equality level at h. Cases off equality levels are
    counted but not compared (the corrections Psi off equality levels are not implemented here)."""
    rows = []
    st = dict(cases=0, at_equality=0, off_equality=0, identity_mismatch=0, sign_mismatch=0, base_identity_checks=0,
              base_identity_mismatch=0, h_dependent_pairs=0, pairs=0, add_c_wins=0, cap_wins=0, ties=0)
    for menu in menus:
        g, A0 = reduced(menu)
        d = max(A0)
        _, c1 = _semigroup([a for a in A0 if a > 0])
        _, c2 = _semigroup([d - a for a in A0 if a != d])
        h0 = max(1, -(-(c1 + c2) // d))
        for cphys in adds:
            if cphys in menu or cphys % g or cphys // g >= d:
                continue
            c = cphys // g
            st["pairs"] += 1
            seen = set()
            for h in range(h0, h0 + n_h):
                r = criterion_case(A0, c, h)
                st["cases"] += 1
                ok_eq = r["eq_new_h"] and r["eq_old_h1"]
                r.update(menu=mstr(menu), g=g, A0=mstr(A0), c_seconds=cphys, c=c)
                if ok_eq:
                    st["at_equality"] += 1
                    idm = (r["tot_add_c_at_h"] != r["M_S2new"]) or (r["tot_cap_plus_1"] != r["M_S2"] - r["omega"])
                    sm = r["computed_sign"] != r["predicted_sign"]
                    st["identity_mismatch"] += int(idm)
                    st["sign_mismatch"] += int(sm)
                    seen.add(r["computed_sign"])
                    r["identity_ok"] = not idm
                    r["sign_ok"] = not sm
                else:
                    st["off_equality"] += 1
                    r["identity_ok"] = ""
                    r["sign_ok"] = ""
                if r["eq_old_h"]:
                    st["base_identity_checks"] += 1
                    st["base_identity_mismatch"] += int(r["tot_base_h"] != r["M_S2"])
                rows.append(r)
            if len(seen) > 1:
                st["h_dependent_pairs"] += 1
            if len(seen) == 1:
                s = seen.pop()
                st["add_c_wins" if s < 0 else "cap_wins" if s > 0 else "ties"] += 1
    return rows, st


def family_tot(menu, h):
    """Tot(h) = sum_{n=0}^{hd} D_h(A0; n) in reduced units (Example 6)."""
    g, A0 = reduced(menu)
    d = max(A0)
    return _window_total(A0, h, 0, h * d)
