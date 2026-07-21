"""Comparaison de visages (photo de la pièce vs selfie).

Utilise les modèles intégrés à OpenCV (aucune dépendance lourde supplémentaire) :
- **YuNet**  (FaceDetectorYN)    : détection + 5 points caractéristiques.
- **SFace**  (FaceRecognizerSF)  : embedding 128-D + similarité cosinus.

Modèles ONNX (OpenCV Zoo) attendus dans ./models/ (voir tools/download_models.py).

Limite : la comparaison de visages n'est PAS une preuve de vivacité (liveness).
Une photo d'une photo peut tromper ce contrôle — la détection d'attaque par
présentation nécessite un capteur/algorithme dédié, hors de portée d'une image.
"""

from __future__ import annotations

import os

import cv2
import numpy as np

YUNET_MODEL = "face_detection_yunet_2023mar.onnx"
SFACE_MODEL = "face_recognition_sface_2021dec.onnx"

# Seuil cosinus recommandé par OpenCV pour « même personne » (SFace).
DEFAULT_COSINE_THRESHOLD = 0.363

_recognizer = None
_detector = None


def _models_dir() -> str:
    env = os.environ.get("KYC_MODELS_DIR")
    if env:
        return env
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "models")


def _model_path(name: str) -> str:
    path = os.path.join(_models_dir(), name)
    if not os.path.isfile(path):
        raise FileNotFoundError(
            f"Modèle visage absent : {path}. "
            f"Lance `python tools/download_models.py`.")
    return path


def _get_detector():
    global _detector
    if _detector is None:
        _detector = cv2.FaceDetectorYN_create(
            _model_path(YUNET_MODEL), "", (320, 320),
            score_threshold=0.7, nms_threshold=0.3, top_k=5000)
    return _detector


def _get_recognizer():
    global _recognizer
    if _recognizer is None:
        _recognizer = cv2.FaceRecognizerSF_create(_model_path(SFACE_MODEL), "")
    return _recognizer


def _load_bgr(source) -> np.ndarray:
    if isinstance(source, np.ndarray):
        return source
    if isinstance(source, (bytes, bytearray)):
        img = cv2.imdecode(np.frombuffer(bytes(source), np.uint8), cv2.IMREAD_COLOR)
    else:  # chemin
        img = cv2.imread(source)
    if img is None:
        raise ValueError("Image visage illisible.")
    return img


def detect_faces(image) -> np.ndarray | None:
    """Retourne le tableau des visages détectés (Nx15) ou None."""
    img = _load_bgr(image)
    h, w = img.shape[:2]
    det = _get_detector()
    det.setInputSize((w, h))
    _, faces = det.detect(img)
    return faces if faces is not None and len(faces) else None


def get_embedding(image) -> np.ndarray | None:
    """Embedding 128-D du plus grand visage, ou None si aucun visage."""
    img = _load_bgr(image)
    faces = detect_faces(img)
    if faces is None:
        return None
    # Plus grand visage (aire bbox = w*h).
    face = max(faces, key=lambda f: float(f[2]) * float(f[3]))
    rec = _get_recognizer()
    aligned = rec.alignCrop(img, face)
    return rec.feature(aligned)


def match_faces(document_image, selfie_image,
                cosine_threshold: float = DEFAULT_COSINE_THRESHOLD) -> dict:
    """Compare le visage de la pièce et celui du selfie.

    Renvoie : { match: bool, score: float|None (cosinus), faces: {...},
                threshold, error? }
    """
    emb_doc = get_embedding(document_image)
    emb_selfie = get_embedding(selfie_image)
    faces = {"document": emb_doc is not None, "selfie": emb_selfie is not None}

    if emb_doc is None or emb_selfie is None:
        missing = [k for k, v in faces.items() if not v]
        return {"match": False, "score": None, "faces": faces,
                "threshold": cosine_threshold,
                "error": "Visage non détecté : " + ", ".join(missing)}

    rec = _get_recognizer()
    cosine = rec.match(emb_doc, emb_selfie, cv2.FaceRecognizerSF_FR_COSINE)
    return {
        "match": bool(cosine >= cosine_threshold),
        "score": round(float(cosine), 4),
        "faces": faces,
        "threshold": cosine_threshold,
    }
