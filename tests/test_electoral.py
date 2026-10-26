import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from knesset_forecast.electoral import AllocationTie, allocate_seats, allocation_diagnostics

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("election", ["2019a", "2019b", "2020", "2021", "2022"])
def test_reproduce_every_official_list_seat_count(election):
    result = json.loads((ROOT / f"data/official/{election}.json").read_text(encoding="utf-8"))
    votes = {row["id"]: row["votes"] for row in result["lists"]}
    assert sum(votes.values()) == result["valid_votes"]
    got = allocate_seats(votes, result["agreements"])
    assert got == {row["id"]: row["seats"] for row in result["lists"]}
    assert sum(got.values()) == 120


@pytest.mark.parametrize("small,passes", [(32499, False), (32500, True), (32501, True)])
def test_threshold_boundary_exact_counts(small, passes):
    result = allocation_diagnostics({"small": small, "large": 1_000_000 - small})
    assert result["passed_threshold"]["small"] is passes
    assert (result["seats"]["small"] > 0) is passes
    assert sum(result["seats"].values()) == 120


def test_failed_partner_does_not_rescue_or_pool_votes():
    votes = {"large": 600_000, "partner": 20_000, "other": 380_000}
    assert allocate_seats(votes, [("large", "partner")]) == allocate_seats(votes)
    assert allocate_seats(votes, [("large", "partner")])["partner"] == 0


def test_denominator_includes_all_valid_votes_and_residuals_are_separate_lists():
    votes = {"a": .50, "b": .40, "c": .031, "tiny1": .023, "tiny2": .023, "tiny3": .023}
    seats = allocate_seats(votes)
    assert all(seats[key] == 0 for key in ["c", "tiny1", "tiny2", "tiny3"])
    assert sum(seats.values()) == 120
    assert allocation_diagnostics(votes)["discarded_valid_vote_share"] == pytest.approx(.10)


def test_lottery_is_explicit_and_convention_is_opt_in():
    with pytest.raises(AllocationTie):
        allocate_seats({"a": .5, "b": .5}, seats=3)
    assert allocate_seats({"a": .5, "b": .5}, seats=3, tie_break="lexicographic") == {"a": 2, "b": 1}


def test_integer_and_continuous_modes_are_identified():
    assert allocation_diagnostics({"a": 550000, "b": 450000})["quota_mode"] == "statutory_integer"
    assert allocation_diagnostics({"a": .55, "b": .45})["quota_mode"] == "continuous_share_extension"
    assert allocate_seats({"a": Fraction(13, 400), "b": Fraction(387, 400)})["a"] > 0


def test_agreements_are_not_transitive_or_repeated():
    with pytest.raises(ValueError, match="multiple"):
        allocate_seats({"a": .4, "b": .3, "c": .3}, [("a", "b"), ("b", "c")])
    with pytest.raises(ValueError, match="registered"):
        allocate_seats({"a": .6, "b": .4}, [("a", "missing")])


@pytest.mark.parametrize("votes", [{}, {"a": 0}, {"a": -1, "b": 100}, {"a": float("nan")}, {"a": float("inf")}, {"a": True}])
def test_reject_invalid_input(votes):
    with pytest.raises(ValueError):
        allocate_seats(votes)


def test_repeated_surplus_awards_and_majority_cap():
    # Half the participating votes may not receive more than half the seats.
    votes = {"a": Fraction(1, 2), **{f"b{i}": Fraction(1, 14) for i in range(7)}}
    result = allocate_seats(votes, tie_break="lexicographic")
    assert result["a"] == 60
    assert sum(result.values()) == 120
    assert all(value >= 0 for value in result.values())


def test_invalid_ballots_are_metadata_and_do_not_enter_threshold():
    result = json.loads((ROOT / "data/official/2022.json").read_text(encoding="utf-8"))
    assert sum(row["votes"] for row in result["lists"]) == 4_764_742
    assert result["invalid_votes"] == 29_851
    assert sum(row["votes"] for row in result["lists"]) != result["valid_votes"] + result["invalid_votes"]
