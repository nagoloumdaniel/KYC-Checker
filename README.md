# KYC Checker

Moteur de vérification de pièces d'identité : lecture et **validation de la MRZ**
(norme ICAO Doc 9303), **rapprochement du nom** avec un nom attendu,
**comparaison de visage** (selfie vs photo de la pièce), API HTTP, et
**archivage chiffré** des dossiers.

Formats gérés : **passeports (TD3)**, **cartes d'identité (TD1)**, **pièces ID-2 (TD2)**
— couverture internationale via la MRZ.

> ⚠️ **Portée et limites.** Ce module vérifie la *cohérence interne* d'un
> document (clés de contrôle MRZ) et la *correspondance du nom*. Il ne
> certifie **pas** l'authenticité physique : une fausse pièce avec des clés
> MRZ correctes passera le contrôle. La seule preuve forte d'authenticité est
> la lecture de la puce NFC (ePassport), hors de portée d'une simple image.
> Considère ce module comme un **filtre anti-fraude grossière + extraction
> fiable + matching de nom**, pas comme un certificat d'authenticité.

## Architecture

```text
kyc/
  names.py        Normalisation + matching flou de noms (Jaro-Winkler, pur Python)
  mrz_reader.py   MRZ TD1/TD2/TD3 : détection format, validation, correction OCR
  scoring.py      Score + décision (VALID / SUSPECT / REJECTED) + règles dures
  pipeline.py     Orchestrateurs : verify_from_mrz / verify_image(s)[_bytes]
  specimens.py    Spécimens synthétiques + rendu d'images de test
  config.py       Seuils réglables
  imaging.py      [opt] OpenCV : localisation de la bande MRZ (fichier ou bytes)
  ocr.py          [opt] Backends OCR (Tesseract + modèle OCR-B / EasyOCR)
  api.py          [opt] API FastAPI (/health, /verify, /verify-mrz, /records)
  storage.py      [opt] Coffre chiffré AES-256-GCM + index SQLite + audit
  cli.py          Interface ligne de commande
```

Le **cœur** (matching, MRZ, scoring) ne dépend que de `mrz`. Les couches
image/OCR, API et stockage sont optionnelles et chargées paresseusement.

## Installation

```powershell
py -V:3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt          # cœur
.\.venv\Scripts\python.exe -m pip install -r requirements-image.txt    # image/OCR
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt      # API
.\.venv\Scripts\python.exe -m pip install -r requirements-storage.txt  # archivage

# Binaire Tesseract (Windows) :
winget install --id UB-Mannheim.TesseractOCR -e --silent
# Modèle OCR-B pour la MRZ (le modèle 'eng' lit mal le '<') :
.\.venv\Scripts\python.exe tools\download_models.py
```

## CLI

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
python -m kyc --json demo
```

## Librairie

```python
from kyc import verify_from_mrz, verify_image, verify_images

report = verify_from_mrz(mrz_text, expected_name="Anna Maria Eriksson")
print(report.status, report.score, report.mrz_format)   # VALID 100.0 TD3
report = verify_images(["recto.jpg", "verso.jpg"], "Anna Eriksson")  # CNI
```

## API HTTP (FastAPI)

```powershell
.\.venv\Scripts\python.exe -m uvicorn kyc.api:app --host 0.0.0.0 --port 8000
```

| Endpoint | Description |
|---|---|
| `GET /health` | état + version + disponibilité OCR |
| `POST /verify-mrz` | JSON `{mrz_text, name}` → rapport |
| `POST /verify` | multipart `name` + 1-2 images, `selfie` & `archive` optionnels → rapport |
| `GET /records` | recherche de dossiers archivés (métadonnées, sans PII en clair) |

Les images sont traitées **en mémoire** (jamais écrites sur disque). Validation
des uploads par signature (JPEG/PNG), limite 8 Mo, max 2 images.

### Authentification

Auth par **clé d'API**, activée dès que `KYC_API_KEYS` est défini (liste
séparée par des virgules). `/health` reste public ; `/verify`, `/verify-mrz`
et `/records` exigent alors une clé :

```powershell
$env:KYC_API_KEYS = "ma-cle-secrete,une-autre"
# Appels : en-tête  X-API-Key: ma-cle-secrete   OU   Authorization: Bearer ma-cle-secrete
```

Sans `KYC_API_KEYS`, l'auth est désactivée (dev) — `/health` l'indique via
`auth_enabled`. En production, définis toujours des clés.

### Intégration Next.js / TypeScript

Un SDK typé + un proxy serveur (la clé d'API reste côté serveur) + un
formulaire d'exemple sont fournis dans [`integration/nextjs/`](integration/nextjs/) :

```ts
import { KycClient } from "@/lib/kycClient";
const report = await new KycClient().verifyMrz(mrzText, "Anna Maria Eriksson");
```

Config par env (`KYC_API_URL`, `KYC_API_KEY`) : marche en local et se déploie
ailleurs sans changement de code. Voir [`integration/nextjs/README.md`](integration/nextjs/README.md).

## Docker

```powershell
docker build -t kyc-checker:latest .
docker run -d -p 8000:8000 kyc-checker:latest
# ou
docker compose up --build
```

L'image embarque Tesseract, OpenCV headless et le modèle OCR-B. ~2 Go de RAM
recommandés.

## Archivage chiffré

```python
from kyc.storage import Vault, StorageConfig
vault = Vault(StorageConfig(root="archive", retention_days=1825))
rid = vault.store(name="Anna Maria Eriksson", report=report,
                  images=[recto_bytes, verso_bytes], registration_date="2026-06-06")
vault.search(name="anna eriksson")          # par jeton HMAC (pas de PII en clair)
vault.retrieve(rid, actor="agent_litige")   # déchiffre (accès tracé)
vault.purge_expired()                        # rétention
```

- **Chiffrement par enveloppe AES-256-GCM** (authentifié → inviolabilité).
- **Aucune PII en clair** : nom/numéro indexés par jetons HMAC.
- **Journal d'audit** de tous les accès. **Purge** automatique par rétention.
- Clé maître via `KYC_MASTER_KEY` (base64) ou fichier `.master.key` (dev).
  En production : utiliser un KMS.

## Comparaison de visage & forensique (Phase 5)

```python
from kyc.pipeline import verify_documents
report = verify_documents(["passeport.jpg"], "Anna Eriksson", selfie="selfie.jpg")
print(report.face_match)   # {match, score (cosinus), faces, threshold}
print(report.forensics)    # {blur_var, low_resolution, ela_*, suspicious, ...}
```

- **Face-matching** (OpenCV YuNet + SFace) : compare le selfie à la photo de
  la pièce ; un visage non concordant rejette le dossier. Modèles ONNX
  téléchargés par `tools/download_models.py`.
- **Forensique** : contrôles qualité *fiables* (résolution, netteté) + ELA
  *expérimental*. ⚠️ Signaux d'aide à la revue, **pas une preuve** de fraude.
- **NFC** (puce ePassport) : **hors pipeline image** — nécessite un client
  mobile NFC. Voir la note d'architecture dans [`kyc/nfc.py`](kyc/nfc.py).

> ⚠️ La comparaison de visage n'est **pas** un test de vivacité (liveness) :
> une photo d'une photo peut tromper ce contrôle.

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

Tous les seuils sont dans [`kyc/config.py`](kyc/config.py).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q          # 48 tests
```

Les tests image/API/stockage se *skippent* proprement si une couche optionnelle
est absente.

## Feuille de route

- [x] **Phase 1** — Passeports (MRZ TD3) + validation clés + matching nom + CLI.
- [x] **Phase 2** — Cartes d'identité (TD1/TD2), recto/verso.
- [x] **Phase 3** — API FastAPI (`/verify`) + Docker.
- [x] **Phase 4** — Archivage chiffré (AES-256-GCM) + index + journal d'audit.
- [x] **Phase 5** — Face-matching (selfie/photo) + heuristiques de falsification.
      NFC documenté (nécessite un client mobile, non implémenté).
- [x] **Auth API** — clé d'API (`KYC_API_KEYS`).
- [ ] PDF en entrée ; KMS en production ; client NFC ; rate-limiting.
