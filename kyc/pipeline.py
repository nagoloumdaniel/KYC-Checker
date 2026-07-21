"""Orchestrateurs de haut niveau.

- verify_from_mrz    : entrée = texte MRZ déjà lu (aucune dépendance image).
- verify_image       : entrée = chemin image.
- verify_image_bytes : entrée = image en mémoire (bytes) — pour l'API.
- verify_images / verify_images_bytes : plusieurs images (recto/verso).

La couche OpenCV/OCR est chargée paresseusement : le cœur (verify_from_mrz)
fonctionne sans elle.
"""

from __future__ import annotations

from datetime import date

from .config import Config
from .mrz_reader import parse_mrz, expiry_status
from .names import match_name
from .scoring import build_report, Report


def _empty_name_match(expected: str) -> dict:
    return {"score": 0.0, "label": "NO_MATCH", "expected": expected,
            "expected_normalized": "", "mrz_normalized": ""}


def _dependency_error(expected_name: str, cfg: Config, message: str) -> Report:
    from .mrz_reader import MrzResult
    mrz = MrzResult(parsed=False, valid=False, error=message,
                    lines=(), fields={}, check_digits={})
    return build_report(mrz, _empty_name_match(expected_name),
                        {"date": None, "expired": None, "valid": False}, cfg)


def verify_from_mrz(mrz_text: str, expected_name: str,
                    cfg: Config | None = None,
                    today: date | None = None) -> Report:
    """Vérifie une pièce à partir du texte MRZ (TD1/TD2/TD3, auto-détecté)."""
    cfg = cfg or Config()
    mrz = parse_mrz(mrz_text)

    if mrz.parsed:
        name_match = match_name(
            expected_name, mrz.fields.get("surname", ""),
            mrz.fields.get("name", ""), cfg,
        )
        expiry = expiry_status(mrz.fields.get("expiry_date", ""), today)
    else:
        name_match = _empty_name_match(expected_name)
        expiry = {"date": None, "expired": None, "valid": False}

    return build_report(mrz, name_match, expiry, cfg)


def _verify_via(extractor, expected_name, cfg, today, not_found_msg):
    """Fabrique commune : `extractor()` -> (mrz_text, meta) puis report."""
    cfg = cfg or Config()
    try:
        mrz_text, _meta = extractor()
    except Exception as exc:  # OCR/binaire manquant, image illisible...
        return _dependency_error(expected_name, cfg, f"{type(exc).__name__}: {exc}")
    if not mrz_text:
        return _dependency_error(expected_name, cfg, not_found_msg)
    return verify_from_mrz(mrz_text, expected_name, cfg, today)


def verify_image(image_path: str, expected_name: str,
                 cfg: Config | None = None, ocr_backend: str = "auto",
                 today: date | None = None) -> Report:
    """Vérifie une pièce à partir d'une image (fichier)."""
    try:
        from .imaging import image_to_mrz_text
    except ImportError as exc:
        return _dependency_error(expected_name, cfg or Config(), str(exc))
    return _verify_via(
        lambda: image_to_mrz_text(image_path, ocr_backend=ocr_backend),
        expected_name, cfg, today, "Zone MRZ introuvable sur l'image.")


def verify_image_bytes(data: bytes, expected_name: str,
                       cfg: Config | None = None, ocr_backend: str = "auto",
                       today: date | None = None) -> Report:
    """Vérifie une pièce à partir d'une image EN MÉMOIRE (bytes)."""
    try:
        from .imaging import image_bytes_to_mrz_text
    except ImportError as exc:
        return _dependency_error(expected_name, cfg or Config(), str(exc))
    return _verify_via(
        lambda: image_bytes_to_mrz_text(data, ocr_backend=ocr_backend),
        expected_name, cfg, today, "Zone MRZ introuvable sur l'image.")


def _pick_best(reports: list[Report], expected_name: str, cfg: Config) -> Report:
    if not reports:
        return _dependency_error(expected_name, cfg, "Aucune image fournie.")
    # MRZ valide d'abord, puis lue, puis meilleur score.
    reports.sort(key=lambda r: (r.mrz_valid, r.mrz_parsed, r.score), reverse=True)
    return reports[0]


def _verify_many(sources, verify_one, expected_name, cfg, ocr_backend, today):
    cfg = cfg or Config()
    reports = []
    for src in sources:
        rep = verify_one(src, expected_name, cfg, ocr_backend, today)
        if rep.mrz_valid and rep.name_match.get("label") == "MATCH":
            return rep                       # cas idéal : on s'arrête
        reports.append(rep)
    return _pick_best(reports, expected_name, cfg)


def verify_images(image_paths, expected_name: str, cfg: Config | None = None,
                  ocr_backend: str = "auto", today: date | None = None) -> Report:
    """Vérifie une pièce à partir de plusieurs images fichiers (recto/verso)."""
    return _verify_many(image_paths, verify_image, expected_name, cfg,
                        ocr_backend, today)


def verify_images_bytes(blobs, expected_name: str, cfg: Config | None = None,
                        ocr_backend: str = "auto",
                        today: date | None = None) -> Report:
    """Vérifie une pièce à partir de plusieurs images en mémoire (recto/verso)."""
    return _verify_many(blobs, verify_image_bytes, expected_name, cfg,
                        ocr_backend, today)


def _to_bytes(source) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    with open(source, "rb") as fh:           # chemin de fichier
        return fh.read()


def verify_documents(images, expected_name: str, selfie=None,
                     cfg: Config | None = None, ocr_backend: str = "auto",
                     today: date | None = None,
                     run_forensics: bool = True) -> Report:
    """Vérification complète (Phase 5) : MRZ + nom, + comparaison de visage
    (si selfie fourni) + heuristiques de falsification.

    images : liste de chemins ou de bytes (recto/verso). selfie : chemin/bytes.
    """
    cfg = cfg or Config()
    blobs = [_to_bytes(s) for s in (images if isinstance(images, (list, tuple))
                                    else [images])]

    report = verify_images_bytes(blobs, expected_name, cfg, ocr_backend, today)

    # --- Comparaison de visage (selfie vs photo de la pièce) ---
    face_match = None
    if selfie is not None:
        selfie_bytes = _to_bytes(selfie)
        try:
            from .face import match_faces
            best = None
            for b in blobs:
                m = match_faces(b, selfie_bytes,
                                cosine_threshold=cfg.face_cosine_threshold)
                score = m.get("score")
                if best is None or (score or -1) > (best.get("score") or -1):
                    best = m
            face_match = best
        except Exception as exc:
            face_match = {"match": False, "score": None, "faces": {},
                          "error": f"{type(exc).__name__}: {exc}"}

    # --- Heuristiques de falsification ---
    forensics = None
    if run_forensics:
        try:
            from .forensics import analyze_image
            results = [analyze_image(b) for b in blobs]
            if results:  # on retient l'image la plus « suspecte »
                forensics = max(results, key=lambda r: r.get("tampering_score", 0))
        except Exception:
            forensics = None

    from .scoring import apply_post_signals
    return apply_post_signals(report, face_match, forensics, cfg)
