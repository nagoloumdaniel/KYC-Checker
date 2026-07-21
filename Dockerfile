# Image du moteur d'analyse KYC (API FastAPI + OpenCV + Tesseract).
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dépendances système : Tesseract (OCR) + libs runtime OpenCV headless.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1) Dépendances Python (couche cache séparée du code).
COPY requirements.txt requirements-image.txt requirements-api.txt ./
RUN pip install -r requirements.txt \
                -r requirements-image.txt \
                -r requirements-api.txt

# 2) Code applicatif + outils.
COPY kyc ./kyc
COPY tools ./tools

# 3) Modèle OCR-B pour la MRZ (auto-détecté via /app/tessdata).
RUN python tools/download_models.py

# Utilisateur non-root (bonne pratique de sécurité).
RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "kyc.api:app", "--host", "0.0.0.0", "--port", "8000"]
