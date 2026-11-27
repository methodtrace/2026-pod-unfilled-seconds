"""Exact values for the accounting-identity decomposition (decompose.py) at rho = 1, for one menu over many
laws, conventions, caps and demand scenarios at once (X1, X3, the demand sweep, full tier): E[U] of the actual
pool (levers.MenuExpect, forward DP over durations with merged reachability states) and the four structural
values at unlimited demand, exact Fractions: D_h(A), D_inf(A), D_h(R), D_inf(R), R the range of lengths.
Keys of U: frozenset() = actual pool; {dem}, {dem, cap}, {arith, dem}, {arith, cap, dem} = the structural
values. Agrees with exact.combos_for (tests)."""
from fractions import Fraction

from . import structural
from .exact import TMAX
from .laws import dynamic_cap
from .levers import MenuExpect, law_parts_by_count
from .numeric import xsum

N = frozenset


def needed_caps(caps, convs):
    out = set()
    for h in caps:
        for conv in convs:
            for st in (0, 1, 2):
                c = dynamic_cap(h, st, conv)
                if c is not None:
                    out.add(c)
    return sorted(out)



def menu_values(menu, laws_dict, lawconvs, caps, means_list, me=None):
    """{(law, conv, h, s): dict(U={S: value}, ET=Fraction, P_struct_pos=Fraction)}; s indexes means_list and
    s = len(means_list) is demand unlimited (values exact Fractions). A prebuilt levers.MenuExpect for the same
    menu, laws and scenarios (with at least the needed caps) may be passed as me."""
    menu = tuple(sorted(menu))
    for law in laws_dict.values():
        if law.Tmax > TMAX:
            raise ValueError("law %s reaches %d s > TMAX %d; set PODSIM_TMAX" % (law.name, law.Tmax, TMAX))
    convs = sorted({c for _, c in lawconvs})
    kcaps = needed_caps(caps, convs)
    rng = structural.range_menu(menu)
    parts = {name: law_parts_by_count(law) for name, law in laws_dict.items()}
    if me is None:
        me = MenuExpect(menu, means_list, laws_dict, caps=kcaps or [1]) if means_list else None
    # exact demand-unlimited pieces per law, number of structured spots and cap
    struct = {}
    for name, law in laws_dict.items():
        for st in parts[name]:
            sup = [(T, w) for (T, s_), w in law.support if int(s_) == st]
            for c in sorted(set(dynamic_cap(h, st, cv) for h in caps for cv in convs), key=lambda x: (x is None, x)) + [None]:
                if (name, c, st) in struct:
                    continue
                d1 = xsum((w * structural.D(menu, c, T) for T, w in sup), Fraction(0))
                d2 = xsum((w * structural.D(rng, c, T) for T, w in sup), Fraction(0))
                pos = xsum((w for T, w in sup if structural.D(menu, c, T) > 0), Fraction(0))
                struct[(name, c, st)] = (d1, d2, pos)
    out = {}
    S = len(means_list)
    for name, conv in lawconvs:
        law = laws_dict[name]
        ET = xsum((w * T for (T, _), w in law.support), Fraction(0))
        pc = parts[name]
        for h in caps:
            cs = {st: dynamic_cap(h, st, conv) for st in pc}

            def sp(i, cs=cs):
                return xsum((struct[(name, cs[st], st)][i] for st in pc), Fraction(0))

            def spu(i):
                return xsum((struct[(name, None, st)][i] for st in pc), Fraction(0))
            base = {N(["dem"]): sp(0), N(["dem", "cap"]): spu(0), N(["arith", "dem"]): sp(1),
                    N(["arith", "cap", "dem"]): spu(1)}
            pos = sp(2)
            for s in range(S + 1):
                U = dict(base)
                U[N()] = base[N(["dem"])] if s == S else me.U(name, conv, h, s)
                out[(name, conv, h, s)] = dict(U=U, ET=ET, P_struct_pos=pos)
    return out
