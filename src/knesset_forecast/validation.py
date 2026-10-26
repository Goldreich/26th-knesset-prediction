"""Fail-closed information-set and observation-definition checks.

Raw releases remain in the archive even when they cannot enter this likelihood.
This module never turns projected seats into vote shares.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
import math
from typing import Any, Iterable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


ELECTION_ORDER = ("2019a", "2019b", "2020", "2021", "2022", "2026")
VOTE_TYPES = {"national_vote_share", "national_adjusted_vote_share", "national_raw_percentage"}
VALID_DENOMINATORS = {"valid_votes", "decided_valid_vote_intentions", "decided_respondents"}
NONPARTY_CATEGORIES = {"undecided", "refuses", "nonvoter", "invalid", "blank", "abstain", "would_not_vote"}
AVAILABILITY_KINDS = frozenset({"archived_version", "reviewed_publisher_version",
                              "reviewed_primary_text", "captured_snapshot"})
FORECAST_STATUSES = frozenset({"unavailable", "conditional_scenario", "experimental_forecast",
                              "frozen_pre_election_forecast"})


class DataContractError(ValueError):
    """A requested transformation is not supported by the data contract."""


def parse_timestamp(value: str | datetime) -> datetime:
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise DataContractError("A timezone-aware information-cutoff/availability timestamp is required")
    return result


def availability_timestamp(value: str, local_timezone: str = "Asia/Jerusalem") -> datetime:
    """Interpret a date-only source timestamp at the *end* of its local day."""
    if len(value) == 10:
        try:
            return datetime.combine(date.fromisoformat(value), time.max, ZoneInfo(local_timezone))
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise DataContractError("Invalid source availability date/timezone") from exc
    return parse_timestamp(value)


def reviewed_availability(poll: dict[str, Any], allowed_kinds: Iterable[str] | None = None) -> datetime:
    """Return availability of the observed version, independent of raw-file capture.

    A review may establish a past version from readable primary text without the
    original PDF. A current capture only establishes availability at retrieval.
    Publisher dates without a review tied to a specific version are insufficient.
    """
    allowed = set(AVAILABILITY_KINDS if allowed_kinds is None else allowed_kinds)
    if not allowed <= AVAILABILITY_KINDS:
        raise DataContractError("Unknown availability evidence kind in run policy")
    evidence = poll.get("availability_evidence")
    if not isinstance(evidence, dict) or evidence.get("reviewed") is not True:
        raise DataContractError("Public availability requires reviewed version evidence")
    kind = evidence.get("kind")
    if kind not in allowed:
        raise DataContractError("Availability evidence is not permitted by this run")
    if poll.get("availability_status") not in {"verified", "reviewed", kind}:
        raise DataContractError("Public availability by cutoff is unverified")
    for key in ("version_id", "source_url", "basis", "reviewed_at"):
        if not isinstance(evidence.get(key), str) or not evidence[key].strip():
            raise DataContractError(f"Availability evidence requires {key}")
    parse_timestamp(evidence["reviewed_at"])
    if not poll.get("available_at") or not poll.get("version_available_at"):
        raise DataContractError("Availability must identify both publication and observed-version timing")
    zone = poll.get("availability_timezone", "Asia/Jerusalem")
    times = [availability_timestamp(poll[key], zone) for key in
             ("available_at", "version_available_at", "modified_at") if poll.get(key)]
    if kind == "captured_snapshot":
        if not poll.get("retrieved_at"):
            raise DataContractError("A captured snapshot requires its actual retrieval timestamp")
        times.append(parse_timestamp(poll["retrieved_at"]))
    return max(times)


def validate_run_config(config: dict[str, Any], election: dict[str, Any] | None = None) -> dict[str, Any]:
    """Check run intent without confusing scientific readiness with archive completeness."""
    cutoff = parse_timestamp(config["information_cutoff"])
    if config.get("timezone") != "Asia/Jerusalem":
        raise DataContractError("Election runs must declare timezone Asia/Jerusalem")
    if cutoff.utcoffset() != cutoff.astimezone(ZoneInfo("Asia/Jerusalem")).utcoffset():
        raise DataContractError("Information cutoff must use the Jerusalem offset for that instant")
    if config.get("target") not in ELECTION_ORDER:
        raise DataContractError("Unknown target election")
    if config.get("view") not in {"available_at_time", "reconstructed_archive"}:
        raise DataContractError("Unknown data view")
    status = config.get("requested_forecast_status", "experimental_forecast")
    if status not in FORECAST_STATUSES:
        raise DataContractError("Unknown forecast lifecycle status")
    for key in ("seed", "n_draws", "window_days"):
        value = config.get(key)
        minimum = 0 if key == "seed" else 2 if key == "n_draws" else 1
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise DataContractError(f"Run requires a valid integer {key}")
    if not set(config.get("availability_policy", AVAILABILITY_KINDS)) <= AVAILABILITY_KINDS:
        raise DataContractError("Unknown availability evidence kind in run policy")
    if status == "frozen_pre_election_forecast":
        if config.get("view") != "available_at_time":
            raise DataContractError("A reconstruction cannot be a frozen pre-election forecast")
        if not election or election.get("cutoff_status") != "verified" or not election.get("final_poll_cutoff"):
            raise DataContractError("Final pre-election freeze requires a verified official cutoff")
        if cutoff != parse_timestamp(election["final_poll_cutoff"]):
            raise DataContractError("Frozen final run must use the verified official cutoff")
    if election and election.get("election_date"):
        if cutoff.astimezone(ZoneInfo("Asia/Jerusalem")).date() >= date.fromisoformat(election["election_date"]):
            raise DataContractError("Forecast information cutoff must precede election day")
    return dict(config)


def _share(estimate: dict[str, Any]) -> float:
    status = estimate.get("status", "reported")
    if status not in {"reported", "reported_zero", "observed"}:
        raise DataContractError(f"Estimate status {status!r} requires a separate observation model")
    value = estimate.get("value")
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise DataContractError("Missing or nonnumeric estimate")
    unit = estimate.get("unit")
    if unit in {"percent", "percentage", "percentage_points"}:
        value = value / 100
    elif unit not in {"proportion", "share"}:
        raise DataContractError(f"Unsupported vote-share unit {unit!r}; seats cannot be inverted")
    if not 0 <= value <= 1:
        raise DataContractError("Vote-share value outside [0, 1]; check percentage units")
    return float(value)


def observation_to_shares(
    poll: dict[str, Any],
    registered_lists: Iterable[str],
    *,
    proportional_undecided: bool = False,
    rounding_tolerance: float | None = None,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    """Return a complete, comparable composition and an explicit transformation log.

    Proportional allocation is opt-in, only for documented all-respondent national
    data with all nonparty responses retained. It is a scenario, not an estimate
    of turnout. Missing lists and pooled 'other' are never assigned zero.
    """
    expected = set(registered_lists)
    if not expected:
        raise DataContractError("An explicit, nonempty list/category universe is required")
    if poll.get("observation_type") not in VOTE_TYPES:
        raise DataContractError("Only comparable national vote-share observations are eligible")
    if poll.get("population_scope", "national") != "national":
        raise DataContractError("Subgroup percentages are not national vote shares")
    if poll.get("contains_outcome", False) or poll.get("release_type") in {"exit_poll", "result", "partial_count"}:
        raise DataContractError("Outcome, exit poll, or partial-count leakage")
    denominator = poll.get("denominator")
    all_respondent = denominator in {"all_respondents", "all_valid_responses"}
    if denominator not in VALID_DENOMINATORS and not (all_respondent and proportional_undecided):
        raise DataContractError(f"Unknown/incomparable denominator {denominator!r}")
    values: dict[str, float] = {}
    nonparty: dict[str, float] = {}
    rounding_bound = 1e-10
    for estimate in poll.get("estimates", []):
        list_id = estimate.get("list_id")
        if not list_id:
            raise DataContractError("Every estimate requires a list/category ID")
        target = nonparty if list_id in NONPARTY_CATEGORIES else values
        if list_id in target:
            raise DataContractError(f"Duplicate estimate for {list_id}")
        target[list_id] = _share(estimate)
        precision = estimate.get("rounding_precision")
        if precision is not None:
            if not isinstance(precision, (int, float)) or not math.isfinite(precision) or precision < 0:
                raise DataContractError("Invalid rounding precision")
            rounding_bound += precision / (200 if estimate["unit"] in {"percent", "percentage", "percentage_points"} else 2)
    if set(values) != expected:
        raise DataContractError(
            f"Incomplete or mismatched list universe: missing={sorted(expected-set(values))}; "
            f"unexpected={sorted(set(values)-expected)}"
        )
    total = sum(values.values())
    disclosed_total = total + sum(nonparty.values())
    tolerance = min(rounding_bound, .02) if rounding_tolerance is None else rounding_tolerance
    if not math.isfinite(tolerance) or tolerance < 0:
        raise DataContractError("Invalid rounding tolerance")
    if abs(disclosed_total - 1) > tolerance:
        raise DataContractError(f"Reported categories total {disclosed_total:.6f}, outside rounding tolerance")
    transformations = []
    if all_respondent:
        if not nonparty or not poll.get("nonparty_categories_complete", False):
            raise DataContractError("Proportional allocation requires complete disclosed nonparty categories")
        transformations.append({
            "operation": "proportional_decided_allocation",
            "excluded_response_share": sum(nonparty.values()),
            "assumption": "Nonparty respondents follow the relative preferences of declared valid-list respondents",
            "status": "conditional_scenario",
        })
    elif nonparty and sum(nonparty.values()) > 0:
        raise DataContractError("Nonparty responses contradict a decided/valid-vote denominator")
    if total <= 0:
        raise DataContractError("No positive valid-list response share")
    if abs(total - 1) > 1e-12:
        transformations.append({"operation": "close_composition", "reported_list_total": total,
                                "reason": "explicit proportional allocation" if all_respondent else "reported rounding"})
    return {key: value / total for key, value in values.items()}, transformations


def select_polls(
    polls: Iterable[dict[str, Any]],
    election_id: str,
    cutoff: str | datetime,
    registered_lists: Iterable[str],
    *,
    view: str = "available_at_time",
    window_days: int = 14,
    proportional_undecided: bool = False,
    require_ballot_match: bool = True,
    availability_policy: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Select one verified version/scenario per survey without favorable timestamps.

    The reconstruction view explicitly permits disclosures retrieved later, but
    still rejects surveys fielded or initially reported after the cutoff.
    Reviewed version dates are interpreted conservatively at the end of the
    source's local day. The archive view cannot be prospective backtesting.
    """
    cutoff_dt = parse_timestamp(cutoff)
    if election_id not in ELECTION_ORDER:
        raise DataContractError("Election outside the prespecified 2019a–2026 scope")
    if view not in {"available_at_time", "reconstructed_archive"}:
        raise DataContractError("Unknown data view")
    if window_days <= 0:
        raise DataContractError("window_days must be positive")
    registered_lists = tuple(registered_lists)
    selected, excluded, duplicates = [], [], []
    candidates: dict[str, list[dict[str, Any]]] = {}
    for source_poll in polls:
        poll = dict(source_poll)
        if poll.get("election_id") != election_id:
            continue
        survey_id = poll.get("survey_id")
        try:
            if not survey_id or not poll.get("pollster_id"):
                raise DataContractError("Survey and actual research firm IDs are required")
            if require_ballot_match and poll.get("ballot_match") is not True:
                raise DataContractError("Registered-ballot match is not verified")
            if not poll.get("source_url") and not poll.get("source_id"):
                raise DataContractError("Missing source provenance")
            availability = poll.get("available_at")
            if view == "available_at_time":
                available_dt = reviewed_availability(poll, availability_policy)
                if available_dt > cutoff_dt:
                    raise DataContractError("Source version became available after cutoff")
            else:
                published = poll.get("publication_date")
                if not published:
                    raise DataContractError("Even reconstruction requires a documented original publication date")
                pubdate = date.fromisoformat(published[:10])
                if availability_timestamp(pubdate.isoformat(), poll.get("availability_timezone", "Asia/Jerusalem")) > cutoff_dt:
                    raise DataContractError("Initial report was published after cutoff")
                available_dt = availability_timestamp(poll.get("version_available_at") or availability,
                                                      poll.get("availability_timezone", "Asia/Jerusalem")) if availability else cutoff_dt
            fieldwork = poll.get("fieldwork_end")
            if not fieldwork:
                raise DataContractError("Fieldwork end date is unknown")
            fielddate = date.fromisoformat(fieldwork[:10])
            if fielddate > cutoff_dt.date():
                raise DataContractError("Fieldwork ends after cutoff")
            if fielddate < (cutoff_dt - timedelta(days=window_days)).date():
                raise DataContractError(f"Fieldwork outside prespecified {window_days}-day window")
            shares, transforms = observation_to_shares(poll, registered_lists, proportional_undecided=proportional_undecided)
            poll.update(shares=shares, transformations=transforms, data_view=view,
                        effective_available_at=available_dt.isoformat())
            poll["_version_sort"] = available_dt.astimezone(timezone.utc)
            candidates.setdefault(survey_id, []).append(poll)
        except (DataContractError, ValueError, TypeError) as exc:
            excluded.append({"survey_id": survey_id, "source_id": poll.get("source_id"), "reason": str(exc)})
    for survey_id, versions in candidates.items():
        # Multiple hypothetical scenarios cannot be counted as independent surveys.
        scenarios = {v.get("scenario_id", "actual") for v in versions}
        if len(scenarios) > 1:
            excluded.append({"survey_id": survey_id, "reason": "Multiple eligible scenarios require an explicit selection"})
            continue
        latest_time = max(v["_version_sort"] for v in versions)
        latest = [v for v in versions if v["_version_sort"] == latest_time]
        signatures = {json.dumps(v["shares"], sort_keys=True) for v in latest}
        if len(signatures) > 1:
            excluded.append({"survey_id": survey_id, "reason": "Conflicting versions with indistinguishable availability"})
            continue
        chosen = latest[0]
        chosen.pop("_version_sort", None)
        selected.append(chosen)
        if len(versions) > 1:
            duplicates.append({"survey_id": survey_id, "removed_publications": len(versions)-1})
    return {"selected": selected, "excluded": excluded, "deduplicated": duplicates,
            "election_id": election_id, "cutoff": cutoff_dt.isoformat(), "view": view,
            "window_days": window_days, "status": "eligible" if selected else "unavailable"}


def assert_training_history(history: Iterable[dict[str, Any]], target_election: str) -> list[dict[str, Any]]:
    if target_election not in ELECTION_ORDER:
        raise DataContractError("Unknown target election")
    position = ELECTION_ORDER.index(target_election)
    records = list(history)
    seen = set()
    for record in records:
        election_id = record.get("election_id")
        if election_id not in ELECTION_ORDER[:position]:
            raise DataContractError(f"Training outcome {election_id!r} is not an earlier permitted election")
        if election_id in seen:
            raise DataContractError("One election cannot contribute repeated independent calibration records")
        seen.add(election_id)
        if record.get("data_view") != "available_at_time":
            raise DataContractError("Reconstructed disclosures cannot silently enter prospective-style calibration")
    return records
