"""Tests des heuristiques forensiques (contrôles qualité fiables + ELA info)."""

import pytest

cv2 = pytest.importorskip("cv2")
import numpy as np

from kyc.forensics import analyze_image


def _sharp_image(w=800, h=500):
    img = np.full((h, w, 3), 230, dtype=np.uint8)
    for x in range(0, w, 20):           # rayures nettes -> Laplacien élevé
        img[:, x:x + 2] = 20
    return img


def test_metrics_present_and_clean_not_suspicious():
    r = analyze_image(_sharp_image())
    for key in ("width", "height", "blur_var", "too_blurry",
                "low_resolution", "tampering_score", "suspicious"):
        assert key in r
    assert r["too_blurry"] is False
    assert r["low_resolution"] is False
    assert r["suspicious"] is False     # image propre -> pas de faux positif


def test_low_resolution_flag():
    r = analyze_image(np.full((100, 100, 3), 200, dtype=np.uint8))
    assert r["low_resolution"] is True


def test_blurry_flag():
    blurred = cv2.GaussianBlur(_sharp_image(), (31, 31), 0)
    r = analyze_image(blurred)
    assert r["too_blurry"] is True
