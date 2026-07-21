# Intégration Next.js / TypeScript

Brancher le service KYC Checker dans une application **Next.js (App Router)**.

## Principe de sécurité

```text
Navigateur ──upload──> Route serveur Next (/api/kyc/verify) ──clé API──> Service KYC
```

La **clé d'API reste côté serveur** (route Next). Le navigateur ne la voit
jamais. Le SDK (`lib/kycClient.ts`) ne s'utilise donc que côté serveur
(route handlers, server actions).

## Fichiers à copier dans ton app

| Fichier | Destination dans ton app |
|---|---|
| `lib/kycClient.ts` | `lib/kycClient.ts` (SDK typé) |
| `app/api/kyc/verify/route.ts` | `app/api/kyc/verify/route.ts` (proxy serveur) |
| `app/kyc/page.tsx` | `app/kyc/page.tsx` (formulaire d'exemple) |
| `.env.local.example` | `.env.local` (puis renseigne les valeurs) |

> Le SDK utilise l'alias d'import `@/lib/kycClient`. Si ton `tsconfig.json` n'a
> pas `"paths": { "@/*": ["./*"] }`, ajuste les imports.

## Configuration (aucun changement de code au déploiement)

`.env.local` :

```bash
KYC_API_URL=http://localhost:8000   # local | http://kyc-api:8000 | https://kyc.tondomaine.com
KYC_API_KEY=                        # = une des clés de KYC_API_KEYS côté service
```

Changer d'environnement = changer ces deux variables. Le code reste identique.

## Lancer en local

```bash
# 1) Le service KYC (depuis ce dépôt)
docker run -d -p 8000:8000 -e KYC_API_KEYS=ma-cle kyc-checker:latest
# 2) Ton app Next.js
#    .env.local : KYC_API_URL=http://localhost:8000  KYC_API_KEY=ma-cle
npm run dev
# 3) Ouvre http://localhost:3000/kyc
```

## Utiliser le SDK côté serveur (server action / route)

```ts
import { KycClient } from "@/lib/kycClient";

const kyc = new KycClient();                 // lit KYC_API_URL / KYC_API_KEY
const report = await kyc.verifyMrz(mrzText, "Anna Maria Eriksson");
if (report.status === "VALID") { /* ... */ }

// Recherche d'un dossier archivé
const { records } = await kyc.searchRecords({ name: "Anna Eriksson" });
```

## Déploiement combiné (optionnel)

Voir `docker-compose.example.yml` : lance le service KYC et ton app sur le même
réseau Docker (l'app appelle `http://kyc-api:8000`, le service n'est pas exposé
publiquement).

## Rappels

- Le service traite les images **en mémoire** ; n'ajoute pas de stockage non
  chiffré côté Next.
- `face_match` et `forensics` ne sont renseignés que si pertinents (selfie
  fourni / couche image active).
- La comparaison de visage **n'est pas** un test de vivacité.
