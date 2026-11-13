"""Vérifications hors ligne sur un défi entièrement fictif."""

import json
from contextlib import closing
from datetime import UTC, datetime, timedelta
from itertools import permutations
from pathlib import Path
from unittest.mock import Mock

import pytest
from ortools.sat.python import cp_model
from pydantic import ValidationError

from sbc_vision.sbc_engine.__main__ import main
from sbc_vision.sbc_engine.models import Assignment, Challenge, Condition
from sbc_vision.sbc_engine.players import (
    list_items,
    load_pool,
    open_database,
    save_cards,
    seed_demo,
)
from sbc_vision.sbc_engine.solver import (
    condition_checks,
    greedy,
    recheck,
    shopping_list,
    solve,
    validate,
    verification,
)

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


@pytest.fixture
def proposal(setup):
    challenge, pool, _, now = setup
    return {
        "challenge": challenge.model_dump(),
        "solution": solve(challenge, pool).model_dump(),
        "selected_candidates": [c.model_dump() for c in pool],
        "price_reference_at": now.isoformat(),
    }


def test_saved_proposal_is_checked_without_requiring_identical_quote_timestamps(setup, proposal):
    challenge, _, db, now = setup
    card = json.loads(db.execute("SELECT data FROM cards WHERE id=900006").fetchone()[0])
    refreshed = now + timedelta(minutes=1)
    save_cards(db, [{**card, "observed_at": refreshed.isoformat()}])
    current = load_pool(db, challenge.market, now=refreshed)
    checked = recheck(proposal, current)
    assert checked["valid"] is True and checked["needs_recalculation"] is False
    assert checked["errors"] == [] and checked["verification"]["valid"] is True
    assert checked["shopping_list"]["estimated_cost"] == 1300


@pytest.mark.parametrize(
    "change", ["protected", "price", "missing", "position", "version", "unknown", "quantity"]
)
def test_changed_selected_cards_require_a_new_proposal(setup, proposal, change):
    _, pool, _, _ = setup
    key = "club:demo-002" if change in {"protected", "missing"} else "market:900006"
    updates = {
        "protected": {"protected": True},
        "price": {"value": 950},
        "position": {"positions": ["GK"]},
        "version": {"card_id": 900099},
        "unknown": {"value": None},
        "quantity": {"max_quantity": 2},
    }
    current = [
        c.model_copy(update=updates.get(change, {})) if c.key == key else c
        for c in pool
        if change != "missing" or c.key != key
    ]
    checked = recheck(proposal, current)
    assert checked["valid"] is False and checked["needs_recalculation"] is True
    assert checked["errors"]
    assert checked["verification"] is None and checked["shopping_list"] is None


@pytest.mark.parametrize("field", ["total_cost", "purchase_cost", "sacrifice_value"])
def test_modified_report_costs_are_not_accepted(setup, proposal, field):
    proposal["solution"][field] = 0
    checked = recheck(proposal, setup[1])
    assert checked["valid"] is False
    assert any("coûts enregistrés" in e for e in checked["errors"])


def test_a_report_without_a_feasible_team_cannot_be_reused(setup, proposal):
    proposal["solution"].update(status="unknown", assignments=[])
    checked = recheck(proposal, setup[1])
    assert checked["valid"] is False and checked["shopping_list"] is None


@pytest.mark.parametrize("change", [None, "protected", "price", "missing", "stale"])
def test_check_cli_reads_the_current_database_and_keeps_the_saved_proposal(
    setup, proposal, tmp_path, change
):
    _, _, db, _ = setup
    path, output = tmp_path / "proposal.json", tmp_path / "check.json"
    path.write_text(json.dumps(proposal))
    original = path.read_text()
    if change == "protected":
        db.execute("UPDATE club_items SET protected=1 WHERE instance_id='demo-002'")
        db.commit()
    elif change == "missing":
        db.execute("DELETE FROM club_items WHERE instance_id='demo-002'")
        db.commit()
    elif change in {"price", "stale"}:
        card = json.loads(db.execute("SELECT data FROM cards WHERE id=900006").fetchone()[0])
        if change == "price":
            card["prices"]["pc"] = 950
        else:
            card["observed_at"] = "2000-01-01T00:00:00+00:00"
        save_cards(db, [card])
    args = [
        "check",
        str(path),
        "--demo",
        "--db",
        db.execute("PRAGMA database_list").fetchone()[2],
        "--output",
        str(output),
    ]
    assert main(args) == (0 if change is None else 2)
    checked = json.loads(output.read_text())
    assert checked["valid"] is (change is None)
    assert checked["needs_recalculation"] is (change is not None)
    assert checked["demo"] is True
    assert path.read_text() == original


def test_check_demo_cannot_use_a_real_database_at_the_fictional_date(setup, proposal, tmp_path):
    _, _, db, _ = setup
    card = json.loads(db.execute("SELECT data FROM cards LIMIT 1").fetchone()[0])
    save_cards(db, [{**card, "source_url": "https://www.futbin.com/27/player/1"}])
    path, output = tmp_path / "proposal.json", tmp_path / "check.json"
    path.write_text(json.dumps(proposal))
    args = [
        "check",
        str(path),
        "--demo",
        "--db",
        db.execute("PRAGMA database_list").fetchone()[2],
        "--output",
        str(output),
    ]
    assert main(args) == 1
    assert not output.exists()


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


def test_scan_to_solver_reuses_copies_and_obeys_a_new_protection(tmp_path):
    database, output = tmp_path / "scan.sqlite3", tmp_path / "solution.json"
    args = [
        "solve",
        "--demo",
        "--scan",
        "--db",
        str(database),
        "--output",
        str(output),
        "--max-card-value",
        "1000",
        "--budget",
        "2500",
        "--alternatives",
        "0",
    ]
    for repetition in range(2):
        assert main(args) == 0
        report = json.loads(output.read_text())
        assert report["scan"]["items"] == 3
        assert report["scan"]["reobserved"] == 1
        assert report["scan"]["new"] == (3 if repetition == 0 else 0)
        assert report["solution"]["total_cost"] == 2100
        assert report["solution"]["purchase_cost"] == 1300
        assert report["solution"]["sacrifice_value"] == 800
        assert {c["key"] for c in report["selected_candidates"] if c["owned"]} == {"club:demo-002"}
        assert {i["card_id"] for i in report["shopping_list"]["items"]} == {900004, 900006}
        assert report["verification"]["valid"] is True
    # Protéger la copie utilisable impose un achat, sans retirer les protections au rescan.
    assert main(["club", "--db", str(database), "protect", "demo-002"]) == 0
    assert main(args) == 0
    report = json.loads(output.read_text())
    assert report["solution"]["purchase_cost"] == 2100
    assert report["solution"]["sacrifice_value"] == 0
    assert all(not c["owned"] for c in report["selected_candidates"])
    with closing(open_database(database)) as db:
        items = list_items(db)
        assert len(items) == 3 and sum(i["protected"] for i in items) == 2


def test_scan_solver_demo_refuses_a_real_database_without_overwriting_outputs(tmp_path):
    database, output = tmp_path / "real.sqlite3", tmp_path / "solution.json"
    fixture = json.loads((FIXTURES / "club.synthetic.json").read_text())
    with closing(open_database(database)) as db:
        save_cards(
            db, [{**fixture["catalogue"][0], "source_url": "https://www.futbin.com/27/player/1"}]
        )
    output.write_text('{"previous": true}')
    assert main(["solve", "--demo", "--scan", "--db", str(database), "--output", str(output)]) == 1
    assert output.read_text() == '{"previous": true}'
    with closing(open_database(database)) as db:
        assert list_items(db) == []
        assert db.execute("SELECT COUNT(*) FROM cards").fetchone()[0] == 1


def test_scan_option_never_confirms_a_real_inventory_implicitly(tmp_path):
    database, output = tmp_path / "club.sqlite3", tmp_path / "solution.json"
    assert (
        main(
            [
                "solve",
                "--scan",
                "--challenge",
                "missing.json",
                "--db",
                str(database),
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert not database.exists() and not output.exists()


def test_greedy_failure_does_not_prove_impossibility(setup):
    challenge, pool, _, _ = setup
    challenge = challenge.model_copy(update={"budget": 1300})
    assert greedy(challenge, pool).status == "unknown"
    assert solve(challenge, pool).status == "optimal"


@pytest.mark.parametrize(
    "update",
    [
        {"budget": 0},
        {"conditions": [Condition(metric="rating", value=99)]},
        {"positions": ["GK"]},
        {"conditions": [Condition(metric="rare", value=2)]},
        {"conditions": [Condition(metric="nation", target=9999, value=1)]},
        {"conditions": [Condition(metric="league", target=9999, value=1)]},
        {"max_card_value": 899},
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
    challenge = Challenge(positions=["ST"], market="pc", budget=500)
    solution = solve(challenge, [expensive, next(c for c in pool if c.key == "market:900004")])
    assert solution.total_cost == 400
    assert solution.assignments[0].candidate_key == "market:900004"


def test_same_player_cannot_fill_two_slots_with_copies_or_versions(setup):
    _, pool, _, _ = setup
    a = next(card for card in pool if card.key == "club:demo-002")
    b = a.model_copy(update={"key": "other-version", "card_id": 900099})
    challenge = Challenge(positions=["CM", "CAM"], market="pc", budget=0)
    assert solve(challenge, [a, b]).status == "infeasible"


def test_ties_preserve_rare_cards_then_prefer_an_owned_copy(setup):
    _, pool, _, _ = setup
    normal = next(card for card in pool if card.key == "club:demo-002")
    rare = normal.model_copy(update={"key": "rare", "base_id": 999001, "is_rare": True})
    purchase = normal.model_copy(update={"key": "purchase", "base_id": 999002, "owned": False})
    challenge = Challenge(positions=["CM"], market="pc", budget=5000)
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
        if sum(c.value for c in team if not c.owned) > challenge.budget:
            continue
        valid = True
        for rule in challenge.conditions:
            if rule.metric == "rating":
                actual = min(c.rating for c in team)
            elif rule.metric == "rare":
                actual = sum(c.is_rare for c in team)
            else:
                actual = sum(getattr(c, f"{rule.metric}_id") == rule.target for c in team)
            valid &= actual >= rule.value
        if not valid:
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
                "rules_version": "dynamic-v1",
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
    assert report["verification"]["valid"] is True
    checks = {row["metric"]: row for row in report["verification"]["checks"]}
    assert checks["budget"]["actual"] == 1300
    assert checks["budget"]["value"] == 2000
    assert all(row["passed"] for row in checks.values())
    purchases = report["shopping_list"]
    assert purchases["estimated_cost"] == 1300
    assert purchases["remaining_budget"] == 700
    assert {item["card_id"] for item in purchases["items"]} == {900004, 900006}
    assert all(item["quoted_unit_price"] == item["max_unit_price"] for item in purchases["items"])
    assert sum(item["max_unit_price"] * item["quantity"] for item in purchases["items"]) <= 2000
    assert all(
        c["source_url"].startswith("urn:sbc-vision:synthetic:")
        for c in report["selected_candidates"]
    )


def test_score_purchases_group_known_quantities_without_multiplying_the_budget(setup):
    _, pool, _, _ = setup
    card = next(c for c in pool if c.key == "market:900006").model_copy(
        update={"item_score": 400, "value": 100, "max_quantity": 3}
    )
    challenge = Challenge(
        mode="score",
        market="pc",
        budget=1000,
        max_card_value=100,
        conditions=[Condition(metric="item_score", value=1000)],
    )
    solution = solve(challenge, [card])
    purchases = shopping_list(challenge, [card], solution)
    assert purchases["estimated_cost"] == 300
    assert purchases["remaining_budget"] == 700
    assert len(purchases["items"]) == 1
    assert purchases["items"][0]["quantity"] == 3
    assert purchases["items"][0]["max_unit_price"] == 100
    assert purchases["items"][0]["slots"] == [0, 1, 2]


@pytest.mark.parametrize("problem", ["unknown_price", "protected", "position", "budget"])
def test_purchase_list_rechecks_the_team_when_prices_or_conditions_change(setup, problem):
    challenge, pool, _, _ = setup
    solution = solve(challenge, pool)
    if problem == "budget":
        challenge = challenge.model_copy(update={"budget": 0})
    else:
        update = {
            "unknown_price": {"value": None},
            "protected": {"protected": True},
            "position": {"positions": ["GK"]},
        }[problem]
        pool = [c.model_copy(update=update) if c.key == "market:900006" else c for c in pool]
    with pytest.raises(ValueError, match="Liste d'achats refusée"):
        shopping_list(challenge, pool, solution)


@pytest.mark.parametrize("status", ["unknown", "infeasible"])
def test_no_purchase_list_is_suggested_without_a_valid_solution(setup, status):
    challenge, pool, _, _ = setup
    solution = solve(challenge, pool).model_copy(update={"status": status})
    assert shopping_list(challenge, pool, solution) is None
    assert verification(challenge, pool, solution) is None


def test_owned_only_solution_does_not_create_a_purchase(setup):
    _, pool, _, _ = setup
    card = next(c for c in pool if c.key == "club:demo-002")
    challenge = Challenge(positions=["CM"], market="pc", budget=0)
    solution = solve(challenge, [card])
    purchases = shopping_list(challenge, [card], solution)
    assert purchases["items"] == []
    assert purchases["estimated_cost"] == 0


@pytest.mark.parametrize("owned", [True, False])
def test_value_cap_is_enforced_for_both_owned_cards_and_purchases(setup, owned):
    _, pool, _, _ = setup
    card = next(c for c in pool if c.key == "club:demo-002").model_copy(update={"owned": owned})
    challenge = Challenge(positions=["CM"], market="pc", budget=1000, max_card_value=799)
    result = solve(challenge, [card])
    assert result.status == "infeasible"
    assert card.key in result.excluded_keys

    # Un ancien plan valide doit être refusé si la préférence utilisateur devient plus stricte.
    old_plan = solve(challenge.model_copy(update={"max_card_value": None}), [card])
    assert "Valeur maximale" in " ".join(validate(challenge, [card], old_plan.assignments))
    with pytest.raises(ValueError, match="Liste d'achats refusée"):
        shopping_list(challenge, [card], old_plan)
    with pytest.raises(ValueError, match="Vérification refusée"):
        verification(challenge, [card], old_plan)
    assert solve(challenge.model_copy(update={"max_card_value": 800}), [card]).status == "optimal"


@pytest.mark.parametrize("value", [0, -10, True, 1_000_000_001])
def test_invalid_value_caps_are_rejected(value):
    with pytest.raises(ValidationError):
        Challenge(positions=["CM"], market="pc", budget=1000, max_card_value=value)


def test_cli_value_cap_is_saved_in_the_plan_and_invalid_limits_are_rejected(tmp_path):
    output = tmp_path / "limited.json"
    args = ["solve", "--demo", "--db", str(tmp_path / "club.sqlite3"), "--alternatives", "0"]
    assert main(args + ["--max-card-value", "1000", "--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["challenge"]["max_card_value"] == 1000
    assert report["solution"]["status"] == "optimal"
    assert report["solution"]["total_cost"] == 2100
    assert all(c["value"] <= 1000 for c in report["selected_candidates"])
    assert main(args + ["--max-card-value", "0", "--output", str(tmp_path / "invalid.json")]) == 1
    assert not (tmp_path / "invalid.json").exists()


def test_cli_budget_override_is_explicit_and_does_not_change_saved_reading(tmp_path):
    fixture = json.loads((FIXTURES / "solver.synthetic.json").read_text())
    reading = tmp_path / "reading.json"
    reading.write_text(json.dumps({"ready": True, "challenge": fixture["challenge"]}))
    output = tmp_path / "solution.json"
    database = tmp_path / "demo.sqlite3"
    assert main(["solve", "--demo", "--db", str(database), "--output", str(output)]) == 0
    with closing(open_database(database)) as db:
        cards = [json.loads(row["data"]) for row in db.execute("SELECT data FROM cards")]
        for card in cards:
            card["observed_at"] = datetime.now(UTC).isoformat()
        save_cards(db, cards)
    args = ["solve", "--reading", str(reading), "--db", str(database), "--alternatives", "0"]
    assert main(args + ["--budget", "1300", "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["challenge"]["budget"] == 1300
    assert result["solution"]["purchase_cost"] == 1300
    assert json.loads(reading.read_text())["challenge"]["budget"] == 2000
    assert main(args + ["--output", str(output)]) == 0
    assert json.loads(output.read_text())["challenge"]["budget"] == 2000
    assert main(args + ["--budget", "-1", "--output", str(tmp_path / "invalid.json")]) == 1


@pytest.mark.parametrize(
    "op, value, expected", [("min", 82, True), ("max", 82, False), ("exact", 83, False)]
)
def test_individual_rating_report_checks_every_selected_card(setup, op, value, expected):
    _, pool, _, _ = setup
    cards = [pool[0].model_copy(update={"rating": r}) for r in (83, 82)]
    challenge = Challenge(
        positions=["CM", "CM"],
        market="pc",
        budget=0,
        conditions=[Condition(metric="rating", op=op, value=value)],
    )
    row = condition_checks(challenge, cards)[0]
    assert row["actual"] == [83, 82]
    assert row["passed"] is expected


def test_missing_club_cannot_create_a_fictional_chemistry_link(setup):
    _, pool, _, _ = setup
    cards = [
        pool[0].model_copy(
            update={
                "key": f"c{i}",
                "base_id": 980000 + i,
                "positions": ["CM"],
                "protected": False,
                "club_id": None,
                "chemistry_kind": "standard",
            }
        )
        for i in range(11)
    ]
    challenge = Challenge(
        positions=["CM"] * 11,
        market="pc",
        budget=0,
        conditions=[Condition(metric="chemistry", value=30)],
    )
    team = [Assignment(slot=i, candidate_key=c.key) for i, c in enumerate(cards)]
    row = condition_checks(challenge, cards)[0]
    assert row["actual"] is None and row["passed"] is False
    assert validate(challenge, cards, team)


def test_verification_rejects_a_plan_when_a_copy_is_now_protected(setup):
    challenge, pool, _, _ = setup
    solution = solve(challenge, pool)
    changed = [
        c.model_copy(update={"protected": True}) if c.key == "club:demo-002" else c for c in pool
    ]
    with pytest.raises(ValueError, match="protégée"):
        verification(challenge, changed, solution)
