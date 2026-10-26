# Estimating the joint discrete mode

This is postprocessing of the issued October 24 reference distribution, not a refit or a new election-information snapshot.
The original 4,000 archived draws, marginal forecasts, source cutoff and
representative parliament remain unchanged.

The target is `argmax_s Pr(allocate(V) = s)`, where s is an entire 37-list
integer seat vector totaling 120. It is not the maximum-density vote vector,
rounded expected seats, or a collection of separately selected party modes.

## Posterior recovery

The terminal-state marginal of each issued Gaussian grid component is computed
by sparse precision solves. The archived hyperparameter probabilities are used
unchanged. Components below probability 1e-12 are omitted; their combined mass
is 6.98e-12, bounding the induced error of any event probability. There are 119
retained components. The original inverse-gamma election discrepancy is then
integrated with generalized Gauss–Laguerre quadrature. Checks at 24, 48 and 96
nodes agree within randomized integration error.

The original issuance verified hashes of the model, electoral engine and ballot
assumptions. This public edition provides the frozen numerical mixture and a
refit from curated measurements, without importing new polls or outcomes. Analytical marginalization avoids resampling
the finite set of 4,000 previously issued simulations.

## Allocation-cell integral

For a fixed set of qualifying lists, eligible surplus pairs form electoral
groups. Away from a binding majority cap, the continuous allocation is the
largest-averages allocation to these groups followed by each pair's internal
allocation. The existing initial-quota algorithm gives the same allocation:
its initial group seats cannot exceed the lower quota respected by that
largest-averages solution.

Let group seat counts be s_g, summing to S=120. Partition the vote region by
the group p winning the last allocated seat. In chart p, put u_p=0 and
u_g in [0,1] for g != p, then

`g_g = (s_g + u_g) / T`, where `T = S + sum(u)`.

The winning quotients are at least 1/T and the next losing quotients are below
1/T. Conversely, every interior point allocating s has one such chart. The
Jacobian in the group simplex is `s_p / T^G`. Sampling p with probability
`s_p/S` gives the combined chart weight `S/T^G`.

For a pair receiving m seats with a going to its first member, its vote fraction
within the pair lies in `[a/(m+1), (a+1)/(m+1)]`. Splitting the group's vote mass
adds the Jacobian factor g/(m+1). Transformation from the qualified-party
simplex q to log ratios adds `1 / product(q)`.

The Gaussian density of the qualified-party log ratios is integrated over these
charts. Excluded-party log ratios are drawn from their conditional Gaussian,
using sequential truncated-normal importance sampling. If b parties fail the
threshold and kappa=.0325/.993, each necessarily satisfies

`exp(z_b) * q_reference < kappa / (1 - b*kappa)`.

Sampling under these necessary upper bounds and retaining the exact final
threshold checks avoids inefficient rare tail hits. The product of the
univariate truncation probabilities supplies the importance weight. Component
sampling is also tilted toward its peak qualified-party density, with exact
importance weights. Fixed unmeasured-minor support remains 0.7%, as in the
issued reference scenario.

The cell integrator excludes candidates whose group seat total reaches 60,
where the majority-cap analysis needs separate handling. It also requires
Likud to qualify, as its current log-ratio reference. These are declared search
restrictions, not claims that the forecast assigns other regimes zero mass.

## Search and verification

Two independent predictive pilots generated 2 million and 10 million new vote
draws. The 32 most frequent threshold regimes contain 97.32% of the independent
pilot's mass. Each regime received a multistart integer search using one-seat
transfers. Both searches found the same leader. They evaluated 21,630 and
15,549 candidate allocations respectively (with overlap).

Every allocation within two seat transfers of the leader was additionally
examined: 3,191 distinct allocations. High-precision evaluation of the leading
five uses eight independently scrambled Sobol replicates of 262,144 points,
with 96 discrepancy quadrature nodes. Shared scrambles allow precise paired
comparisons of the leader and runner-up.

The estimated leader has probability 4.1710e-7, with numerical standard error
3.22e-11. The runner-up has probability 4.0687e-7. Their approximately 2.5%
relative gap is much larger than the numerical integration uncertainty.
Numerical uncertainty is not uncertainty about model adequacy.

Checks cover 1,000 random allocations against the exact rational electoral
engine, cell points mapping to their requested seat allocation, and cell
probabilities agreeing with independent direct simulation in lower-dimensional
examples, including a failed-threshold party.

## Interpretation and limits

The result is an **estimated joint mode**, or the most probable exact allocation
found. It is not an exhaustive proof of a unique global maximum. Approximately
2.7% of predictive mass lies in threshold regimes not optimized in the targeted
search; majority-cap and failed-Likud regimes are also not exhaustively searched.
A small amount of omitted total probability is not by itself a proof that none
of its individual allocations can outrank the selected candidate.

The unusually small probability, about one in 2.4 million, is the probability
of getting every party's integer seat count exactly right. It does not imply
similarly small probabilities for broader events such as a majority.


## Reproduce candidate probabilities

Run `uv run python scripts/verify_mode.py --power 18 --replicates 8` from the
repository root to independently integrate the five leading candidates. Use
`--power 14 --replicates 2` for a quicker execution check with lower precision.
The default input is `data/terminal_posterior.json`; after a fresh model fit,
pass `--posterior generated/terminal_posterior.json` to use the recovered mixture.

The public edition includes the probability integrator and final candidate set.
The larger candidate-search runs described above are the original research
record, not rerun by this verification script. Their full search artifacts and
archive adapters are not redistributed. This limitation is separate from the
absence of a global optimality certificate.
