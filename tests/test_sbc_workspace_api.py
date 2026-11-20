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
    "change", [{"seconds": 10}, {"budget": -1}, {"budget": True}, {"extra": "field"}]
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
