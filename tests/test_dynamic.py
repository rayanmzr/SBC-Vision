"""Chaque capture produit ses propres conditions ; aucun nom de SBC n'est nécessaire."""

import json
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from sbc_vision.sbc_engine.catalogue import import_file, open_database
from sbc_vision.sbc_engine.inventory import load_pool, seed_demo
from sbc_vision.sbc_engine.models import Challenge, ClubItem, Condition
from sbc_vision.sbc_engine.ocr import challenge_from_ocr, number, parse_requirements
from sbc_vision.sbc_engine.solver import alternatives, solve, team_rating, validate

FIXTURES = Path(__file__).resolve().parents[1] / "data/fixtures"


@pytest.fixture
def setup(tmp_path):
    club = json.loads((FIXTURES / "club.synthetic.json").read_text())
    demo = json.loads((FIXTURES / "solver.synthetic.json").read_text())
    with closing(open_database(tmp_path / "dynamic.sqlite3")) as db:
        seed_demo(db, club, demo["extra_cards"])
        pool = load_pool(db, "pc", now=datetime.fromisoformat(demo["price_reference_at"]))
        yield db, pool


def parsed(text, db, positions=None):
    return parse_requirements(text, db, positions=positions or [], market="pc", budget=2000)


@pytest.mark.parametrize("leagues, cost", [(1, 2100), (2, 2600)])
def test_changing_conditions_changes_the_solution_without_challenge_specific_code(
    setup, leagues, cost
):
    db, pool = setup
    text = (
        "Number of players: 3\nPlayer rating: Min. 82\nRare players: Min. 1\n"
        f"Leagues: Exact {leagues}"
    )
    report = parsed(text, db, ["CAM", "CM", "ST"])
    assert report["ready"], report["issues"]
    challenge = Challenge.model_validate(report["challenge"])
    result = solve(challenge, pool)
    assert result.status == "optimal"
    assert result.total_cost == cost
    assert validate(challenge, pool, result.assignments) == []


@pytest.mark.parametrize(
    "text",
    [
        "Unknown requirement: Min. 3",
        "Rare players: 1",
        "Nation ???: Min. 2",
        "Number of players: 3\nLoans: Exact 0",
    ],
)
def test_unknown_or_incomplete_conditions_block_the_entire_request(setup, text):
    db, _ = setup
    report = parsed(text, db, ["CM", "ST", "CAM"])
    assert report["ready"] is False
    assert report["challenge"] is None
    assert report["issues"]


def test_french_labels_and_wrapped_values_are_supported(setup):
    db, pool = setup
    report = parsed(
        "Nombre de joueurs\n3\nNote individuelle: Min 82\nJoueurs or: Min 3",
        db,
        ["CAM", "CM", "ST"],
    )
    assert report["ready"], report["issues"]
    assert solve(Challenge.model_validate(report["challenge"]), pool).status == "optimal"


def test_specific_ids_and_named_targets_require_catalogue_evidence(setup):
    db, _ = setup
    assert parsed("Nation #9003: Min 2", db, ["CM", "ST"])["ready"]
    assert not parsed("Nation France: Min 2", db, ["CM", "ST"])["ready"]
    row = db.execute("SELECT data FROM cards WHERE id=900001").fetchone()
    card = {**json.loads(row["data"]), "nation_name": "France"}
    db.execute("UPDATE cards SET data=? WHERE id=900001", (json.dumps(card),))
    assert parsed("Nation France: Min 2", db, ["CM", "ST"])["ready"]


def test_low_confidence_on_any_condition_blocks_solving(setup):
    db, _ = setup
    report = {
        "positions": ["CM"],
        "regions": [
            {"field": "requirements", "text": "Number of players: 1", "confidence": 0.99},
            {"field": "requirements", "text": "Player rating: Min 90", "confidence": 0.2},
        ],
    }
    assert not challenge_from_ocr(report, db, market="pc", budget=2000)["ready"]


@pytest.mark.parametrize("text, expected", [("1.001K", 1001), ("1,200", 1200), ("1.5K", 1500)])
def test_scores_are_parsed_without_float_rounding(text, expected):
    assert number(text) == expected


def test_score_challenge_can_use_distinct_owned_copies_of_the_same_player(setup):
    db, pool = setup
    report = parsed("Item Score: 820\nPlayer rating: Min 75", db)
    assert report["ready"], report["issues"]
    copies = [
        c.model_copy(update={"protected": False, "item_score": 410})
        for c in pool
        if c.key in {"club:demo-001", "club:demo-002"}
    ]
    challenge = Challenge.model_validate(report["challenge"]).model_copy(update={"budget": 0})
    result = solve(challenge, copies)
    assert result.status == "optimal"
    assert len(result.assignments) == 2
    assert result.purchase_cost == 0
    assert result.sacrifice_value == 1600
    assert validate(challenge, copies, result.assignments) == []


def test_score_progress_and_available_quantity_are_respected(setup):
    db, pool = setup
    report = parsed("Item Score: 500 / 1,000", db)
    challenge = Challenge.model_validate(report["challenge"])
    card = pool[-1].model_copy(update={"item_score": 300, "value": 100, "max_quantity": 2})
    result = solve(challenge, [card])
    assert result.status == "optimal"
    assert len(result.assignments) == 2
    assert result.purchase_cost == 200
    assert solve(challenge, [card.model_copy(update={"max_quantity": 1})]).status == "infeasible"


def test_completed_score_challenge_does_not_sacrifice_anything(setup):
    db, pool = setup
    report = parsed("Item Score: 1,000 / 1,000", db)
    result = solve(Challenge.model_validate(report["challenge"]), pool)
    assert result.status == "optimal"
    assert result.assignments == []
    assert result.total_cost == 0


@pytest.mark.parametrize(
    "ratings, expected", [([80] * 9 + [83] * 2, 81), ([80] * 10 + [83], 80), ([84] * 11, 84)]
)
def test_eleven_player_rating_uses_correction_and_rounding(setup, ratings, expected):
    _, pool = setup
    cards = [
        pool[0].model_copy(
            update={
                "key": str(i),
                "base_id": 990000 + i,
                "rating": rating,
                "positions": ["CM"],
                "protected": False,
            }
        )
        for i, rating in enumerate(ratings)
    ]
    challenge = Challenge(
        rules_version="dynamic-v1",
        positions=["CM"] * 11,
        market="pc",
        budget=0,
        conditions=[Condition(metric="team_rating", value=expected)],
    )
    assert team_rating(ratings) == expected
    assert solve(challenge, cards).status == "optimal"
    wrong = challenge.model_copy(
        update={"conditions": [Condition(metric="team_rating", value=expected + 1)]}
    )
    assert solve(wrong, cards).status == "infeasible"


def test_standard_chemistry_is_checked_and_special_profiles_are_excluded(setup):
    _, pool = setup
    cards = [
        pool[0].model_copy(
            update={
                "key": str(i),
                "base_id": 990000 + i,
                "positions": ["CM"],
                "protected": False,
                "chemistry_kind": "standard",
            }
        )
        for i in range(11)
    ]
    challenge = Challenge(
        rules_version="dynamic-v1",
        positions=["CM"] * 11,
        market="pc",
        budget=0,
        conditions=[Condition(metric="chemistry", value=33)],
    )
    assert solve(challenge, cards).status == "optimal"
    unsupported = [c.model_copy(update={"chemistry_kind": "unsupported"}) for c in cards]
    assert solve(challenge, unsupported).status == "infeasible"


def test_file_import_keeps_original_dates_and_null_prices(setup, tmp_path):
    db, _ = setup
    card = json.loads(db.execute("SELECT data FROM cards WHERE id=900002").fetchone()[0])
    path = tmp_path / "cards.json"
    path.write_text(json.dumps({"cards": [card]}))
    assert import_file(db, path) == 1
    saved = json.loads(db.execute("SELECT data FROM cards WHERE id=900002").fetchone()[0])
    assert saved["observed_at"] == card["observed_at"]
    assert saved["prices"]["pc"] is None


def test_item_score_is_preserved_on_an_owned_copy(setup):
    from sbc_vision.sbc_engine.inventory import list_items, save_item

    db, _ = setup
    save_item(
        db,
        ClubItem(
            instance_id="demo-002", card_id=900001, source_observation="new:score", item_score=410
        ),
        confirmed=True,
    )
    assert next(i for i in list_items(db) if i["instance_id"] == "demo-002")["item_score"] == 410


def test_alternatives_are_recomputed_and_validate_the_whole_team(setup):
    db, pool = setup
    report = parsed("Number of players: 3\nPlayer rating: Min 82", db, ["CAM", "CM", "ST"])
    challenge = Challenge.model_validate(report["challenge"])
    solution = solve(challenge, pool)
    options = alternatives(challenge, pool, solution)
    from sbc_vision.sbc_engine.models import Assignment

    assert options
    for option in options:
        team = [Assignment.model_validate(a) for a in option["solution"]["assignments"]]
        assert validate(challenge, pool, team) == []
        selected = {a.candidate_key for a in team}
        assert not any(c.card_id == option["excluded_card_id"] and c.key in selected for c in pool)


def test_quality_applies_to_every_selected_card_and_max_score_is_not_a_goal(setup):
    db, pool = setup
    report = parsed("Item Score: 100\nQualité des joueurs: Or", db)
    assert report["ready"], report["issues"]
    assert report["challenge"]["card_level"] == "GOLD"
    assert not parsed("Item Score: Max 100", db)["ready"]
