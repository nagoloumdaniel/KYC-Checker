"use client";

/**
 * Exemple de formulaire d'upload KYC (composant client).
 * Envoie pièce(s) + selfie + nom à /api/kyc/verify et affiche le rapport.
 * Aucune clé d'API ici : c'est la route serveur qui la détient.
 */
import { useState } from "react";
import type { KycReport } from "@/lib/kycClient";

const STATUS_COLOR: Record<string, string> = {
  VALID: "#15803d",
  SUSPECT: "#b45309",
  REJECTED: "#b91c1c",
};

export default function KycPage() {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<KycReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      const fd = new FormData(e.currentTarget);
      const res = await fetch("/api/kyc/verify", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error ?? "Échec de la vérification.");
      setReport(data as KycReport);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ maxWidth: 640, margin: "2rem auto", fontFamily: "system-ui" }}>
      <h1>Vérification KYC</h1>
      <form onSubmit={onSubmit} style={{ display: "grid", gap: 12 }}>
        <label>
          Nom attendu
          <input name="name" required placeholder="Anna Maria Eriksson"
                 style={{ display: "block", width: "100%", padding: 8 }} />
        </label>
        <label>
          Pièce d'identité (recto, + verso si carte)
          <input name="images" type="file" accept="image/jpeg,image/png" multiple required />
        </label>
        <label>
          Selfie (optionnel — comparaison de visage)
          <input name="selfie" type="file" accept="image/jpeg,image/png" />
        </label>
        <label style={{ fontSize: 14 }}>
          <input name="archive" type="checkbox" value="true" /> Archiver le dossier (chiffré)
        </label>
        <button type="submit" disabled={loading} style={{ padding: 10 }}>
          {loading ? "Analyse…" : "Vérifier"}
        </button>
      </form>

      {error && <p style={{ color: "#b91c1c" }}>⚠️ {error}</p>}

      {report && (
        <section style={{ marginTop: 24, border: "1px solid #e2e8f0", borderRadius: 8, padding: 16 }}>
          <h2 style={{ color: STATUS_COLOR[report.status] ?? "#333" }}>
            {report.status_fr} — {report.score}/100
          </h2>
          <ul style={{ lineHeight: 1.6 }}>
            <li>Format : <b>{report.mrz_format ?? "?"}</b> — {report.document_type} / {report.country}</li>
            <li>Pièce : <b>{report.fields.surname} {report.fields.name}</b> (n° {report.document_number})</li>
            <li>Nom : <b>{report.name_match.label}</b> ({report.name_match.score}%)</li>
            <li>Expiration : {report.expiry.date ?? "?"}{report.expiry.expired ? " (expiré)" : ""}</li>
            {report.face_match && (
              <li>Visage : <b>{report.face_match.match ? "correspond" : "ne correspond pas"}</b>
                {report.face_match.score != null ? ` (cosinus ${report.face_match.score})` : ` (${report.face_match.error ?? "?"})`}</li>
            )}
            {report.record_id && <li>Archivé : <code>{report.record_id}</code></li>}
          </ul>
          {report.warnings.length > 0 && (
            <ul style={{ color: "#b45309" }}>
              {report.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}
