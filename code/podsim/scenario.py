"""Run one block of scenarios (one law, one demand level, one weight scheme, one menu) over a range of
breaks, for several caps and readiness levels at once (they share every random draw). Per break it records
the accounting-identity parts (decompose.py) so their means verify the exact tables."""
import time

from . import pools as P
from .decompose import Stat, pods_for_break, struct_split, identity_parts


def run_block(master, law, menu, lam, scheme, hs, rhos, conv, n_breaks, vlaw=None, start=0):
    vlaw = vlaw or P.ValueLaw()
    w = P.weights(scheme)
    Tmax = law.Tmax
    kpool = P.kneed_for(Tmax)
    stats = {(h, rho): Stat() for h in hs for rho in rhos}
    t0 = time.time()
    for i in range(start, start + n_breaks):
        T, structured = P.break_target(master, law, i)
        pools_by_dur = {}
        for a in menu:
            pools_by_dur[a] = P.duration_stream(master, i, a, lam * w[a], kpool, vlaw)
        pods = pods_for_break(T, structured, menu, hs, conv, pools_by_dur)
        for h in hs:
            ps, pr = pods[(h, "pool")]
            V = {k: T - pods[(h, k)][0].seconds for k in ("dem", "dem_ar", "dem_cap", "dem_arcap")}
            sp = struct_split(V["dem"], V["dem_ar"], V["dem_cap"], V["dem_arcap"])
            u_r1 = T - ps.seconds
            for rho in rhos:
                ip = identity_parts(u_r1, V["dem"], T, rho)
                vals = {"T": T, "U": T - ps.ready_seconds(rho), "U_r1": u_r1, "Ustruct": V["dem"],
                        "demand": ip["demand"], "readiness": T - ps.ready_seconds(rho) - u_r1,
                        "arith": sp["arith"], "cap": sp["cap"], "residual": sp["residual"], "I_AC": sp["I_AC"],
                        "U_revpol": T - pr.ready_seconds(rho), "rev_secpol": ps.ready_revenue(rho),
                        "rev_revpol": pr.ready_revenue(rho), "ads": ps.n_ads}
                stats[(h, rho)].add(vals, cross_pairs=[("Ustruct", "U"), ("Ustruct", "U_r1")])
    return stats, time.time() - t0
