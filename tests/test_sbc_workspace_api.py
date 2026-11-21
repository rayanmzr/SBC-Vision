import json
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from sbc_vision.api.main import app
from sbc_vision.api.sbc_workspace import SbcConfig, SbcWorkspace, get_workspace, solve_slot
from sbc_vision.sbc_engine.players import open_database, seed_demo, set_protected


def dom_scan(service):
    # Le mode local est testé avec des cartes fictives et un domaine réservé aux exemples.
    service.config = replace(service.config, mode="local", challenge_path=None)
    with closing(open_database(service.config.database)) as db:
        db.execute("DELETE FROM club_items")
        cards = [json.loads(r[0]) for r in db.execute("SELECT data FROM cards")]
        for c in cards:
            c["source_url"] = f"https://example.test/synthetic/{c['id']}"
            db.execute("UPDATE cards SET data=? WHERE id=?", (json.dumps(c), c["id"]))
        db.commit()
    card = next(c for c in cards if c["id"] == 900004)

    def row(element, loan=False):
        return {
            "reading": {
                "capture_id": "synthetic-dom",
                "element_id": element,
                "name": card["name"],
                "rating": card["rating"],
                "position": card["positions"][0],
            },
            "visible": True,
            "loan": loan,
        }

    return {
        "capture_id": "synthetic-dom",
        "complete": True,
        "expected_revision": service.snapshot().revision,
        "pages": [
            {"cards": [row("p1-r1"), row("p1-r2", True)], "has_previous": False, "has_next": True},
            {"cards": [row("p2-r1")], "has_previous": True, "has_next": False},
        ],
    }


def test_dom_scan_saves_observations_then_replaces_only_a_confirmed_local_count(client, service):
    body = dom_scan(service)
    response = client.post("/api/v1/sbc/club-scan", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["source"] == "dom"
    assert response.json()["observed"] == 3
    assert response.json()["identified"] == 2
    assert response.json()["loans"] == 1
    assert response.json()["ocr_readable"] == 0
    assert service.snapshot().items == []
    saved = client.get("/api/v1/sbc/club-scan")
    assert saved.status_code == 200
    assert saved.json()["report"]["observed"] == 3
    assert (
        saved.json()["observation"]["pages"][0]["cards"][0]["reading"]["capture_id"]
        == body["capture_id"]
    )
    body["confirmed"] = True
    body["expected_revision"] = response.json()["expected_revision"]
    assert client.post("/api/v1/sbc/club-scan", json=body).status_code == 200
    assert len(service.snapshot().items) == 2
    assert all(c.protected for c in service.snapshot().items)
    body["expected_revision"] = service.snapshot().revision
    assert client.post("/api/v1/sbc/club-scan", json=body).status_code == 200
    assert len(service.snapshot().items) == 2


@pytest.mark.parametrize(
    "fault", ["partial", "repeated", "capture", "stale", "manual", "confidence"]
)
def test_invalid_dom_scan_never_modifies_the_inventory(client, service, fault):
    body = dom_scan(service)
    body["confirmed"] = True
    if fault == "partial":
        body["complete"] = False
    if fault == "repeated":
        body["pages"][1]["cards"] = body["pages"][0]["cards"]
    if fault == "capture":
        body["pages"][0]["cards"][0]["reading"]["capture_id"] = "other"
    if fault == "stale":
        body["expected_revision"] = "0" * 64
    if fault == "confidence":
        body["pages"][0]["cards"][0]["reading"]["confidence"] = 1
    if fault == "manual":
        from sbc_vision.sbc_engine.models import ClubItem
        from sbc_vision.sbc_engine.players import save_item

        with closing(open_database(service.config.database)) as db:
            save_item(
                db,
                ClubItem(
                    instance_id="manual",
                    card_id=900004,
                    source_observation="synthetic",
                    protected=True,
                ),
                confirmed=True,
            )
        body["expected_revision"] = service.snapshot().revision
    before = service.snapshot().items
    response = client.post("/api/v1/sbc/club-scan", json=body)
    assert response.status_code in {409, 422}, response.text
    assert service.snapshot().items == before


def test_ocr_dom_agreement_counts_visible_rows_once_and_keeps_the_sources_distinct(client, service):
    body = dom_scan(service)
    page = body["pages"][0]
    page["cards"][1]["visible"] = False
    reading = {**page["cards"][0]["reading"], "capture_id": "synthetic-ocr", "confidence": 0.99}
    page["ocr"] = {
        "capture_id": "synthetic-ocr",
        "image": {"width": 100, "height": 100},
        "engine_version": "synthetic",
        "language": "eng",
        "minimum_confidence": 0.75,
        "regions": [],
        "positions": [],
        "challenge_ready": False,
        "challenge": None,
        "challenge_issues": [],
        "cards": [
            {
                "element_id": f"ocr-{i}",
                "reading": {**reading, "element_id": f"ocr-{i}"},
                "candidate_ids": [],
                "issues": [],
                "needs_confirmation": True,
            }
            for i in range(3)
        ],
    }
    response = client.post("/api/v1/sbc/club-scan", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["ocr_readable"] == 3
    assert response.json()["ocr_matched"] == 1
    assert "confidence" not in response.json()["cards"][0]["reading"]


def test_current_sbc_dom_conditions_are_dynamic_and_unknown_rules_block_the_calculation(client):
    body = {
        "source": "dom",
        "requirements": "Rare players: Min. 1\nNumber of Players in the Squad: 3",
        "positions": ["ST", "CM", "CAM"],
        "market": "pc",
        "budget": 5000,
    }
    response = client.post("/api/v1/sbc/read", json=body)
    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["source"] == "dom"
    assert response.json()["challenge"]["positions"] == body["positions"]
    body["requirements"] += "\nNew unsupported rule: Min. 2"
    response = client.post("/api/v1/sbc/read", json=body)
    assert response.json()["ready"] is False
    assert response.json()["challenge"] is None


def test_single_card_sbc_does_not_require_eleven_players_or_a_goalkeeper(client):
    reading = client.post(
        "/api/v1/sbc/read",
        json={
            "source": "dom",
            "requirements": "Player Quality: Min. Bronze\nNumber of Players in the Squad: 1",
            "positions": ["GK"],
            "budget": 5000,
        },
    ).json()
    assert reading["ready"] and reading["challenge"]["position_mode"] == "any"
    workspace = client.get("/api/v1/sbc/workspace").json()
    result = client.post(
        "/api/v1/sbc/solve",
        json={"expected_revision": workspace["revision"], "challenge": reading["challenge"]},
    )
    assert result.status_code == 200, result.text
    report = result.json()["report"]
    assert report["solution"]["status"] == "optimal"
    assert len(report["solution"]["assignments"]) == 1
    assert report["verification"]["valid"]


@pytest.mark.parametrize("fault", [None, "stats", "duplicate", "unconfirmed", "catalogue"])
def test_placement_uses_only_a_unique_confirmed_club_fingerprint(
    client, service, monkeypatch, fault
):
    from sbc_vision.sbc_engine.players import BASE_STATS

    body = dom_scan(service)
    monkeypatch.setattr(
        service, "reference_time", lambda _: datetime.fromisoformat("2026-10-30T12:00:00+00:00")
    )
    body["pages"] = [body["pages"][0]]
    body["pages"][0]["has_next"] = False
    row = body["pages"][0]["cards"][0]
    row["reading"].update(
        stats={k: 70 for k in list(BASE_STATS)[:6]}, nation_id=9003, league_id=9004, club_id=9006
    )
    with closing(open_database(service.config.database)) as db:
        card = json.loads(db.execute("SELECT data FROM cards WHERE id=900004").fetchone()[0])
        row["reading"].update({k: card[k] for k in ("nation_id", "league_id", "club_id")})
        card["stats"] = {BASE_STATS[k]: n for k, n in row["reading"]["stats"].items()}
        db.execute("UPDATE cards SET data=? WHERE id=?", (json.dumps(card), card["id"]))
        db.commit()
    if fault == "stats":
        row["reading"].pop("stats")
    if fault == "duplicate":
        body["pages"][0]["cards"][1] = {
            **row,
            "reading": {**row["reading"], "element_id": "copy-2"},
        }
    body.update(confirmed=True, expected_revision=service.snapshot().revision)
    response = client.post("/api/v1/sbc/club-scan", json=body)
    assert response.status_code == 200, response.text
    with closing(open_database(service.config.database)) as db:
        db.execute("UPDATE club_items SET protected=0")
        if fault == "catalogue":
            card["stats"]["BasePace"] = 71
            db.execute("UPDATE cards SET data=? WHERE id=?", (json.dumps(card), card["id"]))
        db.commit()
    if fault == "unconfirmed":
        body.update(confirmed=False, expected_revision=service.snapshot().revision)
        assert client.post("/api/v1/sbc/club-scan", json=body).status_code == 200
    challenge = {"positions": ["ST"], "conditions": [], "budget": 0, "market": "pc"}
    solved = client.post(
        "/api/v1/sbc/solve",
        json={"expected_revision": service.snapshot().revision, "challenge": challenge},
    )
    assert solved.status_code == 200, solved.text
    data = solved.json()
    assert data["report"]["verification"]["valid"] is True
    if fault:
        assert data["placement"]["cards"] == []
        assert data["placement"]["issues"]
    else:
        assert data["placement"]["issues"] == []
        assert data["placement"]["cards"][0]["reading"]["stats"] == row["reading"]["stats"]
        assert data["placement"]["cards"][0]["candidate_key"].startswith("club:")


def test_a_new_scan_invalidates_an_older_placement_revision(client, service):
    body = dom_scan(service)
    previous = body["expected_revision"]
    assert client.post("/api/v1/sbc/club-scan", json=body).status_code == 200
    assert service.snapshot().revision != previous
    response = client.post(
        "/api/v1/sbc/solve",
        json={
            "expected_revision": previous,
            "challenge": {"positions": ["ST"], "budget": 0, "market": "pc"},
        },
    )
    assert response.status_code == 409


FIXTURES = Path(__file__).resolve().parents[1] / "data/fixtures"


@pytest.fixture
def config(tmp_path):
    club = json.loads((FIXTURES / "club.synthetic.json").read_text())
    solver = json.loads((FIXTURES / "solver.synthetic.json").read_text())
    database = tmp_path / "club.sqlite3"
    with closing(open_database(database)) as db:
        seed_demo(db, club, solver["extra_cards"])
    challenge = tmp_path / "challenge.json"
    challenge.write_text(
        json.dumps(
            {
                "data_kind": "synthetic",
                "price_reference_at": solver["price_reference_at"],
                "challenge": {**solver["challenge"], "max_card_value": 1000},
            }
        )
    )
    return SbcConfig(database, challenge, "demo")


@pytest.fixture
def service(config):
    return SbcWorkspace(config)


@pytest.fixture
def client(service):
    app.dependency_overrides[get_workspace] = lambda: service
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def snapshot(client):
    response = client.get("/api/v1/sbc/workspace")
    assert response.status_code == 200, response.text
    return response.json()


def inventory_request(client):
    return {
        "expected_revision": snapshot(client)["revision"],
        "confirmed": True,
        "report": {
            "capture_id": "synthetic-import",
            "image": {"width": 800, "height": 340},
            "engine_version": "synthetic-test",
            "language": "eng",
            "minimum_confidence": 0.75,
            "regions": [],
            "positions": [],
            "challenge_ready": False,
            "challenge": None,
            "challenge_issues": ["Conditions absentes."],
            "cards": [
                {
                    "element_id": "card-1",
                    "reading": {
                        "capture_id": "synthetic-import",
                        "element_id": "card-1",
                        "name": "Alex Exemple",
                        "rating": 83,
                        "confidence": 0.95,
                    },
                    "candidate_ids": [900001, 900002],
                    "issues": [],
                    "needs_confirmation": True,
                }
            ],
        },
        "choices": {"card-1": {"instance_id": "tracked-copy", "card_id": 900001}},
    }


def test_confirmed_ocr_reaches_inventory_without_duplicate_copies(client):
    body = inventory_request(client)
    first = client.post("/api/v1/sbc/inventory", json=body)
    assert first.status_code == 200, first.text
    assert len(first.json()["items"]) == 4
    item = next(c for c in first.json()["items"] if c["key"] == "club:tracked-copy")
    assert item["protected"] is True
    assert client.post("/api/v1/sbc/inventory", json=body).status_code == 409
    body["expected_revision"] = first.json()["revision"]
    assert len(client.post("/api/v1/sbc/inventory", json=body).json()["items"]) == 4


@pytest.mark.parametrize("problem", ["unconfirmed", "uncertain", "version"])
def test_inventory_import_never_accepts_uncertain_or_unconfirmed_cards(client, problem):
    body = inventory_request(client)
    if problem == "unconfirmed":
        body["confirmed"] = False
    elif problem == "uncertain":
        body["report"]["cards"][0]["issues"] = ["Note à relire."]
    else:
        body["choices"]["card-1"]["card_id"] = 900003
    assert client.post("/api/v1/sbc/inventory", json=body).status_code == 422
    assert len(snapshot(client)["items"]) == 3


def test_solver_uses_the_current_request_conditions_instead_of_a_fixed_sbc(client):
    workspace = snapshot(client)
    challenge = {**workspace["challenge"], "positions": ["GK"], "conditions": []}
    response = client.post(
        "/api/v1/sbc/solve",
        json={"expected_revision": workspace["revision"], "challenge": challenge},
    )
    assert response.status_code == 200, response.text
    assert response.json()["report"]["challenge"]["positions"] == ["GK"]
    assert response.json()["report"]["solution"]["status"] == "infeasible"


def protect(client, revision, protected=True):
    return client.put(
        "/api/v1/sbc/protections",
        json={"instance_id": "demo-002", "protected": protected, "expected_revision": revision},
    )


def test_inventory_distinguishes_instances_and_demo_mode(client):
    data = snapshot(client)
    assert data["mode"] == "demo"
    assert len(data["items"]) == 3
    assert len({item["key"] for item in data["items"]}) == 3
    assert data["items"][0]["protected"] is True
    assert data["challenge"]["budget"] == 2000
    assert snapshot(client)["revision"] == data["revision"]


def test_protection_is_persisted_without_duplication(client, config):
    before = snapshot(client)
    response = protect(client, before["revision"])
    assert response.status_code == 200
    assert response.json()["revision"] != before["revision"]
    with closing(open_database(config.database)) as db:
        assert (
            db.execute("SELECT protected FROM club_items WHERE instance_id='demo-002'").fetchone()[
                0
            ]
            == 1
        )
        assert db.execute("SELECT COUNT(*) FROM club_items").fetchone()[0] == 3
    assert (
        next(card for card in snapshot(client)["items"] if card["key"] == "club:demo-002")[
            "protected"
        ]
        is True
    )


def test_stale_protection_request_cannot_overwrite_a_newer_preference(client):
    old = snapshot(client)["revision"]
    assert protect(client, old).status_code == 200
    stale = protect(client, old, False)
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "workspace_changed"


def test_real_cp_sat_runs_from_json_and_protection_changes_the_result(client):
    before = snapshot(client)
    solved = client.post("/api/v1/sbc/solve", json={"expected_revision": before["revision"]})
    assert solved.status_code == 200, solved.text
    report = solved.json()["report"]
    assert report["solution"]["status"] == "optimal"
    assert report["solution"]["purchase_cost"] == 1300
    assert report["solution"]["total_cost"] == 2100
    assert report["verification"]["valid"] is True
    assert "club:demo-001" not in {a["candidate_key"] for a in report["solution"]["assignments"]}
    after = protect(client, before["revision"]).json()
    assert (
        client.post("/api/v1/sbc/solve", json={"expected_revision": before["revision"]}).status_code
        == 409
    )
    impossible = client.post("/api/v1/sbc/solve", json={"expected_revision": after["revision"]})
    assert impossible.status_code == 200
    assert impossible.json()["report"]["solution"]["status"] == "infeasible"
    increased = client.post(
        "/api/v1/sbc/solve", json={"expected_revision": after["revision"], "budget": 3000}
    )
    assert increased.status_code == 200
    assert increased.json()["report"]["solution"]["purchase_cost"] == 2100


def test_external_change_during_solving_discards_the_proposal(client, service, config, monkeypatch):
    original = service.solver.solve

    def concurrent_change(*args, **kwargs):
        result = original(*args, **kwargs)
        with closing(open_database(config.database)) as db:
            set_protected(db, "demo-002", True)
        return result

    monkeypatch.setattr(service.solver, "solve", concurrent_change)
    response = client.post(
        "/api/v1/sbc/solve", json={"expected_revision": snapshot(client)["revision"]}
    )
    assert response.status_code == 409
    assert "report" not in response.json()


def test_uncertain_conditions_block_solving(client, config):
    data = json.loads(config.challenge_path.read_text())
    data["ready"] = False
    config.challenge_path.write_text(json.dumps(data))
    current = snapshot(client)
    assert current["challenge"] is None
    assert current["challenge_issues"]
    response = client.post("/api/v1/sbc/solve", json={"expected_revision": current["revision"]})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "challenge_uncertain"


def test_solver_capacity_is_bounded(client):
    revision = snapshot(client)["revision"]
    assert solve_slot.acquire(blocking=False)
    try:
        assert (
            client.post("/api/v1/sbc/solve", json={"expected_revision": revision}).status_code
            == 429
        )
    finally:
        solve_slot.release()


@pytest.mark.parametrize(
    "change", [{"seconds": 31}, {"budget": -1}, {"budget": True}, {"extra": "field"}]
)
def test_solver_inputs_are_bounded(client, change):
    response = client.post(
        "/api/v1/sbc/solve", json={"expected_revision": snapshot(client)["revision"], **change}
    )
    assert response.status_code == 422


def test_solver_does_not_accept_an_image(client):
    response = client.post(
        "/api/v1/sbc/solve", content=b"image bytes", headers={"Content-Type": "image/png"}
    )
    assert response.status_code == 422


def test_absent_engine_is_explicit_and_no_database_is_created(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(HTTPException) as failure:
        SbcWorkspace(SbcConfig(missing, None, "local"))
    assert failure.value.status_code == 503
    assert not missing.exists()


def test_modes_cannot_misrepresent_synthetic_data(client, service, config):
    service.config = replace(config, mode="local")
    response = client.get("/api/v1/sbc/workspace")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "data_mode_mismatch"


def test_expired_prices_change_revision_without_database_writes(client, service, monkeypatch):
    before = snapshot(client)
    later = datetime.fromisoformat(before["price_reference_at"]) + timedelta(hours=25)
    monkeypatch.setattr(service, "reference_time", lambda document: later)
    after = snapshot(client)
    assert after["revision"] != before["revision"]
    assert all(card["value"] is None for card in after["items"])
    assert protect(client, before["revision"]).status_code == 409


def test_invalid_demo_configuration_cannot_change_protections(client, config):
    revision = snapshot(client)["revision"]
    data = json.loads(config.challenge_path.read_text())
    data["data_kind"] = "local"
    config.challenge_path.write_text(json.dumps(data))
    assert protect(client, revision).status_code == 503
    with closing(open_database(config.database)) as db:
        assert (
            db.execute("SELECT protected FROM club_items WHERE instance_id='demo-002'").fetchone()[
                0
            ]
            == 0
        )
