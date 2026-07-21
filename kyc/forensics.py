"""Détection de falsification — heuristiques LÉGÈRES (couche optionnelle).

⚠️ Ce sont des *indices*, pas des preuves. Les heuristiques d'imagerie
(Error Level Analysis, netteté, résolution) signalent des anomalies possibles
mais produisent des faux positifs/négatifs. Une détection robuste de fraude
documentaire (photo recollée, recapture d'écran, copier-coller) nécessite des
modèles dédiés. À utiliser comme signal d'aide à la revue, pas comme verdict.

Ne dépend que d'OpenCV/NumPy (déjà présents pour la couche image).
"""

from __future__ import annotations

import cv2
import numpy as np


def _load_bgr(source) -> np.ndarray:
    if isinstance(source, np.ndarray):
        return source
    if isinstance(source, (bytes, bytearray)):
        img = cv2.imdecode(np.frombuffer(bytes(source), np.uint8), cv2.IMREAD_COLOR)
    else:
        img = cv2.imread(source)
    if img is None:
        raise ValueError("Image illisible pour l'analyse forensique.")
    return img


def error_level_analysis(img_bgr: np.ndarray, quality: int = 90):
    """Re-compresse en JPEG puis mesure l'écart : des zones modifiées
    ressortent (niveaux d'erreur localement élevés)."""
    ok, enc = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        return None
    recompressed = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    diff = cv2.absdiff(img_bgr, recompressed)
    return cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)


def analyze_image(source, quality: int = 90) -> dict:
    """Analyse heuristique d'une image. Renvoie des métriques + drapeaux."""
    img = _load_bgr(source)
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Netteté (variance du Laplacien) : faible => flou.
    blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    # Error Level Analysis.
    ela = error_level_analysis(img, quality)
    if ela is not None:
        ela_mean = float(ela.mean())
        ela_p99 = float(np.percentile(ela, 99))
        ela_max = float(ela.max())
        # Fraction de pixels au niveau d'erreur nettement supérieur à la moyenne
        # (signature possible d'une zone recollée / de qualité différente).
        thresh = max(25.0, ela_mean * 4.0)
        high_fraction = float((ela > thresh).mean())
    else:
        ela_mean = ela_p99 = ela_max = high_fraction = 0.0

    too_blurry = blur_var < 50.0
    low_resolution = (w < 400 or h < 250)
    # Règle conservatrice : retouche probable si beaucoup de pixels très
    # au-dessus de la moyenne ET niveau de pointe élevé.
    suspicious = (high_fraction > 0.02 and ela_p99 > 40.0)

    tampering_score = round(min(100.0, high_fraction * 300.0 + ela_p99 / 255.0 * 30.0), 1)

    return {
        "width": w, "height": h,
        "blur_var": round(blur_var, 1),
        "too_blurry": too_blurry,
        "low_resolution": low_resolution,
        "ela_mean": round(ela_mean, 2),
        "ela_p99": round(ela_p99, 2),
        "ela_max": round(ela_max, 2),
        "high_error_fraction": round(high_fraction, 4),
        "tampering_score": tampering_score,
        "suspicious": bool(suspicious),
    }
