"""API : santé, contrats et transport des captures vers le pipeline de perception."""

import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.openapi.utils import get_openapi

from sbc_vision import __version__
from sbc_vision.api.access import AccessMiddleware, load_access_config
from sbc_vision.api.ocr import get_ocr_reader
from sbc_vision.api.ocr import router as ocr_router
from sbc_vision.api.perception import get_perception_pipeline
from sbc_vision.api.perception import router as perception_router
from sbc_vision.api.sbc_workspace import SbcConfig, get_sbc_config, sbc_available
from sbc_vision.api.sbc_workspace import router as sbc_router
from sbc_vision.contracts.ocr import OcrAnalysisRequest
from sbc_vision.contracts.perception import PerceptionResponse
from sbc_vision.perception.lab_colors import LabColorPipeline
from sbc_vision.perception.ocr_regions import RegionOcrReader, load_ocr_reader
from sbc_vision.perception.pipeline import DetectorPipeline, PerceptionPipeline


@asynccontextmanager
async def lifespan(application: FastAPI):
    application.state.access_config = load_access_config()
    mode = os.getenv("SBC_PERCEPTION_MODE", "disabled")
    if mode not in {"disabled", "lab-colors", "detector"}:
        raise RuntimeError("SBC_PERCEPTION_MODE doit valoir disabled, lab-colors ou detector.")
    previous = getattr(application.state, "perception_pipeline", None)
    previous_ocr = getattr(application.state, "ocr_reader", None)
    application.state.ocr_reader = load_ocr_reader()
    if mode == "lab-colors":
        application.state.perception_pipeline = LabColorPipeline()
    elif mode == "detector":
        if not os.getenv("SBC_DETECTOR"):
            raise RuntimeError("Configurer SBC_DETECTOR avec le type et le chemin du modèle.")
        config = get_sbc_config()
        application.state.perception_pipeline = DetectorPipeline(
            os.environ["SBC_DETECTOR"],
            float(os.getenv("SBC_DETECTION_THRESHOLD", "0.61")),
            application.state.ocr_reader,
            config.database if config else None,
            layout=os.getenv("SBC_CARD_LAYOUT", "card"),
        )
    try:
        yield
    finally:
        application.state.access_config = None
        application.state.ocr_reader = previous_ocr
        if mode in {"lab-colors", "detector"}:
            application.state.perception_pipeline = previous


app = FastAPI(
    lifespan=lifespan,
    title="SBC Vision",
    version=__version__,
    description=(
        "Transport d'images prêt pour le raccordement détection/OCR. Sans pipeline chargé, "
        "l'analyse renvoie 503. Le moteur SBC est activé par configuration explicite. "
        "Aucune action sur le navigateur n'est exposée."
    ),
)
app.include_router(perception_router)
app.include_router(ocr_router)
app.include_router(sbc_router)
app.add_middleware(AccessMiddleware)


def protected_openapi():
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyBearer"] = {
            "type": "http",
            "scheme": "bearer",
            "description": "Clé du service partagé ; facultative en développement local sans clé.",
        }
        for path, methods in schema["paths"].items():
            if path != "/health":
                for operation in methods.values():
                    if isinstance(operation, dict):
                        operation["security"] = [{"ApiKeyBearer": []}]
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = protected_openapi


@app.get("/health", tags=["system"])
def health(request: Request) -> dict[str, str | bool]:
    """Indique l'état du processus HTTP ; aucune readiness de modèle n'est présumée."""
    return {
        "status": "ok",
        "version": __version__,
        "environment": os.getenv("SBC_ENV", "development"),
        "model_loaded": isinstance(
            getattr(request.app.state, "perception_pipeline", None), DetectorPipeline
        ),
    }


@app.get("/api/v1/capabilities", tags=["system"])
def capabilities(
    config: Annotated[SbcConfig | None, Depends(get_sbc_config)],
    pipeline: Annotated[PerceptionPipeline | None, Depends(get_perception_pipeline)],
    reader: Annotated[RegionOcrReader | None, Depends(get_ocr_reader)],
) -> dict[str, bool | str]:
    engine = sbc_available(config)
    return {
        "stage": "foundation",
        "perception": pipeline is not None,
        "perception_mode": (
            "lab-colors"
            if isinstance(pipeline, LabColorPipeline)
            else "detector"
            if isinstance(pipeline, DetectorPipeline)
            else "custom"
            if pipeline
            else "disabled"
        ),
        "ocr": reader is not None,
        "ocr_mode": "tesseract-regions" if reader else "disabled",
        "ocr_regions_required": reader is not None and not isinstance(pipeline, DetectorPipeline),
        "inventory": engine,
        "solver": engine,
        "sbc_workspace": engine,
        "controller": False,
        "live_actions_enabled": False,
    }


@app.get("/api/v1/contracts/perception", tags=["contracts"])
def perception_contract() -> dict:
    return PerceptionResponse.model_json_schema()


@app.get("/api/v1/contracts/ocr-request", tags=["contracts"])
def ocr_request_contract() -> dict:
    return OcrAnalysisRequest.model_json_schema()
