from datetime import date

from kyc.mrz_reader import (parse_td3, parse_mrz, extract_td3_lines,
                           expiry_status, interpret_mrz_date)
from kyc.specimens import (synthetic_passport, synthetic_id_td1,
                          synthetic_id_td2, tamper_first_check_digit,
                          PUBLIC_SAMPLES)


def test_parse_td1_card():
    res = parse_mrz(synthetic_id_td1())
    assert res.parsed and res.valid
    assert res.format == "TD1"
    assert res.fields["surname"] == "ERIKSSON"
    assert res.fields["document_number"] == "D23145890"


def test_parse_td2_card():
    res = parse_mrz(synthetic_id_td2())
    assert res.parsed and res.valid
    assert res.format == "TD2"
    assert res.fields["name"] == "ANNA MARIA"


def test_format_autodetection():
    assert parse_mrz(synthetic_id_td1()).format == "TD1"
    assert parse_mrz(synthetic_id_td2()).format == "TD2"
    assert parse_mrz(synthetic_passport()).format == "TD3"


def test_parse_valid_synthetic():
    mrz = synthetic_passport()
    res = parse_td3(mrz)
    assert res.parsed and res.valid
    assert res.fields["surname"] == "ERIKSSON"
    assert res.fields["name"] == "ANNA MARIA"
    assert res.fields["document_type"] == "P"
    assert all(res.check_digits.values())


def test_parse_public_sample():
    res = parse_td3(PUBLIC_SAMPLES["icao_anna_eriksson"])
    assert res.parsed and res.valid
    assert res.fields["document_number"] == "L898902C3"


def test_tampered_check_digit_detected():
    mrz = tamper_first_check_digit(synthetic_passport())
    res = parse_td3(mrz)
    assert res.parsed          # structure lisible
    assert not res.valid       # mais clé invalide
    assert "document_number_hash" in res.invalid_check_digits


def test_malformed_does_not_raise():
    res = parse_td3("GARBAGE\nLINE")
    assert not res.parsed
    assert res.error is not None


def test_extract_lines_from_noisy_ocr():
    mrz = synthetic_passport()
    noisy = "QUELQUE BRUIT\n\n" + mrz.replace("\n", "  \n ") + "\nfooter"
    extracted = extract_td3_lines(noisy)
    assert extracted is not None
    assert parse_td3(extracted).valid


def test_expiry_detection():
    # 1204 -> avril 2012, donc expiré au 2026.
    status = expiry_status("120415", today=date(2026, 6, 6))
    assert status["expired"] is True
    status2 = expiry_status("300101", today=date(2026, 6, 6))
    assert status2["expired"] is False


def test_birth_date_century():
    info = interpret_mrz_date("740812", "birth", today=date(2026, 6, 6))
    assert info["iso"] == "1974-08-12"


def test_positional_correction_recovers_ocr_confusions():
    # Sortie OCR typique : 'UTO' lu 'UT0' (O->0) sur la nationalité (ligne 2).
    ocr = ("P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
           "L898902C36UT07408122F3001019ZE184226B<<<<<16")
    # Sans correction : invalide (nationalité numérique impossible).
    assert not parse_td3(ocr, autocorrect=False).valid
    # Avec correction positionnelle : récupéré et valide.
    res = parse_td3(ocr, autocorrect=True)
    assert res.valid
    assert res.fields["nationality"] == "UTO"
