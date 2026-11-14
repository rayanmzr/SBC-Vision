"""Protection de l'API partagée, limites de charge et absence de secrets en réponse."""

import asyncio
from dataclasses import replace

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from sbc_vision.api.access import AccessConfig, AccessMiddleware, load_access_config
from sbc_vision.api.main import app

KEY = "local_test_key_" + "x" * 32


@pytest.fixture(autouse=True)
def clean_configuration(monkeypatch):
    for name in ("SBC_API_KEY", "SBC_API_KEY_FILE", "SBC_ACCESS_MODE", "SBC_MAX_INFLIGHT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SBC_ENV", "development")


def test_local_default_is_compatible_and_shared_requires_key(monkeypatch):
    assert load_access_config().key is None
    monkeypatch.setenv("SBC_ENV", "production")
    with pytest.raises(RuntimeError, match="obligatoire"):
        with TestClient(app):
            pass
    monkeypatch.setenv("SBC_API_KEY", KEY)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/api/v1/capabilities").status_code == 401


@pytest.mark.parametrize("key", ["short", "é" * 40, "x" * 32 + "\n", "x" * 257])
def test_invalid_secret_is_rejected_without_echo(monkeypatch, key):
    monkeypatch.setenv("SBC_API_KEY", key)
    with pytest.raises(RuntimeError) as error:
        load_access_config()
    assert key not in str(error.value)


def test_key_file_is_supported_and_sources_cannot_conflict(monkeypatch, tmp_path):
    target = tmp_path / "key"
    target.write_text(KEY + "\n")
    monkeypatch.setenv("SBC_ACCESS_MODE", "shared")
    monkeypatch.setenv("SBC_API_KEY_FILE", str(target))
    assert load_access_config().key == KEY
    monkeypatch.setenv("SBC_API_KEY", KEY)
    with pytest.raises(RuntimeError, match="pas les deux"):
        load_access_config()


@pytest.mark.parametrize("maximum", ["0", "17", "nope", "1.5"])
def test_capacity_configuration_is_bounded(monkeypatch, maximum):
    monkeypatch.setenv("SBC_MAX_INFLIGHT", maximum)
    with pytest.raises(RuntimeError, match="SBC_MAX_INFLIGHT"):
        load_access_config()


def test_all_business_routes_are_protected_before_body_parsing(monkeypatch):
    monkeypatch.setenv("SBC_API_KEY", KEY)
    with TestClient(app) as client:
        for method, route in (
            ("GET", "/api/v1/sbc/workspace"),
            ("PUT", "/api/v1/sbc/protections"),
            ("POST", "/api/v1/sbc/solve"),
            ("POST", "/api/v1/perception/analyze"),
        ):
            for headers in ({}, {"Authorization": "Bearer wrong"}, {"X-API-Key": KEY}):
                response = client.request(
                    method, route, content=b"not-json-or-image", headers=headers
                )
                assert response.status_code == 401
                assert response.headers["www-authenticate"] == "Bearer"
                assert KEY not in response.text
        assert client.get("/api/v1/capabilities", params={"api_key": KEY}).status_code == 401
        assert (
            client.get(
                "/api/v1/capabilities",
                headers=[("Authorization", f"Bearer {KEY}"), ("Authorization", f"Bearer {KEY}")],
            ).status_code
            == 401
        )
        response = client.get("/api/v1/capabilities", headers={"Authorization": f"Bearer {KEY}"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"


def test_public_health_and_contract_docs_never_disclose_key(monkeypatch):
    monkeypatch.setenv("SBC_API_KEY", KEY)
    with TestClient(app) as client:
        for route in ("/health", "/docs", "/openapi.json"):
            response = client.get(route)
            assert response.status_code == 200
            assert KEY not in response.text
        schema = client.get("/openapi.json").json()
        assert schema["components"]["securitySchemes"]["ApiKeyBearer"]["scheme"] == "bearer"
        assert "security" not in schema["paths"]["/health"]["get"]
        assert schema["paths"]["/api/v1/sbc/workspace"]["get"]["security"] == [{"ApiKeyBearer": []}]


def limited_app(**overrides):
    service = FastAPI()
    service.state.access_config = replace(AccessConfig(), **overrides)
    service.add_middleware(AccessMiddleware)

    @service.post("/api/v1/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    return service


def test_payload_limit_checks_actual_chunks_not_only_content_length():
    service = limited_app(max_bytes=32)

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/echo", content=b"x" * 40)
            assert response.status_code == 413

            async def chunks():
                yield b"a" * 20
                yield b"b" * 20

            response = await client.post("/api/v1/echo", content=chunks())
            assert response.status_code == 413
            assert response.json()["detail"]["code"] == "payload_too_large"
            assert response.headers["cache-control"] == "no-store"

    asyncio.run(exercise())


def test_capacity_limit_and_timeout_release_the_slot():
    service = limited_app(max_inflight=1, timeout_seconds=0.03)
    started = asyncio.Event()

    @service.get("/api/v1/slow")
    async def slow():
        started.set()
        await asyncio.sleep(10)

    @service.get("/health")
    async def health():
        return {"status": "ok"}

    async def exercise():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=service), base_url="http://test"
        ) as client:
            pending = asyncio.create_task(client.get("/api/v1/slow"))
            await started.wait()
            response = await client.post("/api/v1/echo", content=b"hello")
            assert response.status_code == 429
            assert response.headers["retry-after"] == "2"
            assert (await client.get("/health")).status_code == 200
            assert (await pending).status_code == 504
            assert (await client.post("/api/v1/echo", content=b"hello")).status_code == 200

    asyncio.run(exercise())
