"""Scoring et décision finale à partir des signaux collectés.

Schéma transparent et auditable :
  score = part_clés_MRZ (cfg.weight_check_digits, proportionnel aux clés OK)
        + part_nom      (cfg.weight_name_match, proportionnel au score de nom)

La décision applique ensuite des "caps" de sévérité (règles dures), car un
score numérique seul ne doit pas pouvoir blanchir un nom qui ne correspond
pas ou une clé de contrôle invalide.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import IntEnum

from .mrz_reader import MrzResult


class Status(IntEnum):
    VALID = 0       # aucune anomalie détectée
    SUSPECT = 1     # à revoir manuellement
    REJECTED = 2    # incohérence forte


_STATUS_FR = {
    Status.VALID: "VALIDÉ",
    Status.SUSPECT: "SUSPECT",
    Status.REJECTED: "REJETÉ",
}


@dataclass
class Report:
    status: str                      # "VALID" / "SUSPECT" / "REJECTED"
    status_fr: str
    score: float                     # 0-100
    mrz_parsed: bool
    mrz_valid: bool
    mrz_format: str | None           # "TD1" / "TD2" / "TD3"
    document_type: str | None
    country: str | None
    nationality: str | None
    document_number: str | None
    sex: str | None
    birth_date: str | None
    expiry: dict
    name_match: dict
    check_digits: dict
    fields: dict
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    face_match: dict | None = None       # Phase 5 : selfie vs photo pièce
    forensics: dict | None = None        # Phase 5 : heuristiques de falsification

    def to_dict(self) -> dict:
        return asdict(self)


def _worse(current: Status, candidate: Status) -> Status:
    return current if current >= candidate else candidate


def apply_post_signals(report: Report, face_match: dict | None = None,
                       forensics: dict | None = None, cfg=None) -> Report:
    """Intègre les signaux Phase 5 (visage, forensique) à un rapport déjà
    construit : attache les sections et ajuste la sévérité/décision."""
    from .config import Config
    cfg = cfg or Config()
    sev = Status[report.status]

    if face_match is not None:
        report.face_match = face_match
        if face_match.get("score") is None:
            report.warnings.append(
                "Comparaison de visage impossible : "
                + face_match.get("error", "visage non détecté") + ".")
        elif not face_match.get("match"):
            report.warnings.append(
                f"Le selfie ne correspond pas à la photo de la pièce "
                f"(similarité {face_match['score']}).")
            if cfg.face_nomatch_is_reject:
                sev = _worse(sev, Status.REJECTED)

    if forensics is not None:
        report.forensics = forensics
        if forensics.get("too_blurry"):
            report.warnings.append("Image peu nette (qualité réduite).")
        if forensics.get("low_resolution"):
            report.warnings.append("Résolution de l'image faible.")
        if forensics.get("suspicious") and cfg.tampering_is_suspect:
            report.warnings.append(
                f"Indice de retouche détecté (score "
                f"{forensics.get('tampering_score')}).")
            sev = _worse(sev, Status.SUSPECT)

    report.status = sev.name
    report.status_fr = _STATUS_FR[sev]
    return report


def build_report(mrz: MrzResult, name_match: dict, expiry: dict, cfg) -> Report:
    warnings: list[str] = []
    errors: list[str] = []

    # --- Cas non lisible : rejet immédiat. ---
    if not mrz.parsed:
        return Report(
            status=Status.REJECTED.name,
            status_fr=_STATUS_FR[Status.REJECTED],
            score=0.0,
            mrz_parsed=False, mrz_valid=False, mrz_format=mrz.format,
            document_type=None, country=None, nationality=None,
            document_number=None, sex=None, birth_date=None,
            expiry=expiry, name_match=name_match,
            check_digits={}, fields={},
            warnings=warnings,
            errors=[mrz.error or "MRZ illisible"],
        )

    # --- Score numérique ---
    cd = mrz.check_digits
    n_total = len(cd) or 1
    n_ok = sum(1 for v in cd.values() if v)
    score_mrz = cfg.weight_check_digits * (n_ok / n_total)
    score_name = cfg.weight_name_match * (name_match["score"] / 100.0)
    score = round(score_mrz + score_name, 1)

    # --- Décision par seuils ---
    if score >= cfg.accept_score:
        status = Status.VALID
    elif score >= cfg.reject_score:
        status = Status.SUSPECT
    else:
        status = Status.REJECTED

    # --- Règles dures (caps de sévérité) ---
    if not mrz.valid:
        warnings.append(
            "Clé(s) de contrôle MRZ invalide(s) : "
            + ", ".join(mrz.invalid_check_digits)
        )
        if cfg.invalid_check_digit_is_suspect:
            status = _worse(status, Status.SUSPECT)

    label = name_match["label"]
    if label == "NO_MATCH":
        warnings.append(
            f"Le nom de la pièce ne correspond pas au nom attendu "
            f"(similarité {name_match['score']}%)."
        )
        if cfg.name_nomatch_is_reject:
            status = _worse(status, Status.REJECTED)
    elif label == "PARTIAL":
        warnings.append(
            f"Correspondance de nom partielle (similarité {name_match['score']}%)."
        )
        if cfg.name_partial_is_suspect:
            status = _worse(status, Status.SUSPECT)

    if expiry.get("valid") and expiry.get("expired"):
        warnings.append(f"Document expiré (expiration {expiry['date']}).")
        if cfg.expired_is_suspect:
            status = _worse(status, Status.SUSPECT)

    f = mrz.fields
    return Report(
        status=status.name,
        status_fr=_STATUS_FR[status],
        score=score,
        mrz_parsed=True,
        mrz_valid=mrz.valid,
        mrz_format=mrz.format,
        document_type=f.get("document_type"),
        country=f.get("country"),
        nationality=f.get("nationality"),
        document_number=f.get("document_number"),
        sex=f.get("sex"),
        birth_date=f.get("birth_date"),
        expiry=expiry,
        name_match=name_match,
        check_digits=cd,
        fields=f,
        warnings=warnings,
        errors=errors,
    )
