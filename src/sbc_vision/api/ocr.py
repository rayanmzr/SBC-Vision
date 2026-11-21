"""Lecture de régions par HTTP, sans inventaire modifié ni action dans le navigateur."""

import asyncio
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from sbc_vision.api.perception import AnalysisLimits, decode_image, reject
from sbc_vision.api.sbc_workspace import SbcConfig, get_sbc_config
from sbc_vision.contracts.ocr import OcrAnalysisRequest, OcrAnalysisResponse
from sbc_vision.perception.ocr_regions import OcrBusyError, RegionOcrReader

router = APIRouter(prefix="/api/v1/ocr", tags=["ocr"])


def get_ocr_reader(request: Request) -> RegionOcrReader | None:
    return getattr(request.app.state, "ocr_reader", None)


def get_ocr_limits() -> AnalysisLimits:
    return replace(AnalysisLimits(), max_dimension=4096, max_pixels=4_000_000)


@router.post(
    "/analyze",
    response_model=OcrAnalysisResponse,
    summary="Lire une capture et des régions fournies avec l'OCR de Rayan",
    description=(
        "Multipart : image PNG/JPEG et metadata JSON (OcrAnalysisRequest). "
        "Aucune détection automatique, confirmation d'exemplaire ni exécution de clics. "
        "Le modèle de metadata est disponible à /api/v1/contracts/ocr-request."
    ),
    responses={
        400: {"description": "Image invalide"},
        413: {"description": "Image ou métadonnées trop grandes"},
        415: {"description": "Format d'image non pris en charge"},
        422: {"description": "Régions invalides ou dimensions incohérentes"},
        429: {"description": "Une lecture OCR est déjà en cours"},
        502: {"description": "Erreur OCR ou de catalogue"},
        503: {"description": "OCR non activé"},
        504: {"description": "Délai OCR dépassé"},
    },
)
async def analyze_regions(
    image: Annotated[UploadFile, File(description="Capture PNG ou JPEG")],
    metadata: Annotated[str, Form(description="OcrAnalysisRequest encodé en JSON")],
    reader: Annotated[RegionOcrReader | None, Depends(get_ocr_reader)],
    limits: Annotated[AnalysisLimits, Depends(get_ocr_limits)],
    config: Annotated[SbcConfig | None, Depends(get_sbc_config)],
) -> OcrAnalysisResponse:
    if reader is None:
        raise reject(503, "ocr_unavailable", "Activer SBC_OCR_MODE=tesseract-regions.")
    if len(metadata.encode("utf-8")) > 64 * 1024:
        raise reject(413, "ocr_metadata_too_large", "Métadonnées OCR limitées à 64 Kio.")
    try:
        spec = OcrAnalysisRequest.model_validate_json(metadata)
    except (ValidationError, ValueError) as exc:
        raise reject(422, "invalid_ocr_regions", "Régions ou paramètres OCR invalides.") from exc
    media = (image.content_type or "").split(";", 1)[0].strip().lower()
    if media not in {"image/png", "image/jpeg"}:
        raise reject(415, "unsupported_media_type", "Capture PNG ou JPEG attendue.")
    data = await image.read(limits.max_bytes + 1)
    if len(data) > limits.max_bytes:
        raise reject(413, "payload_too_large", "La capture dépasse la taille autorisée.")
    decoded = await run_in_threadpool(decode_image, data, media, limits)
    with decoded:
        if (spec.image.width, spec.image.height) != decoded.size:
            raise reject(
                422, "ocr_image_mismatch", "Les régions décrivent une autre taille d'image."
            )
    try:
        async with asyncio.timeout(limits.inference_timeout_seconds):
            return await run_in_threadpool(
                reader.analyze, data, spec, config.database if config else None
            )
    except TimeoutError as exc:
        raise reject(504, "ocr_timeout", "Délai de lecture OCR dépassé.") from exc
    except OcrBusyError as exc:
        raise reject(429, "ocr_busy", "Une lecture OCR est déjà en cours.") from exc
    except Exception as exc:
        raise reject(502, "ocr_failed", "Lecture OCR ou catalogue indisponible.") from exc
