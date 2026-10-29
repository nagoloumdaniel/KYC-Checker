# Politique de sécurité

Ce projet est un **prototype** : il ne doit pas traiter de vraies données personnelles en production (voir les limites du [README](README.md#limites)).

## Signaler une vulnérabilité

- **Faille sensible** : utilisez le signalement privé GitHub (onglet *Security* > *Report a vulnerability*) de ce dépôt. N'ouvrez pas d'issue publique.
- **Problème non sensible** (durcissement, dépendance obsolète sans exploitation connue) : ouvrez une issue normale.

Ne joignez jamais de vraie pièce d'identité, de clé d'API ni de clé maître : utilisez uniquement des spécimens synthétiques (`python -m kyc demo`, `tools/make_specimen.py`).

Il s'agit d'un projet personnel : aucun délai de réponse n'est garanti.

## Limites connues (déjà documentées)

Authentification désactivée si `KYC_API_KEYS` est absent, pas de rate limiting, clé maître en fichier en développement, pas de liveness, NFC non implémenté.
