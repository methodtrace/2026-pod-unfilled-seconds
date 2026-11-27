# podsim: design of the pod simulator

Python 3.9 or newer, standard library only (numpy is not used; matplotlib draws the figures and nothing else).
The platforms on which results were checked to be identical are listed in README.md (Python versions).

This file describes the model as the code implements it, the source of every design choice (a cited
specification or industry figure, a model definition, or a synthetic value), and the implementation choices
the code makes, each with its reason.

## Layout

| Path | What it does |
| --- | --- |
| `podsim/engines.py` | Imports the exact undershoot engines of the undershoot companion (the paper on undershoot of h-fold sumsets) from `vendor/sumset-undershoot` (override the location with `UNDERSHOOT_ENGINES`). Hashes every imported file and refuses to run if any differs from `vendor/sumset-undershoot/ENGINES.sha256`. |
| `podsim/structural.py` | Structural floor D_h(A;T) by a direct bounded DP (least number of parts); exact means over a pmf; least cap for a window; cross-check against engines E-A and E-B. |
| `podsim/pod.py` | Pod construction for a finite pool of distinct creatives, both policies: `dp_select` (exact DP over (seconds used, ads used), the reference), `select_menu` (faster exact method used in runs), `select_elastic` (arithmetic relaxation with elastic creatives) and brute-force oracles. |
| `podsim/laws.py` | Break-length laws as exact pmfs (L1 to L8 and the hybrid families H2 and H3); the two cap conventions. |
| `podsim/pools.py` | Poisson creative supply, value law, floor, readiness draws, demand-relaxation extras; seeding for common random numbers. |
| `podsim/exact.py`, `podsim/grid.py`, `podsim/levers.py` | Exact expectations over the break law and the truncated count laws (Poisson or negative binomial): reachability profiles, the forward DP over durations, per-menu tables for many laws, caps and demand scenarios at once. |
| `podsim/decompose.py` | Accounting identity (structural, demand, readiness), the two-player split of the structural floor (arithmetic, cap, range residual), the arithmetic-cap interaction, pods per break for the sampled verifier, running statistics. |
| `podsim/scenario.py` | One block of sampled breaks for one (law, menu, lambda, weights, convention), all caps and readiness levels on shared draws (the Monte Carlo verifier of the exact tables). |
| `podsim/eligibility.py` | Range lever at finite demand: eligibility of fixed-length creatives of the other lengths in [min A, max A], sampled with standard errors under the declared nonstandard supply. |
| `podsim/demand.py` | Demand sweep (fine lambda grid, negative binomial counts) and readiness by creative age. |
| `podsim/reversal.py` | Menu-ranking reversal map (X4). |
| `podsim/clutter.py`, `podsim/hullchecks.py` | Value-cardinality hulls and the seller optimum under a per-ad clutter cost (X5); the knapsack companion's necessary conditions on hull pairs. |
| `podsim/revenue.py`, `podsim/greedy.py` | Value laws, floors and both exact policies on one pool (X6); greedy baselines and the dominance check. |
| `podsim/ticks.py` | Integer seconds against 90 kHz ticks (X7). |
| `podsim/x0.py`, `run_x0.py` | X0: regression checks against two tables of fixed reference values. Writes `x0_report.md`. |
| `podsim/checks.py`, `run_checks.py` | Consistency checks (structural floor against the engines, pods against brute force, stability criterion, non-CM tau bound). Writes `checks_report.md`, `checks.json`. |
| `podsim/numeric.py` | `xsum`: `math.fsum` for float totals, exact builtin sum for integers and Fractions; `nondominated`, the tie rule for lever rankings. |
| `podsim/registry.py` | Scenario catalog, tiers, deterministic writers, unit cache and code hash. |
| `tests/` | The unit tests: `python3 -m unittest` from `code/` (about a minute). |

Run order for a quick look: `python3 -m unittest && python3 run_x0.py && python3 run_checks.py`. A whole tier:
`sh code/run_all.sh --tier quick|narrow|full` (see Tiered runner below).

## Model as implemented

- Target T (integer seconds) = poddur of the dynamic portion. Menu A = rqddurs. Cap h = maxseq.
- Filled seconds F = max sum c_a a subject to sum c_a a <= T, sum c_a <= h, 0 <= c_a <= n_a. Each creative is
  used at most once.
- Structural floor U_struct(T) = D_h(A;T) = T - max(hA0 intersect [0, T]), A0 = A u {0}. The sampled simulator
  asserts on every break that the demand-relaxed seconds-max pod at rho = 1 leaves exactly D_h(A;T) unfilled.
- Readiness: after selection, each selected creative is ready at the deadline if and only if its pre-drawn
  uniform u is below rho (the definition of the DAI timing companion, the paper on trigger timing and deadline
  readiness in dynamic ad insertion); an unready creative becomes fallback and its seconds count as unfilled.
- Policies: seconds-max (ties broken by revenue) and revenue-max (ties broken by seconds). The decomposition uses
  the seconds-max policy; the sampled simulator also records the revenue policy per break (`U_revpol`,
  `rev_revpol`). X6 adds greedy baselines (P3, P3d, P4).
- Decomposition: the exact accounting identity U = (T - F_inf) + (F_inf - F_n) + (1 - rho) F_n = structural +
  demand + readiness, F_inf the fill at unlimited demand and F_n the fill of the actual pool; no ordering choice
  is involved. The structural floor splits at unlimited demand by a two-player Shapley value over arith (A
  replaced by every integer in [min A, max A], creatives available at every length) and cap (h unbounded) into
  arith_part + cap_part + range_residual (= D_inf of the range).
- Arithmetic-cap interaction: I_AC = V() - V(arith) - V(cap) + V(arith, cap) at unlimited demand, V the
  structural floor under the relaxations. Positive: substitutes; negative: complements.
- Hybrid caps: convention a (OpenRTB signaling) applies maxseq = h to the dynamic remainder; convention b (the
  knapsack companion, the paper on two-capacity knapsack conditions for value-cardinality hulls) counts each
  structured spot toward K = h, so a remainder after n structured spots gets max(0, h - n). A break with no
  structured portion gets h under both.
- Break-length laws (podsim/laws.py): L1 grid {60, 90, ..., 240}; L2 hybrid remainder T = B - S, B from L1, S
  uniform on {5, 10, 15, 20, 45} and present with probability p (p = 1 except in X3 and X3b); L3u uniform
  integers [60, 240]; L3s discretized Beta(2, 5) on [60, 240]; L4u5, L4u15, L4s5, L4s15 the L3 laws restricted to
  5 s or 15 s lattices; L5 FreeWheel mid-roll minute bins; L6 uniform [15, 60]; L7 uniform [240, 360]; L8q25,
  L8q50, L8q75 bimodal live (L1 with probability 1 - q, stoppage breaks uniform [30, 120] with probability q).
- Law families H2 and H3 (catalog hybrid axis): H2 is L2 with S uniform on another set, {15, 30} (L2s1530),
  {5, 10} (L2s510), {7, 8, 12} (L2s7812) or {60} (L2s60), B from L1, p = 1. H3 is L2two: B from L1, an opening
  spot S1 and a closing spot S2, each uniform on {5, 10, 15, 20, 45}, independent, conditioned per B on
  S1 + S2 <= B, T = B - S1 - S2 (two structured spots, so convention b gives the remainder max(0, h - 2)).

## Design choices and their sources

| Item | Choice | Source |
| --- | --- | --- |
| Per-break model, F, D_h, structural share | as stated above | Model definition (the paper's model section) |
| Decomposition | accounting identity (structural, demand, readiness); structural floor split by a two-player Shapley value at unlimited demand | Implementation choice: a Shapley split with elastic creatives at finite demand lets the arithmetic channel absorb demand loss, so the split is taken where demand cannot enter |
| I_AC definition | V() - V(arith) - V(cap) + V(arith, cap) at unlimited demand | Implementation choice |
| Cap conventions | (a) maxseq on the dynamic portion; (b) structured spots count toward K = h | (a) OpenRTB 2.6 hybrid pod example; (b) knapsack companion |
| L1 grid {60, 90, ..., 240} | as stated | Model choice (scheduled 30 s grid) |
| L2 hybrid remainder | T = B - S, S uniform on {5, 10, 15, 20, 45}, present with probability p | Model choice; the S set and p are **synthetic** parameters |
| L3 uniform integers [60, 240] | as stated | Model choice (irregular live breaks) |
| L3 right-skewed law | discretized Beta(2, 5) on [60, 240] at bin midpoints, weight x (1 - x)^4; mean about 111 s, mode about 96 s | **Synthetic, no source** |
| L4 | L3 (uniform or skewed) restricted to multiples of 5 s or 15 s, renormalized | Model choice |
| L5 | minute-bin shares 8/32/26/10/24% for < 1, 1-2, 2-3, 3-4 and 4 or more minutes, uniform seconds inside [1, 59], [60, 119], [120, 179], [180, 239], [240, 300] | Shares: FreeWheel, The State of TV Advertising Viewer Experience (Q1 2023). Bin edges and the 300 s cut: modeling choices |
| L6, L7, L8 | uniform [15, 60]; uniform [240, 360]; stoppage breaks uniform [30, 120] with q in {0.25, 0.5, 0.75} | **Synthetic** |
| H2, H3 | S sets {15, 30}, {5, 10}, {7, 8, 12}, {60}; two spots conditioned on S1 + S2 <= B | **Synthetic** sets; the conditioning is a modeling choice |
| Menus, caps, rho values | seven study menus and the 85-menu grid (every 2- and 3-part subset of {5, 6, 10, 15, 20, 30, 45, 60} plus {10, 15, 20, 30}); caps 1 to 20 and uncapped; rho in {1, 0.99, 0.95, 0.90} | Model choice; rho values are stress values, not field rates |
| n_a ~ Poisson(lambda w_a) | as stated; negative binomial with the same means in the demand sweep | Model choice |
| Meaning of lambda | expected total distinct creatives per break over the union {5, 6, 10, 15, 20, 30, 45, 60} before the floor; a menu sees only its own durations' share | **Synthetic convention** |
| Weight schemes | over the union: balanced (1/8 each); 30-heavy (30 s gets 1/2, others share 1/2); 15-heavy (same for 15 s); short-scarce (below 15 s weight 1/4 against 1, renormalized); 15/30-dominant (0.6 on 30, 0.4 on 15, 0.02 on each other, renormalized) | **Synthetic values**; 15/30-dominant is informed by a public Wurl (2021) statement that 15 s and 30 s creatives dominate |
| Value law V1 | per-second value v (cents of CPM per second) = max(1, round(100 exp(mu + sigma Z) (a/30)^beta)), mu = ln(20/30), sigma = 0.5, beta = 0; bid = v a | **Synthetic, no source** |
| Value law V2 | as V1 with beta = -0.3 (duration premium) | **Synthetic, no source** |
| Floors | OpenRTB mincpmpersec (per-second floor) and durfloors (floor per duration range, the spec's example ranges 1-15, 16-30, 31+ s); a creative below its floor is dropped before construction | Mechanisms: OpenRTB 2.6 (Index Exchange explainer for mincpmpersec). Levels: **synthetic** sweep values |
| Readiness drawn after selection, independent with probability rho | as stated | DAI timing companion |
| Pod DP over (seconds, ads) on distinct creatives, both policies | `dp_select` is the reference; runs use the equivalent exact enumeration `select_menu`, checked equal in the tests | Implementation choice |
| Common random numbers | every relaxation, cap and rho shares the break, pool, bids and readiness draws | Implementation choice, as in the DAI timing companion |
| Seeds | `random.Random(str)`: break length from (master, law, break index); each duration's pool from (master, break index, duration) only, with the same number of creatives generated per duration for every law up to 240 s, so adding a duration to a menu leaves the other pools identical | Implementation choice |
| Exact expectations (`exact.py`, `grid.py`, `levers.py`) | X1, X2 (except the sampled range lever), X3, X3b, X4, X7 part A and the demand sweep are exact finite sums over the law of T and the truncated count laws; the Monte Carlo simulator is an independent verifier | Implementation choice (implementation choice 13) |
| Nonstandard creative lengths (range lever) | share eps = 0.01 of lambda spread over the 48 other integer lengths in [5, 60]; sweep eps in {0, 0.01, 0.05, 0.2} | Qualitative: Wurl (2021), lengths other than about 15 s and 30 s almost never occur. Levels: **synthetic** |
| Clutter cost (X5) | per-ad cost c from 0 to $20 of CPM in 12 steps; anchor A1 doubles it past 180 s, anchor A2 raises it by half when a pod mixes 15 s and 30 s creatives | Anchors: FreeWheel Viewer Experience Lab with MediaScience, Designing a Better Ad Pod (January 2024), qualitative. Multipliers and threshold reading: **synthetic** |
| Tick model (X7) | 1 s = 90,000 ticks; eps sweep from 15 ms to 0.5 s; 29.97 fps stretch delta = 90 a ticks | Clock: SCTE-35 / MPEG-TS presentation clock. The 29.97 fps stretch is **derived, not sourced** |
| Hull-pair conditions (X5) | dimension, dominance and the scalar bounds, on every simulated (full break, remainder) pair | Knapsack companion |

## Implementation choices

1. **Cap convention of X0 reference check 1.** The reference values of check 1 are reproduced in all 20 cells
   by convention a and not by convention b (for example {15, 30} at h = 4 on the remainder: 14.00 s under a,
   27.20 s under b). Both are reported in `x0_report.md`.
2. **Lattice of X0 reference check 2.** "Lattice" means the multiples of the menu gcd. This reading matches the
   reference values, the least caps stated in Appendix A of the paper and the closed form of
   Proposition 1(c); the 5 s and 15 s lattice readings do not, and `x0_report.md` tabulates them for comparison.
3. **Arithmetic relaxation.** The structural split replaces A by every integer length in [min A, max A] with
   creatives available at every length, and only at unlimited demand, so demand never enters the split. At
   finite demand the range lever is eligibility of fixed-length creatives (item 20); nothing stretches. The
   elastic pool of `pod.select_elastic` (each creative may run at any integer length in the range, bid v x run
   length) is used only by the pod checks and the tick study's sampled arm.
4. **Demand relaxation as a superset.** The relaxed pool is the real pool plus kneed fresh creatives per
   duration (`pools.kneed_for`: max(Tmax, 240) // 5, so 48 for laws up to 240 s) drawn above the floor from the
   same value law. Seconds results do not depend on the extras' values;
   revenue results do.
5. **Pool truncation.** Only the top kneed creatives per duration are generated (exact descending order
   statistics); no pod can use more, because every duration is at least 5 s, so this is exact, not an
   approximation.
6. **Readiness and the seconds policy.** The seller picks the seconds-max pod without seeing readiness. Among
   seconds-tied pods the revenue tie-break decides, so readiness interacts with bids only through that tie-break.
7. **Per-break parts in the sampled verifier.** The identity parts are computed per break and averaged; by
   linearity this equals the decomposition of expected U. Standard errors are across breaks.
8. **Standard error of the structural share** by the delta method for a ratio of means; reported as n/a when
   E[U] = 0.
9. **Common random numbers across menus.** Per-duration means are fixed over the union of durations and pools
   are seeded by (break, duration), so menus that share a duration share its creatives exactly.
10. **Stability check (`checks.json` item7).** The stable cap is per window, the maximum over T of l(p(T)) for
    both menus; it can be large on [60, 240] for menus with small parts (the largest value is in
    `checks_report.md`). The window criterion is checked at h_stab, h_stab + 1 and h_stab + 2.
11. **Non-CM tau check (`checks.json` item8).** tau is computed by direct sumsets up to h = 3d + 10 with a
    truncation guard. The undershoot engines' fan.py regularity reg(I) is reported alongside for reference.
12. **Hull-pair checks.** X5 checks the knapsack companion's necessary conditions on every simulated (full break,
    remainder) pair; a violation stops the run (`podsim/hullchecks.py`).
13. **Exact instead of sampled.** Every X1 and X3 number is an exact expectation (`podsim/exact.py`,
    `podsim/grid.py`); the Monte Carlo simulator runs 100,000 breaks on each of six verifier blocks and is
    compared with the exact values in `x1/x1_verify.json`. The reported tables carry no Monte Carlo error.
14. **Seconds-max policy in the exact tables.** The exact shortcut holds because the seconds-max fill depends only
    on the counts. Revenue-policy quantities (X6) use the sampled simulator.
15. **Readiness in closed form.** Readiness enters exactly as (1 - rho) T + rho (T - F) in expectation, because it
    is drawn after selection and independently of bids. So the readiness part (1 - rho) E[F_n] is a closed form
    of the rho = 1 table, and X6 fixes rho = 1.
16. **Precision.** Demand-unlimited sums are exact Fractions; demand-limited sums of count probabilities are in
    double precision. The forward DP over durations drops states whose probability is below a threshold (default 1e-15) in every scenario and
    returns a bound on the dropped mass (`exact.profile_dist`).
17. **Break range of X1.** L1 in X1 runs to 240 s; X0 reference check 1 uses breaks up to 180 s.
18. **Wurl-comparable slice.** The narrow-tier X1 summary reports E[U]/E[T], uncapped, no hybrid, laws L3 and
    L4, demand unlimited (pure arithmetic) and with finite 15/30-dominant demand.
19. **X2 levers are exact paired contrasts.** Each gain is a difference of two exact expectations over the same
    joint law of breaks and per-duration counts; adding a duration adds an independent count for it. The floor
    lever is not applicable (no floor in X1). The range lever at finite demand is sampled (item 20), so it is
    the one X2 gain with a standard error (`range_se`).
20. **Range lever as eligibility.** rqddurs -> [min A, max A] admits existing creatives of every other length in
    the range. Union lengths keep their scheme means; each of the 48 other integer lengths in [5, 60] has mean
    eps lambda / 48, eps = 0.01 declared, with the sweep eps in {0, 0.01, 0.05, 0.2} (X2 columns `range_e*`).
    Sampled: one uniform per (sample, length) from `random.Random("pods-range-v1|<i>")`, counts by inverse CDF
    truncated at TMAX // d, exact expectation over the break law per sample, paired with the baseline counts.
    Samples: quick 200, narrow 4,000, full 2,000 (X2) and 1,000 (demand sweep), fullsmoke 40 and 20. The sampled
    baseline is compared with the exact one in `x2/x2_meta.json` (`range_lever`). Menus must lie in the union.
21. **Rankings with sampled gains.** A lever wins when no other lever beats it by more than 1e-9 s plus two
    standard errors of the difference (`numeric.nondominated`), so a tied winning set does not depend on which
    sampled lever has the largest point estimate. X2, the X2 split and the demand sweep use this rule.
22. **X2 split.** `run_x2_split.py` splits each finite-demand winning gain into its structural part (the same
    lever's gain at unlimited demand) and a signed finite-demand residual; a winner is "structural" if any lever
    of the tied winning set has a positive structural part.
23. **Proposition 2 asserted in X2** at every target whose cap is stable for both menus (demand unlimited); a
    violation stops the run.
24. **X3b normalization.** X3b divides by the full break length B (mean of ratios); the ratio of means is the X3
    value times 60/150.
25. **X7 tick model.** Pod construction maximizes true filled ticks with creatives taken in bid order within a
    duration, so the perturbation does not steer which creative of a duration runs. Part A (systematic
    perturbations, demand unlimited) is exact; part B (independent per-creative jitter and the 29.97 fps
    stretch, lambda = 16 balanced) is Monte Carlo with paired standard errors against the integer model. The
    part A columns `phi_arith_*` and `phi_cap_*` are the two-player split of the structural floor.
26. **TMAX.** The exact engines work on targets up to `PODSIM_TMAX` seconds (240 by default; the full tier sets
    360 for L7). Results for laws inside 240 s do not depend on TMAX.
27. **Laws per spot count.** Every law is an exact pmf over (T, number of structured spots), and every exact
    routine works per spot count, so H3 (two spots) uses the same code as the one-spot laws.
28. **Demand sweep (catalog D3 and D4, `run_xd.py`).** lambda 1 to 256 in log2 steps for every weight scheme;
    negative binomial counts with the same per-duration means and dispersion k in {1, 4}. Exact by the same
    argument as for Poisson counts (the fill depends only on the counts): `exact.nb_trunc` and
    `exact.total_trunc` (convolution for the total count).
29. **Readiness by creative age (catalog R2, exact).** A share s of creatives is new, ready with probability
    rho_new; older ones with rho_old. Age is independent of everything the seller sees and readiness is drawn
    after selection, so each selected creative is ready with rho_eff = s rho_new + (1 - s) rho_old and the
    independent-readiness closed form applies at rho_eff. Age correlated with duration and a seller that sees age
    (catalog R3) are not built.
30. **Full-tier breadth.** X1, X2, X3, X3b, X4, X7 part A and the demand sweep run over all 86 menus (the seven
    study menus and the 85-menu grid); X5 and X6 run over 31 menus (the seven study menus plus 24 sampled from
    the grid with `random.Random("menu-sample-v1")`, listed in `catalog/menu_sample.csv`), every built law, caps 3
    to 12 and uncapped. `catalog/README.md` of a full-tier output lists what the tier narrows or skips.
31. **Units and cache.** Every step splits its work into units (`registry.map_units`); each unit's result is
    cached in `OUT/.cache/<tier>/<step>/<key>.json.gz` with a hash of the code (`registry.code_hash`), written
    atomically. The hash covers the package, the unit-computing `run_x*.py` scripts and the vendored engines,
    not the report scripts or documentation. An entry from other code is refused. `cluster/` runs units on
    Grid Engine or as a SLURM array and merges them into the same files.
32. **Deterministic outputs.** Floats are rounded to 9 decimals, JSON keys are sorted, gzip files carry mtime 0,
    and no file holds a timestamp or an absolute path. Timing and the code record (code hash and whole-tree
    digest) go to `timing.json` files, which manifests exclude; the manifest hash of a `.gz` file is of its
    decompressed content.
33. **Summation.** Sums are evaluated in a fixed order. Totals over a collection go through
    `podsim.numeric.xsum` (`math.fsum` for floats, correctly rounded whatever the order, and the exact builtin
    sum for integers and Fractions); `tests/test_numeric.py` checks that the package and the result-writing
    scripts call no builtin `sum()`. Accumulation loops with `+=` (for example in `podsim/exact.py`,
    `podsim/pools.py` and `podsim/levers.py`) run in a fixed order, where IEEE addition gives the same result on
    every Python version; only the builtin `sum()` of floats changed, in Python 3.12.
34. **Seed strings.** Master seeds: `pods-x1-verify-v1` (X1 verifier), `pods-range-v1` (range lever),
    `pods-x5-v1`, `pods-x6-v1`, `pods-x7-v1`; menu sample `menu-sample-v1`. Sampled results depend on these
    strings.
35. **Storage.** In the full tier every large table is written gzipped (deterministic, mtime 0), including
    `x2/split`, `x3/x3_slopes`, `x3b/x3b_slopes`, `x4/demand_pairs` and `x7/x7_partB`; the X5 comparison file
    is `x5/matched_cells.json.gz` there.

## Tiered runner

`sh code/run_all.sh --tier quick|narrow|full [--out DIR] [--check] [--jobs N] [--list]` runs the unit tests and
then the tier's experiments into DIR (default ./podsim-run-<tier>), prints the time of each step and writes
DIR/MANIFEST.sha256; `--check` compares it with code/expected/MANIFEST-<tier>.sha256. Tiers and the scenario
catalog are defined in `podsim/registry.py`; DIR/catalog/ lists every registered axis and what the tier skips.
