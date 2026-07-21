"""Tests de la comparaison de visages (OpenCV YuNet + SFace).

Nécessite les modèles ONNX (tools/download_models.py). Les tests de match
positif/négatif nécessitent en plus des fixtures visages dans samples/
(face_a.jpg, face_b.jpg) — sinon ils se *skippent*.
"""

import os

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np

from kyc.face import match_faces, YUNET_MODEL, SFACE_MODEL, _models_dir

FA = os.path.join("samples", "face_a.jpg")
FB = os.path.join("samples", "face_b.jpg")


def _models_present():
    d = _models_dir()
    return (os.path.isfile(os.path.join(d, YUNET_MODEL))
            and os.path.isfile(os.path.join(d, SFACE_MODEL)))


def _faces_present():
    return os.path.isfile(FA) and os.path.isfile(FB)


pytestmark = pytest.mark.skipif(not _models_present(),
                                reason="modèles visage absents")


def test_no_face_is_graceful():
    flat = np.full((200, 200, 3), 127, dtype=np.uint8)
    r = match_faces(flat, flat)
    assert r["match"] is False
    assert r["score"] is None
    assert "error" in r


@pytest.mark.skipif(not _faces_present(), reason="fixtures visages absentes")
def test_self_match_is_high():
    r = match_faces(FA, FA)
    assert r["match"] is True
    assert r["score"] > 0.9


@pytest.mark.skipif(not _faces_present(), reason="fixtures visages absentes")
def test_different_people_do_not_match():
    r = match_faces(FA, FB)
    assert r["match"] is False
    assert r["score"] < r["threshold"]
