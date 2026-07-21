"""API HTTP du KYC Checker (FastAPI).

Endpoints :
- GET  /health      -> état du service + version + dispo OCR
- POST /verify       -> multipart : name + 1..n images (recto/verso) -> rapport
- POST /verify-mrz   -> JSON : { mrz_text, name } -> rapport (sans image)

Principe RGPD : les images sont traitées EN MÉMOIRE (jamais écrites sur disque).

Lancement :
    uvicorn kyc.api:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import hmac
import os

from fastapi import (Depends, FastAPI, File, Form, Header, HTTPException,
                     Query, UploadFile)
from pydantic import BaseModel

from . import __version__
from .config import Config
from .pipeline import verify_from_mrz, verify_documents

app = FastAPI(
    title="KYC Checker API",
    version=__version__,
    description="Vérification de pièces d'identité (MRZ TD1/TD2/TD3) + nom.",
)


# --------------------------------------------------------------------------- #
# Authentification par clé d'API
# --------------------------------------------------------------------------- #
def _allowed_keys() -> set[str]:
    """Clés autorisées (env KYC_API_KEYS, séparées par des virgules).
    Vide => authentification désactivée (mode dev)."""
    raw = os.environ.get("KYC_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _extract_key(x_api_key: str | None, authorization: str | None) -> str | None:
    if x_api_key:
        return x_api_key
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def require_api_key(x_api_key: str | None = Header(None),
                    authorization: str | None = Header(None)):
    """Dépendance : exige une clé valide si des clés sont configurées."""
    allowed = _allowed_keys()
    if not allowed:
        return  # auth désactivée (aucune clé configurée)
    provided = _extract_key(x_api_key, authorization)
    if provided and any(hmac.compare_digest(provided, k) for k in allowed):
        return
    raise HTTPException(status_code=401, detail="Clé d'API invalide ou absente.")

# Taille max acceptée par image (anti-abus / anti-DoS).
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 Mo
MAX_IMAGES = 2

_vault = None


def _get_vault():
    """Coffre d'archivage (chargé paresseusement ; nécessite `cryptography`)."""
    global _vault
    if _vault is None:
        from .storage import Vault, StorageConfig
        root = os.environ.get("KYC_ARCHIVE_DIR", "archive")
        _vault = Vault(StorageConfig(root=root))
    return _vault


class MrzRequest(BaseModel):
    mrz_text: str
    name: str
    ocr: str | None = None  # ignoré ici (pas d'image), présent pour symétrie


@app.get("/health")
def health():
    ocr_available = False
    ocr_detail = None
    try:
        from .ocr import get_ocr_backend
        backend = get_ocr_backend("auto")
        ocr_available, ocr_detail = True, backend.name
    except Exception as exc:
        ocr_detail = str(exc)
    return {
        "status": "ok",
        "version": __version__,
        "ocr_available": ocr_available,
        "ocr_backend": ocr_detail,
        "auth_enabled": bool(_allowed_keys()),
    }


@app.post("/verify-mrz", dependencies=[Depends(require_api_key)])
def verify_mrz_endpoint(req: MrzRequest):
    """Vérifie une pièce à partir d'un texte MRZ déjà extrait."""
    report = verify_from_mrz(req.mrz_text, req.name, Config())
    return report.to_dict()


@app.post("/verify", dependencies=[Depends(require_api_key)])
async def verify_endpoint(
    name: str = Form(..., description="Nom attendu (saisie formulaire)"),
    images: list[UploadFile] = File(..., description="1 à 2 images (recto/verso)"),
    selfie: UploadFile | None = File(None, description="Selfie (comparaison visage)"),
    ocr: str = Form("auto"),
    archive: bool = Form(False, description="Archiver le dossier (chiffré)"),
    registration_date: str | None = Form(None),
    actor: str = Form("api"),
):
    """Vérifie une pièce à partir d'images téléversées (traitées in-memory).

    Optionnel : `selfie` pour la comparaison de visage. Si archive=true, le
    dossier (rapport + images) est stocké chiffré et le record_id est renvoyé.
    """
    if len(images) > MAX_IMAGES:
        return _error(f"Maximum {MAX_IMAGES} images.", 413)

    blobs: list[bytes] = []
    for up in images[:MAX_IMAGES]:
        data = await up.read()
        if not data:
            return _error("Image vide.", 400)
        if len(data) > MAX_IMAGE_BYTES:
            return _error("Image trop volumineuse (max 8 Mo).", 413)
        if not _looks_like_image(data):
            return _error(f"Format non supporté : {up.filename}", 415)
        blobs.append(data)

    selfie_bytes = None
    if selfie is not None:
        selfie_bytes = await selfie.read()
        if selfie_bytes and not _looks_like_image(selfie_bytes):
            return _error("Selfie : format non supporté.", 415)
        if len(selfie_bytes) > MAX_IMAGE_BYTES:
            return _error("Selfie trop volumineux (max 8 Mo).", 413)

    report = verify_documents(blobs, name, selfie=selfie_bytes,
                              cfg=Config(), ocr_backend=ocr)
    result = report.to_dict()

    if archive:
        try:
            rid = _get_vault().store(
                name=name, report=report, images=blobs,
                registration_date=registration_date, actor=actor)
            result["record_id"] = rid
        except Exception as exc:  # cryptography absent, disque, etc.
            result["archive_error"] = f"{type(exc).__name__}: {exc}"

    # Les bytes restent en mémoire locale et sont libérés à la fin de la requête.
    return result


@app.get("/records", dependencies=[Depends(require_api_key)])
def search_records(
    name: str | None = Query(None),
    document_number: str | None = Query(None),
    registration_date: str | None = Query(None),
    actor: str = Query("api"),
):
    """Recherche de dossiers archivés (métadonnées seules, sans PII en clair)."""
    try:
        rows = _get_vault().search(
            name=name, document_number=document_number,
            registration_date=registration_date, actor=actor)
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}", 500)
    return {"count": len(rows), "records": rows}


# --------------------------------------------------------------------------- #
def _looks_like_image(data: bytes) -> bool:
    """Validation par signature (magic bytes) : JPEG / PNG."""
    return (data[:3] == b"\xff\xd8\xff"             # JPEG
            or data[:8] == b"\x89PNG\r\n\x1a\n")    # PNG


def _error(message: str, status: int):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=status, content={"error": message})
