"""Purge les dossiers archivés dont la rétention est dépassée.

À planifier (cron / tâche planifiée). Respecte KYC_ARCHIVE_DIR et
KYC_MASTER_KEY (ou le fichier .master.key du dossier d'archive).

    python tools/purge_expired.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kyc.storage import Vault, StorageConfig

root = os.environ.get("KYC_ARCHIVE_DIR", "archive")
vault = Vault(StorageConfig(root=root))
n = vault.purge_expired()
print(f"Dossiers purgés : {n}")
