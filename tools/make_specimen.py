"""Génère des images de pièces synthétiques pour tester le chemin image.

    python tools/make_specimen.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kyc.specimens import (synthetic_passport, synthetic_id_td1,
                          render_passport_image, render_id_card_front,
                          render_id_card_back)

os.makedirs("samples", exist_ok=True)

render_passport_image(synthetic_passport(), "samples/specimen_passport.jpg")
print("Passeport      : samples/specimen_passport.jpg")

td1 = synthetic_id_td1()
render_id_card_front("samples/specimen_cni_recto.jpg")
render_id_card_back(td1, "samples/specimen_cni_verso.jpg")
print("CNI recto      : samples/specimen_cni_recto.jpg (sans MRZ)")
print("CNI verso      : samples/specimen_cni_verso.jpg (MRZ TD1)")
