# KYC Checker

![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-5C3EE8?logo=opencv&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript%20SDK-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?logo=pytest&logoColor=white)

> Moteur de vérification de pièces d'identité (MRZ, correspondance de nom, comparaison de visage) exposé via une API FastAPI, avec archivage chiffré et SDK TypeScript.

## Description

KYC Checker lit et valide la **MRZ** des pièces d'identité (passeports TD3, cartes d'identité TD1, pièces TD2, norme ICAO Doc 9303), effectue un **rapprochement du nom** par similarité floue (Jaro-Winkler) et une **comparaison de visage** (selfie vs photo de la pièce, OpenCV YuNet + SFace). Les dossiers peuvent être **archivés chiffrés** (AES-256-GCM) avec journal d'audit.

> ⚠️ **Portée et limites.** Ce module vérifie la *cohérence interne* d'un document (clés de contrôle MRZ) et la *correspondance du nom/visage*. Il ne certifie **pas** l'authenticité physique de la pièce : un faux document avec des clés MRZ correctes passera le contrôle. La seule preuve forte d'authenticité serait la lecture de la puce NFC (ePassport), hors de portée d'une analyse d'image seule.

## Fonctionnalités clés

- **Lecture et validation MRZ** — formats TD1/TD2/TD3, détection automatique, correction d'erreurs OCR courantes, vérification des clés de contrôle.
- **Correspondance de nom** — similarité floue (Jaro-Winkler, implémentation pure Python), classée MATCH / PARTIAL / NO_MATCH.
- **Comparaison de visage** — OpenCV YuNet (détection) + SFace (embedding), seuil cosinus configurable ; rejette un selfie qui ne correspond pas à la photo de la pièce.
- **Contrôles qualité / forensique image** — résolution, netteté (flou), détection ELA expérimentale ; signaux d'aide à la revue, pas une preuve de fraude.
- **Archivage chiffré** — coffre AES-256-GCM (chiffrement par enveloppe), index SQLite sans PII en clair (tokens HMAC), purge automatique par rétention.
- **Journal d'audit** — traçabilité des accès aux dossiers archivés (consultation, acteur, date).
- **Scoring et décision** — VALID / SUSPECT / REJECTED, seuils et règles de plafonnement centralisés et réglables.
- **CLI** — démonstration, vérification par MRZ, image(s) ou image + selfie.

## Stack technique

| Composant | Rôle |
|---|---|
| Python 3.11+ | Langage principal |
| `mrz` | Parsing et validation des clés de contrôle MRZ (seule dépendance du cœur) |
| FastAPI + Uvicorn | API HTTP |
| OpenCV (headless) + modèles ONNX (YuNet/SFace) | Détection et comparaison de visage, localisation de la bande MRZ |
| Tesseract / EasyOCR | OCR de la MRZ sur image |
| `cryptography` | Archivage chiffré AES-256-GCM |
| SQLite (stdlib) | Index des dossiers archivés |
| TypeScript / Next.js | SDK client + exemple d'intégration |
| pytest | Tests automatisés |
| Docker | Conteneurisation de l'API |

Le **cœur** (MRZ, matching de nom, scoring) ne dépend que de la librairie `mrz`. Les couches image/OCR, API et archivage sont optionnelles et chargées à la demande.

## Documentation de l'API

FastAPI expose automatiquement un schéma OpenAPI et une UI interactive une fois le serveur lancé en local :

- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`
- Schéma brut : `http://localhost:8000/openapi.json`

| Endpoint | Description |
|---|---|
| `GET /health` | État du service, version, disponibilité OCR, auth activée ou non |
| `POST /verify-mrz` | JSON `{mrz_text, name}` → rapport (sans image) |
| `POST /verify` | Multipart `name` + 1-2 images (recto/verso), `selfie` et `archive` optionnels → rapport |
| `GET /records` | Recherche de dossiers archivés (métadonnées uniquement, sans PII en clair) |

Les images sont traitées **en mémoire** (jamais écrites sur disque), validées par signature (JPEG/PNG), limitées à 8 Mo et 2 images max.

### Authentification

Auth par **clé d'API**, activée dès que la variable d'environnement `KYC_API_KEYS` est définie (liste de clés séparées par des virgules). `/health` reste public ; `/verify`, `/verify-mrz` et `/records` exigent alors une clé via l'en-tête `X-API-Key` ou `Authorization: Bearer <clé>`. Sans `KYC_API_KEYS`, l'authentification est désactivée (mode développement).

## Installation et lancement local

```powershell
py -V:3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt          # cœur
.\.venv\Scripts\python.exe -m pip install -r requirements-image.txt    # image/OCR
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt      # API
.\.venv\Scripts\python.exe -m pip install -r requirements-storage.txt  # archivage

# Binaire Tesseract (Windows) :
winget install --id UB-Mannheim.TesseractOCR -e --silent
# Modèle OCR-B pour la MRZ (le modèle 'eng' par défaut lit mal le caractère '<') :
.\.venv\Scripts\python.exe tools\download_models.py
```

Lancer l'API :

```powershell
.\.venv\Scripts\python.exe -m uvicorn kyc.api:app --host 0.0.0.0 --port 8000
```

Variables d'environnement principales (sans valeurs secrètes réelles) :

| Variable | Rôle |
|---|---|
| `KYC_API_KEYS` | Active l'authentification par clé d'API (liste séparée par des virgules) |
| `KYC_ARCHIVE_DIR` | Dossier racine du coffre d'archivage (défaut : `archive`) |
| `KYC_MASTER_KEY` | Clé maître base64 pour le chiffrement (sinon fichier `.master.key` généré en dev) |

### Docker

```powershell
docker build -t kyc-checker:latest .
docker run -d -p 8000:8000 kyc-checker:latest
# ou
docker compose up --build
```

L'image embarque Tesseract, OpenCV headless et le modèle OCR-B (~2 Go de RAM recommandés).

### CLI

```powershell
$env:PYTHONUTF8="1"
python -m kyc demo                      # passeport cohérent      -> VALIDÉ
python -m kyc demo --format td1         # carte d'identité (TD1)  -> VALIDÉ
python -m kyc demo --tamper             # clé MRZ falsifiée       -> SUSPECT
python -m kyc demo --wrong-name         # nom non concordant      -> REJETÉ

python -m kyc verify --name "Anna Eriksson" --mrz "<ligne1>\n<ligne2>"
python -m kyc verify --name "Anna Eriksson" --image passeport.jpg
python -m kyc verify --name "Anna Eriksson" --image recto.jpg --image verso.jpg
python -m kyc verify --name "Anna Eriksson" --image passeport.jpg --selfie selfie.jpg
```

### Librairie Python

```python
from kyc import verify_from_mrz, verify_images

report = verify_from_mrz(mrz_text, expected_name="Anna Maria Eriksson")
print(report.status, report.score, report.mrz_format)   # VALID 100.0 TD3

report = verify_images(["recto.jpg", "verso.jpg"], "Anna Eriksson")  # CNI
```

### Archivage chiffré

```python
from kyc.storage import Vault, StorageConfig

vault = Vault(StorageConfig(root="archive", retention_days=1825))
rid = vault.store(name="Anna Maria Eriksson", report=report,
                  images=[recto_bytes, verso_bytes], registration_date="2026-06-06")
vault.search(name="anna eriksson")          # recherche par jeton HMAC (pas de PII en clair)
vault.retrieve(rid, actor="agent_litige")   # déchiffre (accès tracé dans le journal d'audit)
vault.purge_expired()                        # purge selon la rétention configurée
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

50 tests couvrant la MRZ, le matching de nom, le pipeline, la comparaison de visage, la forensique, l'API et l'archivage (`tests/`). Les tests des couches optionnelles (image/API/stockage) se *skippent* proprement si la dépendance correspondante est absente.

## SDK TypeScript (intégration Next.js)

Un SDK client typé, un proxy serveur (la clé d'API reste côté serveur) et un formulaire d'exemple sont fournis dans [`integration/nextjs/`](integration/nextjs/) :

```ts
import { KycClient } from "@/lib/kycClient";

const report = await new KycClient().verifyMrz(mrzText, "Anna Maria Eriksson");
```

Configuration par variables d'environnement (`KYC_API_URL`, `KYC_API_KEY`) : fonctionne en local et se déploie ailleurs sans changement de code. Voir [`integration/nextjs/README.md`](integration/nextjs/README.md) pour le détail (route API Next.js, page d'exemple, docker-compose).

## Décision

| Signal | Effet |
|---|---|
| MRZ illisible | **REJETÉ** |
| Nom NO_MATCH | **REJETÉ** |
| Clé de contrôle MRZ invalide | plafond **SUSPECT** |
| Nom PARTIAL | plafond **SUSPECT** |
| Document expiré | plafond **SUSPECT** |
| Selfie ≠ photo de la pièce | **REJETÉ** |
| Indice de retouche (forensique) | plafond **SUSPECT** |
| Tout cohérent, nom MATCH, visage OK, non expiré | **VALIDÉ** |

Tous les seuils sont centralisés dans [`kyc/config.py`](kyc/config.py).

## Architecture du code

```text
kyc/
  names.py        Normalisation + matching flou de noms (Jaro-Winkler, pur Python)
  mrz_reader.py   MRZ TD1/TD2/TD3 : détection format, validation, correction OCR
  scoring.py      Score + décision (VALID / SUSPECT / REJECTED) + règles dures
  pipeline.py     Orchestrateurs : verify_from_mrz / verify_image(s)[_bytes] / verify_documents
  specimens.py    Spécimens synthétiques + rendu d'images de test
  config.py       Seuils réglables
  imaging.py      [opt] OpenCV : localisation de la bande MRZ (fichier ou bytes)
  ocr.py          [opt] Backends OCR (Tesseract + modèle OCR-B / EasyOCR)
  face.py         [opt] Détection/comparaison de visage (OpenCV YuNet + SFace)
  forensics.py    [opt] Contrôles qualité image + heuristiques de falsification
  api.py          [opt] API FastAPI (/health, /verify, /verify-mrz, /records)
  storage.py      [opt] Coffre chiffré AES-256-GCM + index SQLite + audit
  nfc.py          Note d'architecture (lecture puce ePassport, non implémentée)
  cli.py          Interface ligne de commande
```

## Feuille de route

- [x] Passeports (MRZ TD3) + validation clés + matching nom + CLI.
- [x] Cartes d'identité (TD1/TD2), recto/verso.
- [x] API FastAPI (`/verify`) + Docker.
- [x] Archivage chiffré (AES-256-GCM) + index + journal d'audit.
- [x] Comparaison de visage (selfie/photo) + heuristiques de falsification. NFC documenté (nécessite un client mobile, non implémenté).
- [x] Authentification API par clé (`KYC_API_KEYS`).
- [ ] PDF en entrée, KMS en production, client NFC, rate-limiting.

---

Développé par [Daniel Nagoloum Talla](https://github.com/nagoloumdaniel) — [portfolio](https://nagoloum.vercel.app)
