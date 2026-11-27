# Data notes

`code/DATA.md` defines the columns of every output. This file adds the columns and values it leaves out, and the catalog of design IDs. It describes the files the tiers write; nothing here changes how they are computed.

## General

- Tables are CSV. In the full tier the large tables are gzipped (`.csv.gz`); the small ones (`x4/by_law.csv`, `x4/lattice*.csv`, `x4/family_tot.csv` and others) stay plain CSV.
- `lam` and `weights` take the value `unlimited` for demand-unlimited rows in every table, not only in X2.
- Tie notation: `x2/x2_table` writes `best_primary` and `best_full` as `tie:a+b`; `x2/split` writes `winner` as `a+b`, and its `split_winners` source column joins the names with `|`; `xd/xd_table` writes `top_lever` as `cap+1 & range`. All three mean that the named levers are pairwise within two standard errors (or within 1e-9 s where both are exact) and that none of them is dominated.
- `winner_kind` (`x2/split`) and `top_kind` (`xd`) take the values `structural` (a winning lever also gains at unlimited demand), `no structural gain`, or empty when there is no winner; `winner` is then `none`.

## x3, x3b

- `demand`: `unlimited` (structural) or `lambda8_balanced` (Poisson pools with mean 8 per pool, balanced weights).
- `x3b/x3b_table`: `E_U` is expected unsold seconds of the dynamic portion; `E_U_over_B` is E[U/B] for the full break length B; `per60_ratio_of_means` is 60 E[U]/E[B] and `per60_mean_of_ratios` is 60 E[U/B], both in seconds per 60 s of break; `E_U_over_B_exact` is E[U/B] as an exact fraction (demand-unlimited rows only).
- `x3b/x3b_slopes`: `slope_U` and `slope_U_over_B` are the change from p = 0 to p = 1 (the quantities are linear in p); `slope_per60_mean_of_ratios` is 60 times `slope_U_over_B`; `sign_raw` and `sign_norm` are their signs (-1, 0, 1); `sign_changes` is true when normalizing by B reverses the sign.

## x5

- `frontier`: `anchor` is the clutter-cost shape: `base` (cost c per ad; every result in the paper), `A1` (2c per ad when the pod's filled seconds exceed 180) and `A2` (1.5c per ad when the pod holds both a 15 s and a 30 s creative); A1 and A2 are synthetic readings of qualitative viewer findings and are not used in the paper. `c_dollars` is the per-ad clutter cost, the paper's kappa, in dollars of CPM. `n` is the number of sampled breaks; `p_unfilled` is the share of breaks with unsold time and `p_lo`, `p_hi` its 95% Wilson interval.
- `matched_ads`: `ref` names the comparison curve, `base_same_h` (the base menu at the same cap) or `base_h_plus_one` (the base menu at one more ad); `ref_unfilled_at_ads` is that curve's unsold seconds interpolated at the same mean number of ads, and `d_unfilled` the difference.

## x6

- `floor`: `none`; `ps50`, `ps67`, `ps100` (a `mincpmpersec` floor of 50, 67 or 100 cents of CPM per second); `dfA` (a `durfloors` schedule of $10, $20 and $40 CPM for 1 to 15, 16 to 30 and 31 s or more).
- Per condition: `E_T` is the mean target; `E_n_pool` and `E_n_kept` the mean pool size before and after the floor; `U_Px`, `R_Px` and `ads_Px` unsold seconds, revenue in dollars of CPM per pod and ads under policy Px (P1 seconds-max exact, P2 revenue-max exact, P3 greedy by price per second, P3d longest first, P4 first-come).
- `gapS_Px` = E[S_P1 - S_Px] and `gapR_Px` = E[R_P2 - R_Px]; `gapSrev_Px` = E[S_P2 - S_Px]; `dU_floor_Px` and `dR_floor_Px` are the paired changes against the no-floor condition on the same draws; `P_gapS_P2_pos` and `P_gapR_P2_pos` are the shares of breaks with a positive gap; `P_empty_P2` the share where the revenue-max pod is empty; `rel_revgap_P2` = `gapR_P2` / `R_P2`.
- For each greedy policy g: `P_gapR0_g` and `P_gapS0_g` are the shares of breaks with no revenue or seconds gap; `relgapR_mean_g`, `relgapR_p50_g`, `relgapR_p90_g`, `relgapR_p99_g` and `relgapR_max_g` summarize the relative revenue gap (R_P2 - R_g) / R_P2.
- `x6_greedy_hist` holds, per condition and greedy policy, the histogram of that relative gap in 0.1% bins; `x6_conditions.json` (quick and narrow tiers) is `x6_conditions.csv` as JSON.

## x7

- `part`: `A` (exact) or `B` (Monte Carlo). `model`: `sys+` and `sys-` (every creative longer or shorter by epsilon), `ntsc` (every creative 1001/1000 of its nominal length), `indep` (part B: each creative perturbed independently and uniformly by up to epsilon). `eps_label` names epsilon (for example `1 frame (3003 ticks)`); `eps_ticks` and `tol_ticks` are epsilon and the stitcher's overrun tolerance in 90 kHz ticks.
- `overrun` is the expected amount by which the chosen pod's true total exceeds the break, within the tolerance; `delta` is the change in unsold seconds against the integer-second model after removing the mean sub-second offset, and `delta_exact` the same as an exact fraction. `U_tick0`, `overrun0` and `delta0` are the same quantities for whole-second breaks (no sub-second offset). Part B rows (`x7_partB`) give, per `quantity`, the integer-second mean `int_mean`, the tick mean `tick_mean`, their paired difference `paired_diff` with standard error `paired_se`, the mean sub-second offset `offset_mean` and the number of sampled breaks `n`.

## xd

- `count_law`: `poisson`, `nb1` and `nb4` (negative binomial pools with dispersion k = 1 and 4, same means).
- `pruned` bounds the probability mass of pool states dropped by the exact sum; the error on any expectation is at most 360 s times `pruned`.
- `xd_r2`: `share_new` is the share s of creatives that are new, `rho_new` and `rho_old` their readiness, and `rho_eff` = s rho_new + (1 - s) rho_old, at which the identity is evaluated.

## Catalog of design IDs

`catalog/axes.csv` in a tier's output folder lists every design axis with its ID, description and status (`built`, `extension` or `planned`); `code/DESIGN.md` uses these IDs. The axes are break length (L1 to L10), hybrid structure (H0 to H5), menus (M7, M85, MR, MX, MW), caps (C1-2, C3-12, C13-20), demand (D1 to D6), value (V1 to V4), separation (G1, G2), pod policy (P1 to P4), readiness (R1 to R3), units (J1, J2) and fate of unfilled time (K1 to K3). The labels P1 and P2 of the X0 report and P1 to P4 of the X4 summary number checks, not pod policies.
