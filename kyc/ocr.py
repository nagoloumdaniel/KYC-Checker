"""Abstraction du moteur OCR (couche optionnelle).

Deux backends interchangeables :
- TesseractBackend : léger, nécessite le binaire Tesseract installé sur le
  système + le paquet `pytesseract`. Idéal pour la MRZ (police OCR-B).
- EasyOCRBackend   : pip-only (tire PyTorch), plus lourd en RAM.

Le choix 'auto' prend le premier disponible. Les imports sont paresseux :
importer ce module ne tire aucune dépendance lourde tant qu'on n'instancie
pas un backend.
"""

from __future__ import annotations

# Caractères autorisés dans une MRZ (police OCR-B).
MRZ_WHITELIST = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"


class OCRBackend:
    name = "base"

    def read_mrz(self, image) -> str:
        """Retourne le texte brut OCR d'une image de zone MRZ (np.ndarray)."""
        raise NotImplementedError


def _resolve_tesseract_cmd() -> str | None:
    """Localise le binaire Tesseract : variable d'env, PATH, puis chemins
    d'installation Windows courants."""
    import os
    import shutil

    env = os.environ.get("KYC_TESSERACT_CMD")
    if env and os.path.isfile(env):
        return env
    on_path = shutil.which("tesseract")
    if on_path:
        return on_path
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ):
        if os.path.isfile(candidate):
            return candidate
    return None


def _resolve_ocrb_tessdata() -> str | None:
    """Cherche un dossier tessdata contenant le modèle OCR-B (ocrb.traineddata),
    bien plus fiable que 'eng' pour la MRZ (caractère '<' notamment)."""
    import os

    candidates = []
    env = os.environ.get("KYC_TESSDATA_DIR")
    if env:
        candidates.append(env)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(project_root, "tessdata"))
    for d in candidates:
        if d and os.path.isfile(os.path.join(d, "ocrb.traineddata")):
            return d
    return None


class TesseractBackend(OCRBackend):
    name = "tesseract"

    def __init__(self, lang: str | None = None, tessdata_dir: str | None = None):
        import pytesseract  # échoue tôt si le paquet est absent
        cmd = _resolve_tesseract_cmd()
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        # Vérifie que le binaire répond (sinon erreur claire en amont).
        pytesseract.get_tesseract_version()
        self._pt = pytesseract

        # Modèle OCR-B si disponible, sinon anglais standard.
        self.tessdata_dir = tessdata_dir or _resolve_ocrb_tessdata()
        if lang:
            self.lang = lang
        else:
            self.lang = "ocrb" if self.tessdata_dir else "eng"

    def read_mrz(self, image) -> str:
        import os
        # On passe par TESSDATA_PREFIX (et non --tessdata-dir) car pytesseract
        # découpe la config sur les espaces, ce qui casse les chemins espacés.
        if self.tessdata_dir:
            os.environ["TESSDATA_PREFIX"] = self.tessdata_dir
        config = f"--psm 6 --oem 1 -c tessedit_char_whitelist={MRZ_WHITELIST}"
        return self._pt.image_to_string(image, lang=self.lang, config=config)


class EasyOCRBackend(OCRBackend):
    name = "easyocr"

    def __init__(self, languages=("en",)):
        import easyocr
        # gpu=False pour rester compatible CPU / faible RAM.
        self._reader = easyocr.Reader(list(languages), gpu=False)

    def read_mrz(self, image) -> str:
        results = self._reader.readtext(
            image, detail=0, allowlist=MRZ_WHITELIST, paragraph=False)
        return "\n".join(results)


def get_ocr_backend(name: str = "auto") -> OCRBackend:
    """Instancie un backend OCR. 'auto' = premier disponible."""
    name = (name or "auto").lower()

    if name == "tesseract":
        return TesseractBackend()
    if name == "easyocr":
        return EasyOCRBackend()
    if name == "auto":
        errors = []
        for factory in (TesseractBackend, EasyOCRBackend):
            try:
                return factory()
            except Exception as exc:  # dépendance/binaire absent
                errors.append(f"{factory.__name__}: {exc}")
        raise RuntimeError(
            "Aucun moteur OCR disponible. Installe Tesseract (+ pytesseract) "
            "ou easyocr.\nDétails : " + " | ".join(errors)
        )
    raise ValueError(f"Backend OCR inconnu : {name!r}")
