/**
 * SDK client TypeScript pour le service KYC Checker.
 *
 * ⚠️ À utiliser CÔTÉ SERVEUR uniquement (route handlers, server actions, API
 * routes) : il porte la clé d'API, qui ne doit JAMAIS arriver dans le navigateur.
 * Le navigateur appelle ta route Next, qui appelle ce client.
 *
 * Config par variables d'environnement (aucun changement de code au déploiement) :
 *   KYC_API_URL  (défaut http://localhost:8000)
 *   KYC_API_KEY  (si l'API exige une clé)
 */

export type KycStatus = "VALID" | "SUSPECT" | "REJECTED";
export type NameLabel = "MATCH" | "PARTIAL" | "NO_MATCH";

export interface NameMatch {
  score: number;
  label: NameLabel;
  expected: string;
  expected_normalized: string;
  mrz_normalized: string;
}

export interface FaceMatch {
  match: boolean;
  score: number | null;
  faces: Record<string, boolean>;
  threshold: number;
  error?: string;
}

export interface KycReport {
  status: KycStatus;
  status_fr: string;
  score: number;
  mrz_parsed: boolean;
  mrz_valid: boolean;
  mrz_format: "TD1" | "TD2" | "TD3" | null;
  document_type: string | null;
  country: string | null;
  nationality: string | null;
  document_number: string | null;
  sex: string | null;
  birth_date: string | null;
  expiry: { date: string | null; expired: boolean | null; valid: boolean };
  name_match: NameMatch;
  check_digits: Record<string, boolean>;
  fields: Record<string, string | null>;
  warnings: string[];
  errors: string[];
  face_match: FaceMatch | null;
  forensics: Record<string, unknown> | null;
  record_id?: string;
  archive_error?: string;
}

export interface RecordRow {
  record_id: string;
  registration_date: string;
  created_at: string;
  retention_until: string;
  doc_type: string | null;
  country: string | null;
  mrz_format: string | null;
  status: string | null;
  score: number | null;
  image_count: number;
}

export type ImageInput = Blob | { blob: Blob; filename?: string };

export interface VerifyParams {
  name: string;
  images: ImageInput[];      // 1 à 2 (recto/verso)
  selfie?: ImageInput;        // optionnel : comparaison de visage
  archive?: boolean;          // archiver le dossier (chiffré) côté service
  registrationDate?: string;  // YYYY-MM-DD
  ocr?: "auto" | "tesseract" | "easyocr";
}

export class KycError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "KycError";
    this.status = status;
  }
}

export class KycClient {
  private baseUrl: string;
  private apiKey?: string;

  constructor(opts: { baseUrl?: string; apiKey?: string } = {}) {
    this.baseUrl = (opts.baseUrl ?? process.env.KYC_API_URL ?? "http://localhost:8000")
      .replace(/\/+$/, "");
    this.apiKey = opts.apiKey ?? process.env.KYC_API_KEY;
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    return { ...(this.apiKey ? { "X-API-Key": this.apiKey } : {}), ...extra };
  }

  private async parse<T>(res: Response): Promise<T> {
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = (body as any)?.detail ?? (body as any)?.error ?? res.statusText;
      throw new KycError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg));
    }
    return body as T;
  }

  async health(): Promise<{ status: string; version: string; ocr_available: boolean; auth_enabled: boolean }> {
    return this.parse(await fetch(`${this.baseUrl}/health`));
  }

  /** Vérifie une pièce à partir d'un texte MRZ déjà extrait. */
  async verifyMrz(mrzText: string, name: string): Promise<KycReport> {
    const res = await fetch(`${this.baseUrl}/verify-mrz`, {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify({ mrz_text: mrzText, name }),
    });
    return this.parse<KycReport>(res);
  }

  /** Vérifie une pièce à partir d'images (+ selfie optionnel). */
  async verify(params: VerifyParams): Promise<KycReport> {
    const fd = new FormData();
    fd.append("name", params.name);
    if (params.ocr) fd.append("ocr", params.ocr);
    if (params.archive) fd.append("archive", "true");
    if (params.registrationDate) fd.append("registration_date", params.registrationDate);

    const append = (field: string, input: ImageInput, fallback: string) => {
      const blob = input instanceof Blob ? input : input.blob;
      const filename = input instanceof Blob ? fallback : (input.filename ?? fallback);
      fd.append(field, blob, filename);
    };
    params.images.forEach((img, i) => append("images", img, `image_${i}.jpg`));
    if (params.selfie) append("selfie", params.selfie, "selfie.jpg");

    const res = await fetch(`${this.baseUrl}/verify`, {
      method: "POST",
      headers: this.headers(),     // pas de Content-Type : fetch gère le boundary
      body: fd,
    });
    return this.parse<KycReport>(res);
  }

  /** Recherche de dossiers archivés (métadonnées, sans PII en clair). */
  async searchRecords(query: { name?: string; documentNumber?: string; registrationDate?: string }):
    Promise<{ count: number; records: RecordRow[] }> {
    const qs = new URLSearchParams();
    if (query.name) qs.set("name", query.name);
    if (query.documentNumber) qs.set("document_number", query.documentNumber);
    if (query.registrationDate) qs.set("registration_date", query.registrationDate);
    const res = await fetch(`${this.baseUrl}/records?${qs}`, { headers: this.headers() });
    return this.parse(res);
  }
}
