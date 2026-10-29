"""Génère docs/assets/demo-overview.png (visuel du README).

Reproductible, sans service lancé : spécimen synthétique (kyc.specimens) +
sortie réelle du CLI (`python -m kyc demo`). Aucune donnée réelle.

    python tools/make_readme_visual.py
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from kyc.specimens import render_passport_image, synthetic_passport  # noqa: E402

MONO = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/lucon.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "DejaVuSansMono.ttf"]
SANS_B = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
          "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
          "DejaVuSans-Bold.ttf"]


def font(paths, size):
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def cli(*args):
    env = dict(os.environ, PYTHONUTF8="1")
    out = subprocess.run([sys.executable, "-m", "kyc", *args], cwd=ROOT,
                         env=env, capture_output=True, text=True,
                         encoding="utf-8").stdout
    return out.strip("\n").splitlines()


def summary(lines):
    keep = [l for l in lines if ("STATUT" in l or "Rapprochement" in l
                                 or l.strip().startswith(("!", ">>")))]
    return [l.replace("=", "") if set(l) <= {"="} else l for l in keep]


def main():
    W, H, PAD = 1600, 720, 40
    img = Image.new("RGB", (W, H), "#0f172a")
    d = ImageDraw.Draw(img)
    d.text((PAD, 28), "KYC Checker - spécimens synthétiques + CLI (python -m kyc demo)",
           font=font(SANS_B, 30), fill="#e2e8f0")

    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "passport.jpg")
        render_passport_image(synthetic_passport(), p)
        doc = Image.open(p).convert("RGB")
    doc.thumbnail((640, 760))
    img.paste(doc, (PAD, 110))
    d.text((PAD, 110 + doc.height + 12), "Spécimen synthétique (fictif)",
           font=font(MONO, 18), fill="#94a3b8")

    cases = [("demo", [], "#22c55e"),
             ("demo --tamper", ["--tamper"], "#f59e0b"),
             ("demo --wrong-name", ["--wrong-name"], "#ef4444")]
    f = font(MONO, 19)
    x0, y = 740, 110
    for title, extra, color in cases:
        lines = summary(cli("demo", *extra))
        h = 70 + 27 * len(lines)
        d.rounded_rectangle((x0, y, W - PAD, y + h), 14, fill="#1e293b",
                            outline=color, width=3)
        d.text((x0 + 20, y + 14), "$ python -m kyc " + title,
               font=font(SANS_B, 22), fill=color)
        for i, l in enumerate(lines):
            d.text((x0 + 20, y + 52 + 27 * i), l[:78], font=f, fill="#e2e8f0")
        y += h + 24
    out = os.path.join(ROOT, "docs", "assets", "demo-overview.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, optimize=True)
    print(out)


if __name__ == "__main__":
    main()
