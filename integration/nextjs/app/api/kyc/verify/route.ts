/**
 * Route serveur Next.js (App Router) : reçoit l'upload du navigateur et le
 * relaie au service KYC. La clé d'API reste CÔTÉ SERVEUR (jamais exposée).
 *
 * POST /api/kyc/verify   (multipart/form-data)
 *   - name    : string
 *   - images  : 1 à 2 fichiers
 *   - selfie  : fichier (optionnel)
 *   - archive : "true" (optionnel)
 */
import { NextRequest, NextResponse } from "next/server";
import { KycClient, KycError, type ImageInput } from "@/lib/kycClient";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData();
    const name = String(form.get("name") ?? "").trim();
    if (!name) {
      return NextResponse.json({ error: "Nom requis." }, { status: 400 });
    }

    const images = form.getAll("images")
      .filter((f): f is File => f instanceof File && f.size > 0)
      .slice(0, 2)
      .map((f): ImageInput => ({ blob: f, filename: f.name }));
    if (images.length === 0) {
      return NextResponse.json({ error: "Au moins une image requise." }, { status: 400 });
    }

    const selfieFile = form.get("selfie");
    const selfie = selfieFile instanceof File && selfieFile.size > 0
      ? { blob: selfieFile, filename: selfieFile.name }
      : undefined;

    const client = new KycClient(); // lit KYC_API_URL / KYC_API_KEY
    const report = await client.verify({
      name,
      images,
      selfie,
      archive: form.get("archive") === "true",
    });
    return NextResponse.json(report);
  } catch (err) {
    if (err instanceof KycError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Erreur interne." },
      { status: 502 },
    );
  }
}
