"""API : santé, contrats et transport des captures vers le pipeline de perception."""

import os
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI

from sbc_vision import __version__
from sbc_vision.api.perception import get_perception_pipeline
from sbc_vision.api.perception import router as perception_router
from sbc_vision.api.sbc_workspace import SbcConfig, get_sbc_config, sbc_available
from sbc_vision.api.sbc_workspace import router as sbc_router
from sbc_vision.contracts.perception import PerceptionResponse
from sbc_vision.perception.lab_colors import LabColorPipeline
from sbc_vision.perception.pipeline import PerceptionPipeline


@asynccontextmanager
async def lifespan(application: FastAPI):
    mode = os.getenv("SBC_PERCEPTION_MODE", "disabled")
    if mode not in {"disabled", "lab-colors"}:
        raise RuntimeError("SBC_PERCEPTION_MODE doit valoir disabled ou lab-colors.")
    previous = getattr(application.state, "perception_pipeline", None)
    if mode == "lab-colors":
        application.state.perception_pipeline = LabColorPipeline()
    try:
        yield
    finally:
        if mode == "lab-colors":
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
app.include_router(sbc_router)


@app.get("/health", tags=["system"])
def health() -> dict[str, str | bool]:
    """Indique l'état du processus HTTP ; aucune readiness de modèle n'est présumée."""
    return {
        "status": "ok",
        "version": __version__,
        "environment": os.getenv("SBC_ENV", "development"),
        "model_loaded": False,
    }


@app.get("/api/v1/capabilities", tags=["system"])
def capabilities(
    config: Annotated[SbcConfig | None, Depends(get_sbc_config)],
    pipeline: Annotated[PerceptionPipeline | None, Depends(get_perception_pipeline)],
) -> dict[str, bool | str]:
    engine = sbc_available(config)
    return {
        "stage": "foundation",
        "perception": pipeline is not None,
        "perception_mode": (
            "lab-colors"
            if isinstance(pipeline, LabColorPipeline)
            else "custom"
            if pipeline
            else "disabled"
        ),
        "ocr": False,
        "inventory": engine,
        "solver": engine,
        "sbc_workspace": engine,
        "controller": False,
        "live_actions_enabled": False,
    }


@app.get("/api/v1/contracts/perception", tags=["contracts"])
def perception_contract() -> dict:
    return PerceptionResponse.model_json_schema()
