from kyc.config import Config
from kyc.names import normalize_name, name_similarity, match_name

CFG = Config()


def test_normalize_strips_accents_and_separators():
    assert normalize_name("Éric  De-La Croïx") == "ERIC DE LA CROIX"
    assert normalize_name("ANNA<MARIA<<ERIKSSON") == "ANNA MARIA ERIKSSON"


def test_german_transliteration_matches_mrz():
    # Müller (visuel) vs MUELLER (MRZ) -> doit normaliser pareil.
    assert normalize_name("Müller") == "MUELLER"
    assert normalize_name("Straße") == "STRASSE"


def test_order_independent():
    s = name_similarity("Anna Maria Eriksson", "ERIKSSON ANNA MARIA")
    assert s > 0.95


def test_exact_match_label():
    m = match_name("Anna Maria Eriksson", "ERIKSSON", "ANNA MARIA", CFG)
    assert m["label"] == "MATCH"
    assert m["score"] >= 95


def test_partial_match_label():
    # Prénom manquant -> correspondance partielle.
    m = match_name("Anna Eriksson", "ERIKSSON", "ANNA MARIA CHARLOTTE", CFG)
    assert m["label"] in ("PARTIAL", "MATCH")  # tolérance, mais pas NO_MATCH


def test_no_match_label():
    m = match_name("Jean Dupont", "ERIKSSON", "ANNA MARIA", CFG)
    assert m["label"] == "NO_MATCH"
    assert m["score"] < 65


def test_accented_form_input_matches_unaccented_mrz():
    m = match_name("Éric Müller", "MUELLER", "ERIC", CFG)
    assert m["label"] == "MATCH"
