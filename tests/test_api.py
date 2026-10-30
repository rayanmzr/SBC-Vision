from fastapi.testclient import TestClient

from sbc_vision.api.main import app

client = TestClient(app)


def test_health_does_not_claim_model_readiness():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["model_loaded"] is False


def test_foundation_never_advertises_live_actions():
    response = client.get("/api/v1/capabilities")
    assert response.status_code == 200
    assert response.json()["live_actions_enabled"] is False
    assert response.json()["perception"] is False
    assert response.json()["solver"] is False


def test_contract_is_available_for_other_components():
    response = client.get("/api/v1/contracts/perception")
    assert response.status_code == 200
    assert "elements" in response.json()["required"]
