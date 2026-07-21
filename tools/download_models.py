"""Télécharge les modèles nécessaires :
- OCR-B (MRZ) dans ./tessdata/  — le modèle 'eng' lit mal le '<' des MRZ ;
- YuNet + SFace (visage) dans ./models/  — comparaison selfie/pièce (Phase 5).

    python tools/download_models.py
"""
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DOWNLOADS = [
    ("tessdata", "ocrb.traineddata", 1_000_000,
     "https://github.com/Shreeshrii/tessdata_ocrb/raw/master/ocrb.traineddata"),
    ("models", "face_detection_yunet_2023mar.onnx", 100_000,
     "https://github.com/opencv/opencv_zoo/raw/main/models/"
     "face_detection_yunet/face_detection_yunet_2023mar.onnx"),
    ("models", "face_recognition_sface_2021dec.onnx", 1_000_000,
     "https://github.com/opencv/opencv_zoo/raw/main/models/"
     "face_recognition_sface/face_recognition_sface_2021dec.onnx"),
]

for subdir, name, min_size, url in DOWNLOADS:
    dest_dir = os.path.join(ROOT, subdir)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    if os.path.isfile(dest) and os.path.getsize(dest) > min_size:
        print(f"Déjà présent : {subdir}/{name}")
        continue
    print(f"Téléchargement de {subdir}/{name} ...")
    urllib.request.urlretrieve(url, dest)
    print(f"  OK ({os.path.getsize(dest) / 1_048_576:.1f} Mo)")
