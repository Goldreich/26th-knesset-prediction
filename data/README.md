# Data and provenance

These files preserve the numerical inputs used for the October 24 snapshot. They are a curated research dataset, not an official election data service. Reproduction reads local JSON and does not download new sources or update the cutoff.

| File | Meaning |
| --- | --- |
| `polls.json` | 127 archived campaign reports plus one partial Lazar disclosure; percentages, reported seats, fieldwork, sample sizes, source links and inclusion decisions |
| `ballot.json` | Conditional 37-list universe, names, polling aliases, six surplus agreements and completion assumptions |
| `error_calibration.json` | 2022 reported national percentages and observed shares used for one election-level discrepancy update |
| `official/*.json` | Valid-vote counts, official seat counts, thresholds and agreements for the five elections from April 2019 through 2022 |
| `terminal_posterior.json` | Frozen terminal-state Gaussian mixture and election-discrepancy parameters for exact-parliament probability integration |
| `mode_candidates.json` | Five leading candidate seat vectors with original replicated integration results |

## Campaign observations

`measurements` maps a polling category to `pct` (percentage points) and/or `seats` (reported seat projection). A stored percentage is not automatically eligible for the model. `vote_likelihood` is the report-level eligibility decision; `included_categories`, `omitted_categories` and `vote_exclusion` describe the usable measurements and exclusions. `reference_key` identifies the denominator of the log-ratio observation, usually Likud. Zero or absent percentages are omitted, not imputed. Sample size describes the source survey, not reconstructed respondent counts.

The [LittlePolls source snapshot](https://littlepolls.com/resources/data-8fefb410f0.json.gz) was captured at 2026-10-24T13:56:48.333256+00:00. Its SHA-256 is recorded in `polls.json`. It contains 127 reports from nine reporting series; 68 contribute national percentage measurements. The other 59 reports are excluded: 39 have seat-derived percentages, 13 lack percentages, and seven have unsupported subgroup-derived percentages. Their reported measurements remain available for audit and are never inverted into votes.

A separate October 22 Lazar report contributes only its published 3.5% Reservists/Economic and 3.0% Amcha Israel ratio. Together these inputs yield 69 usable observations from six series. Each row has a source URL and evidence description. Fieldwork dates locate observations in the model; they do not prove when a document became publicly available.

The archived compiler's narrative notes and full source documents are not redistributed. The public adapter starts from these curated inclusion decisions; it is not a source acquisition or PDF parsing pipeline. The archive hash identifies the captured source, but reproduction does not claim to revalidate an omitted source file.

## Historical data

Official result URLs appear in each historical file. Three historical agreement sets were assembled from secondary evidence; matching official seats does not resolve that provenance limitation. Polling calibration and historical outcome counts are separate files. Only the 2022 percentage case updates the vote-scale error distribution, with 16 centered party discrepancies summarized as one election-level energy. The historical data are not five independent vote-forecast calibration cases.

## Identifiers and units

List IDs join ballot, result and forecast tables. Polling aliases describe observed categories and are not assumed to be permanent political lineages. Vote shares in model outputs and `actual_share` are fractions of valid votes; `reported_percent` and poll `pct` values are percentage points. Seat draws are joint integer vectors summing to 120.

`terminal_posterior.json` uses additive log ratios relative to Likud. Its `list_ids` order covers modeled active parties; `all_list_ids` also includes unmeasured minor lists. Candidate seat vectors use the modeled-party order recorded in `mode_candidates.json`; omitted minor lists have zero seats under the fixed completion assumption.
