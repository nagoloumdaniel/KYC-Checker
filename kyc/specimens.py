"""Spécimens MRZ pour les démos et les tests (aucune vraie pièce requise).

- synthetic_passport(...) génère une MRZ TD3 valide via la librairie `mrz`.
- PUBLIC_SAMPLES contient l'exemple ICAO/Wikipedia bien connu (Anna Eriksson).
- tamper_first_check_digit(...) falsifie une clé de contrôle pour tester la
  détection d'incohérence.
"""

from __future__ import annotations

from mrz.generator.td1 import TD1CodeGenerator
from mrz.generator.td2 import TD2CodeGenerator
from mrz.generator.td3 import TD3CodeGenerator


def synthetic_id_td1(surname: str = "ERIKSSON",
                     given_names: str = "ANNA MARIA",
                     country: str = "UTO", nationality: str = "UTO",
                     document_number: str = "D23145890",
                     birth_date: str = "740812", sex: str = "F",
                     expiry_date: str = "300101") -> str:
    """MRZ TD1 valide (carte d'identité, 3 lignes × 30)."""
    return str(TD1CodeGenerator(
        "I", country, document_number, birth_date, sex, expiry_date,
        nationality, surname, given_names,
        optional_data1="", optional_data2=""))


def synthetic_id_td2(surname: str = "ERIKSSON",
                     given_names: str = "ANNA MARIA",
                     country: str = "UTO", nationality: str = "UTO",
                     document_number: str = "D23145890",
                     birth_date: str = "740812", sex: str = "F",
                     expiry_date: str = "300101") -> str:
    """MRZ TD2 valide (pièce ID-2, 2 lignes × 36)."""
    return str(TD2CodeGenerator(
        "I", country, surname, given_names, document_number,
        nationality, birth_date, sex, expiry_date, optional_data=""))


def synthetic_passport(surname: str = "ERIKSSON",
                       given_names: str = "ANNA MARIA",
                       country: str = "UTO",
                       nationality: str = "UTO",
                       document_number: str = "L898902C3",
                       birth_date: str = "740812",
                       sex: str = "F",
                       expiry_date: str = "300101",
                       optional_data: str = "ZE184226B") -> str:
    """Retourne une MRZ TD3 valide (clés de contrôle correctes)."""
    return str(TD3CodeGenerator(
        "P", country, surname, given_names, document_number,
        nationality, birth_date, sex, expiry_date, optional_data,
    ))


# Exemple public de référence (ICAO Doc 9303 / Wikipedia), expiré.
PUBLIC_SAMPLES = {
    "icao_anna_eriksson": (
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\n"
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
    ),
}


def render_passport_image(mrz_text: str, out_path: str,
                          surname: str = "ERIKSSON",
                          given_names: str = "ANNA MARIA",
                          face_path: str | None = None):
    """Génère une image de page passeport synthétique avec sa MRZ.

    Si face_path est fourni, la photo réelle est incrustée dans l'emplacement
    photo (utile pour tester la comparaison de visage).

    Sert à tester le pipeline image de bout en bout sans vraie pièce.
    Pillow est importé paresseusement : le cœur n'en dépend pas.
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1000, 700
    img = Image.new("RGB", (W, H), (232, 228, 216))  # fond clair type document
    draw = ImageDraw.Draw(img)

    def font(path_candidates, size):
        for p in path_candidates:
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
        return ImageFont.load_default()

    mono = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf",
            "DejaVuSansMono.ttf"]
    sans = ["C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]
    f_title = font(sans, 34)
    f_label = font(sans, 18)
    f_value = font(sans, 24)
    f_mrz = font(mono, 30)

    # En-tête
    draw.text((30, 25), "PASSEPORT / PASSPORT", fill=(20, 40, 90), font=f_title)
    draw.text((30, 70), "TYPE  P    CODE  UTO", fill=(60, 60, 60), font=f_label)

    # Emplacement photo
    draw.rectangle([30, 120, 230, 380], fill=(200, 200, 200),
                   outline=(120, 120, 120), width=2)
    if face_path:
        face = Image.open(face_path).convert("RGB").resize((200, 260))
        img.paste(face, (30, 120))
    else:
        draw.text((70, 240), "PHOTO", fill=(120, 120, 120), font=f_label)

    # Champs visuels
    fields = [("Surname / Nom", surname),
              ("Given names / Prénoms", given_names),
              ("Nationality / Nationalité", "UTOPIAN"),
              ("Date of birth", "12 AUG 1974"),
              ("Sex", "F"),
              ("Date of expiry", "01 JAN 2030")]
    y = 130
    for label, value in fields:
        draw.text((270, y), label, fill=(90, 90, 90), font=f_label)
        draw.text((270, y + 22), value, fill=(10, 10, 10), font=f_value)
        y += 75

    # Bande MRZ : strip blanc, texte noir monospace, en bas du document
    draw.rectangle([0, H - 130, W, H], fill=(255, 255, 255))
    my = H - 110
    for line in mrz_text.split("\n"):
        draw.text((40, my), line, fill=(0, 0, 0), font=f_mrz)
        my += 48

    img.save(out_path, quality=95)
    return out_path


def _load_font(candidates, size):
    from PIL import ImageFont
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


_MONO = ["C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf",
         "DejaVuSansMono.ttf"]
_SANS = ["C:/Windows/Fonts/arial.ttf", "DejaVuSans.ttf"]


def render_id_card_front(out_path: str, surname: str = "ERIKSSON",
                         given_names: str = "ANNA MARIA"):
    """Recto de carte d'identité : photo + champs, SANS MRZ."""
    from PIL import Image, ImageDraw

    W, H = 860, 540
    img = Image.new("RGB", (W, H), (224, 232, 224))
    draw = ImageDraw.Draw(img)
    draw.text((30, 25), "CARTE NATIONALE D'IDENTITÉ", fill=(20, 40, 90),
              font=_load_font(_SANS, 28))
    draw.rectangle([30, 90, 210, 330], fill=(200, 200, 200),
                   outline=(120, 120, 120), width=2)
    draw.text((90, 200), "PHOTO", fill=(120, 120, 120),
              font=_load_font(_SANS, 16))
    fields = [("Nom", surname), ("Prénoms", given_names),
              ("Nationalité", "UTOPIENNE"), ("Né(e) le", "12.08.1974")]
    y = 100
    for label, value in fields:
        draw.text((250, y), label, fill=(90, 90, 90), font=_load_font(_SANS, 16))
        draw.text((250, y + 20), value, fill=(10, 10, 10),
                  font=_load_font(_SANS, 22))
        y += 70
    img.save(out_path, quality=95)
    return out_path


def render_id_card_back(mrz_text: str, out_path: str):
    """Verso de carte d'identité : MRZ (2 ou 3 lignes) en bas."""
    from PIL import Image, ImageDraw

    W, H = 860, 540
    img = Image.new("RGB", (W, H), (224, 232, 224))
    draw = ImageDraw.Draw(img)
    draw.text((30, 25), "ADRESSE / OBSERVATIONS", fill=(60, 60, 60),
              font=_load_font(_SANS, 18))

    lines = mrz_text.split("\n")
    f_mrz = _load_font(_MONO, 28)
    strip_h = 30 + len(lines) * 42
    draw.rectangle([0, H - strip_h, W, H], fill=(255, 255, 255))
    my = H - strip_h + 14
    for line in lines:
        draw.text((30, my), line, fill=(0, 0, 0), font=f_mrz)
        my += 42
    img.save(out_path, quality=95)
    return out_path


def tamper_first_check_digit(mrz_text: str) -> str:
    """Modifie la 1re clé de contrôle (clé du numéro de document, ligne 2,
    position 9) pour produire une MRZ falsifiée détectable."""
    lines = mrz_text.split("\n")
    if len(lines) != 2 or len(lines[1]) < 10:
        return mrz_text
    line2 = list(lines[1])
    pos = 9  # check digit du numéro de document
    line2[pos] = "0" if line2[pos] != "0" else "1"
    lines[1] = "".join(line2)
    return "\n".join(lines)
