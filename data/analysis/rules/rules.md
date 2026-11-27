# Configuration rules: coverage on the full tier

Exact structural quantities (demand unlimited, readiness 1) for 86 menus and 25 law-convention pairs (2150 menu-law cells), caps 1 to 20 and uncapped, recomputed from the simulator package and equal to the tier's own table in all 45150 cells checked. Definitions in code/analysis_rules.py.

## Rule 1. Feasibility

A pod of at most k ads of at most M seconds reaches at most kM seconds, so a break longer than kM leaves at least T - kM unsold whatever the demand. Share of menu-law cells with any such shortfall, and the share of the structural floor that is this certain shortfall, by nominal cap:

| h | cells with shortfall | shortfall share of floor (pooled) |
| --- | --- | --- |
| 1 | 2121 of 2150 (98.7%) | 99.1% |
| 2 | 2084 of 2150 (96.9%) | 96.7% |
| 3 | 2045 of 2150 (95.1%) | 93.9% |
| 4 | 1554 of 2150 (72.3%) | 90.6% |
| 5 | 1367 of 2150 (63.6%) | 87.7% |
| 6 | 975 of 2150 (45.3%) | 85.9% |
| 7 | 875 of 2150 (40.7%) | 84.4% |
| 8 | 593 of 2150 (27.6%) | 82.0% |
| 9 | 519 of 2150 (24.1%) | 79.6% |
| 10 | 476 of 2150 (22.1%) | 76.4% |
| 11 | 476 of 2150 (22.1%) | 72.4% |
| 12 | 304 of 2150 (14.1%) | 67.9% |
| 13 | 258 of 2150 (12.0%) | 63.5% |
| 14 | 248 of 2150 (11.5%) | 58.8% |
| 15 | 232 of 2150 (10.8%) | 53.8% |
| 16 | 142 of 2150 (6.6%) | 48.9% |
| 17 | 124 of 2150 (5.8%) | 44.4% |
| 18 | 105 of 2150 (4.9%) | 40.2% |
| 19 | 102 of 2150 (4.7%) | 36.3% |
| 20 | 96 of 2150 (4.5%) | 32.5% |

Per law and convention (the pooled share is dominated by long-break laws): shortfall share of the floor at h = 3 and h = 6, summed over menus.

| law | h = 3 | h = 6 |
| --- | --- | --- |
| L1 | 97.9% | 96.7% |
| L2 (a) | 91.2% | 83.5% |
| L2 (b) | 95.3% | 84.1% |
| L2s1530 (a) | 94.7% | 91.5% |
| L2s1530 (b) | 97.2% | 90.7% |
| L2s510 (a) | 90.7% | 81.9% |
| L2s510 (b) | 95.0% | 82.9% |
| L2s60 (a) | 93.5% | 95.6% |
| L2s60 (b) | 96.9% | 95.0% |
| L2s7812 (a) | 90.8% | 79.4% |
| L2s7812 (b) | 95.2% | 81.7% |
| L2two (a) | 89.5% | 81.6% |
| L2two (b) | 97.7% | 85.1% |
| L3s | 78.7% | 62.4% |
| L3u | 92.6% | 81.6% |
| L4s15 | 87.8% | 84.6% |
| L4s5 | 81.9% | 73.4% |
| L4u15 | 96.4% | 93.6% |
| L4u5 | 94.0% | 87.3% |
| L5 | 94.1% | 84.9% |
| L6 | 12.5% | 2.1% |
| L7 | 100.0% | 94.4% |
| L8q25 | 94.7% | 91.1% |
| L8q50 | 89.6% | 82.4% |
| L8q75 | 80.4% | 66.9% |

By the menu's longest duration M (menus with M <= 20 s are unlikely live-CTV offers and dominate the pooled share): pooled shortfall share, cells with a shortfall, and the median per-cell share (floor > 0).

| h | M class | menus | pooled share | cells with shortfall | median per-cell share |
| --- | --- | --- | --- | --- | --- |
| 3 | M >= 30 s | 66 | 89.5% | 1555 of 1650 | 90.0% |
| 3 | M <= 20 s | 20 | 99.8% | 490 of 500 | 100.0% |
| 4 | M >= 30 s | 66 | 80.8% | 1070 of 1650 | 68.2% |
| 4 | M <= 20 s | 20 | 99.6% | 484 of 500 | 100.0% |
| 6 | M >= 30 s | 66 | 56.5% | 494 of 1650 | 0.0% |
| 6 | M <= 20 s | 20 | 99.2% | 481 of 500 | 99.8% |
| 8 | M >= 30 s | 66 | 25.6% | 112 of 1650 | 0.0% |
| 8 | M <= 20 s | 20 | 98.6% | 481 of 500 | 99.6% |

## Rule 2. Cap regime

h* = least cap at which the floor equals the uncapped floor. Distribution of h* over the 86 menus, by law (quartiles and max):

| law | h* q1 / median / q3 / max | floor minus the rule-1 shortfall at h = 3, 4, 6 (contains the lattice floor; median over menus, s per break) |
| --- | --- | --- |
| L1 | 6 / 8 / 10 / >20 (4 menus never within caps 1 to 20) | 0.0, 0.0, 0.0 |
| L2 (a) | 7 / 9 / 12 / >20 (4 menus never within caps 1 to 20) | 2.1, 2.7, 1.4 |
| L2 (b) | 8 / 10 / 13 / >20 (4 menus never within caps 1 to 20) | 1.9, 2.1, 2.0 |
| L2s1530 (a) | 6 / 8 / 12 / >20 (4 menus never within caps 1 to 20) | 0.7, 1.0, 0.0 |
| L2s1530 (b) | 7 / 9 / 13 / >20 (4 menus never within caps 1 to 20) | 0.6, 0.7, 0.8 |
| L2s510 (a) | 7 / 9 / 12 / >20 (4 menus never within caps 1 to 20) | 2.4, 3.8, 1.5 |
| L2s510 (b) | 8 / 10 / 13 / >20 (4 menus never within caps 1 to 20) | 2.5, 2.4, 2.5 |
| L2s60 (a) | 4 / 6 / 8 / >20 (1 menus never within caps 1 to 20) | 0.0, 0.0, 0.0 |
| L2s60 (b) | 5 / 7 / 9 / >20 (1 menus never within caps 1 to 20) | 0.0, 0.0, 0.0 |
| L2s7812 (a) | 6 / 9 / 12 / >20 (4 menus never within caps 1 to 20) | 2.5, 4.0, 2.9 |
| L2s7812 (b) | 7 / 10 / 13 / >20 (4 menus never within caps 1 to 20) | 2.4, 2.5, 3.2 |
| L2two (a) | 7 / 9 / 12 / >20 (4 menus never within caps 1 to 20) | 2.3, 2.2, 1.2 |
| L2two (b) | 9 / 11 / 14 / >20 (4 menus never within caps 1 to 20) | 1.6, 1.8, 2.2 |
| L3s | 7 / 9 / 13 / >20 (4 menus never within caps 1 to 20) | 4.7, 3.5, 2.0 |
| L3u | 7 / 9 / 13 / >20 (4 menus never within caps 1 to 20) | 2.8, 3.3, 2.5 |
| L4s15 | 6 / 8 / 12 / >20 (4 menus never within caps 1 to 20) | 0.8, 0.7, 0.0 |
| L4s5 | 7 / 9 / 12 / >20 (4 menus never within caps 1 to 20) | 3.3, 2.3, 1.2 |
| L4u15 | 6 / 8 / 12 / >20 (4 menus never within caps 1 to 20) | 0.4, 0.8, 0.0 |
| L4u5 | 7 / 9 / 12 / >20 (4 menus never within caps 1 to 20) | 1.9, 2.2, 1.3 |
| L5 | 9 / 11 / 15 / >20 (9 menus never within caps 1 to 20) | 2.7, 3.0, 3.1 |
| L6 | 3 / 4.5 / 6 / 11 | 3.9, 2.5, 2.0 |
| L7 | 10 / 13 / 18 / >20 (14 menus never within caps 1 to 20) | 0.0, 0.0, 2.7 |
| L8q25 | 6 / 8 / 12 / >20 (4 menus never within caps 1 to 20) | 1.4, 1.1, 0.6 |
| L8q50 | 6 / 8 / 12 / >20 (4 menus never within caps 1 to 20) | 2.6, 2.1, 1.1 |
| L8q75 | 6 / 8 / 12 / >20 (4 menus never within caps 1 to 20) | 3.5, 2.8, 1.6 |

Cap cost: E[D_h - D_inf] is everything the cap costs relative to no cap (it includes rule 1); the cap's loss beyond both lower bounds is E[D_h - max(D_inf, (T - kM)^+)], exact per target. Median over menu-law cells, range of per-law medians, seconds per break:

| h | cap cost, all menus | beyond both bounds, all menus | cap cost, M >= 30 s | beyond both bounds, M >= 30 s |
| --- | --- | --- | --- | --- |
| 3 | 35.65 (1.37 to 163.02) | 0.57 (0.00 to 1.75) | 25.71 (0.54 to 163.02) | 1.43 (0.00 to 3.01) |
| 4 | 15.71 (0.10 to 118.02) | 0.48 (0.00 to 2.14) | 10.71 (0.00 to 118.02) | 1.14 (0.00 to 3.57) |
| 6 | 2.90 (0.00 to 36.57) | 0.00 (0.00 to 1.03) | 0.92 (0.00 to 33.39) | 0.15 (0.00 to 2.48) |
| 8 | 0.06 (0.00 to 8.46) | 0.00 (0.00 to 0.19) | 0.00 (0.00 to 3.31) | 0.00 (0.00 to 0.40) |

## Rules 3 to 5. Lattice floor, hybrid remainders, live mix

Past the conductor a target misses exactly T mod g, so the uncapped floor equals E[T mod g] plus the excess of targets below the conductor. Cells where the uncapped floor is within 0.1 s of E[T mod g], by law family; the rest have targets below the conductor (mass shown).

| law family | cells | within 0.1 s of E[T mod g] | largest gap (s) | median mass below conductor where off |
| --- | --- | --- | --- | --- |
| irregular uniform (L3u, L6, L7) | 258 | 229 (88.8%) | 14.67 | 0.46 |
| irregular skewed and binned (L3s, L5) | 172 | 151 (87.8%) | 2.68 | 0.05 |
| lattice laws (L4) | 344 | 332 (96.5%) | 2.57 | 0.32 |
| grid (L1) | 86 | 86 (100.0%) | 0.00 | - |
| hybrid remainders (L2, L2s*, L2two) | 1032 | 922 (89.3%) | 4.30 | 0.15 |
| live mix (L8q25, L8q50, L8q75) | 258 | 233 (90.3%) | 5.56 | 0.16 |

Closed form (g - 1)/2 on irregular uniform breaks: cells within 0.1 s of (g - 1)/2, by law, among menus whose conductor is at or below the law's shortest break:

| law | breaks | menus above conductor | within 0.1 s of (g - 1)/2 | all menus within 0.1 s |
| --- | --- | --- | --- | --- |
| L3u | uniform [60, 240] | 82 | 82 | 83 of 86 |
| L6 | uniform [15, 60] | 48 | 34 | 46 of 86 |
| L7 | uniform [240, 360] | 86 | 85 | 85 of 86 |

Floor by gcd (uncapped, irregular uniform [60, 240], all menus): g = 1: 0.00, 0.02 s (11 menus); g = 2: 0.50 s (7 menus); g = 3: 0.99 s (7 menus); g = 5: 1.99, 2.68 s (39 menus); g = 6: 2.49 s (3 menus); g = 10: 4.48 s (8 menus); g = 15: 6.96, 8.20 s (9 menus); g = 20: 9.45 s (1 menus); g = 30: 14.42 s (1 menus).

Hybrid remainders T = B - S (B on the 30 s grid, S uniform on the spot set): when g divides 30 the lattice term is E[(-S) mod g], so spots on the menu's lattice add nothing and off-lattice spots add their residue. Predicted E[(-S) mod g] and the menus (convention a; the uncapped floor does not depend on the convention) whose uncapped floor matches it within 0.1 s, among menus with that gcd:

| spot set | g = 1 | g = 2 | g = 3 | g = 5 | g = 6 | g = 10 | g = 15 | g = 30 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| {5, 10, 15, 20, 45} | 0.00: 10 of 11 | 0.60: 7 of 7 | 0.80: 4 of 7 | 0.00: 32 of 39 | 2.60: 3 of 3 | 3.00: 6 of 8 | 5.00: 6 of 9 | 17.00: 1 of 1 |
| {15, 30} | 0.00: 11 of 11 | 0.50: 7 of 7 | 0.00: 7 of 7 | 0.00: 37 of 39 | 1.50: 3 of 3 | 2.50: 8 of 8 | 0.00: 8 of 9 | 7.50: 1 of 1 |
| {5, 10} | 0.00: 11 of 11 | 0.50: 7 of 7 | 1.50: 7 of 7 | 0.00: 36 of 39 | 1.50: 3 of 3 | 2.50: 8 of 8 | 7.50: 8 of 9 | 22.50: 1 of 1 |
| {7, 8, 12} | 0.00: 11 of 11 | 0.33: 7 of 7 | 1.00: 7 of 7 | 2.67: 37 of 39 | 3.00: 3 of 3 | 4.33: 8 of 8 | 6.00: 8 of 9 | 21.00: 1 of 1 |
| {60} | 0.00: 11 of 11 | 0.00: 7 of 7 | 0.00: 7 of 7 | 0.00: 37 of 39 | 0.00: 3 of 3 | 0.00: 8 of 8 | 0.00: 8 of 9 | 0.00: 1 of 1 |

Two spots (L2two, S1 + S2 <= B): see the E[T mod g] coverage above; the remainder's lattice term follows the sum of the two spots in the same way.

Live mix: the uncapped floor is exactly linear in the stoppage share q in 86 of 86 menus (q = 0.25, 0.5, 0.75; exact rational check).

## Rule 6. Levers at demand unlimited

Below h* (18734 menu-law-cap cells with a positive best gain): raising the cap is the best lever or ties in 5089 (27.2%); only added durations longer than the menu's longest part are best in 9878 (52.7%); only shorter ones in 3333 (17.8%); a longer and a shorter added duration tie exactly in 434 (2.3%).

At or above h* the cap no longer matters. Prediction 'an added duration helps if and only if it lowers the gcd' over every (menu, law, cap, added duration): helps and predicted 43316, predicted but no gain 15845, gain but not predicted 7666, neither 71130 (precision 0.732, recall 0.850). On irregular uniform laws: 7205, 0, 1051, 8531. A gain without a gcd drop fills a target below the conductor (the exact criterion is the stability proposition; it is asserted on every stable target of the tier).

Restricted to cells whose every target is at or past the menu's conductor: 35657, 12858, 0, 57502 (precision 0.735, recall 1.000).

Stability proposition (exact criterion for when adding a duration helps at a stable cap), asserted by the tier: 238875 (menu, law, cap, duration) cases, 10349408 stable targets of 14170065, 2419079 gain targets at stable caps, no violation.

Menu-ranking reversals (designed consequence): 44248 of 91375 pair-law cells reverse at least once along the caps (x4/summary.md).

## Rule 7. Practice

From the tier's X6 summary (sampled; full grid of 341,000 conditions on 31 menus; P1 exact seconds-max, P2 exact revenue-max, P3 greedy by price per second, P3d greedy longest first, P4 first come):

- P3 versus the exact DP: mean shortfall 5.189 s against P1 (max 225.018 s) and 2.8% of revenue against P2 (max condition mean 70.1%; worst single pool 91.7%); P(revenue gap = 0) from 0.0% to 100.0% across conditions.
- P3d versus the exact DP: mean shortfall 0.275 s against P1 (max 13.091 s) and 3.0% of revenue against P2 (max condition mean 42.9%; worst single pool 96.7%); P(revenue gap = 0) from 0.0% to 100.0% across conditions.
- P4 versus the exact DP: mean shortfall 4.294 s against P1 (max 148.871 s) and 15.5% of revenue against P2 (max condition mean 78.2%; worst single pool 99.5%); P(revenue gap = 0) from 0.0% to 100.0% across conditions.
- Policy component (deliberate emptiness, same pool): mean E[S_P1 - S_P2] is 1.576 s with no floor and 0.581 s averaged over the floored conditions; it is positive with no floor at all, so revenue-max leaves seconds empty without any floor, by swapping several cheaper short ads for fewer high bids.
- Floor component (seconds-max policy; filtering removes the same creatives from both policies' pools): mean E[U_P1(f) - U_P1(none)] is 18.637 s over the floored conditions.

