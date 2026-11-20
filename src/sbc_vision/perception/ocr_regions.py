"""Adaptateur du lecteur existant ; ne détecte pas les régions et ne confirme rien."""

import os
import sqlite3
from contextlib import closing
from io import BytesIO
from pathlib import Path
from threading import BoundedSemaphore

from sbc_vision.contracts.ocr import OcrAnalysisRequest, OcrAnalysisResponse


class OcrBusyError(Exception):
    pass


class RegionOcrReader:
    def __init__(self, language: str = "eng"):
        # Les dépendances OCR restent facultatives tant que ce mode est désactivé.
        import pytesseract

        from sbc_vision.sbc_engine import ocr, players

        if not language or not set(language.split("+")) <= set(pytesseract.get_languages()):
            raise RuntimeError("Les langues Tesseract configurées ne sont pas installées.")
        self.language, self.ocr, self.players = language, ocr, players
        self.engine_version = str(pytesseract.get_tesseract_version())
        self.slot = BoundedSemaphore(1)

    def analyze(
        self, data: bytes, request: OcrAnalysisRequest, database: Path | None = None
    ) -> OcrAnalysisResponse:
        # Le verrou appartient au worker : une annulation HTTP ne libère pas un calcul en cours.
        if not self.slot.acquire(blocking=False):
            raise OcrBusyError
        try:
            if database is None:
                db = self.players.open_database(":memory:")
            else:
                db = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
                db.row_factory = sqlite3.Row
                db.execute("PRAGMA query_only = ON")
            with closing(db):
                report = self.ocr.analyze(
                    BytesIO(data),
                    request.specification,
                    db,
                    lang=self.language,
                    minimum=request.minimum_confidence,
                )
                challenge = self.ocr.challenge_from_ocr(
                    report,
                    db,
                    market=request.market,
                    budget=request.budget,
                    minimum=request.minimum_confidence,
                )
                return OcrAnalysisResponse(
                    capture_id=report["capture_id"],
                    image=request.image,
                    engine_version=self.engine_version,
                    language=self.language,
                    minimum_confidence=request.minimum_confidence,
                    regions=report["regions"],
                    cards=report["cards"],
                    positions=report["positions"],
                    challenge_ready=challenge["ready"],
                    challenge=challenge["challenge"],
                    challenge_issues=challenge["issues"],
                )
        finally:
            self.slot.release()


def load_ocr_reader() -> RegionOcrReader | None:
    mode = os.getenv("SBC_OCR_MODE", "disabled")
    if mode == "disabled":
        return None
    if mode != "tesseract-regions":
        raise RuntimeError("SBC_OCR_MODE doit valoir disabled ou tesseract-regions.")
    try:
        return RegionOcrReader(os.getenv("SBC_OCR_LANG", "eng"))
    except (ImportError, OSError, RuntimeError) as exc:
        raise RuntimeError(
            "OCR indisponible : installer les options data,ocr, Tesseract et ses langues."
        ) from exc
