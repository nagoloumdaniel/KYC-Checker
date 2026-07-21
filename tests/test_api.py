"""Tests de l'API FastAPI (TestClient)."""

import base64
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cv2")

from fastapi.testclient import TestClient

import kyc.api as api
from kyc.api import app
from kyc.ocr import get_ocr_backend
from kyc.specimens import synthetic_passport, render_passport_image

client = TestClient(app)


def _ocr_available():
    try:
        get_ocr_backend("tesseract")
        return True
    except Exception:
        return False


def _crypto_available():
    try:
        import cryptography  # noqa: F401
        return True
    except Exception:
        return False


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_verify_mrz_valid():
    mrz = synthetic_passport(expiry_date="300101")
    r = client.post("/verify-mrz",
                    json={"mrz_text": mrz, "name": "Anna Maria Eriksson"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "VALID"
    assert body["mrz_format"] == "TD3"
    assert body["name_match"]["label"] == "MATCH"


def test_verify_mrz_wrong_name():
    mrz = synthetic_passport(expiry_date="300101")
    r = client.post("/verify-mrz",
                    json={"mrz_text": mrz, "name": "Jean Dupont"})
    assert r.json()["status"] == "REJECTED"


def test_health_reports_auth_disabled_by_default():
    assert client.get("/health").json()["auth_enabled"] is False


def test_auth_enforced_when_keys_configured(monkeypatch):
    monkeypatch.setenv("KYC_API_KEYS", "secret123, other-key")
    mrz = synthetic_passport(expiry_date="300101")
    payload = {"mrz_text": mrz, "name": "Anna Maria Eriksson"}

    # Sans clé -> 401
    assert client.post("/verify-mrz", json=payload).status_code == 401
    # Mauvaise clé -> 401
    assert client.post("/verify-mrz", json=payload,
                       headers={"X-API-Key": "wrong"}).status_code == 401
    # Bonne clé (X-API-Key) -> 200
    assert client.post("/verify-mrz", json=payload,
                       headers={"X-API-Key": "secret123"}).status_code == 200
    # Bonne clé (Bearer) -> 200
    assert client.post("/verify-mrz", json=payload,
                       headers={"Authorization": "Bearer other-key"}).status_code == 200
    # /health reste public
    assert client.get("/health").status_code == 200
    assert client.get("/health").json()["auth_enabled"] is True


def test_verify_rejects_non_image():
    r = client.post("/verify", data={"name": "X"},
                    files=[("images", ("x.txt", b"hello world", "text/plain"))])
    assert r.status_code == 415


@pytest.mark.skipif(not _ocr_available(), reason="Tesseract/OCR indisponible")
def test_verify_upload_image(tmp_path):
    mrz = synthetic_passport(expiry_date="300101")
    path = os.path.join(tmp_path, "passport.jpg")
    render_passport_image(mrz, path)
    with open(path, "rb") as fh:
        data = fh.read()

    r = client.post(
        "/verify",
        data={"name": "Anna Maria Eriksson", "ocr": "tesseract"},
        files=[("images", ("passport.jpg", data, "image/jpeg"))],
    )
    assert r.status_code == 200
    assert r.json()["status"] == "VALID"


@pytest.mark.skipif(not _ocr_available() or not _crypto_available(),
                    reason="OCR ou cryptography indisponible")
def test_verify_with_archive_then_search(tmp_path, monkeypatch):
    monkeypatch.setenv("KYC_ARCHIVE_DIR", str(tmp_path / "arch"))
    monkeypatch.setenv("KYC_MASTER_KEY", base64.b64encode(b"0" * 32).decode())
    monkeypatch.setattr(api, "_vault", None)  # force ré-init sur le dossier temp

    mrz = synthetic_passport(expiry_date="300101")
    path = os.path.join(tmp_path, "passport.jpg")
    render_passport_image(mrz, path)
    with open(path, "rb") as fh:
        data = fh.read()

    r = client.post(
        "/verify",
        data={"name": "Anna Maria Eriksson", "ocr": "tesseract",
              "archive": "true", "registration_date": "2026-06-06"},
        files=[("images", ("passport.jpg", data, "image/jpeg"))],
    )
    body = r.json()
    assert body["status"] == "VALID"
    assert "record_id" in body

    found = client.get("/records", params={"name": "Anna Maria Eriksson"})
    assert found.json()["count"] == 1
    assert found.json()["records"][0]["record_id"] == body["record_id"]
    monkeypatch.setattr(api, "_vault", None)
