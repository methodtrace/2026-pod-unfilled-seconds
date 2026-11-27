# Data dictionary

Every result folder written by `run_tier.py` (`OUT/`) has one subfolder per experiment, a `MANIFEST.sha256` of
every result file (content hashes; `.gz` files by their decompressed bytes) and `timing.json` files, which record
run times, the cache code hash (`code_sha256`) and a digest of the whole code tree (`tree_sha256`). Tables are CSV
(gzipped in the full tier); JSON files hold metadata and aggregates; `summary.md` files are readable reports.
Units are seconds per break unless a column says otherwise. "Exact" columns are rational numbers written as
`p/q`.

## Common columns

| Column | Meaning |
| --- | --- |
| `law` | Break-length law: L1 (30-second grid, 60 to 240 s), L2 and L2s* (hybrid: grid break minus one structured spot; the suffix names the spot set), L2two (two structured spots), L3u, L3s (irregular live breaks, uniform or skewed), L4u5, L4u15, L4s5, L4s15 (lattice laws), L5 (mid-roll minute bins), L6 (short breaks, 15 to 60 s), L7 (long breaks, 240 to 360 s), L8q25, L8q50, L8q75 (grid breaks mixed with irregular stoppages with probability q). `DESIGN.md` gives each law in full. |
| `conv` | Cap convention for laws with structured spots: `a` = `maxseq` applies to the dynamic remainder; `b` = the structured spots count toward a total of h (a cap below the number of spots places the spots and leaves the remainder no slot). Plain laws are `a`. |
| `menu` | Duration menu (`rqddurs`), durations in seconds separated by spaces. |
| `h` | Cap on ads per pod (`maxseq`); `none` = no cap. |
| `weights`, `scheme` | Demand mix over durations: `balanced`, `d1530` (15/30-dominant), `w15`, `w30`, `short` (short-scarce); `unlimited` = demand unlimited. |
| `lam` | Mean number of creatives per break (Poisson unless `count_law` says negative binomial). |
| `rho` | Readiness: probability that a selected creative is ready at the deadline. |
| `ET` | Expected dynamic target E[T]. |
| `U` | Expected unsold paid seconds per break. |
| `Ustruct`, `Ustruct_exact` | Structural floor: unsold seconds with unlimited demand and perfect readiness. |
| `share` | Structural share E[Ustruct] / E[U] (empty when E[U] = 0). |
| `demand_part`, `ready_part` | The demand and readiness parts of the accounting identity U = structural + demand + readiness. |
| `arith_part`, `cap_part` | Two-player split of the structural floor into the part due to the menu's arithmetic (menu versus its integer range) and the part due to the cap. |
| `range_residual` | Structural floor of the integer range menu at the same cap, V_range,h. Not the residual of eq. (5) of the paper, which is the uncapped V_range,inf. |
| `I_AC`, `I_AC_exact` | Interaction term of the two-player split. |

## Tables by experiment

- `x1/x1_table` and `extracts/x1_*`: the exact decomposition grid; one row per (law, convention, menu, cap, demand, readiness). `struct_cap_part` and `struct_arith_floor` are the cap and arithmetic parts in seconds; `unfilled_frac_of_time` is E[U]/E[T]; `P_struct_pos` is the probability that a break has a positive structural floor. `x1/x1_verify.json`: the sampled verification of the exact sums (z-scores).
- `x2/x2_table` and `extracts/x2_m7`: the lever study. `dur:c` is the seconds recovered by adding duration c; `dur_best` and `dur_best_c` the best added duration (ties go to the shorter c); `cap+1`, `cap+2` raising the cap by one or two; `range` the sampled gain of switching to the range at the declared nonstandard share 0.01 with standard error `range_se`; `range_e0`, `range_e0.01`, `range_e0.05`, `range_e0.2` the same at nonstandard shares 0, 0.01, 0.05 and 0.2 (the paper's theta; the code calls it eps); `ready.99`, `ready1` raising readiness to 0.99 or 1. `best_primary` and `best_full` name the winning lever among the primary and the full set; `tie:a+b` lists levers no other lever beats by more than 1e-9 s plus two standard errors of the difference. `dur_vs_cap1` compares the best added duration with one more ad. `range_rank` is the value the range is ranked on: the larger of the sampled `range` and the best exact gain of a duration strictly inside [min A, M], since the range admits every creative such a duration admits. `split_winners` is the winner set among `dur_best`, `cap+1` and the range (ranked on `range_rank`), chosen on unrounded gains and joined by `|`; `x2/split` reads it.
- `x2/split`: for each finite-demand winner, the structural part (its gain at unlimited demand) and the residual (`lever:struct`, `lever:residual`), the winner and `winner_kind` (structural gain or no structural gain). `x2/split.md` counts winners by cap regime.
- `x3/x3_table`, `x3/x3_slopes`: hybrid remainders as the probability p of a structured spot varies; slopes of the floor in p. `x3b/*`: the same normalized by the full break length B.
- `x4/*`: menu-ranking reversals across caps. `reversals`: pairs (A, B) by law with the sign string along the caps, the reversal points and the magnitude (the smaller of the two menus' largest leads); `by_law`: shares and magnitudes by law; `floors`: the exact floor by menu, law and cap; `criterion`: the exact check of the comparison between adding a duration and one more ad; `lattice*`, `family_tot`: reversals by lattice family and closed-form totals.
- `x5/*`: the clutter policy curve (sampled). `frontier`: unsold seconds, ads, revenue and net value per clutter cost step `k` (`c_dollars` = cost per ad in dollars of CPM); `contrasts`: paired differences between menus or caps; `matched_ads`: the short-duration menu at cap h against {15,30} at cap h + 1 at matched ads per break (`d_unfilled` < 0: the short menu fills more); `matched_cells.json.gz`: per cell, the counts behind the matched comparison; `hullchecks.json`: the hull-pair conditions checked.
- `x6/x6_conditions`: the revenue and pod-builder study (sampled), one row per condition. Policies: P1 exact seconds-max, P2 exact revenue-max, P3 greedy by price per second, P3d greedy longest duration first, P4 first come. `U_Px`, `R_Px`, `ads_Px`: unsold seconds, revenue and ads of policy x; `gapS_Px` = E[S_P1 - S_Px] seconds short of seconds-max; `gapR_Px` revenue short of revenue-max; `dU_floor_Px` seconds added by the floor setting `floor` relative to no floor; `vlaw` the value law (V1 flat, V2 premium); `pass_rate` the share of creatives clearing the floor. `x6_aggregates.json`: the unrounded aggregates the paper cites.
- `x7/x7_partA`, `extracts/x7a_*`: integer seconds against 90 kHz ticks, exact. `model`: `sys+`/`sys-` every creative longer or shorter by `eps_ticks`, `ntsc` the 1001/1000 stretch; `tol_ticks` the overrun tolerance; `U_int`, `U_tick` the floor in integer seconds and in ticks with a uniform sub-second break offset; `delta` = U_tick - U_int - 89999/180000 s (the mean offset removed); `U_tick0`, `delta0`, `overrun0` the same for breaks that are whole seconds (offset 0); `phi_*` the arithmetic and cap parts in ticks and in integer seconds. `x7/x7_partB`: sampled per-creative perturbation; `quantity` is U, Ustruct, demand, arith or cap; `paired_diff` = tick minus integer with `paired_se`.
- `xd/*`, `extracts/xd_m7`: the demand sweep (lambda from 1 to 256, Poisson and negative binomial counts with `count_law`), with `gain_cap1`, `gain_range`, `gain_range_se`, the winning lever `top_lever` and `top_kind` (structural gain or no structural gain); `xd_r2`: readiness by creative age.
- `catalog/*`: the axes of the scenario catalog and the menu sample; `checks/*`: the start-up checks.
