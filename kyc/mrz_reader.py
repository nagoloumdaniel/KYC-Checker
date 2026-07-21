"""Lecture, extraction et validation MRZ multi-formats.

Formats gérés (norme ICAO Doc 9303) :
- TD3 : passeports          (2 lignes × 44)
- TD1 : cartes d'identité   (3 lignes × 30)
- TD2 : pièces ID-2         (2 lignes × 36)

S'appuie sur la librairie `mrz` pour le calcul des clés de contrôle. Ajoute :
- la détection automatique du format,
- l'extraction tolérante des lignes depuis un texte OCR bruité,
- la correction positionnelle des confusions OCR (O↔0, I↔1…) par format,
- une interprétation lisible des dates,
- un résultat structuré qui ne lève jamais d'exception en aval.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from mrz.checker.td1 import TD1CodeChecker
from mrz.checker.td2 import TD2CodeChecker
from mrz.checker.td3 import TD3CodeChecker

_VALID_CHARS = re.compile(r"[A-Z0-9<]")

_FIELD_NAMES = [
    "surname", "name", "document_type", "country", "nationality",
    "document_number", "birth_date", "expiry_date", "sex",
    "optional_data", "optional_data_2",
]


@dataclass(frozen=True)
class FormatSpec:
    name: str
    num_lines: int
    line_len: int
    checker_cls: type
    hash_attrs: tuple          # clés de contrôle exposées par le checker
    digit_pos: dict            # {index_ligne: [positions numériques]}
    alpha_pos: dict            # {index_ligne: [positions alphabétiques]}


_FORMATS = {
    "TD1": FormatSpec(
        "TD1", 3, 30, TD1CodeChecker,
        ("document_number_hash", "birth_date_hash", "expiry_date_hash",
         "final_hash"),
        digit_pos={0: [14],
                   1: [0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 29]},
        alpha_pos={0: [0, 2, 3, 4], 1: [15, 16, 17], 2: list(range(30))},
    ),
    "TD2": FormatSpec(
        "TD2", 2, 36, TD2CodeChecker,
        ("document_number_hash", "birth_date_hash", "expiry_date_hash",
         "final_hash"),
        digit_pos={1: [9, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26,
                       27, 35]},
        alpha_pos={0: [0] + list(range(2, 36)), 1: [10, 11, 12]},
    ),
    "TD3": FormatSpec(
        "TD3", 2, 44, TD3CodeChecker,
        ("document_number_hash", "birth_date_hash", "expiry_date_hash",
         "optional_data_hash", "final_hash"),
        digit_pos={1: [9, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26,
                       27, 42, 43]},
        alpha_pos={0: list(range(44)), 1: [10, 11, 12]},
    ),
}


@dataclass
class MrzResult:
    parsed: bool                 # les lignes ont pu être lues/structurées
    valid: bool                  # toutes les clés de contrôle sont valides
    error: str | None
    lines: tuple
    fields: dict
    check_digits: dict           # {nom_de_cle: bool}
    format: str | None = None

    @property
    def invalid_check_digits(self) -> list[str]:
        return [k for k, ok in self.check_digits.items() if not ok]


# --------------------------------------------------------------------------- #
# Nettoyage / ajustement de lignes
# --------------------------------------------------------------------------- #
def _clean_line(line: str) -> str:
    line = line.strip().upper().replace(" ", "")
    return "".join(ch for ch in line if _VALID_CHARS.match(ch))


def _fit(line: str, length: int) -> str:
    return line[:length] if len(line) > length else line.ljust(length, "<")


def _detect_format(lines: list[str]) -> str | None:
    lens = [len(x) for x in lines]
    n = len(lines)
    if n == 3 and all(abs(x - 30) <= 4 for x in lens):
        return "TD1"
    if n == 2 and all(abs(x - 44) <= 4 for x in lens):
        return "TD3"
    if n == 2 and all(abs(x - 36) <= 4 for x in lens):
        return "TD2"
    return None


def extract_mrz_lines(raw_text: str) -> tuple[list[str] | None, str | None]:
    """Isole les lignes MRZ d'un texte OCR bruité et devine le format.

    Retourne (lignes_normalisées, nom_format) ou (None, None).
    """
    cands = [_clean_line(x) for x in raw_text.replace("\r", "").split("\n")]
    cands = [c for c in cands if len(c) >= 25 and "<" in c]
    if not cands:
        return None, None
    # Les longueurs (30 / 36 / 44) sont distinctes : pas de confusion possible.
    for name, length, count in (("TD1", 30, 3), ("TD3", 44, 2), ("TD2", 36, 2)):
        matching = [c for c in cands if abs(len(c) - length) <= 5]
        if len(matching) >= count:
            chosen = matching[-count:]
            return [_fit(c, length) for c in chosen], name
    return None, None


def extract_td3_lines(raw_text: str) -> str | None:
    """Compat : renvoie les 2 lignes TD3 jointes, ou None."""
    lines, fmt = extract_mrz_lines(raw_text)
    if fmt == "TD3" and lines:
        return "\n".join(lines)
    return None


# --------------------------------------------------------------------------- #
# Correction positionnelle (confusions OCR)
# --------------------------------------------------------------------------- #
_TO_DIGIT = {"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1", "Z": "2",
             "S": "5", "B": "8", "G": "6", "T": "7", "A": "4", "J": "1"}
_TO_ALPHA = {"0": "O", "1": "I", "2": "Z", "5": "S", "8": "B", "6": "G",
             "4": "A", "7": "T"}


def _force_digit(ch: str) -> str:
    return ch if ch.isdigit() else _TO_DIGIT.get(ch, ch)


def _force_alpha(ch: str) -> str:
    if ch == "<" or ch.isalpha():
        return ch
    return _TO_ALPHA.get(ch, ch)


def _apply_correction(lines: list[str], spec: FormatSpec) -> list[str]:
    out = []
    for i, ln in enumerate(lines):
        if len(ln) != spec.line_len:
            out.append(ln)
            continue
        c = list(ln)
        for p in spec.digit_pos.get(i, []):
            c[p] = _force_digit(c[p])
        for p in spec.alpha_pos.get(i, []):
            c[p] = _force_alpha(c[p])
        out.append("".join(c))
    return out


def _ok_count(res: MrzResult) -> int:
    return (1 if res.parsed else 0) + sum(1 for v in res.check_digits.values() if v)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _check(lines: list[str], spec: FormatSpec) -> MrzResult:
    code = "\n".join(lines)
    try:
        checker = spec.checker_cls(code)
    except Exception as exc:
        return MrzResult(False, False, f"{type(exc).__name__}: {exc}",
                         tuple(lines), {}, {}, spec.name)
    try:
        f = checker.fields()
        fields = {k: getattr(f, k) for k in _FIELD_NAMES if hasattr(f, k)}
    except Exception as exc:
        return MrzResult(False, False, f"fields() {type(exc).__name__}: {exc}",
                         tuple(lines), {}, {}, spec.name)
    check_digits = {k: bool(getattr(checker, k)) for k in spec.hash_attrs}
    return MrzResult(True, bool(checker), None, tuple(lines), fields,
                     check_digits, spec.name)


def parse_mrz(mrz_text: str, fmt: str | None = None,
              autocorrect: bool = True) -> MrzResult:
    """Détecte le format puis valide la MRZ. N'émet jamais d'exception."""
    cleaned = [_clean_line(x) for x in mrz_text.strip().split("\n")]
    cleaned = [c for c in cleaned if c]
    if fmt is None:
        fmt = _detect_format(cleaned)
    if fmt is None or fmt not in _FORMATS:
        return MrzResult(False, False, "Format MRZ non reconnu",
                         tuple(cleaned), {}, {}, None)

    spec = _FORMATS[fmt]
    if len(cleaned) < spec.num_lines:
        return MrzResult(False, False, "Nombre de lignes MRZ insuffisant",
                         tuple(cleaned), {}, {}, spec.name)
    chosen = cleaned[-spec.num_lines:]
    # Garde-fou : une vraie ligne MRZ ne perd au plus que quelques '<' finaux.
    # On rejette les lignes manifestement trop courtes (texte parasite).
    if any(len(c) < spec.line_len - 10 for c in chosen):
        return MrzResult(False, False, "Lignes MRZ trop courtes / illisibles",
                         tuple(cleaned), {}, {}, spec.name)
    lines = [_fit(c, spec.line_len) for c in chosen]

    res = _check(lines, spec)
    if res.valid or not autocorrect:
        return res
    res2 = _check(_apply_correction(lines, spec), spec)
    return res2 if (res2.valid or _ok_count(res2) > _ok_count(res)) else res


def parse_td3(mrz_text: str, autocorrect: bool = True) -> MrzResult:
    """Compat : validation forcée au format TD3."""
    return parse_mrz(mrz_text, fmt="TD3", autocorrect=autocorrect)


# --------------------------------------------------------------------------- #
# Dates MRZ (format YYMMDD) -> interprétation lisible + expiration
# --------------------------------------------------------------------------- #
def interpret_mrz_date(yymmdd: str, kind: str, today: date | None = None) -> dict:
    """Convertit une date MRZ 'YYMMDD' en date ISO.

    kind='birth'  : année interprétée comme passée (pivot = today).
    kind='expiry' : année interprétée comme proche (fenêtre -50/+50 ans).
    """
    today = today or date.today()
    if not (yymmdd and len(yymmdd) == 6 and yymmdd.isdigit()):
        return {"raw": yymmdd, "iso": None, "valid": False}

    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    cur_yy = today.year % 100
    cur_century = today.year - cur_yy

    if kind == "birth":
        century = cur_century if yy <= cur_yy else cur_century - 100
    else:  # expiry : fenêtre glissante centrée sur l'année courante
        century = cur_century
        year = century + yy
        if year < today.year - 50:
            century += 100
        elif year > today.year + 50:
            century -= 100
    year = century + yy

    try:
        iso = date(year, mm, dd)
    except ValueError:
        return {"raw": yymmdd, "iso": None, "valid": False}
    return {"raw": yymmdd, "iso": iso.isoformat(), "valid": True, "_date": iso}


def expiry_status(expiry_yymmdd: str, today: date | None = None) -> dict:
    today = today or date.today()
    info = interpret_mrz_date(expiry_yymmdd, "expiry", today)
    if not info["valid"]:
        return {"date": None, "expired": None, "valid": False}
    expired = info["_date"] < today
    return {"date": info["iso"], "expired": expired, "valid": True}
