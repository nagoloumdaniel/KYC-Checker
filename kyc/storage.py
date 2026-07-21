"""Coffre d'archivage chiffré des dossiers KYC.

Objectifs (cf. besoin « consultable en cas de souci avec l'utilisateur ») :
- **Chiffrement au repos** par enveloppe AES-256-GCM. Le GCM est *authentifié* :
  toute altération d'un octet est détectée (preuve d'intégrité).
- **Aucune donnée personnelle en clair** : le nom et le numéro de document ne
  sont jamais stockés en clair. L'index est recherchable via des *jetons* HMAC
  (recherche par égalité sans exposer la valeur).
- **Index SQLite** : récupération par nom + numéro + date d'inscription.
- **Journal d'audit** : trace des accès (stockage, recherche, consultation).
- **Rétention** : purge automatique passé un délai configurable.

Modèle de clés (enveloppe) :
    clé maître (32 o, env KYC_MASTER_KEY ou fichier) ──chiffre──> DEK par dossier
    DEK ──chiffre──> images + rapport (AAD = record_id)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .names import tokens


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _name_key(name: str) -> str:
    """Forme canonique du nom, indépendante de l'ordre/casse/accents."""
    return " ".join(sorted(tokens(name)))


def _docnum_key(document_number: str) -> str:
    return "".join(c for c in (document_number or "").upper() if c.isalnum())


@dataclass(frozen=True)
class StorageConfig:
    root: str = "archive"
    retention_days: int = 1825   # 5 ans (recommandation LCB-FT courante)


class IntegrityError(Exception):
    """Levée si un blob déchiffré échoue à la vérification d'intégrité GCM."""


class Vault:
    def __init__(self, config: StorageConfig | None = None,
                 master_key: bytes | None = None):
        self.cfg = config or StorageConfig()
        os.makedirs(self.cfg.root, exist_ok=True)
        self._master = master_key or _resolve_master_key(self.cfg.root)
        if len(self._master) != 32:
            raise ValueError("La clé maître doit faire 32 octets (AES-256).")
        self._db_path = os.path.join(self.cfg.root, "index.db")
        self._init_db()

    # ----------------------------------------------------------------- DB --
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS records (
                    record_id        TEXT PRIMARY KEY,
                    name_token       TEXT NOT NULL,
                    docnum_token     TEXT NOT NULL,
                    registration_date TEXT NOT NULL,
                    created_at       TEXT NOT NULL,
                    retention_until  TEXT NOT NULL,
                    doc_type         TEXT,
                    country          TEXT,
                    mrz_format       TEXT,
                    status           TEXT,
                    score            REAL,
                    image_count      INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_name   ON records(name_token);
                CREATE INDEX IF NOT EXISTS idx_docnum ON records(docnum_token);
                CREATE INDEX IF NOT EXISTS idx_date   ON records(registration_date);
                CREATE TABLE IF NOT EXISTS audit_log (
                    ts        TEXT NOT NULL,
                    actor     TEXT,
                    action    TEXT NOT NULL,
                    record_id TEXT
                );
                """
            )

    def _audit(self, conn, action: str, actor: str, record_id: str | None):
        conn.execute(
            "INSERT INTO audit_log (ts, actor, action, record_id) VALUES (?,?,?,?)",
            (_now_iso(), actor, action, record_id),
        )

    # ----------------------------------------------------------- jetons ----
    def _hmac(self, label: str, value: str) -> str:
        return hmac.new(self._master, f"{label}:{value}".encode(),
                        hashlib.sha256).hexdigest()

    def _record_id(self, name: str, docnum: str, reg_date: str) -> str:
        raw = f"{_name_key(name)}|{_docnum_key(docnum)}|{reg_date}"
        return self._hmac("rec", raw)[:32]

    # --------------------------------------------------- chiffrement -------
    def _wrap_dek(self, dek: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._master).encrypt(nonce, dek, b"dek")

    def _unwrap_dek(self, blob: bytes) -> bytes:
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(self._master).decrypt(nonce, ct, b"dek")

    @staticmethod
    def _seal(dek: bytes, plaintext: bytes, aad: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(dek).encrypt(nonce, plaintext, aad)

    @staticmethod
    def _open(dek: bytes, blob: bytes, aad: bytes) -> bytes:
        nonce, ct = blob[:12], blob[12:]
        return AESGCM(dek).decrypt(nonce, ct, aad)

    # ------------------------------------------------------- API publique --
    def store(self, *, name: str, report, images: list[bytes],
              registration_date: str | date | None = None,
              actor: str = "system") -> str:
        """Archive un dossier (rapport + images) chiffré. Renvoie le record_id.

        `report` peut être un objet Report ou un dict (doit fournir to_dict()
        ou être déjà un dict).
        """
        report_dict = report.to_dict() if hasattr(report, "to_dict") else dict(report)
        docnum = (report_dict.get("document_number")
                  or report_dict.get("fields", {}).get("document_number") or "")
        reg = _coerce_date(registration_date) or date.today().isoformat()

        record_id = self._record_id(name, docnum, reg)
        rec_dir = os.path.join(self.cfg.root, record_id)
        os.makedirs(rec_dir, exist_ok=True)
        aad = record_id.encode()

        dek = os.urandom(32)
        _write(os.path.join(rec_dir, "dek.bin"), self._wrap_dek(dek))
        _write(os.path.join(rec_dir, "report.enc"),
               self._seal(dek, json.dumps(report_dict, ensure_ascii=False).encode(), aad))
        for i, img in enumerate(images):
            _write(os.path.join(rec_dir, f"img_{i:03d}.enc"),
                   self._seal(dek, img, aad))
        del dek  # on ne garde pas la clé de données en mémoire

        created = _now_iso()
        retention = (date.fromisoformat(reg)
                     + timedelta(days=self.cfg.retention_days)).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO records
                   (record_id, name_token, docnum_token, registration_date,
                    created_at, retention_until, doc_type, country, mrz_format,
                    status, score, image_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, self._hmac("name", _name_key(name)),
                 self._hmac("doc", _docnum_key(docnum)), reg, created, retention,
                 report_dict.get("document_type"), report_dict.get("country"),
                 report_dict.get("mrz_format"), report_dict.get("status"),
                 report_dict.get("score"), len(images)),
            )
            self._audit(conn, "store", actor, record_id)
        return record_id

    def search(self, *, name: str | None = None,
               document_number: str | None = None,
               registration_date: str | date | None = None,
               actor: str = "system") -> list[dict]:
        """Recherche par nom et/ou numéro et/ou date. Renvoie des métadonnées
        (jamais d'images ni de PII en clair). Journalise l'accès."""
        clauses, params = [], []
        if name:
            clauses.append("name_token = ?")
            params.append(self._hmac("name", _name_key(name)))
        if document_number:
            clauses.append("docnum_token = ?")
            params.append(self._hmac("doc", _docnum_key(document_number)))
        if registration_date:
            clauses.append("registration_date = ?")
            params.append(_coerce_date(registration_date))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT record_id, registration_date, created_at, "
                "retention_until, doc_type, country, mrz_format, status, "
                "score, image_count FROM records" + where
                + " ORDER BY created_at DESC", params).fetchall()
            self._audit(conn, "search", actor, None)
        return [dict(r) for r in rows]

    def retrieve(self, record_id: str, *, actor: str = "system") -> dict:
        """Déchiffre et renvoie {report, images:[bytes], image_count}.

        Réservé à l'usage légitime (consultation en cas de litige) : l'accès
        est tracé. Lève IntegrityError si une donnée a été altérée."""
        rec_dir = os.path.join(self.cfg.root, record_id)
        if not os.path.isdir(rec_dir):
            raise FileNotFoundError(f"Dossier introuvable : {record_id}")
        aad = record_id.encode()
        try:
            dek = self._unwrap_dek(_read(os.path.join(rec_dir, "dek.bin")))
            report = json.loads(self._open(dek, _read(os.path.join(rec_dir, "report.enc")), aad))
            images = []
            i = 0
            while os.path.isfile(os.path.join(rec_dir, f"img_{i:03d}.enc")):
                images.append(self._open(dek, _read(os.path.join(rec_dir, f"img_{i:03d}.enc")), aad))
                i += 1
        except Exception as exc:  # InvalidTag, etc.
            raise IntegrityError(
                f"Échec de déchiffrement/intégrité pour {record_id}: {exc}") from exc
        with self._connect() as conn:
            self._audit(conn, "retrieve", actor, record_id)
        return {"report": report, "images": images, "image_count": len(images)}

    def purge_expired(self, today: date | None = None,
                      actor: str = "system") -> int:
        """Supprime les dossiers dont la rétention est dépassée. Renvoie le
        nombre de dossiers purgés."""
        today = today or date.today()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT record_id FROM records WHERE retention_until < ?",
                (today.isoformat(),)).fetchall()
            purged = 0
            for r in rows:
                rid = r["record_id"]
                _rmtree(os.path.join(self.cfg.root, rid))
                conn.execute("DELETE FROM records WHERE record_id = ?", (rid,))
                self._audit(conn, "purge", actor, rid)
                purged += 1
        return purged

    def audit_trail(self, record_id: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if record_id:
                rows = conn.execute(
                    "SELECT * FROM audit_log WHERE record_id = ? ORDER BY ts",
                    (record_id,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM audit_log ORDER BY ts").fetchall()
        return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _coerce_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _write(path: str, data: bytes):
    with open(path, "wb") as fh:
        fh.write(data)


def _read(path: str) -> bytes:
    with open(path, "rb") as fh:
        return fh.read()


def _rmtree(path: str):
    if not os.path.isdir(path):
        return
    for name in os.listdir(path):
        os.remove(os.path.join(path, name))
    os.rmdir(path)


def _resolve_master_key(root: str) -> bytes:
    """Clé maître : variable d'env KYC_MASTER_KEY (base64) sinon fichier local
    auto-généré (.master.key) — pratique en dev, à remplacer par un KMS en prod."""
    env = os.environ.get("KYC_MASTER_KEY")
    if env:
        return base64.b64decode(env)
    key_path = os.path.join(root, ".master.key")
    if os.path.isfile(key_path):
        return base64.b64decode(_read(key_path))
    key = os.urandom(32)
    _write(key_path, base64.b64encode(key))
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key
