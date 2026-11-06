"""Vérifications hors ligne sur un défi entièrement fictif."""

import json
from contextlib import closing
from datetime import datetime, timedelta
from itertools import permutations
from pathlib import Path
from unittest.mock import Mock

import pytest
from ortools.sat.python import cp_model
from pydantic import ValidationError

from sbc_vision.sbc_engine.__main__ import main
from sbc_vision.sbc_engine.catalogue import open_database
from sbc_vision.sbc_engine.inventory import load_pool, seed_demo
from sbc_vision.sbc_engine.models import Assignment, Challenge
from sbc_vision.sbc_engine.solver import greedy, solve, validate

FIXTURES = Path(__file__).resolve().parents[1] / "data/fixtures"


@pytest.fixture
def setup(tmp_path):
    club = json.loads((FIXTURES / "club.synthetic.json").read_text())
    demo = json.loads((FIXTURES / "solver.synthetic.json").read_text())
    now = datetime.fromisoformat(demo["price_reference_at"])
    challenge = Challenge.model_validate(demo["challenge"])
    with closing(open_database(tmp_path / "solver.sqlite3")) as db:
        seed_demo(db, club, demo["extra_cards"])
        pool = load_pool(db, challenge.market, now=now)
        yield challenge, pool, db, now


def test_global_optimization_saves_value_and_keeps_protected_copy(setup):
    challenge, pool, _, _ = setup
    baseline, solution = greedy(challenge, pool), solve(challenge, pool)
    assert baseline.total_cost == 2600
    assert solution.status == "optimal"
    assert solution.total_cost == 2100
    assert solution.purchase_cost == 1300
    assert solution.sacrifice_value == 800
    assert [a.candidate_key for a in solution.assignments] == [
        "market:900006",
        "club:demo-002",
        "market:900004",
    ]
    assert "club:demo-001" in solution.excluded_keys
    assert "market:900002" in solution.excluded_keys
    assert validate(challenge, pool, solution.assignments) == []


def test_greedy_failure_does_not_prove_impossibility(setup):
    challenge, pool, _, _ = setup
    challenge = challenge.model_copy(update={"budget": 1300})
    assert greedy(challenge, pool).status == "unknown"
    assert solve(challenge, pool).status == "optimal"


@pytest.mark.parametrize(
    "update",
    [
        {"budget": 0},
        {"min_card_rating": 99},
        {"positions": ["GK"]},
        {"min_rare": 2},
        {"nation_id": 9999, "min_nation": 1},
        {"league_id": 9999, "min_league": 1},
    ],
)
def test_infeasibility_is_reported_without_a_fake_team(setup, update):
    challenge, pool, _, _ = setup
    solution = solve(challenge.model_copy(update=update), pool)
    assert solution.status == "infeasible"
    assert solution.assignments == []
    assert solution.total_cost is None


def test_unknown_price_and_stale_or_future_quotes_are_not_free(setup):
    challenge, pool, db, now = setup
    unknown = next(card for card in pool if card.key == "market:900002")
    assert unknown.value is None
    for shifted in (now + timedelta(days=2), now - timedelta(days=2)):
        stale = load_pool(db, challenge.market, now=shifted)
        assert all(card.value is None for card in stale)
        assert solve(challenge, stale).status == "infeasible"


def test_other_market_price_is_never_used_as_fallback(setup):
    _, pool, db, now = setup
    assert next(c.value for c in pool if c.key == "market:900002") is None
    console = load_pool(db, "ps", now=now)
    assert next(c.value for c in console if c.key == "market:900002") == 1300


def test_owned_card_is_valued_instead_of_automatically_free(setup):
    _, pool, _, _ = setup
    expensive = next(card for card in pool if card.key == "club:demo-003")
    challenge = Challenge(rules_version="prototype-v1", positions=["ST"], market="pc", budget=500)
    solution = solve(challenge, [expensive, next(c for c in pool if c.key == "market:900004")])
    assert solution.total_cost == 400
    assert solution.assignments[0].candidate_key == "market:900004"


def test_same_player_cannot_fill_two_slots_with_copies_or_versions(setup):
    _, pool, _, _ = setup
    a = next(card for card in pool if card.key == "club:demo-002")
    b = a.model_copy(update={"key": "other-version", "card_id": 900099})
    challenge = Challenge(
        rules_version="prototype-v1", positions=["CM", "CAM"], market="pc", budget=0
    )
    assert solve(challenge, [a, b]).status == "infeasible"


def test_ties_preserve_rare_cards_then_prefer_an_owned_copy(setup):
    _, pool, _, _ = setup
    normal = next(card for card in pool if card.key == "club:demo-002")
    rare = normal.model_copy(update={"key": "rare", "base_id": 999001, "is_rare": True})
    purchase = normal.model_copy(update={"key": "purchase", "base_id": 999002, "owned": False})
    challenge = Challenge(rules_version="prototype-v1", positions=["CM"], market="pc", budget=5000)
    assert solve(challenge, [rare, purchase, normal]).assignments[0].candidate_key == normal.key


@pytest.mark.parametrize(
    "change, expected",
    [
        ("protected", "protégée"),
        ("position", "Poste"),
        ("duplicate", "plusieurs fois"),
        ("unknown", "inconnu"),
        ("slot", "emplacement"),
    ],
)
def test_independent_verifier_rejects_tampered_compositions(setup, change, expected):
    challenge, pool, _, _ = setup
    team = solve(challenge, pool).assignments
    if change == "protected":
        team[1] = Assignment(slot=1, candidate_key="club:demo-001")
    elif change == "position":
        team[0] = Assignment(slot=0, candidate_key="market:900005")
    elif change == "duplicate":
        team[0] = Assignment(slot=0, candidate_key="club:demo-002")
    elif change == "unknown":
        team[0] = Assignment(slot=0, candidate_key="does-not-exist")
    else:
        team[0] = Assignment(slot=1, candidate_key=team[0].candidate_key)
    assert expected in " ".join(validate(challenge, pool, team))


def test_small_case_matches_exhaustive_enumeration(setup):
    challenge, pool, _, _ = setup
    scores = []
    # Toutes les affectations du petit exemple sont vérifiées sans appeler le solveur.
    for team in permutations(pool, len(challenge.positions)):
        if any(c.protected or c.value is None for c in team):
            continue
        if len({c.base_id for c in team}) != len(team):
            continue
        if any(p not in c.positions for p, c in zip(challenge.positions, team, strict=True)):
            continue
        if min(c.rating for c in team) < challenge.min_card_rating:
            continue
        if sum(c.value for c in team if not c.owned) > challenge.budget:
            continue
        if sum(c.is_rare for c in team) < challenge.min_rare:
            continue
        if sum(c.nation_id == challenge.nation_id for c in team) < challenge.min_nation:
            continue
        if sum(c.league_id == challenge.league_id for c in team) < challenge.min_league:
            continue
        scores.append(
            (
                sum(c.value for c in team),
                sum(c.is_rare for c in team),
                sum(not c.owned for c in team),
            )
        )
    solution = solve(challenge, pool)
    chosen = [next(c for c in pool if c.key == a.candidate_key) for a in solution.assignments]
    assert (
        solution.total_cost,
        sum(c.is_rare for c in chosen),
        sum(not c.owned for c in chosen),
    ) == min(scores)


def test_unknown_solver_status_never_claims_impossibility(setup, monkeypatch):
    challenge, pool, _, _ = setup
    fake = Mock()
    fake.solve.return_value = cp_model.UNKNOWN
    monkeypatch.setattr("sbc_vision.sbc_engine.solver.cp_model.CpSolver", lambda: fake)
    solution = solve(challenge, pool)
    assert solution.status == "unknown"
    assert solution.assignments == []
    assert solution.total_cost is None
    fake.value.assert_not_called()


def test_duplicate_candidate_keys_are_rejected(setup):
    challenge, pool, _, _ = setup
    with pytest.raises(ValueError, match="uniques"):
        solve(challenge, pool + [pool[0]])


@pytest.mark.parametrize("extra", [{"min_team_rating": 83}, {"min_chemistry": 33}])
def test_unimplemented_fc_rules_are_rejected(extra):
    with pytest.raises(ValidationError):
        Challenge.model_validate(
            {
                "rules_version": "prototype-v1",
                "positions": ["CM"],
                "market": "pc",
                "budget": 1000,
                **extra,
            }
        )


def test_cli_produces_a_verifiable_local_report(tmp_path):
    output = tmp_path / "plan.json"
    assert (
        main(["solve", "--demo", "--db", str(tmp_path / "demo.sqlite3"), "--output", str(output)])
        == 0
    )
    report = json.loads(output.read_text())
    assert report["solution"]["status"] == "optimal"
    assert report["solution"]["total_cost"] == 2100
    assert all(
        c["source_url"].startswith("urn:sbc-vision:synthetic:")
        for c in report["selected_candidates"]
    )
