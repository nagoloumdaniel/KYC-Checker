"""Normalisation et rapprochement flou (fuzzy matching) de noms.

Sans dépendance externe : la similarité Jaro-Winkler et les ratios
token-sort / token-set sont implémentés ici en Python pur.

Difficultés gérées :
- accents et diacritiques (É -> E, Ü -> UE...),
- ordre nom/prénom inversé (token-sort, indépendant de l'ordre),
- noms composés, particules, séparateurs MRZ ('<', '-', '.', ',').
"""

from __future__ import annotations

import re
import unicodedata

# Translittération alignée sur les règles MRZ/ICAO pour les caractères
# qui ne se décomposent pas en NFKD (sinon ils seraient simplement perdus).
_TRANSLIT = {
    "Ä": "AE", "Ö": "OE", "Ü": "UE", "ß": "SS",
    "Ø": "OE", "Æ": "AE", "Œ": "OE", "Þ": "TH",
    "Đ": "D", "Ð": "D", "Ł": "L", "Ĳ": "IJ",
}


def normalize_name(value: str) -> str:
    """Met un nom sous forme canonique comparable : MAJUSCULES, sans accent,
    lettres A-Z uniquement, espaces simples."""
    if not value:
        return ""
    out = []
    for ch in value:
        out.append(_TRANSLIT.get(ch, _TRANSLIT.get(ch.upper(), ch)))
    s = "".join(out)
    # Décompose puis retire les diacritiques combinants (é -> e, ñ -> n...).
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.upper()
    # Tout ce qui n'est pas une lettre A-Z devient un séparateur.
    s = re.sub(r"[^A-Z]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def tokens(value: str) -> list[str]:
    norm = normalize_name(value)
    return [t for t in norm.split(" ") if t]


# --------------------------------------------------------------------------- #
# Similarité Jaro-Winkler (Python pur)
# --------------------------------------------------------------------------- #
def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0

    match_dist = max(0, max(len1, len2) // 2 - 1)
    s1_matches = [False] * len1
    s2_matches = [False] * len2
    matches = 0

    for i in range(len1):
        start = max(0, i - match_dist)
        end = min(i + match_dist + 1, len2)
        for j in range(start, end):
            if s2_matches[j] or s1[i] != s2[j]:
                continue
            s1_matches[i] = s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    # Transpositions
    k = transpositions = 0
    for i in range(len1):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    transpositions //= 2

    return (
        matches / len1
        + matches / len2
        + (matches - transpositions) / matches
    ) / 3.0


def jaro_winkler(s1: str, s2: str, prefix_weight: float = 0.1,
                 max_prefix: int = 4) -> float:
    base = _jaro(s1, s2)
    prefix = 0
    for a, b in zip(s1, s2):
        if a != b:
            break
        prefix += 1
        if prefix == max_prefix:
            break
    return base + prefix * prefix_weight * (1.0 - base)


def name_similarity(expected: str, candidate: str) -> float:
    """Similarité 0.0-1.0 indépendante de l'ordre des tokens."""
    e_tokens, c_tokens = tokens(expected), tokens(candidate)
    if not e_tokens or not c_tokens:
        return 0.0

    # token-sort : on trie les tokens des deux côtés avant de comparer.
    sort_ratio = jaro_winkler(" ".join(sorted(e_tokens)),
                              " ".join(sorted(c_tokens)))

    # token-set : on isole l'intersection et les restes.
    set_e, set_c = set(e_tokens), set(c_tokens)
    inter = " ".join(sorted(set_e & set_c))
    rest_e = (inter + " " + " ".join(sorted(set_e - set_c))).strip()
    rest_c = (inter + " " + " ".join(sorted(set_c - set_e))).strip()
    set_ratio = max(
        jaro_winkler(inter, rest_e) if inter else 0.0,
        jaro_winkler(inter, rest_c) if inter else 0.0,
        jaro_winkler(rest_e, rest_c),
    )
    return max(sort_ratio, set_ratio)


def match_name(expected: str, mrz_surname: str, mrz_given: str,
               cfg) -> dict:
    """Compare un nom attendu (saisie formulaire) au nom de la MRZ.

    Retourne un dict : score (0-100), label (MATCH/PARTIAL/NO_MATCH) et les
    formes normalisées pour traçabilité.
    """
    candidate = f"{mrz_surname} {mrz_given}".strip()
    score = round(name_similarity(expected, candidate) * 100, 1)

    if score >= cfg.name_match_threshold:
        label = "MATCH"
    elif score >= cfg.name_partial_threshold:
        label = "PARTIAL"
    else:
        label = "NO_MATCH"

    return {
        "score": score,
        "label": label,
        "expected": expected,
        "expected_normalized": normalize_name(expected),
        "mrz_normalized": normalize_name(candidate),
    }
