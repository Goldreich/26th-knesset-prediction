"""Israeli Bader--Ofer allocation (Election Law sections 81--82).

Integer inputs use the statutory integer quota. Non-integer inputs use the
scale-free continuous-share extension: exact rational quota, with no fabricated
number of ballots. Ties require an explicit convention or an actual CEC lot.
"""
from __future__ import annotations

from fractions import Fraction
from numbers import Integral
from typing import Iterable, Mapping


class AllocationTie(ValueError):
    """A statutory lottery is needed; a deterministic result is not known."""


def _fraction(value: int | float | Fraction) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("Votes and thresholds must be finite numbers") from exc
    if result < 0:
        raise ValueError("Votes must be nonnegative")
    return result


def _winner(quotients: Mapping[tuple[str, ...], Fraction], tie_break: str) -> tuple[str, ...]:
    if not quotients:
        raise ValueError("No list eligible for a remaining seat")
    best = max(quotients.values())
    tied = sorted(key for key, value in quotients.items() if value == best)
    if len(tied) > 1 and tie_break == "error":
        raise AllocationTie(f"CEC lottery required between {tied}")
    return tied[0]


def _initial(votes: Mapping[str, Fraction], seats: int, integer_counts: bool) -> dict[str, int]:
    total = sum(votes.values())
    quota = total // seats if integer_counts else total / seats
    if quota <= 0:
        raise ValueError("Integer vote total is too small for the statutory quota")
    result = {key: int(value // quota) for key, value in votes.items()}
    if sum(result.values()) > seats:
        raise ValueError("Integer-quota initial allocation exceeds seats; unsupported degenerate small-count input")
    return result


def allocate_seats(
    votes: Mapping[str, int | float | Fraction],
    agreements: Iterable[tuple[str, str]] = (),
    threshold: float | Fraction = 0.0325,
    seats: int = 120,
    tie_break: str = "error",
) -> dict[str, int]:
    """Allocate seats to explicit registered lists, including zeros for failures.

    `votes` contains valid votes only. Invalid/blank ballots must not be included.
    A residual pool must be split among explicit lists before this function.
    An agreement only operates if both partners individually meet the threshold.
    `lexicographic` is an optional computational tie convention, not the law's lot.
    """
    if not votes or isinstance(seats, bool) or not isinstance(seats, int) or seats <= 0:
        raise ValueError("Provide votes and a positive integer seat count")
    if tie_break not in {"error", "lexicographic"}:
        raise ValueError("tie_break must be error or lexicographic")
    if any(not isinstance(key, str) or not key for key in votes):
        raise ValueError("List IDs must be nonempty strings")
    if any(isinstance(value, bool) for value in votes.values()):
        raise ValueError("Boolean vote counts are invalid")
    threshold_q = _fraction(threshold)
    if not 0 <= threshold_q < 1:
        raise ValueError("threshold must be a proportion in [0, 1)")
    exact = {key: _fraction(value) for key, value in votes.items()}
    total = sum(exact.values())
    if total <= 0:
        raise ValueError("At least one valid vote is required")
    eligible = {key: value for key, value in exact.items() if value > 0 and value >= threshold_q * total}
    if not eligible:
        raise ValueError("No list meets the electoral threshold")
    integer_counts = all(isinstance(value, Integral) for value in votes.values())
    pairs = []
    used: set[str] = set()
    for pair in agreements:
        if len(pair) != 2 or pair[0] == pair[1] or any(key not in exact for key in pair):
            raise ValueError("An agreement requires two distinct registered list IDs")
        if any(key in used for key in pair):
            raise ValueError("A list cannot participate in multiple surplus agreements")
        used.update(pair)
        if all(key in eligible for key in pair):
            pairs.append(tuple(sorted(pair)))
    paired = {key for pair in pairs for key in pair}
    groups = pairs + [(key,) for key in eligible if key not in paired]
    initial = _initial(eligible, seats, integer_counts)
    group_votes = {group: sum(eligible[key] for key in group) for group in groups}
    group_seats = {group: sum(initial[key] for key in group) for group in groups}
    eligible_total = sum(eligible.values())
    for _ in range(seats - sum(initial.values())):
        quotients = {
            group: group_votes[group] / (count + 1)
            for group, count in group_seats.items()
            if not (2 * count >= seats and 2 * group_votes[group] <= eligible_total)
        }
        group_seats[_winner(quotients, tie_break)] += 1
    output = {key: 0 for key in exact}
    for group, count in group_seats.items():
        if len(group) == 1:
            output[group[0]] = count
            continue
        # Section 82(b): recompute the pair's internal quota from its final seats.
        internal_votes = {key: eligible[key] for key in group}
        internal = _initial(internal_votes, count, integer_counts)
        for _ in range(count - sum(internal.values())):
            quotients = {
                (key,): value / (internal[key] + 1)
                for key, value in internal_votes.items()
                if not (2 * internal[key] >= count and 2 * value <= group_votes[group])
            }
            internal[_winner(quotients, tie_break)[0]] += 1
        output.update(internal)
    if sum(output.values()) != seats:
        raise AssertionError("Seat allocation failed conservation")
    return output


def allocation_diagnostics(votes: Mapping[str, int | float], **kwargs) -> dict:
    """Return allocation with discarded share; keep this separate from forecasting."""
    result = allocate_seats(votes, **kwargs)
    exact = {key: _fraction(value) for key, value in votes.items()}
    total = sum(exact.values())
    threshold = _fraction(kwargs.get("threshold", 0.0325))
    passed = {key: value > 0 and value >= threshold * total for key, value in exact.items()}
    return {
        "seats": result,
        "passed_threshold": passed,
        "discarded_valid_vote_share": float(sum(value for key, value in exact.items() if not passed[key]) / total),
        "quota_mode": "statutory_integer" if all(isinstance(v, Integral) for v in votes.values()) else "continuous_share_extension",
    }
