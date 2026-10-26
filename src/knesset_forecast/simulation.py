"""Draw-wise electoral simulation and clearly labeled conditional illustrations."""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np

from .models import forecast_draws
from .validation import DataContractError


def conditional_reported_support(
    reported_percentages: Mapping[str, float], *, n_draws: int = 5000, seed: int = 20261023,
    shared_scale: float = .12, zero_mass: float = .0001,
    residual_categories: tuple[str, ...] = ("other",),
) -> dict[str, Any]:
    """Illustrate consequences of assuming a reported composition is valid support.

    This explicitly bypasses the primary likelihood only to create a labeled
    conditional scenario. It cannot establish the source denominator, availability,
    turnout, registered-list completeness, or electoral forecast validity.
    """
    p = {key: value / 100 for key, value in reported_percentages.items()}
    if not p or any(not math.isfinite(v) or v < 0 for v in p.values()) or abs(sum(p.values())-1) > .02:
        raise DataContractError("Conditional illustration requires nonnegative reported percentages totaling approximately 100")
    zero_ids = [key for key, value in p.items() if value == 0]
    if zero_mass <= 0 or zero_mass * len(zero_ids) >= 1:
        raise DataContractError("Explicit small positive zero mass required")
    positive_total = sum(p.values())
    reserve = zero_mass * len(zero_ids)
    center = {key: zero_mass if value == 0 else (1-reserve)*value/positive_total for key, value in p.items()}
    prediction = forecast_draws(center, n_draws, seed, shared_scale=shared_scale)
    prediction["metadata"].update({
        "status": "conditional_reported_composition_illustration",
        "is_forecast": False,
        "assumptions": [
            "Treat the reported percentage column as national valid-vote support, although its denominator is unresolved",
            "Close the reported composition and replace reported zeros by explicitly assumed small masses",
            "Apply an uncalibrated exchangeable log-ratio error distribution",
        ],
        "zero_mass_per_reported_zero": zero_mass, "zero_replaced_categories": zero_ids,
        "residual_categories": [key for key in residual_categories if key in p],
        "seat_simulation_status": "unavailable_without_complete_verified_list_universe",
        "warning": "A mathematical sensitivity illustration, not an issued forecast or historical performance claim",
    })
    prediction["center"] = center
    return prediction


def _event_summary(event: np.ndarray) -> dict[str, float]:
    n = len(event)
    p = float(np.mean(event))
    # Wilson interval remains honest when no events occur in a finite simulation.
    z = 1.959963984540054
    denominator = 1+z*z/n
    mid = (p+z*z/(2*n))/denominator
    half = z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/denominator
    return {"probability": p, "mc_standard_error": math.sqrt(p*(1-p)/n),
            "mc_interval_95": [max(0., mid-half), min(1., mid+half)]}


def summarize_draws(
    prediction: dict[str, Any], *, agreements: list[tuple[str, str]] | tuple = (),
    groups: Mapping[str, list[str]] | None = None, threshold: float = .0325, seat_count: int = 120,
    simulate_seats: bool = False, registered_lists: list[str] | None = None,
    agreements_status: str = "unverified", list_universe_status: str = "unverified",
    residual_categories: tuple[str, ...] = (),
    conditional_ballot_id: str | None = None,
) -> dict[str, Any]:
    keys, x = prediction["list_ids"], np.asarray(prediction["draws"], dtype=float)
    if x.ndim != 2 or x.shape[1] != len(keys) or len(x) < 2 or np.any(x < 0) or not np.all(np.isfinite(x)) or not np.allclose(x.sum(axis=1), 1):
        raise DataContractError("Draws must be a finite joint simplex matrix")
    if len(set(keys)) != len(keys):
        raise DataContractError("Duplicate list IDs")
    residuals = set(residual_categories) | set(prediction.get("metadata", {}).get("residual_categories", []))
    summaries = []
    for j, key in enumerate(keys):
        intervals = {str(level): [float(v) for v in np.quantile(x[:, j], [(1-level)/2, (1+level)/2])]
                     for level in (.5, .8, .95)}
        summaries.append({"list_id": key, "mean_share": float(x[:, j].mean()), "median_share": float(np.median(x[:, j])),
                          "vote_intervals": intervals, "threshold": _event_summary(x[:, j] >= threshold) if key not in residuals else None,
                          "threshold_status": "not_a_single_registered_list" if key in residuals else "conditional_on_model"})
    result = {"lists": summaries, "n_draws": len(x), "threshold": threshold,
              "seat_status": "unavailable", "majority_events": {}, "metadata": prediction.get("metadata", {})}
    if not simulate_seats:
        return result
    if residuals:
        raise DataContractError("A pooled residual is not a registered list and cannot receive seats")
    conditional_ballot = (list_universe_status == "conditional_scenario" and
                          isinstance(conditional_ballot_id, str) and bool(conditional_ballot_id.strip()) and
                          prediction.get("metadata", {}).get("status") == "conditional_scenario" and
                          bool(prediction.get("metadata", {}).get("assumptions")))
    if (list_universe_status != "verified" and not conditional_ballot) or registered_lists is None or set(registered_lists) != set(keys):
        raise DataContractError("Seat simulation requires the complete verified registered-list universe")
    if agreements_status != "verified":
        raise DataContractError("Election-specific surplus agreements must be verified")
    from .electoral import allocate_seats
    seat_draws = np.zeros(x.shape, dtype=int)
    for i, row in enumerate(x):
        allocation = allocate_seats(dict(zip(keys, map(float, row))), agreements, threshold=threshold, seats=seat_count, tie_break="lexicographic")
        seat_draws[i] = [allocation[key] for key in keys]
    if not np.all(seat_draws.sum(axis=1) == seat_count):
        raise RuntimeError("Electoral engine did not conserve seats")
    for j, summary in enumerate(summaries):
        counts = np.bincount(seat_draws[:, j], minlength=seat_count+1)
        summary.update(mean_seats=float(seat_draws[:, j].mean()), median_seats=float(np.median(seat_draws[:, j])),
                       seat_probabilities=[float(c/len(x)) for c in counts],
                       zero_seats=_event_summary(seat_draws[:, j] == 0),
                       seat_intervals={str(level): [float(v) for v in np.quantile(seat_draws[:, j], [(1-level)/2, (1+level)/2], method="inverted_cdf")]
                                       for level in (.5, .8, .95)})
    for group_name, members in (groups or {}).items():
        if len(set(members)) != len(members) or not set(members) <= set(keys):
            raise DataContractError("Majority groups require distinct explicit registered-list members")
        totals = seat_draws[:, [keys.index(key) for key in members]].sum(axis=1)
        result["majority_events"][group_name] = {"members": list(members), "event": f"at_least_{seat_count//2+1}_seats",
                                                    **_event_summary(totals >= seat_count//2+1),
                                                    "seat_probabilities": (np.bincount(totals, minlength=seat_count+1)/len(x)).tolist(),
                                                    "interpretation": "Seat arithmetic, not government formation"}
    representative = int(np.argmin(np.abs(seat_draws-seat_draws.mean(axis=0)).sum(axis=1)))
    result.update(seat_status="simulated", seat_draws=seat_draws,
                  ballot_status=list_universe_status, conditional_ballot_id=conditional_ballot_id if conditional_ballot else None,
                  representative_parliament={key: int(seat_draws[representative, j]) for j, key in enumerate(keys)},
                  representative_rule="Actual draw minimizing L1 distance from marginal mean seats",
                  discarded_vote_share={"mean": float(np.sum(np.where(x < threshold, x, 0), axis=1).mean())},
                  numerical_tie_convention="lexicographic; probability zero under continuous model; statutory lottery is not predicted")
    return result
