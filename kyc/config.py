"""Paramètres réglables du moteur KYC.

Tous les seuils sont centralisés ici pour pouvoir être ajustés sans toucher
à la logique. Tu pourras les surcharger à l'intégration dans ton app.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    # --- Matching de nom (similarité 0-100) ---
    # >= name_match_threshold        -> MATCH
    # >= name_partial_threshold      -> PARTIAL
    # sinon                          -> NO_MATCH
    name_match_threshold: float = 85.0
    name_partial_threshold: float = 65.0

    # --- Décision globale ---
    # Score (0-100) au-dessus duquel un dossier *peut* être accepté.
    accept_score: float = 85.0
    # Score en dessous duquel le dossier est rejeté d'office.
    reject_score: float = 50.0

    # Pondération du score final (doit sommer à 100).
    weight_check_digits: float = 60.0   # part des clés de contrôle MRZ
    weight_name_match: float = 40.0     # part du rapprochement de nom

    # --- Règles dures (caps de sévérité) ---
    # Un nom NO_MATCH plafonne la décision à REJECTED.
    name_nomatch_is_reject: bool = True
    # Un nom PARTIAL plafonne la décision à SUSPECT.
    name_partial_is_suspect: bool = True
    # Une clé de contrôle MRZ invalide plafonne à SUSPECT.
    invalid_check_digit_is_suspect: bool = True
    # Un document expiré plafonne à SUSPECT.
    expired_is_suspect: bool = True

    # --- Phase 5 : signaux additionnels ---
    # Visage selfie != photo de la pièce plafonne à REJECTED.
    face_nomatch_is_reject: bool = True
    # Indice de retouche/falsification plafonne à SUSPECT.
    tampering_is_suspect: bool = True
    # Seuil cosinus de correspondance de visage (SFace).
    face_cosine_threshold: float = 0.363
