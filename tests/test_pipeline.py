from datetime import date

from kyc.config import Config
from kyc.pipeline import verify_from_mrz
from kyc.specimens import (synthetic_passport, synthetic_id_td1,
                          synthetic_id_td2, tamper_first_check_digit)

CFG = Config()
TODAY = date(2026, 6, 6)


def test_valid_passport_matching_name():
    mrz = synthetic_passport(expiry_date="300101")
    r = verify_from_mrz(mrz, "Anna Maria Eriksson", CFG, today=TODAY)
    assert r.status == "VALID"
    assert r.score >= CFG.accept_score
    assert r.mrz_valid
    assert r.name_match["label"] == "MATCH"
    assert not r.warnings


def test_valid_id_card_td1():
    mrz = synthetic_id_td1(expiry_date="300101")
    r = verify_from_mrz(mrz, "Anna Maria Eriksson", CFG, today=TODAY)
    assert r.status == "VALID"
    assert r.mrz_format == "TD1"
    assert r.name_match["label"] == "MATCH"


def test_valid_id_card_td2():
    mrz = synthetic_id_td2(expiry_date="300101")
    r = verify_from_mrz(mrz, "Anna Maria Eriksson", CFG, today=TODAY)
    assert r.status == "VALID"
    assert r.mrz_format == "TD2"


def test_wrong_name_is_rejected():
    mrz = synthetic_passport(expiry_date="300101")
    r = verify_from_mrz(mrz, "Jean Dupont", CFG, today=TODAY)
    assert r.status == "REJECTED"
    assert r.name_match["label"] == "NO_MATCH"


def test_tampered_mrz_is_suspect_at_least():
    mrz = tamper_first_check_digit(synthetic_passport(expiry_date="300101"))
    r = verify_from_mrz(mrz, "Anna Maria Eriksson", CFG, today=TODAY)
    assert r.status in ("SUSPECT", "REJECTED")
    assert not r.mrz_valid


def test_expired_passport_is_suspect():
    mrz = synthetic_passport(expiry_date="120415")  # expiré
    r = verify_from_mrz(mrz, "Anna Maria Eriksson", CFG, today=TODAY)
    assert r.status == "SUSPECT"
    assert r.expiry["expired"] is True


def test_unreadable_mrz_is_rejected():
    r = verify_from_mrz("NOT A MRZ", "Anna Eriksson", CFG, today=TODAY)
    assert r.status == "REJECTED"
    assert not r.mrz_parsed
    assert r.errors


def test_report_is_json_serializable():
    import json
    mrz = synthetic_passport()
    r = verify_from_mrz(mrz, "Anna Maria Eriksson", CFG, today=TODAY)
    json.dumps(r.to_dict())  # ne doit pas lever
