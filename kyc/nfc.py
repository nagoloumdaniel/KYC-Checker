"""Lecture NFC de la puce (ePassport / eID) — note d'architecture.

⚠️ La lecture de la puce NE PEUT PAS se faire depuis une image téléversée.
Elle nécessite :
1. un **lecteur NFC** (smartphone ou lecteur sans-contact) côté CLIENT ;
2. l'établissement d'un canal sécurisé avec la puce via **BAC** ou **PACE**
   (clé dérivée de la MRZ : n° doc + date naissance + date expiration) ;
3. la lecture des *Data Groups* (DG1 = MRZ, DG2 = photo, …) et du
   **Document Security Object (SOD)**.

La seule preuve cryptographique d'authenticité est la **Passive
Authentication** (PA), réalisable CÔTÉ SERVEUR une fois le SOD transmis :
- vérifier la signature CMS/PKCS#7 du SOD par le **Document Signer (DS)** ;
- vérifier que le certificat DS chaîne vers une **CSCA** de confiance
  (masterlist ICAO PKD du pays émetteur) ;
- vérifier que les empreintes des Data Groups lus correspondent à celles
  signées dans le SOD.

→ Architecture cible : une **app mobile** (NFC) lit la puce et POSTe le SOD +
les DG vers un endpoint serveur qui exécute `verify_passive_authentication`.
Ce module définit ce contrat ; l'implémentation complète requiert l'ASN.1 du
SOD (LDS) et une masterlist CSCA, hors périmètre du pipeline image actuel.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChipPayload:
    """Données transmises par le client NFC (mobile) au serveur."""
    sod_der: bytes                       # Document Security Object (DER)
    data_groups: dict = field(default_factory=dict)  # {1: bytes(DG1), 2: bytes(DG2), ...}


@dataclass
class PassiveAuthResult:
    authentic: bool
    ds_signature_valid: bool
    csca_chain_valid: bool
    data_group_hashes_valid: bool
    issuer_country: str | None = None
    details: list = field(default_factory=list)


def verify_passive_authentication(payload: ChipPayload,
                                  csca_trust_store) -> PassiveAuthResult:
    """Vérifie l'authenticité de la puce (Passive Authentication).

    NON IMPLÉMENTÉ dans cette phase : nécessite le parsing ASN.1 du SOD (LDS
    ICAO Doc 9303 partie 10/11) et une masterlist CSCA. À brancher quand l'app
    mobile NFC sera développée. Voir la docstring du module pour le flux.
    """
    raise NotImplementedError(
        "Passive Authentication non implémentée : nécessite un client NFC "
        "(mobile), le parsing ASN.1 du SOD et une masterlist CSCA. "
        "Voir kyc/nfc.py (note d'architecture)."
    )
