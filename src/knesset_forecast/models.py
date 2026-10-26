"""Transparent polling baselines and a joint compositional predictive model."""
from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any, Iterable, Mapping

import numpy as np

from .validation import DataContractError, assert_training_history, parse_timestamp


METHODS = ("latest_per_firm", "recency", "precision")


def aggregate_polls(
    polls: Iterable[dict[str, Any]],
    cutoff: str | datetime,
    method: str = "latest_per_firm",
    *,
    half_life_days: float = 7,
    design_effect: float = 1.5,
    variance_floor: float = 0.0001,
) -> dict[str, Any]:
    """Aggregate already validated compositions; normalize within each firm first.

    Precision is an explicitly assumed SRS design-effect approximation at p=.5,
    capped by a non-sampling floor. Missing sample sizes cause an error for this
    alternative; no effective sample sizes are fabricated.
    """
    if method not in METHODS:
        raise DataContractError(f"Unknown baseline {method}")
    cutoff_dt = parse_timestamp(cutoff)
    if not all(math.isfinite(x) for x in [half_life_days, design_effect, variance_floor]) or half_life_days <= 0 or design_effect < 1 or variance_floor <= 0:
        raise DataContractError("Positive half-life/floor and design effect >=1 are required")
    polls = list(polls)
    if not polls:
        raise DataContractError("No comparable polls: an aggregate is unavailable")
    by_survey: dict[str, dict[str, Any]] = {}
    for poll in polls:
        key = poll["survey_id"]
        if key in by_survey and by_survey[key]["shares"] != poll["shares"]:
            raise DataContractError("Conflicting duplicate surveys must be resolved before aggregation")
        by_survey[key] = poll
    polls = list(by_survey.values())
    list_ids = sorted(polls[0]["shares"])
    firms: dict[str, list[dict[str, Any]]] = {}
    for poll in polls:
        shares = poll["shares"]
        if sorted(shares) != list_ids or abs(sum(shares.values()) - 1) > 1e-8:
            raise DataContractError("All polls require the same complete simplex")
        if any(not math.isfinite(x) or x < 0 for x in shares.values()):
            raise DataContractError("Invalid share")
        if date.fromisoformat(poll["fieldwork_end"][:10]) > cutoff_dt.date():
            raise DataContractError("Future fieldwork cannot enter aggregation")
        firms.setdefault(poll["pollster_id"], []).append(poll)
    weights: dict[str, float] = {}
    within_precision: dict[str, float] = {}
    chosen_by_firm: dict[str, list[dict[str, Any]]] = {}
    for firm, group in firms.items():
        if method == "latest_per_firm":
            newest = max(p["fieldwork_end"][:10] for p in group)
            group = [p for p in group if p["fieldwork_end"][:10] == newest]
            local = np.ones(len(group))
        else:
            ages = [(cutoff_dt.date()-date.fromisoformat(p["fieldwork_end"][:10])).days for p in group]
            local = np.exp2(-np.asarray(ages) / half_life_days)
        if method == "precision":
            variances = []
            for poll in group:
                n = poll.get("sample_size")
                if isinstance(n, bool) or not isinstance(n, (float, int)) or not math.isfinite(n) or n <= 0:
                    raise DataContractError("Precision alternative requires an actual disclosed sample size")
                variances.append(0.25 * design_effect / n + variance_floor)
            # Repeated releases do not reduce the firm's variance as independent samples.
            local = local / np.asarray(variances)
            normalized = local / local.sum()
            within_precision[firm] = 1 / float(np.dot(normalized, variances))
        chosen_by_firm[firm] = group
        local = local / local.sum()
        for poll, weight in zip(group, local):
            weights[poll["survey_id"]] = float(weight)
    raw_firm = within_precision if method == "precision" else {firm: 1.0 for firm in firms}
    firm_total = sum(raw_firm.values())
    firm_weights = {firm: raw / firm_total for firm, raw in raw_firm.items()}
    center = {key: 0.0 for key in list_ids}
    for firm, group in chosen_by_firm.items():
        for poll in group:
            weight = weights[poll["survey_id"]] * firm_weights[firm]
            weights[poll["survey_id"]] = weight
            for key in list_ids:
                center[key] += weight * poll["shares"][key]
    return {"shares": center, "method": method, "weights": weights, "firm_weights": firm_weights,
            "survey_count": len(weights), "firm_count": len(firms), "cutoff": cutoff_dt.isoformat(),
            "observation": "polling_consensus", "half_life_days": half_life_days,
            "precision_assumptions": {"design_effect": design_effect, "variance_floor": variance_floor,
                                      "reference_share": 0.5} if method == "precision" else None}


def _simplex(values: Mapping[str, float]) -> tuple[list[str], np.ndarray]:
    keys = sorted(values)
    vector = np.array([values[key] for key in keys], dtype=float)
    if len(keys) < 2 or not np.all(np.isfinite(vector)) or np.any(vector <= 0):
        raise DataContractError("Log-ratio prediction requires at least two strictly positive categories; zeros need a documented model")
    if abs(vector.sum() - 1) > 1e-8:
        raise DataContractError("Predictive center must sum to one")
    return keys, vector


def calibrate_shared_error(
    history: Iterable[dict[str, Any]],
    target_election: str,
    *,
    prior_scale: float = 0.12,
    prior_df: float = 4,
    cluster_adjacent: bool = True,
) -> dict[str, Any]:
    """Conservative scalar error calibration, not an unrestricted covariance fit.

    Each election contributes at most one effective unit to a generalized
    inverse-gamma scale update. The 2019a–2021 cluster contributes at most one
    unit in total. This is a prespecified working likelihood for election-level
    squared CLR residual energy; it does not treat parties as independent trials.
    """
    records = assert_training_history(history, target_election)
    if not math.isfinite(prior_scale) or not math.isfinite(prior_df) or prior_scale <= 0 or prior_df <= 0:
        raise DataContractError("Positive prior scale and degrees of freedom required")
    adjacent = {"2019a", "2019b", "2020", "2021"}
    adjacent_n = sum(r["election_id"] in adjacent for r in records)
    alpha, beta = prior_df / 2, prior_df * prior_scale**2 / 2
    diagnostics = []
    for record in records:
        keys, center = _simplex(record["center"])
        outcome_keys, outcome = _simplex(record["outcome"])
        if keys != outcome_keys:
            raise DataContractError("Within-election forecast and outcome lists must match")
        residual = np.log(outcome) - np.log(center)
        residual -= residual.mean()
        energy = float(residual @ residual / (len(keys) - 1))
        weight = 1 / adjacent_n if cluster_adjacent and record["election_id"] in adjacent else 1.0
        alpha += weight / 2
        beta += weight * energy / 2
        diagnostics.append({"election_id": record["election_id"], "clr_squared_error": energy, "effective_weight": weight})
    return {"family": "inverse_gamma", "alpha": alpha, "beta": beta,
            "target_election": target_election, "training_elections": [r["election_id"] for r in records],
            "status": "prior_only" if not records else "experimental_generalized_calibration",
            "calibration_target": "total_aggregate_to_result_error", "cluster_adjacent": cluster_adjacent,
            "diagnostics": diagnostics,
            "warning": "Working scalar scale model; five dependent elections cannot validate covariance or tail probabilities"}


def forecast_draws(
    center: Mapping[str, float],
    n_draws: int = 5000,
    seed: int = 20261023,
    *,
    shared_scale: float = 0.12,
    scale_log_sd: float = 0.25,
    house_scale: float = 0,
    firm_weights: Mapping[str, float] | None = None,
    calibration: dict[str, Any] | None = None,
    tail_df: float | None = None,
) -> dict[str, Any]:
    """IID joint draws using centered log ratios, then exact inverse softmax.

    The exchangeable projected Gaussian covariance is scale²(I-11'/K).
    This is a generative logistic-normal model, not independent percentages
    clipped and renormalized. shared_scale represents total forecast residual
    uncertainty by default, so no sampling/turnout term is added again.
    """
    keys, p = _simplex(center)
    if not isinstance(n_draws, int) or n_draws < 2 or not all(math.isfinite(v) for v in [shared_scale, scale_log_sd, house_scale]) or shared_scale < 0 or scale_log_sd < 0 or house_scale < 0:
        raise DataContractError("At least two draws and nonnegative scales required")
    if tail_df is not None and (not math.isfinite(tail_df) or tail_df <= 2):
        raise DataContractError("Heavy-tail degrees of freedom must exceed 2")
    if calibration and house_scale:
        raise DataContractError("Total aggregate residual calibration already includes poll/firm uncertainty")
    rng = np.random.default_rng(seed)
    if calibration:
        if calibration.get("family") != "inverse_gamma":
            raise DataContractError("Unknown scale calibration")
        if not all(math.isfinite(calibration[k]) and calibration[k] > 0 for k in ("alpha", "beta")):
            raise DataContractError("Invalid calibration parameters")
        scales = np.sqrt(1 / rng.gamma(calibration["alpha"], 1 / calibration["beta"], n_draws))
    else:
        scales = shared_scale * np.exp(rng.normal(-0.5 * scale_log_sd**2, scale_log_sd, n_draws))
    noise = rng.normal(size=(n_draws, len(keys)))
    noise -= noise.mean(axis=1, keepdims=True)
    if tail_df is not None:
        # Unit marginal variance t alternative, apart from the sampled scale.
        scales *= np.sqrt((tail_df - 2) / rng.chisquare(tail_df, n_draws))
    errors = scales[:, None] * noise
    if house_scale:
        if not firm_weights or abs(sum(firm_weights.values())-1) > 1e-8 or any(w < 0 for w in firm_weights.values()):
            raise DataContractError("Explicit normalized firm weights required for firm-error scenario")
        h = rng.normal(size=errors.shape)
        h -= h.mean(axis=1, keepdims=True)
        errors += house_scale * math.sqrt(sum(w*w for w in firm_weights.values())) * h
    z = np.log(p)[None, :] + errors
    z -= z.max(axis=1, keepdims=True)
    draws = np.exp(z)
    draws /= draws.sum(axis=1, keepdims=True)
    return {"list_ids": keys, "draws": draws,
            "metadata": {"model": "exchangeable-clr-logistic-normal-v1", "seed": seed, "n_draws": n_draws,
                         "shared_scale": shared_scale, "scale_log_sd": scale_log_sd, "house_scale": house_scale,
                         "tail_df": tail_df, "calibration": calibration,
                         "uncertainty_status": calibration["status"] if calibration else "assumption_based_prior",
                         "basis": "centered log ratios; covariance is projected exchangeable Gaussian",
                         "inference": "independent direct simulation; no MCMC convergence diagnostic applies",
                         "center_interpretation": "poll consensus and median log-ratio location, not predictive arithmetic mean"}}


def leave_one_firm_out(polls: Iterable[dict[str, Any]], cutoff: str, method: str = "latest_per_firm") -> list[dict[str, Any]]:
    polls = list(polls)
    full = aggregate_polls(polls, cutoff, method)
    result = []
    for firm in sorted({p["pollster_id"] for p in polls}):
        remaining = [p for p in polls if p["pollster_id"] != firm]
        if not remaining:
            result.append({"removed_firm": firm, "status": "unavailable", "reason": "No independent firms remain"})
        else:
            reduced = aggregate_polls(remaining, cutoff, method)
            result.append({"removed_firm": firm, "status": "available", "shares": reduced["shares"],
                           "difference": {k: reduced["shares"][k]-full["shares"][k] for k in full["shares"]}})
    return result


def sensitivity_draws(center: Mapping[str, float], *, n_draws: int = 5000, seed: int = 20261023) -> dict[str, dict[str, Any]]:
    """Prespecified conditional scale/dependence alternatives, never model averaging."""
    return {name: forecast_draws(center, n_draws, seed, shared_scale=scale, tail_df=df)
            for name, scale, df in [("low_shared_error", .06, None), ("primary", .12, None),
                                    ("high_shared_error", .24, None), ("heavy_tail", .12, 5),
                                    ("naive_no_shared_error", 0, None)]}
