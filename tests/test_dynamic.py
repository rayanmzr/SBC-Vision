"""Chaque capture produit ses propres conditions ; aucun nom de SBC n'est nécessaire."""

import json
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from sbc_vision.sbc_engine.models import Challenge, ClubItem, Condition
from sbc_vision.sbc_engine.ocr import challenge_from_ocr, number, parse_requirements
from sbc_vision.sbc_engine.players import import_file, load_pool, open_database, seed_demo
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
    from sbc_vision.sbc_engine.players import list_items, save_item

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
        assert option["shopping_list"]["estimated_cost"] == option["solution"]["purchase_cost"]


def test_quality_applies_to_every_selected_card_and_max_score_is_not_a_goal(setup):
    db, pool = setup
    report = parsed("Item Score: 100\nQualité des joueurs: Or", db)
    assert report["ready"], report["issues"]
    assert report["challenge"]["card_level"] == "GOLD"
    assert not parsed("Item Score: Max 100", db)["ready"]


@pytest.mark.parametrize(
    "label, accepted",
    [
        ("Min. Silver", {"SILVER", "GOLD"}),
        ("Max. Silver", {"BRONZE", "SILVER"}),
        ("Exactly Silver", {"SILVER"}),
        ("Min. Gold", {"GOLD"}),
    ],
)
def test_quality_minimum_maximum_and_exact_are_not_confused(setup, label, accepted):
    db, pool = setup
    report = parsed(f"Player Quality: {label}\nNumber of players: 1", db, ["CM"])
    assert report["ready"], report["issues"]
    challenge = Challenge.model_validate(report["challenge"])
    for level in ("BRONZE", "SILVER", "GOLD", None):
        card = pool[0].model_copy(update={"protected": False, "card_level": level})
        result = solve(challenge, [card])
        assert result.status == ("optimal" if level in accepted else "infeasible")


def test_eleven_players_must_meet_all_constraints_together(setup):
    db, pool = setup
    positions = ["GK", "RB", "CB", "CB", "LB", "CDM", "RM", "LM", "CAM", "ST", "ST"]
    text = (
        "Number of Players in the Squad: 11\nPlayer Quality: Min. Gold\n"
        "Nationalities: Exact 2\nLeagues: Max 2\nClubs: Exact 3\n"
        "Players from the same club: Max 4\nPlayers from the same nation: Min 6\n"
        "Rare players: Min 3\nSquad rating: Min 83\nTotal chemistry: Min 30"
    )
    report = parsed(text, db, positions)
    assert report["ready"], report["issues"]
    cards = [
        pool[0].model_copy(
            update={
                "key": f"complex:{i}",
                "base_id": 990000 + i,
                "card_id": 990000 + i,
                "protected": False,
                "rating": 83,
                "positions": [position],
                "card_level": "GOLD",
                "nation_id": 9001 if i < 6 else 9002,
                "league_id": 9011 if i < 6 else 9012,
                "club_id": 9020 + i % 3,
                "is_rare": i < 3,
                "owned": i < 9,
                "value": 100,
                "chemistry_kind": "standard",
            }
        )
        for i, position in enumerate(positions)
    ]
    challenge = Challenge.model_validate(report["challenge"]).model_copy(update={"budget": 200})
    result = solve(challenge, cards)
    assert result.status == "optimal"
    assert result.purchase_cost == 200
    assert result.sacrifice_value == 900
    assert len(result.assignments) == 11
    assert validate(challenge, cards, result.assignments) == []
    from collections import Counter

    assert sorted(Counter(c.nation_id for c in cards).values()) == [5, 6]
    assert sorted(Counter(c.club_id for c in cards).values()) == [3, 4, 4]
    assert sum(c.is_rare for c in cards) == 3
    # Un minimum supplémentaire incompatible doit faire échouer le même moteur.
    for impossible in [
        Condition(metric="rare", value=4),
        Condition(metric="nations", op="exact", value=3),
        Condition(metric="same_club", op="max", value=3),
        Condition(metric="team_rating", value=84),
    ]:
        harder = challenge.model_copy(update={"conditions": [*challenge.conditions, impossible]})
        assert solve(harder, cards).status == "infeasible"


def test_seven_visible_conditions_are_read_and_enforced_on_a_synthetic_pool(setup):
    from collections import Counter

    from sbc_vision.sbc_engine.solver import chemistry

    db, pool = setup
    positions = ["ST", "ST", "LM", "CM", "CM", "RM", "LB", "CB", "CB", "RB", "GK"]
    # Libellés vus à l'écran ; les joueurs et leurs identifiants restent entièrement fictifs.
    texts = [
        "Players from the same\nCountries/Regions: Min. 5",
        "Players from the same League: Max\n3",
        "Leagues in Squad: Min. 4",
        "Silver: Min. 5 Players",
        "Player Quality: Min. Bronze",
        "Total Chemistry: Min. 16",
        "Number of Players in the Squad: 11",
    ]
    report = {
        "positions": positions,
        "regions": [{"field": "requirements", "text": text, "confidence": 0.95} for text in texts],
    }
    parsed = challenge_from_ocr(report, db, market="pc", budget=2000)
    assert parsed["ready"], parsed["issues"]
    challenge = Challenge.model_validate(parsed["challenge"])
    assert [(r.metric, r.op, r.value, r.target) for r in challenge.conditions] == [
        ("same_nation", "min", 5, None),
        ("same_league", "max", 3, None),
        ("leagues", "min", 4, None),
        ("quality", "min", 5, "SILVER"),
        ("chemistry", "min", 16, None),
        ("players", "exact", 11, None),
    ]
    assert challenge.card_level == "BRONZE" and challenge.card_level_op == "min"
    cards = [
        pool[0].model_copy(
            update={
                "key": f"seven:{i}",
                "base_id": 980000 + i,
                "card_id": 980000 + i,
                "protected": False,
                "positions": [position],
                "owned": False,
                "value": 100,
                "card_level": "SILVER" if i < 5 else "BRONZE",
                "rating": 70 if i < 5 else 60,
                "nation_id": 9001 if i < 5 else (9002 if i < 8 else 9003),
                "league_id": 9010 + i // 3,
                "club_id": 9020 + i,
                "chemistry_kind": "standard",
            }
        )
        for i, position in enumerate(positions)
    ]
    result = solve(challenge, cards)
    assert result.status == "optimal" and result.purchase_cost == 1100
    assert validate(challenge, cards, result.assignments) == []
    assert sorted(Counter(c.nation_id for c in cards).values()) == [3, 3, 5]
    assert sorted(Counter(c.league_id for c in cards).values()) == [2, 3, 3, 3]
    assert sum(c.card_level == "SILVER" for c in cards) == 5
    assert chemistry(cards) == 25
    # Une carte or ne compte pas comme une carte argent dans le quota demandé.
    wrong_silver = [cards[0].model_copy(update={"card_level": "GOLD", "rating": 80}), *cards[1:]]
    wrong_nation = [cards[0].model_copy(update={"nation_id": 9002}), *cards[1:]]
    wrong_league = [
        *cards[:3],
        cards[3].model_copy(update={"league_id": cards[0].league_id}),
        *cards[4:],
    ]
    for invalid in (wrong_silver, wrong_nation, wrong_league):
        assert solve(challenge, invalid).status == "infeasible"


def test_wrapped_numeric_value_does_not_insert_an_extra_colon(setup):
    db, _ = setup
    report = parsed("Players from the same League: Max\n3", db, ["CM"])
    assert report["ready"], report["issues"]
    assert report["challenge"]["conditions"][0]["metric"] == "same_league"
