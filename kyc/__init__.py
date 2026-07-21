"""KYC Checker — moteur de vérification de pièces d'identité.

Phase 1 : passeports (MRZ TD3, norme ICAO Doc 9303).
- Lecture + validation mathématique des clés de contrôle MRZ.
- Rapprochement (matching flou) du nom de la pièce avec un nom attendu.
- Scoring et décision (VALID / SUSPECT / REJECTED).

Le cœur (parsing MRZ, matching, scoring) n'a qu'une seule dépendance
externe : la librairie `mrz`. La couche image/OCR (OpenCV + Tesseract /
EasyOCR) est optionnelle et chargée paresseusement.
"""

from .config import Config
from .pipeline import (verify_from_mrz, verify_image, verify_image_bytes,
                       verify_images, verify_images_bytes, verify_documents)
from .scoring import Report, Status

__all__ = [
    "Config", "Report", "Status",
    "verify_from_mrz", "verify_image", "verify_image_bytes",
    "verify_images", "verify_images_bytes", "verify_documents",
]
__version__ = "0.3.0"
