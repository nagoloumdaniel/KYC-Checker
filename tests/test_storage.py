"""Tests du coffre d'archivage chiffré."""

import os
from datetime import date

import pytest

pytest.importorskip("cryptography")

from kyc.storage import Vault, StorageConfig, IntegrityError
from kyc.pipeline import verify_from_mrz
from kyc.specimens import synthetic_passport

MASTER = b"0123456789abcdef0123456789abcdef"  # 32 octets


def _vault(tmp_path, retention_days=1825):
    cfg = StorageConfig(root=str(tmp_path / "archive"),
                        retention_days=retention_days)
    return Vault(cfg, master_key=MASTER)


def _report():
    return verify_from_mrz(synthetic_passport(expiry_date="300101"),
                           "Anna Maria Eriksson")


def test_store_and_retrieve(tmp_path):
    v = _vault(tmp_path)
    rid = v.store(name="Anna Maria Eriksson", report=_report(),
                  images=[b"\xff\xd8firstimage", b"\xff\xd8second"],
                  registration_date="2026-06-06")
    assert rid
    got = v.retrieve(rid)
    assert got["image_count"] == 2
    assert got["images"][0] == b"\xff\xd8firstimage"
    assert got["report"]["status"] == "VALID"


def test_no_plaintext_pii_on_disk(tmp_path):
    v = _vault(tmp_path)
    v.store(name="Anna Maria Eriksson", report=_report(),
            images=[b"\xff\xd8imagecontent"], registration_date="2026-06-06")

    blob = b""
    for dirpath, _, files in os.walk(str(tmp_path / "archive")):
        for f in files:
            with open(os.path.join(dirpath, f), "rb") as fh:
                blob += fh.read()
    # Ni le nom ni le numéro de document ne doivent apparaître en clair.
    assert b"ERIKSSON" not in blob
    assert b"L898902C3" not in blob
    assert b"imagecontent" not in blob


def test_search_by_name_order_insensitive(tmp_path):
    v = _vault(tmp_path)
    rid = v.store(name="Anna Maria Eriksson", report=_report(),
                  images=[b"\xff\xd8X"], registration_date="2026-06-06")
    # Ordre et casse différents -> même jeton.
    res = v.search(name="eriksson  anna maria")
    assert len(res) == 1 and res[0]["record_id"] == rid
    assert v.search(name="Jean Dupont") == []


def test_search_by_document_number(tmp_path):
    v = _vault(tmp_path)
    v.store(name="Anna Maria Eriksson", report=_report(),
            images=[b"\xff\xd8X"], registration_date="2026-06-06")
    assert len(v.search(document_number="L898902C3")) == 1


def test_tampering_is_detected(tmp_path):
    v = _vault(tmp_path)
    rid = v.store(name="Anna Maria Eriksson", report=_report(),
                  images=[b"\xff\xd8XYZ"], registration_date="2026-06-06")
    path = os.path.join(str(tmp_path / "archive"), rid, "img_000.enc")
    data = bytearray(open(path, "rb").read())
    data[-1] ^= 0x01                      # on corrompt un octet
    open(path, "wb").write(data)
    with pytest.raises(IntegrityError):
        v.retrieve(rid)


def test_purge_expired(tmp_path):
    v = _vault(tmp_path, retention_days=0)   # expire immédiatement
    rid = v.store(name="Anna Maria Eriksson", report=_report(),
                  images=[b"\xff\xd8X"], registration_date="2020-01-01")
    purged = v.purge_expired(today=date(2026, 6, 6))
    assert purged == 1
    assert v.search() == []
    assert not os.path.isdir(os.path.join(str(tmp_path / "archive"), rid))


def test_audit_trail(tmp_path):
    v = _vault(tmp_path)
    rid = v.store(name="Anna Maria Eriksson", report=_report(),
                  images=[b"\xff\xd8X"], registration_date="2026-06-06",
                  actor="alice")
    v.retrieve(rid, actor="bob")
    trail = v.audit_trail(rid)
    actions = {e["action"] for e in trail}
    assert {"store", "retrieve"} <= actions
    assert any(e["actor"] == "bob" for e in trail)
