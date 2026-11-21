"""Accès et limites du service partagé ; aucun secret dans les réponses ou journaux."""

import asyncio
import os
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


@dataclass(frozen=True)
class AccessConfig:
    key: str | None = None
    max_inflight: int = 4
    max_bytes: int = 5 * 1024 * 1024
    timeout_seconds: float = 30


def load_access_config() -> AccessConfig:
    mode = os.getenv(
        "SBC_ACCESS_MODE", "shared" if os.getenv("SBC_ENV") == "production" else "local"
    )
    if mode not in {"local", "shared"}:
        raise RuntimeError("SBC_ACCESS_MODE doit valoir local ou shared.")
    value, key_file = os.getenv("SBC_API_KEY", ""), os.getenv("SBC_API_KEY_FILE", "")
    if value and key_file:
        raise RuntimeError("Choisir SBC_API_KEY ou SBC_API_KEY_FILE, pas les deux.")
    if key_file:
        try:
            value = Path(key_file).read_text().strip()
        except (OSError, UnicodeError) as exc:
            raise RuntimeError("Le fichier de clé API est illisible.") from exc
    if value and not re.fullmatch(r"[A-Za-z0-9_-]{32,256}", value):
        raise RuntimeError("La clé API doit contenir 32 à 256 caractères alphanumériques, _ ou -.")
    if mode == "shared" and not value:
        raise RuntimeError("Une clé API est obligatoire en mode partagé.")
    try:
        maximum = int(os.getenv("SBC_MAX_INFLIGHT", "4"))
        if not 1 <= maximum <= 16:
            raise ValueError
    except ValueError as exc:
        raise RuntimeError("SBC_MAX_INFLIGHT doit être un entier entre 1 et 16.") from exc
    return AccessConfig(key=value or None, max_inflight=maximum)


class AccessMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app
        self.active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        config = getattr(scope["app"].state, "access_config", None) or load_access_config()
        public = scope["method"] in {"GET", "HEAD"} and scope["path"] in PUBLIC_PATHS

        async def refuse(status: int, code: str, message: str, headers=None):
            response = JSONResponse(
                {"detail": {"code": code, "message": message}},
                status_code=status,
                headers={"Cache-Control": "no-store", **(headers or {})},
            )
            await response(scope, receive, send)

        if config.key and not public:
            values = [value for name, value in scope["headers"] if name.lower() == b"authorization"]
            expected = f"Bearer {config.key}".encode("ascii")
            if len(values) != 1 or not secrets.compare_digest(values[0], expected):
                return await refuse(
                    401,
                    "authentication_required",
                    "Clé API absente ou incorrecte.",
                    {"WWW-Authenticate": "Bearer"},
                )
        if public:
            return await self.app(scope, receive, send)
        if self.active >= config.max_inflight:
            return await refuse(
                429, "api_busy", "Service occupé. Réessayer plus tard.", {"Retry-After": "2"}
            )
        for name, value in scope["headers"]:
            if name.lower() == b"content-length":
                try:
                    if int(value) > config.max_bytes:
                        return await refuse(
                            413, "payload_too_large", "Corps de requête trop volumineux."
                        )
                except ValueError:
                    return await refuse(400, "invalid_length", "Content-Length invalide.")
        consumed, started = 0, False

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > config.max_bytes:
                    raise HTTPException(
                        413,
                        detail={
                            "code": "payload_too_large",
                            "message": "Corps de requête trop volumineux.",
                        },
                    )
            return message

        async def private_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                message = {**message, "headers": [*headers, (b"cache-control", b"no-store")]}
            await send(message)

        self.active += 1
        try:
            async with asyncio.timeout(config.timeout_seconds):
                await self.app(scope, bounded_receive, private_send)
        except TimeoutError:
            if not started:
                await refuse(504, "request_timeout", "Délai de traitement dépassé.")
        finally:
            self.active -= 1
