"""Interface en ligne de commande du KYC Checker.

Exemples :
  python -m kyc demo
  python -m kyc demo --tamper
  python -m kyc demo --wrong-name
  python -m kyc verify --mrz-file mrz.txt --name "Anna Maria Eriksson"
  python -m kyc verify --image passeport.jpg --name "Anna Eriksson"
"""

from __future__ import annotations

import argparse
import json
import sys

from .config import Config
from .pipeline import verify_from_mrz, verify_documents
from .specimens import (synthetic_passport, synthetic_id_td1,
                        synthetic_id_td2, tamper_first_check_digit,
                        PUBLIC_SAMPLES)


def _ensure_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass


_STATUS_MARK = {"VALID": "[+]", "SUSPECT": "[?]", "REJECTED": "[-]"}


def render(report, as_json: bool):
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return

    r = report
    mark = _STATUS_MARK.get(r.status, "[ ]")
    line = "=" * 60
    print(line)
    print(f" {mark} STATUT : {r.status_fr}    |    Score : {r.score}/100")
    print(line)
    if r.mrz_parsed:
        print(f" Format MRZ      : {r.mrz_format}")
        print(f" Type document   : {r.document_type}   Pays : {r.country}"
              f"   Nationalité : {r.nationality}")
        print(f" N° document     : {r.document_number}   Sexe : {r.sex}")
        print(f" Nom (MRZ)       : {r.fields.get('surname')} "
              f"{r.fields.get('name')}")
        print(f" Naissance (MRZ) : {r.birth_date}")
        exp = r.expiry
        exp_txt = exp.get("date") or "?"
        if exp.get("expired"):
            exp_txt += "  (EXPIRÉ)"
        print(f" Expiration      : {exp_txt}")
        print("-" * 60)
        print(" Clés de contrôle MRZ :")
        for k, ok in r.check_digits.items():
            print(f"   - {k:<22} {'OK' if ok else 'ÉCHEC'}")
        print("-" * 60)
        nm = r.name_match
        print(f" Rapprochement nom : {nm['label']}  ({nm['score']}%)")
        print(f"   attendu (norm.) : {nm['expected_normalized']}")
        print(f"   pièce   (norm.) : {nm['mrz_normalized']}")
    if r.face_match is not None:
        fm = r.face_match
        verdict = "CORRESPOND" if fm.get("match") else "NE CORRESPOND PAS"
        score = fm.get("score")
        print("-" * 60)
        print(f" Visage (selfie)  : {verdict}"
              + (f"  (cosinus {score})" if score is not None
                 else f"  ({fm.get('error', '?')})"))
    if r.forensics is not None:
        fo = r.forensics
        flag = "SUSPECT" if fo.get("suspicious") else "RAS"
        print("-" * 60)
        print(f" Forensique image : {flag}  (score retouche "
              f"{fo.get('tampering_score')}, netteté {fo.get('blur_var')})")
    print("-" * 60)
    if r.warnings:
        print(" Avertissements :")
        for w in r.warnings:
            print(f"   ! {w}")
    if r.errors:
        print(" Erreurs :")
        for e in r.errors:
            print(f"   x {e}")
    if not r.warnings and not r.errors:
        print(" Aucune anomalie détectée.")
    print(line)


def _cmd_demo(args):
    cfg = Config()
    if args.sample:
        mrz = PUBLIC_SAMPLES["icao_anna_eriksson"]
    elif args.format == "td1":
        mrz = synthetic_id_td1()
    elif args.format == "td2":
        mrz = synthetic_id_td2()
    else:
        mrz = synthetic_passport()
    expected = "Anna Maria Eriksson"

    doc = {"td1": "carte d'identité (TD1)", "td2": "pièce ID-2 (TD2)"}.get(
        args.format, "passeport (TD3)")
    if args.tamper:
        mrz = tamper_first_check_digit(mrz)
        print(f">> Démo : {doc} — MRZ FALSIFIÉE (clé de contrôle modifiée)\n")
    elif args.wrong_name:
        expected = "Jean Dupont"
        print(f">> Démo : {doc} — NOM NE CORRESPOND PAS au document\n")
    else:
        print(f">> Démo : {doc} cohérent(e)\n")

    report = verify_from_mrz(mrz, expected, cfg)
    render(report, args.json)


def _cmd_verify(args):
    cfg = Config()
    if args.mrz_file:
        with open(args.mrz_file, "r", encoding="utf-8") as fh:
            mrz_text = fh.read()
        report = verify_from_mrz(mrz_text, args.name, cfg)
    elif args.mrz:
        report = verify_from_mrz(args.mrz.replace("\\n", "\n"), args.name, cfg)
    elif args.image:
        report = verify_documents(args.image, args.name, selfie=args.selfie,
                                  cfg=cfg, ocr_backend=args.ocr)
    else:
        print("Fournis --image, --mrz ou --mrz-file.", file=sys.stderr)
        return 2
    render(report, args.json)
    return 0 if report.status == "VALID" else 1


def build_parser():
    p = argparse.ArgumentParser(
        prog="kyc", description="KYC Checker — vérification passeport (MRZ TD3)")
    p.add_argument("--json", action="store_true", help="sortie JSON")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("demo", help="démonstration sur spécimen synthétique")
    d.add_argument("--tamper", action="store_true",
                   help="falsifie une clé de contrôle")
    d.add_argument("--wrong-name", action="store_true",
                   help="utilise un nom qui ne correspond pas")
    d.add_argument("--sample", action="store_true",
                   help="utilise l'exemple public ICAO au lieu du généré")
    d.add_argument("--format", choices=["td1", "td2", "td3"], default="td3",
                   help="format de la pièce générée (td3=passeport, td1/td2=CNI)")
    d.set_defaults(func=_cmd_demo)

    v = sub.add_parser("verify", help="vérifie une pièce réelle")
    v.add_argument("--name", required=True, help="nom attendu (formulaire)")
    src = v.add_mutually_exclusive_group()
    src.add_argument("--image", action="append",
                     help="chemin image (répéter pour recto/verso)")
    src.add_argument("--mrz", help="texte MRZ (utilise \\n entre les lignes)")
    src.add_argument("--mrz-file", help="fichier texte contenant la MRZ")
    v.add_argument("--selfie", help="image selfie (comparaison de visage)")
    v.add_argument("--ocr", default="auto",
                   choices=["auto", "tesseract", "easyocr"],
                   help="moteur OCR pour --image")
    v.set_defaults(func=_cmd_verify)
    return p


def main(argv=None):
    _ensure_utf8()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
