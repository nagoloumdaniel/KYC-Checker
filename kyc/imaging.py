"""Couche image : prétraitement OpenCV + localisation de la bande MRZ.

Pipeline image -> texte MRZ :
  1. chargement + redimensionnement,
  2. localisation de la bande MRZ par morphologie (blackhat + gradient +
     fermeture), approche classique robuste aux fonds variés,
  3. recadrage de la bande, OCR (backend au choix),
  4. extraction des 2 lignes TD3 depuis le texte OCR.

Si la bande n'est pas trouvée, on bascule en OCR plein cadre (fallback).
Ce module importe OpenCV/NumPy : son seul import échoue proprement
(ImportError) si la couche image n'est pas installée — le cœur du moteur
continue alors de fonctionner sur une entrée MRZ texte.
"""

from __future__ import annotations

import cv2
import numpy as np

from .mrz_reader import extract_mrz_lines, parse_mrz
from .ocr import get_ocr_backend


def _resize_max_width(image, max_width: int = 1000):
    h, w = image.shape[:2]
    if w <= max_width:
        return image, 1.0
    scale = max_width / float(w)
    return cv2.resize(image, (max_width, int(h * scale)),
                      interpolation=cv2.INTER_AREA), scale


def locate_mrz_band(gray):
    """Retourne un recadrage (np.ndarray) de la bande MRZ, ou None.

    Méthode morphologique : la MRZ est un bloc de texte sombre, large et bas
    sur le document. On la fait ressortir puis on la referme en un rectangle.
    """
    h, w = gray.shape[:2]
    rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 7))
    sq_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))

    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    blackhat = cv2.morphologyEx(blurred, cv2.MORPH_BLACKHAT, rect_kernel)

    grad = cv2.Sobel(blackhat, ddepth=cv2.CV_32F, dx=1, dy=0, ksize=-1)
    grad = np.absolute(grad)
    (min_v, max_v) = (np.min(grad), np.max(grad))
    if max_v - min_v < 1e-6:
        return None
    grad = (255 * ((grad - min_v) / (max_v - min_v))).astype("uint8")

    grad = cv2.morphologyEx(grad, cv2.MORPH_CLOSE, rect_kernel)
    thresh = cv2.threshold(grad, 0, 255,
                           cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, sq_kernel)
    thresh = cv2.erode(thresh, None, iterations=4)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for c in contours:
        (x, y, cw, ch) = cv2.boundingRect(c)
        aspect = cw / float(ch) if ch else 0
        width_ratio = cw / float(w)
        # La MRZ est large (faible hauteur, grand ratio) et plutôt en bas.
        if aspect > 5 and width_ratio > 0.6 and (y / h) > 0.4:
            candidates.append((y, x, cw, ch))

    if not candidates:
        return None

    # On prend la bande la plus basse (la MRZ est en pied de document).
    # La détection ne capte souvent qu'UNE ligne : on étend vers le haut pour
    # englober les 2 lignes TD3 (voire 3 pour les futures cartes TD1).
    candidates.sort(reverse=True)
    (y, x, cw, ch) = candidates[0]
    pad_x = int(0.03 * w)
    pad_top = int(3.0 * ch)     # remonte pour capter la/les ligne(s) du dessus
    pad_bottom = int(0.8 * ch)
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_top)
    x1 = min(w, x + cw + pad_x)
    y1 = min(h, y + ch + pad_bottom)
    return gray[y0:y1, x0:x1]


def image_to_mrz_text(image_path: str, ocr_backend: str = "auto"):
    """Charge une image depuis un fichier et renvoie (texte_mrz, meta)."""
    image = cv2.imread(image_path)
    if image is None:
        raise FileNotFoundError(f"Image illisible : {image_path}")
    return _bgr_to_mrz_text(image, ocr_backend)


def image_bytes_to_mrz_text(data: bytes, ocr_backend: str = "auto"):
    """Décode une image EN MÉMOIRE (sans écriture disque) -> (texte_mrz, meta).

    Utilisé par l'API pour respecter le principe RGPD du traitement in-memory.
    """
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Données image illisibles ou format non supporté.")
    return _bgr_to_mrz_text(image, ocr_backend)


def _bgr_to_mrz_text(image, ocr_backend: str = "auto"):
    """Cœur du traitement : image BGR -> (texte_mrz, meta).

    texte_mrz : lignes MRZ jointes par '\\n', ou None si rien d'exploitable.
    meta      : infos de traitement (backend, bande trouvée, format, source).
    """
    image, _scale = _resize_max_width(image)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    backend = get_ocr_backend(ocr_backend)
    meta = {"ocr_backend": backend.name, "band_found": False,
            "source": None, "format": None}

    def _extract(image):
        lines, fmt = extract_mrz_lines(backend.read_mrz(image))
        return ("\n".join(lines), fmt) if lines else (None, None)

    # On collecte des candidats : bande MRZ recadrée puis plein cadre.
    candidates: list[tuple[str, str, str]] = []  # (source, texte, format)

    band = locate_mrz_band(gray)
    if band is not None and band.size > 0:
        meta["band_found"] = True
        band_norm = cv2.normalize(band, None, 0, 255, cv2.NORM_MINMAX)
        text, fmt = _extract(band_norm)
        if text:
            candidates.append(("band", text, fmt))

    text, fmt = _extract(gray)
    if text:
        candidates.append(("full", text, fmt))

    # On privilégie la lecture qui VALIDE réellement la MRZ.
    for source, text, fmt in candidates:
        if parse_mrz(text).valid:
            meta["source"], meta["format"] = source, fmt
            return text, meta

    # Aucune ne valide : on renvoie la première lecture exploitable (le
    # rapport signalera les clés invalides).
    if candidates:
        meta["source"], meta["format"] = candidates[0][0], candidates[0][2]
        return candidates[0][1], meta
    return None, meta
