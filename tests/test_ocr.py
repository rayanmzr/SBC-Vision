"""Lectures locales sur images fictives et traitement des incertitudes."""

import json
import shutil
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from PIL import Image, ImageDraw, ImageFont
from pydantic import ValidationError

from sbc_vision.sbc_engine.models import OcrInput
from sbc_vision.sbc_engine.ocr import (
    analyze,
    challenge_from_ocr,
    edit_distance,
    evaluate,
    read_regions,
)
from sbc_vision.sbc_engine.players import (
    BASE_STATS,
    confirm_readings,
    list_items,
    open_database,
    save_cards,
    seed_demo,
)


def specification():
    return OcrInput.model_validate(
        {
            "capture_id": "synthetic-screen",
            "regions": [
                {
                    "element_id": "card-1",
                    "field": field,
                    "bbox": {"x": 10, "y": y, "width": 750, "height": 65},
                }
                for field, y in [("name", 10), ("rating", 80), ("position", 145)]
            ],
        }
    )


@pytest.fixture
def db(tmp_path):
    path = Path(__file__).resolve().parents[1] / "data/fixtures/club.synthetic.json"
    fixture = json.loads(path.read_text())
    with closing(open_database(tmp_path / "ocr.sqlite3")) as db:
        save_cards(db, fixture["catalogue"])
        yield db


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_real_ocr_requires_a_chosen_version_before_adding_an_owned_item(tmp_path, db):
    image = Image.new("RGB", (800, 230), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=36)
    for text, y in [("ALEX EXEMPLE", 25), ("83", 95), ("CM", 160)]:
        draw.text((30, y), text, fill="black", font=font)
    path = tmp_path / "synthetic.png"
    image.save(path)
    report = analyze(path, specification(), db)
    assert report["cards"][0]["reading"]["rating"] == 83
    assert report["cards"][0]["candidate_ids"] == [900001, 900002]
    assert report["cards"][0]["needs_confirmation"] is True
    assert list_items(db) == []
    for region in report["regions"]:
        for word in region["words"]:
            assert 0 <= word["x"] < image.width
            assert 0 <= word["y"] < image.height
    confirm_readings(
        db, report, {"card-1": {"instance_id": "ocr-copy", "card_id": 900001}}, confirmed=True
    )
    assert list_items(db)[0]["card_id"] == 900001
    assert list_items(db)[0]["source_observation"] == "synthetic-screen:card-1"


@pytest.mark.parametrize("rating, confidence", [("8B", 0.99), ("83", 0.2), ("", 0)])
def test_unreadable_rating_never_becomes_a_confirmed_card(monkeypatch, db, rating, confidence):
    monkeypatch.setattr(
        "sbc_vision.sbc_engine.ocr.read_regions",
        lambda *a, **kw: [
            {"element_id": "card-1", "field": "name", "text": "Alex Exemple", "confidence": 0.99},
            {"element_id": "card-1", "field": "rating", "text": rating, "confidence": confidence},
        ],
    )
    report = analyze("unused.png", specification(), db)
    assert report["cards"][0]["reading"] is None
    assert report["cards"][0]["issues"]
    assert list_items(db) == []


@pytest.mark.parametrize(
    "text, confidence, valid",
    [
        ("PAC SHO PAS DRI DEF PHY\n70 71 72 73 74 75", 0.99, True),
        ("DIV HAN KIC REF SPD POS\n70 71 72 73 74 75", 0.99, True),
        ("PAC SHO PAS DRI DEF PHY\n70 71 72 73 74 75", 0.3, False),
        ("PAC SHO PAS DRI DEF PHY\n70 71 72 73 74", 0.99, False),
        ("PAC SHO PAS DRI DEF PHY\n100 71 72 73 74 75", 0.99, False),
        ("PAC SHO PAS DRI DEF PHY\n7O 71 72 73 74 75", 0.99, False),
        ("PAC PAC PAS DRI DEF PHY\n70 71 72 73 74 75", 0.99, False),
    ],
)
def test_stat_reading_selects_a_version_only_when_all_six_values_are_readable(
    db, text, confidence, valid
):
    labels = list(BASE_STATS)[6:] if text.startswith("DIV") else list(BASE_STATS)[:6]
    # Même nom et même note, mais une statistique différente selon la version.
    cards = [json.loads(r["data"]) for r in db.execute("SELECT data FROM cards WHERE rating=83")]
    for card in cards:
        card["stats"] = {BASE_STATS[k]: 70 + i for i, k in enumerate(labels)}
        if card["id"] == 900002:
            card["stats"][BASE_STATS[labels[0]]] = 80
    save_cards(db, cards)
    regions = [
        {"element_id": "card-1", "field": f, "text": t, "confidence": c}
        for f, t, c in [
            ("name", "Alex Exemple", 0.99),
            ("rating", "83", 0.99),
            ("stats", text, confidence),
        ]
    ]
    report = analyze("unused.png", specification(), db, regions=regions)
    card = report["cards"][0]
    assert card["candidate_ids"] == ([900001] if valid else [])
    assert bool(card["issues"]) is not valid
    assert card["needs_confirmation"] is True
    assert list_items(db) == []
    if not valid:
        with pytest.raises(ValueError, match="corriger"):
            confirm_readings(
                db, report, {"card-1": {"instance_id": "copy", "card_id": 900001}}, confirmed=True
            )


def test_out_of_bounds_region_is_rejected_before_ocr(tmp_path):
    path = tmp_path / "tiny.png"
    Image.new("RGB", (10, 10), "white").save(path)
    with pytest.raises(ValueError, match="hors de l'image"):
        read_regions(path, specification())


def test_isolated_retry_restores_original_coordinates_without_faking_confidence(
    tmp_path, monkeypatch
):
    path = tmp_path / "blank.png"
    Image.new("RGB", (800, 230), "white").save(path)
    from sbc_vision.sbc_engine.ocr import ocr_words

    def data(image, **kwargs):
        return {
            "text": ["83"],
            "conf": [55],
            "left": [6],
            "top": [9],
            "width": [30],
            "height": [45],
            "block_num": [1],
            "par_num": [1],
            "line_num": [1],
        }

    monkeypatch.setattr("sbc_vision.sbc_engine.ocr.pytesseract.image_to_data", data)
    result = ocr_words(Image.open(path), lang="eng", scale=3, x=10, y=80, psm=7)
    assert result[0]["x"] == 12
    assert result[0]["y"] == 83
    assert result[0]["confidence"] == 0.55


def test_item_score_accepts_the_visible_label_without_guessing_the_number(db, monkeypatch):
    regions = [
        {"element_id": "card-1", "field": "name", "text": "Alex Exemple", "confidence": 0.99},
        {"element_id": "card-1", "field": "rating", "text": "83", "confidence": 0.99},
        {
            "element_id": "card-1",
            "field": "item_score",
            "text": "Score: 14,000",
            "confidence": 0.95,
        },
    ]
    monkeypatch.setattr("sbc_vision.sbc_engine.ocr.read_regions", lambda *a, **kw: regions)
    report = analyze("unused.png", specification(), db)
    assert report["cards"][0]["reading"]["item_score"] == 14000
    regions[-1]["text"] = "Score: 14,OOO"
    invalid = analyze("unused.png", specification(), db)
    assert invalid["cards"][0]["reading"]["item_score"] is None
    assert invalid["cards"][0]["issues"]


def test_uncertain_requirement_is_read_as_a_block_and_keeps_its_confidence(tmp_path, monkeypatch):
    path = tmp_path / "requirements.png"
    Image.new("RGB", (400, 100), "white").save(path)
    words = [
        {
            "text": "Silver: Min. 5 Players",
            "confidence": 0.69,
            "x": 20,
            "y": 20,
            "width": 200,
            "height": 30,
            "line": (1, 1, 1),
        },
    ]
    reader = Mock(side_effect=[words, [{**words[0], "confidence": 0.74}]])
    monkeypatch.setattr("sbc_vision.sbc_engine.ocr.ocr_words", reader)
    spec = OcrInput(
        capture_id="retry",
        regions=[
            {
                "element_id": "condition",
                "field": "requirements",
                "bbox": {"x": 10, "y": 10, "width": 300, "height": 60},
            }
        ],
    )
    result = read_regions(path, spec)
    assert reader.call_count == 2
    assert reader.call_args.kwargs["psm"] == 6
    assert result[0]["method"] == "region"
    assert result[0]["confidence"] == 0.74
    with closing(open_database(tmp_path / "unused.sqlite3")) as db:
        assert not challenge_from_ocr(
            {"regions": result, "positions": ["CM"]}, db, market="pc", budget=2000
        )["ready"]


def test_duplicate_fields_cannot_silently_overwrite_one_another():
    data = specification().model_dump()
    data["regions"].append(data["regions"][0])
    with pytest.raises(ValidationError, match="Une seule région"):
        OcrInput.model_validate(data)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_real_capture_conditions_become_a_dynamic_request(tmp_path, db):
    image = Image.new("RGB", (1000, 300), "white")
    draw, font = ImageDraw.Draw(image), ImageFont.load_default(size=36)
    for text, y in [
        ("Number of players: 3", 20),
        ("Player rating: Min 82", 90),
        ("Rare players: Min 1", 160),
    ]:
        draw.text((30, y), text, fill="black", font=font)
    path = tmp_path / "conditions.png"
    image.save(path)
    spec = OcrInput(
        capture_id="new-sbc",
        positions=["CAM", "CM", "ST"],
        regions=[
            {
                "element_id": "requirements",
                "field": "requirements",
                "bbox": {"x": 0, "y": 0, "width": 1000, "height": 300},
            }
        ],
    )
    report = analyze(path, spec, db)
    parsed = challenge_from_ocr(report, db, market="pc", budget=2000)
    assert parsed["ready"], parsed["issues"]
    assert parsed["challenge"]["positions"] == ["CAM", "CM", "ST"]
    assert [c["metric"] for c in parsed["challenge"]["conditions"]] == ["players", "rating", "rare"]

    # Le même rapport OCR est ensuite consommé par la commande du solveur.
    from sbc_vision.sbc_engine.__main__ import main

    root = Path(__file__).resolve().parents[1]
    club = json.loads((root / "data/fixtures/club.synthetic.json").read_text())
    demo = json.loads((root / "data/fixtures/solver.synthetic.json").read_text())
    seed_demo(db, club, demo["extra_cards"])
    cards = [json.loads(row["data"]) for row in db.execute("SELECT data FROM cards")]
    for card in cards:
        card["observed_at"] = datetime.now(UTC).isoformat()
    save_cards(db, cards)
    db_path = db.execute("PRAGMA database_list").fetchone()[2]
    regions, reading, output = [
        tmp_path / name for name in ["regions.json", "reading.json", "plan.json"]
    ]
    regions.write_text(spec.model_dump_json())
    assert (
        main(
            [
                "ocr",
                str(path),
                str(regions),
                "--db",
                db_path,
                "--market",
                "pc",
                "--budget",
                "2000",
                "--output",
                str(reading),
            ]
        )
        == 0
    )
    assert main(["solve", "--reading", str(reading), "--db", db_path, "--output", str(output)]) == 0
    assert json.loads(output.read_text())["solution"]["total_cost"] == 2100


def text_report(text, *, capture="screen-1", field="name", confidence=0.99):
    return {
        "capture_id": capture,
        "regions": [
            {"element_id": "card-1", "field": field, "text": text, "confidence": confidence}
        ],
    }


@pytest.mark.parametrize(
    "expected, actual, edits",
    [("kitten", "sitting", 3), ("ABC", "AB", 1), ("AB", "AXB", 1), ("É", "E", 1), ("", "AB", 2)],
)
def test_character_distance_counts_insertions_deletions_and_substitutions(expected, actual, edits):
    assert edit_distance(expected, actual) == edits


def test_batch_cer_is_weighted_by_characters_and_separates_fields():
    expected = [text_report("ABCDEFGHIJ"), text_report("8", capture="screen-2", field="rating")]
    observed = [text_report("ABCDEFGHIK"), text_report("9", capture="screen-2", field="rating")]
    metrics = evaluate(observed, expected)
    assert metrics["summary"]["fields"] == 2
    assert metrics["summary"]["characters"] == 11
    assert metrics["summary"]["cer"] == pytest.approx(2 / 11)
    assert metrics["by_field"]["name"]["cer"] == pytest.approx(0.1)
    assert metrics["by_field"]["rating"]["cer"] == 1
    assert metrics["summary"]["exact_accuracy"] == 0


def test_missing_or_uncertain_fields_are_never_reported_as_accepted_correct_fields():
    expected = [text_report("ABC"), text_report("83", capture="screen-2", field="rating")]
    observed = [text_report("ABC", confidence=0.2), text_report("extra", capture="another-screen")]
    metrics = evaluate(observed, expected)
    assert metrics["missing_regions"] == 1
    assert metrics["unexpected_regions"] == 1
    assert metrics["summary"]["cer"] == pytest.approx(2 / 5)
    assert metrics["summary"]["exact_accuracy"] == 0
    assert metrics["summary"]["unknown_rate"] == 1


def test_unicode_and_whitespace_are_normalized_without_hiding_real_errors():
    metrics = evaluate(text_report("E\u0301li\n  Test"), text_report("Éli Test"))
    assert metrics["summary"]["cer"] == 0
    assert metrics["summary"]["exact_accuracy"] == 1
    assert evaluate(text_report("a"), text_report("A"))["summary"]["cer"] == 1
    assert evaluate(text_report("ABC"), text_report("A"))["summary"]["cer"] == 2


@pytest.mark.parametrize("problem", ["duplicate", "empty", "confidence", "blank", "threshold"])
def test_invalid_evaluation_input_does_not_produce_plausible_metrics(problem):
    observed, expected, minimum = text_report("Alex"), text_report("Alex"), 0.75
    if problem == "duplicate":
        expected["regions"].append(expected["regions"][0])
    elif problem == "empty":
        expected = []
    elif problem == "confidence":
        observed["regions"][0]["confidence"] = -0.1
    elif problem == "blank":
        expected["regions"][0]["text"] = " "
    else:
        minimum = 1.1
    with pytest.raises(ValueError):
        evaluate(observed, expected, minimum=minimum)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_evaluation_cli_creates_a_reproducible_synthetic_demo(tmp_path):
    from sbc_vision.sbc_engine.__main__ import main

    output, replay = tmp_path / "metrics.json", tmp_path / "replay.json"
    assert main(["evaluate", "--demo", "--output", str(output)]) == 0
    metrics = json.loads(output.read_text())
    assert metrics["data_kind"] == "synthetic"
    assert metrics["summary"]["fields"] == 6
    assert metrics["summary"]["characters"] > 0
    assert metrics["summary"]["cer"] >= 0
    assert (tmp_path / "ocr_demo.png").is_file()
    assert (
        main(
            [
                "evaluate",
                "--reading",
                str(tmp_path / "ocr_demo.report.json"),
                "--expected",
                str(tmp_path / "ocr_demo.expected.json"),
                "--output",
                str(replay),
            ]
        )
        == 0
    )
    assert json.loads(replay.read_text())["summary"] == metrics["summary"]
    assert main(["evaluate", "--reading", str(tmp_path / "ocr_demo.report.json")]) == 1


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_complete_demo_reads_once_and_repeated_captures_keep_the_same_inventory(
    tmp_path, monkeypatch
):
    from sbc_vision.sbc_engine.__main__ import main

    reader = Mock(wraps=read_regions)
    monkeypatch.setattr("sbc_vision.sbc_engine.ocr.read_regions", reader)
    args = ["demo", "--directory", str(tmp_path)]
    assert main(args) == 0
    assert reader.call_count == 1
    report = json.loads((tmp_path / "reading.json").read_text())
    solution = json.loads((tmp_path / "solution.json").read_text())
    assert report["ready"]
    assert report["challenge"]["positions"] == ["CAM", "CM", "ST"]
    assert {r["metric"] for r in report["challenge"]["conditions"]} == {
        "players",
        "rating",
        "rare",
        "nation",
        "league",
    }
    assert solution["solution"]["total_cost"] == 2100
    assert solution["challenge"]["max_card_value"] == 1000
    assert solution["shopping_list"]["estimated_cost"] == 1300
    assert main(args) == 0
    assert reader.call_count == 2
    with closing(open_database(tmp_path / "club.sqlite3")) as db:
        items = list_items(db)
    assert len(items) == 3
    assert next(i for i in items if i["instance_id"] == "demo-001")["protected"] is True
    assert all(i["source_observation"].startswith("synthetic-ocr-demo:") for i in items)


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
@pytest.mark.parametrize("problem, status", [("condition", 2), ("card", 1)])
def test_complete_demo_stops_on_bad_ocr_and_removes_the_previous_proposal(
    tmp_path, monkeypatch, problem, status
):
    from sbc_vision.sbc_engine.__main__ import main

    def damaged(*args, **kwargs):
        regions = read_regions(*args, **kwargs)
        for region in regions:
            if problem == "condition" and region["element_id"] == "condition-0":
                region["confidence"] = 0.1
            if problem == "card" and (region["element_id"], region["field"]) == (
                "card-1",
                "rating",
            ):
                region["text"] = "8B"
        return regions

    monkeypatch.setattr("sbc_vision.sbc_engine.ocr.read_regions", damaged)
    (tmp_path / "solution.json").write_text('{"old_proposal": true}')
    assert main(["demo", "--directory", str(tmp_path)]) == status
    assert not (tmp_path / "solution.json").exists()
    assert (tmp_path / "reading.json").exists()
    with closing(open_database(tmp_path / "club.sqlite3")) as db:
        assert list_items(db) == []


def test_complete_demo_refuses_a_real_catalogue_before_overwriting_outputs(tmp_path):
    from sbc_vision.sbc_engine.__main__ import main

    fixture = json.loads(
        (Path(__file__).resolve().parents[1] / "data/fixtures/club.synthetic.json").read_text()
    )
    card = {**fixture["catalogue"][0], "source_url": "https://www.futbin.com/27/player/1"}
    with closing(open_database(tmp_path / "club.sqlite3")) as db:
        save_cards(db, [card])
    old = '{"private_proposal": true}'
    (tmp_path / "solution.json").write_text(old)
    assert main(["demo", "--directory", str(tmp_path)]) == 1
    assert (tmp_path / "solution.json").read_text() == old
    assert not (tmp_path / "ocr_demo.png").exists()


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract doit être installé")
def test_complex_demo_reads_ten_conditions_and_rejects_the_cheaper_invalid_player(tmp_path):
    from sbc_vision.sbc_engine.__main__ import main
    from sbc_vision.sbc_engine.models import Assignment, Challenge
    from sbc_vision.sbc_engine.players import load_pool
    from sbc_vision.sbc_engine.solver import validate

    assert main(["demo", "--complex", "--directory", str(tmp_path)]) == 0
    reading = json.loads((tmp_path / "reading.json").read_text())
    report = json.loads((tmp_path / "solution.json").read_text())
    challenge = Challenge.model_validate(report["challenge"])
    assert len(challenge.conditions) == 9
    assert challenge.card_level == "GOLD" and challenge.card_level_op == "min"
    assert len(challenge.positions) == 11
    assert reading["ready"] is True
    assert report["solution"]["total_cost"] == 1100
    assert report["solution"]["purchase_cost"] == 200
    assert report["baseline"]["status"] == "unknown"
    assert all(a["candidate_key"] != "market:910099" for a in report["solution"]["assignments"])
    with closing(open_database(tmp_path / "club.sqlite3")) as db:
        pool = load_pool(
            db, challenge.market, now=datetime.fromisoformat(report["price_reference_at"])
        )
        assert len(list_items(db)) == 9
    team = [Assignment.model_validate(a) for a in report["solution"]["assignments"]]
    assert validate(challenge, pool, team) == []
