"""API initiale : santé, état des capacités et contrat de perception."""

import os

from fastapi import FastAPI

from sbc_vision import __version__
from sbc_vision.contracts.perception import PerceptionResponse

app = FastAPI(
    title="SBC Vision",
    version=__version__,
    description=(
        "Socle du projet. Les routes présentes ne réalisent pas encore d'inférence, "
        "de résolution de SBC ou de pilotage de la Web App."
    ),
)


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
def capabilities() -> dict[str, bool | str]:
    return {
        "stage": "foundation",
        "perception": False,
        "ocr": False,
        "inventory": False,
        "solver": False,
        "controller": False,
        "live_actions_enabled": False,
    }


@app.get("/api/v1/contracts/perception", tags=["contracts"])
def perception_contract() -> dict:
    return PerceptionResponse.model_json_schema()
