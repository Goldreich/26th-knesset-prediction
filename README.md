# 26th Knesset Prediction

A Bayesian election forecast that turns national polling measurements into a joint distribution over votes and all 120 Knesset seats. The dashboard presents expected seats, uncertainty intervals, majority probabilities, and an estimated most probable exact parliament.

This public portfolio edition includes the numerical model, reproducible inputs, tests, technical documentation, and a self-contained static dashboard. Its fixed snapshot uses information captured by **24 October 2026, 17:37:50 Israel time**, targeting **27 October 2026**. It is an experimental forecast conditional on a specified 37-list ballot, not an official final forecast or a live polling feed.

## What the project demonstrates

- **Statistical modeling:** a compositional state-space model with daily support, partially pooled pollster effects, and integrated uncertainty over variance parameters.
- **Data judgment:** 127 campaign reports audited, with 68 eligible percentage reports plus one partial primary disclosure used in the likelihood. Seat-derived percentages and unsupported subgroup reconstructions are excluded.
- **Numerical engineering:** sparse Gaussian inference, posterior prediction, exact rational electoral allocation, and randomized integration of rare exact-parliament probabilities.
- **Product design:** a static reader interface separated from model execution, with joint majority arithmetic and downloadable results.
- **Reproducibility:** pinned Python and Node dependencies, frozen inputs, and checks against published outputs.

## Explore the dashboard

**[Open the prediction dashboard](https://goldreich.github.io/26th-knesset-prediction/)** — no installation required.

From the repository root, with Python installed:

```sh
python -m http.server 8786 --directory site
```

Open **http://localhost:8786**. The included forecast is ready to view; no model fit or Node build is needed. GitHub Pages serves only `site/`; the deployment workflow checks the dashboard before publishing changes to that directory on `main`.

## Reproduce the prediction

Install [uv](https://docs.astral.sh/uv/), then run from the repository root:

```sh
uv sync --frozen
uv run knesset
uv run python scripts/check_reproduction.py
```

The fit uses **69 national surveys from six reporting series**, a 448-point variance grid, and 4,000 joint predictive draws. It writes vote/seat draws, summaries, diagnostics, and the terminal Gaussian mixture into `generated/`. It does not overwrite the issued dashboard snapshot. Dependencies require Python 3.12; uv can manage that interpreter.

The reproduction check compares all 4,000 seat vectors and the recovered mixture with the issued data. Fixed seeds and locked dependencies reproduced them exactly on the development platform; the check allows small floating-point differences in mixture parameters across platforms.

To independently estimate the probabilities of the five leading exact parliaments:

```sh
uv run python scripts/verify_mode.py --power 18 --replicates 8
```

This integrates each candidate's full allocation region, rather than counting repeats among the 4,000 dashboard draws. The script verifies the supplied candidates; it does not rerun the original broad candidate search or prove global optimality. See [the joint-mode derivation](docs/joint_mode.md) for the search record, integration method, and restrictions.

## How the model works

```text
Reported national vote percentages + explicit inclusion decisions
    -> log-ratio observations with measurement covariance
    -> daily latent support + relative pollster effects
    -> election-day prediction + shared election discrepancy
    -> conditional ballot completion
    -> threshold and Bader-Ofer seat allocation
    -> joint seat distribution and dashboard
```

The model estimates support through election day using a zero-drift random walk. Its forecast uncertainty includes future movement, pollster differences, measurement error, and an election-wide discrepancy that does not disappear when more polls are added. Each completed vote draw passes through the 3.25% threshold and six specified surplus agreements.

Expected seats describe marginal averages. The estimated joint mode describes one complete integer parliament totaling 120 seats. Its probability is approximately **one in 2.4 million** because every party's seat count must match exactly; this differs from the probability of a broader event such as a majority.

The implementation adapts polling components from [Stoetzer et al.](https://doi.org/10.1017/pan.2018.49) and [Montalvo, Papaspiliopoulos and Stumpf-Fetizon](https://doi.org/10.1016/j.ejpoleco.2019.01.006). It does not replicate either complete model, include fundamentals regression, or perform MRP. [Technical specification](docs/dynamic.md).

## Evidence and limitations

- The electoral engine reproduces all five official seat vectors from April 2019 through 2022. This validates allocation mechanics, not predictive accuracy.
- Two retrospective, overlapping poll holdouts yielded log-ratio RMSE of 0.223 and 0.234, versus 0.329 and 0.332 for a latest-per-series baseline. These use current archived versions and are not election-outcome backtests. [Recorded diagnostics](docs/poll_holdouts.json).
- The election-discrepancy scale has only one usable historical national-percentage calibration case, from 2022. Its total error can overlap with uncertainty already modeled elsewhere. Threshold and majority probabilities should not be interpreted as historically calibrated.
- Most campaign values are secondary transcriptions linked to original filings. Not every primary filing was independently cross-checked. Observed capture times establish availability for this snapshot, not earlier historical availability.
- Ballot completion removes Blue and White proportionally and assigns unmeasured minor lists 0.7% combined support, equally split. These are explicit scenario assumptions.
- The exact parliament is the most probable allocation found, not a certified global maximum. Numerical precision does not establish model adequacy.

## Tests

```sh
uv run pytest -q
npm ci --ignore-scripts
npm test
```

Node 22 is used for the dashboard tests. Tests cover historical allocation, threshold/tie behavior, Gaussian posterior calculations, cell-integration checks, joint seat conservation, actual dashboard interactions, majority calculations, and text escaping. DOM checks do not substitute for browser layout review. CI also refits the model and checks the frozen output.

## Repository guide

| Path | Contents |
| --- | --- |
| `src/knesset_forecast/` | Statistical model, electoral engine, simulation and probability integration |
| `config/model.json` | Cutoff, dates, grid, seed and assumptions |
| `data/` | Curated observations, provenance, ballot, historical counts and mode inputs |
| `site/` | Static dashboard and issued forecast exports |
| `docs/` | Model specification, mode derivation and evaluation record |
| `scripts/` | Reproduction and mode probability verification |
| `tests/` | Numerical, electoral and dashboard checks |
| `generated/` | Local reproduction output; ignored by Git |

See [the data dictionary and provenance](data/README.md). Source documents retain their original rights. Full PDFs, cached web pages, internal research notes, and the working archive's Git history are not redistributed here.
