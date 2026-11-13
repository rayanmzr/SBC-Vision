"""Transport des captures ; aucune détection synthétique servie par défaut."""

import asyncio
import warnings
from dataclasses import dataclass
from io import BytesIO
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from sbc_vision.contracts.perception import PerceptionResponse
from sbc_vision.perception.pipeline import Capture, PerceptionPipeline

router = APIRouter(prefix="/api/v1/perception", tags=["perception"])
FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG"}


@dataclass(frozen=True)
class AnalysisLimits:
    max_bytes: int = 5 * 1024 * 1024
    max_dimension: int = 8192
    max_pixels: int = 20_000_000
    upload_timeout_seconds: float = 10
    inference_timeout_seconds: float = 15


def get_analysis_limits() -> AnalysisLimits:
    return AnalysisLimits()


def get_perception_pipeline(request: Request) -> PerceptionPipeline | None:
    """À configurer au démarrage, après chargement des véritables modèles."""
    return getattr(request.app.state, "perception_pipeline", None)


def reject(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def decode_image(data: bytes, media_type: str, limits: AnalysisLimits) -> Image.Image:
    """Contrôler l'en-tête avant de décoder tous les pixels ; conserver leur repère."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=list(FORMATS.values())) as source:
                if source.format != FORMATS[media_type]:
                    raise reject(415, "format_mismatch", "Le format réel diffère du Content-Type.")
                width, height = source.size
                if max(width, height) > limits.max_dimension or width * height > limits.max_pixels:
                    raise reject(413, "image_too_large", "Dimensions de l'image hors limites.")
                if getattr(source, "n_frames", 1) != 1:
                    raise reject(415, "animated_image", "Une capture statique est attendue.")
                source.verify()
            with Image.open(BytesIO(data), formats=list(FORMATS.values())) as source:
                source.load()
                return source.convert("RGB")
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise reject(413, "image_too_large", "Dimensions de l'image hors limites.") from exc
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise reject(
            400, "invalid_image", "L'image PNG ou JPEG est vide, invalide ou tronquée."
        ) from exc


@router.post(
    "/analyze",
    response_model=PerceptionResponse,
    summary="Analyser une capture PNG ou JPEG",
    description=(
        "Corps binaire brut, sans multipart ni base64. Boîtes dans la capture d'origine. "
        "Sans pipeline configuré, retourne 503 ; aucun résultat fictif n'est substitué."
    ),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media: {"schema": {"type": "string", "format": "binary"}} for media in FORMATS
            },
        }
    },
    responses={
        400: {"description": "Image invalide ou tronquée"},
        408: {"description": "Délai de réception de l'image dépassé"},
        413: {"description": "Taille ou dimensions hors limites"},
        415: {"description": "Format non pris en charge ou Content-Type incorrect"},
        502: {"description": "Erreur du pipeline ou résultat incohérent avec la capture"},
        503: {"description": "Pipeline de perception non configuré"},
        504: {"description": "Délai d'inférence dépassé"},
    },
)
async def analyze_capture(
    request: Request,
    limits: Annotated[AnalysisLimits, Depends(get_analysis_limits)],
    pipeline: Annotated[PerceptionPipeline | None, Depends(get_perception_pipeline)],
    capture_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
) -> PerceptionResponse:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type not in FORMATS:
        raise reject(
            415, "unsupported_media_type", "Content-Type attendu : image/png ou image/jpeg."
        )
    data = bytearray()
    try:
        async with asyncio.timeout(limits.upload_timeout_seconds):
            async for chunk in request.stream():
                if len(data) + len(chunk) > limits.max_bytes:
                    raise reject(
                        413, "payload_too_large", "La capture dépasse la taille autorisée."
                    )
                data.extend(chunk)
    except TimeoutError as exc:
        raise reject(408, "upload_timeout", "Délai de réception de la capture dépassé.") from exc

    image = await run_in_threadpool(decode_image, bytes(data), media_type, limits)
    with image:
        if pipeline is None:
            raise reject(
                503, "perception_unavailable", "Le pipeline de perception n'est pas branché."
            )
        identifier = capture_id or str(uuid4())
        original_size = image.size
        try:
            async with asyncio.timeout(limits.inference_timeout_seconds):
                result = await pipeline.analyze(Capture(capture_id=identifier, image=image))
        except TimeoutError as exc:
            raise reject(
                504, "inference_timeout", "Délai d'analyse de la capture dépassé."
            ) from exc
        except Exception as exc:
            raise reject(
                502, "inference_failed", "Le pipeline n'a pas pu analyser la capture."
            ) from exc
        try:
            # Revalider aussi les instances Pydantic éventuellement modifiées par l'adaptateur.
            payload = result.model_dump() if isinstance(result, PerceptionResponse) else result
            response = PerceptionResponse.model_validate(payload)
            if response.capture_id != identifier:
                raise ValueError("capture_id mismatch")
            if (response.image.width, response.image.height) != original_size:
                raise ValueError("image size mismatch")
        except (ValidationError, ValueError, TypeError) as exc:
            raise reject(
                502, "invalid_perception_result", "Le résultat ne correspond pas à la capture."
            ) from exc
        return response
