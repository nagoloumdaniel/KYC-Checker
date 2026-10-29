# Contribuer

Projet en cours : les issues et pull requests sont bienvenues, mais aucune licence n'est encore accordée (voir le [README](README.md#droits)).

1. Créez une branche depuis `main` : `feat/...`, `fix/...`, `docs/...`.
2. Installez les dépendances et lancez les tests :
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-image.txt -r requirements-api.txt -r requirements-storage.txt -r requirements-dev.txt httpx
   .\.venv\Scripts\python.exe -m pytest -q
   ```
3. Ajoutez un test pour tout changement de comportement.
4. Commits conventionnels en anglais (`feat:`, `fix:`, `docs:`), puis ouvrez une pull request.

**Données** : uniquement des spécimens synthétiques. Jamais de vraie pièce d'identité, de selfie réel, de clé ou de fichier `.env`.
**Sécurité** : voir [SECURITY.md](SECURITY.md).
