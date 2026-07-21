"""Test d'intégration du chemin image (génération -> OCR -> validation).

Se *skip* automatiquement si la couche image/OCR n'est pas disponible
(OpenCV, Pillow, Tesseract + modèle OCR-B), afin de rester portable.
"""

import os

import pytest

cv2 = pytest.importorskip("cv2")
PIL = pytest.importorskip("PIL")

from kyc.ocr import get_ocr_backend
from kyc.pipeline import verify_image, verify_images, verify_documents
from kyc.specimens import (synthetic_passport, synthetic_id_td1,
                          render_passport_image, render_id_card_front,
                          render_id_card_back)
from kyc.face import _models_dir, YUNET_MODEL, SFACE_MODEL

FA = os.path.join("samples", "face_a.jpg")
FB = os.path.join("samples", "face_b.jpg")


def _face_ready():
    d = _models_dir()
    return (os.path.isfile(os.path.join(d, YUNET_MODEL))
            and os.path.isfile(os.path.join(d, SFACE_MODEL))
            and os.path.isfile(FA) and os.path.isfile(FB))


def _ocr_available():
    try:
        get_ocr_backend("tesseract")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _ocr_available(), reason="Tesseract/OCR indisponible")


def test_image_roundtrip_valid(tmp_path):
    mrz = synthetic_passport(expiry_date="300101")
    img_path = os.path.join(tmp_path, "passport.jpg")
    render_passport_image(mrz, img_path)

    report = verify_image(img_path, "Anna Maria Eriksson", ocr_backend="tesseract")
    assert report.mrz_parsed
    assert report.fields["surname"] == "ERIKSSON"
    assert report.name_match["label"] == "MATCH"
    assert report.status == "VALID"


def test_recto_verso_id_card(tmp_path):
    # Carte TD1 : MRZ au dos uniquement. verify_images doit la trouver.
    mrz = synthetic_id_td1(expiry_date="300101")
    front = os.path.join(tmp_path, "front.jpg")
    back = os.path.join(tmp_path, "back.jpg")
    render_id_card_front(front)
    render_id_card_back(mrz, back)

    report = verify_images([front, back], "Anna Maria Eriksson",
                           ocr_backend="tesseract")
    assert report.mrz_parsed
    assert report.mrz_format == "TD1"
    assert report.name_match["label"] == "MATCH"
    assert report.status == "VALID"


@pytest.mark.skipif(not _ocr_available() or not _face_ready(),
                    reason="OCR ou modèles/fixtures visage indisponibles")
def test_verify_documents_with_matching_selfie(tmp_path):
    mrz = synthetic_passport(expiry_date="300101")
    doc = os.path.join(tmp_path, "passport.jpg")
    render_passport_image(mrz, doc, face_path=FA)   # photo = face_a

    ok = verify_documents([doc], "Anna Maria Eriksson", selfie=FA,
                          ocr_backend="tesseract")
    assert ok.face_match is not None
    assert ok.face_match["match"] is True
    assert ok.status == "VALID"

    ko = verify_documents([doc], "Anna Maria Eriksson", selfie=FB,
                          ocr_backend="tesseract")
    assert ko.face_match["match"] is False
    assert ko.status == "REJECTED"     # visage non concordant -> rejet
