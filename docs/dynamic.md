# Dynamic campaign forecast

The primary public forecast now fits a Bayesian voting-intention model to 69
national surveys from six reporting series. It estimates daily latent support,
relative pollster effects and variance parameters jointly, propagates support to
27 October, adds an election-wide discrepancy, and applies the verified electoral
calculator to each draw. The repository contains this dynamic reference model and its frozen outputs.

## Connection to the papers

[Stoetzer et al., *Forecasting Elections in Multi-Party Systems*](https://www.marcel-neunhoeffer.com/pdf/papers/pa_forecast-multiparty.pdf)
supplies the compositional state-space structure and partial pooling of house
effects. [Montalvo, Papaspiliopoulos and Stumpf-Fetizon](https://arxiv.org/html/1612.03073v2)
distinguish persistent house effects, election effects and time dependence.
The implementation adapts these polling components. It does **not** replicate
either complete paper, fit a fundamentals regression, perform MRP, or estimate
an unrestricted party covariance matrix.

## Observations and coverage

The immutable LittlePolls snapshot contains 127 campaign reports, July 29–October
21, from nine series. Its captured version was available at 13:56:48 UTC on
October 24, before the fixed information cutoff of 14:37:50 UTC. Dates within the
snapshot are fieldwork dates, not proof of earlier availability. Values remain
labeled secondary transcriptions with links to the original filings.

68 reports contribute national percentage measurements. Kantar and Next Data
percentage columns were reconstructed from seats; Rosner percentages were
reconstructed by the secondary compiler from subgroup tables. These columns are
excluded. Reports without percentages are also excluded from this likelihood.
Their seat vectors remain preserved, never inverted into votes. Percentage values, seat values, URLs, the snapshot hash and individual inclusion
decisions are retained in `data/polls.json`. Compiler narrative notes and full
source documents are not redistributed.

A 69th survey, the mirrored October 22 Lazar primary report, contributes its
published 3.5% Reservists/Economic and 3.0% Amcha Israel observations as a ratio.
Its fieldwork ran October 19–22, with 1,048 respondents. It does not supply a
fabricated percentage vector for the other parties. The original research issuance checked the source capture and hash. This public
adapter starts from the frozen curated measurements; it does not revalidate a
PDF that is not redistributed.

The October 12 Midgam transcription is checked against the independently curated
primary values. Other originals have not all been independently reviewed.
This is broader usable coverage, not a complete or fully verified archive.

## Likelihood

For positive published percentages, form `y_ij = log(p_ij / p_i,Likud)`.
An unknown common denominator cancels in these ratios. This does not establish
that different pollsters' turnout or undecided adjustments are equivalent; that
remains an explicit conditional interpretation. Rounded zero and unreported
categories are omitted individually, rather than replaced by arbitrary positive
values. No integer respondent counts are reconstructed.

The model is `y_i ~ Normal(H_i alpha[t_i] + H_i b[firm_i], s² R_i)`.
For a standard observation, H selects the observed party coordinates. For the
Lazar partial observation it contrasts Reservists/Economic with Amcha Israel.
Fieldwork end dates locate observations in time; a fieldwork-average observation
operator is not implemented.

`R_i = diag(1/(n_eff p_ij) + 0.08²) + 11'/(n_eff p_i,ref)`, with
`n_eff = min(n_i,1500)/2`. This delta-method covariance preserves the shared
reference's measurement error. The design effect, sample-size cap and reporting
floor are assumptions; the multiplier s is fitted and may be below one.

The repeated surveys are conditionally independent given their daily state and
house effect. Undocumented shared panels and overlapping samples are not
separately modeled; the common discrepancy prevents this assumption from making
election error vanish with more polls.

## Dynamic states, pollsters and inference

`alpha[t] = alpha[t-1] + Normal(0, q² C)` and `C = I + 11'` in log-ratio
coordinates. This corresponds to isotropic innovations in centered log
coordinates, including correlations induced by the shared reference.
Initial states have broad covariance `9C`. Relative house effects use an
orthonormal Helmert basis across firms, enforcing an exact sum of zero; their
prior covariance is `h² C`. Both q and h are learned, not fixed around an average.

Reported lineup events increase innovation SD by five on the event date. Old
RZ/Joint List and other pre-formation observations are not assigned to current
successor lists. DRI's Hadash–Taal column is not treated as the full Joint List.
Blue and White remains a distinct latent category and is removed only in the
explicit current-ballot completion. No old alliance's voters are automatically
transferred to a successor.

q, h and s have an explicit finite-grid prior with weights proportional to a
lognormal kernel (log SD .8, medians .024, .12 and 1). The grids are recorded in
the run configuration. Conditional latent posteriors are Gaussian and are
integrated analytically to compute grid probabilities. Independent posterior
draws use precision perturbation and a sparse solve, not MCMC. The normalizers
for the state, house and observation variances are included.

Checks include comparison against dense Gaussian posterior means/covariances,
precision-solve residuals, variance-grid boundary mass, and a separate geometric
midpoint grid. The original issuance included a midpoint check that changed mean modeled support
by less than 0.1 percentage point. The public adapter repeats the reference grid
fit and exposes its diagnostics; it does not rerun the shifted-grid sensitivity. These checks establish numerical behavior, not
electoral calibration.

## Election prediction and completion

The last latent state is October 27, beyond the observed polls. A shared
centered-log-coordinate election discrepancy is drawn once for each simulated
result. It is not independent noise added for every poll.

The working discrepancy variance starts from `InvGamma(3, 2 × .12²)` and receives
one election-level energy update from the 2022 national percentage report and
official results. Its 16 party errors are centered and summarized as one energy;
they are not counted as 16 independent elections. The resulting shape is 3.5
and scale about .140. This is total historical forecast discrepancy, including
sampling and house error, not an identified estimate of shared election bias.
It may be conservative when added to separately propagated uncertainty. The
2019–2021 seat-only observations remain usable for the old seat-model diagnostics
but cannot calibrate vote-scale error. No target outcomes enter this pipeline.

Each draw is completed to the approved conditional 37-list ballot. The reference
assigns unmeasured minor lists 0.7% combined support, equally split. Blue and White is dropped and the remaining modeled
composition renormalized, corresponding to proportional removal rather than a
named transfer. The public edition reproduces only this reference scenario. It contains 4,000
joint vote draws and 4,000 exact 120-seat allocations using the six reviewed
surplus agreements. Original sensitivity runs are not redistributed here.

## Evaluation and current limits

The original evaluation fitted through October 8 and October 15 and held out
later percentage reports; its recorded outputs are in `docs/poll_holdouts.json`.
The public edition includes the diagnostic results, not the original holdout runner. These are **retrospective current-version
poll-prediction checks**, not available-at-time election backtests. They compare
later reported log ratios, including house effects, against an equal-weight
latest-per-series log-ratio baseline. The dynamic model's RMSE was .223 and .234,
versus .329 and .332 for the baseline. The two folds overlap and belong to one
campaign; they do not establish election accuracy or calibrated threshold odds.

The broad archive is now integrated and the dynamic model is implemented.
Remaining research tasks are expanded historical national-percentage acquisition,
earlier-only election evaluation, primary-document cross-checks, shared-panel
dependence sensitivity, and testing a justified fundamentals extension. These
limitations do not turn the fitted election prediction into a polling average.

