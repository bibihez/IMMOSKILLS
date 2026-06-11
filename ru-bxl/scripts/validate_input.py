"""Validation fail-fast de l'input.json AVANT de lancer auth_irisbox.py.

Chaque erreur attrapée ici = 44 secondes d'itsme épargnées à l'agent. Vérifie
les champs requis, les formats, les enums IRISbox, et les contraintes upload
réelles (extensions, 20MB/fichier, 100MB total, 255 chars/filename).

    python3 validate_input.py --data input.json

Sortie : une ligne JSON par problème {check, ok, detail} + résumé final.
Exit 0 = prêt à lancer. Exit 1 = corriger l'input d'abord (la liste des
erreurs est conçue pour être relayée telle quelle à l'agent en chat).
"""
import argparse
import json
import re
import sys
from pathlib import Path

from _selectors import (
    QUALITY_LAWYER,
    QUALITY_MANDATARY,
    QUALITY_OTHER,
    QUALITY_REAL_ESTATE_AGENT,
    RE_CAPAKEY,
    UNITE_DESTINATIONS,
    is_excluded_commune,
)

ALLOWED_QUALITIES = {QUALITY_REAL_ESTATE_AGENT, QUALITY_LAWYER,
                     QUALITY_MANDATARY, QUALITY_OTHER}
ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
ALLOWED_DOC_KEYS = {"titre_propriete", "mandat", "reportage", "croquis",
                    "plan_parcellaire", "matrice_cadastrale", "autre"}
MAX_FILE_BYTES = 20 * 1024 * 1024     # 20MB par fichier (limite IRISbox)
MAX_TOTAL_BYTES = 100 * 1024 * 1024   # 100MB total
MAX_FILES_PER_CATEGORY = 10
MAX_FILENAME_CHARS = 255
# Champs intervenant requis par le modal IRISbox (email/phone/box optionnels)
INTERVENANT_REQUIRED = ("firstName", "lastName", "streetName", "streetNumber",
                        "zipCode", "city", "country")

ERRORS = []


def report(check: str, ok: bool, detail: str = "") -> None:
    if not ok:
        ERRORS.append(check)
    print(json.dumps({"check": check, "ok": ok, "detail": detail},
                     ensure_ascii=False), flush=True)


def validate(data: dict) -> None:
    # --- itsme ---
    phone = re.sub(r"[\s.\-/]", "", str(data.get("phone_number", "")))
    phone = re.sub(r"^(\+32|0032|0)", "", phone)
    report("phone_number", bool(re.fullmatch(r"\d{8,9}", phone)),
           "numéro itsme requis (formats acceptés: 047..., +32..., 0032...)")

    # --- localisation ---
    capakey = (data.get("cadastral_reference") or "").strip()
    address = (data.get("address") or "").strip()
    if capakey:
        report("cadastral_reference_format", bool(RE_CAPAKEY.match(capakey)),
               f"capakey invalide '{capakey}' — format attendu 21013B0029/00A005 "
               "(17 caractères, sur le titre de propriété ou la matrice cadastrale)")
    else:
        report("localisation_source", bool(address),
               "ni capakey ni adresse — il faut au moins l'un des deux "
               "(capakey extrait du titre de propriété = chemin le plus fiable)")
        if address:
            report("address_has_number", bool(re.search(r"\d", address)),
                   "l'autocomplete IRISbox exige un numéro de rue dans l'adresse")

    commune = (data.get("commune") or "").strip()
    report("commune_present", bool(commune), "commune requise pour le check d'exclusion")
    if commune:
        report("commune_supported", not is_excluded_commune(commune),
               f"'{commune}' ne passe pas par IRISbox (Evere, Forest, Koekelberg, "
               "Watermael-Boitsfort) — demande directe à la commune")

    # --- demandeur ---
    is_owner = data.get("is_owner", True)
    if not is_owner:
        report("quality_valid", data.get("quality") in ALLOWED_QUALITIES,
               f"quality '{data.get('quality')}' hors enum {sorted(ALLOWED_QUALITIES)}")
        intervenants = data.get("intervenants") or []
        report("intervenants_present", len(intervenants) > 0,
               "is_owner=false exige au moins 1 propriétaire dans intervenants[]")
        for i, interv in enumerate(intervenants):
            if interv.get("type", "PHYSICAL") != "PHYSICAL":
                report(f"intervenant_{i}_type", False,
                       "personne morale (SCI/SPRL) non supportée en V1 — abort")
                continue
            missing = [f for f in INTERVENANT_REQUIRED if not str(interv.get(f, "")).strip()]
            report(f"intervenant_{i}_complete", not missing,
                   f"champs manquants: {missing}" if missing else "")

    # --- bien ---
    def check_unit(label: str, u: dict) -> None:
        report(f"{label}_floor", bool(str(u.get("floor", "")).strip()), "étage requis")
        report(f"{label}_destination", u.get("destination") in UNITE_DESTINATIONS,
               f"destination '{u.get('destination')}' hors enum IRISbox: "
               f"{', '.join(UNITE_DESTINATIONS)}")

    bien_type = data.get("type", "construction")
    report("type_valid", bien_type in ("construction", "terrain_nu"),
           f"type '{bien_type}' — attendu 'construction' ou 'terrain_nu'")
    if bien_type == "construction":
        constructions = data.get("constructions") or []
        report("constructions_present", len(constructions) > 0,
               "type=construction exige au moins 1 construction")
        for i, c in enumerate(constructions):
            report(f"construction_{i}_denomination", bool(str(c.get("denomination", "")).strip()),
                   "dénomination requise (ex: 'Immeuble principal')")
            units = c.get("units") or []
            report(f"construction_{i}_units", len(units) > 0,
                   "au moins 1 unité requise (pour une copro: uniquement l'unité vendue)")
            for j, u in enumerate(units):
                check_unit(f"construction_{i}_unit_{j}", u)
    else:
        # terrain_nu : units[] top-level optionnel (rare) mais consommé par
        # prefill_form.py → mêmes checks, sinon crash post-itsme
        for j, u in enumerate(data.get("units") or []):
            check_unit(f"terrain_unit_{j}", u)

    parking = data.get("parking_count", 0)
    report("parking_count", isinstance(parking, int) and parking >= 0,
           f"parking_count '{parking}' — entier ≥ 0 attendu")

    # --- documents ---
    docs = data.get("documents") or {}
    unknown = set(docs) - ALLOWED_DOC_KEYS
    report("document_keys_known", not unknown,
           f"clés inconnues {sorted(unknown)} — autorisées: {sorted(ALLOWED_DOC_KEYS)}"
           if unknown else "")
    report("titre_propriete_provided", bool(docs.get("titre_propriete")),
           "titre de propriété obligatoire (sinon invoquer le skill titre-propriete)")
    if not is_owner:
        report("mandat_provided", bool(docs.get("mandat")),
               "mandat signé obligatoire quand le demandeur n'est pas propriétaire")

    total_bytes = 0
    for key, value in docs.items():
        if not value:
            continue
        # IRISbox accepte jusqu'à 10 fichiers/catégorie : string OU liste de paths
        paths = value if isinstance(value, list) else [value]
        report(f"document_{key}_count", len(paths) <= MAX_FILES_PER_CATEGORY,
               f"{len(paths)} fichiers > {MAX_FILES_PER_CATEGORY}/catégorie"
               if len(paths) > MAX_FILES_PER_CATEGORY else "")
        for k, path_str in enumerate(paths):
            suffix = f"_{k}" if len(paths) > 1 else ""
            p = Path(path_str)
            if not p.is_file():
                report(f"document_{key}{suffix}_exists", False, f"fichier introuvable: {p}")
                continue
            size = p.stat().st_size
            total_bytes += size
            ok_ext = p.suffix.lower() in ALLOWED_DOC_EXTENSIONS
            ok_size = size <= MAX_FILE_BYTES
            ok_name = len(p.name) <= MAX_FILENAME_CHARS
            ok_nonempty = size > 0
            report(f"document_{key}{suffix}_valid", ok_ext and ok_size and ok_name and ok_nonempty,
                   "; ".join(filter(None, [
                       None if ok_ext else f"extension {p.suffix} non acceptée ({'/'.join(sorted(ALLOWED_DOC_EXTENSIONS))})",
                       None if ok_size else f"{size / 1e6:.1f}MB > 20MB",
                       None if ok_name else f"nom de fichier > {MAX_FILENAME_CHARS} chars",
                       None if ok_nonempty else "fichier vide",
                   ])))
    report("documents_total_size", total_bytes <= MAX_TOTAL_BYTES,
           f"{total_bytes / 1e6:.1f}MB > 100MB total" if total_bytes > MAX_TOTAL_BYTES else "")

    # --- resume_url (rempli post-auth ; toléré absent en pré-auth) ---
    resume_url = (data.get("resume_url") or "").strip()
    if resume_url and "REPLACE" not in resume_url and resume_url != "FILLED_AFTER_AUTH":
        url_ok = bool(re.match(r"https://irisbox\.irisnet\.be/.+/edit/[0-9a-f]+/\w+", resume_url))
        report("resume_url_format", url_ok,
               "" if url_ok else
               f"resume_url suspect '{resume_url[:80]}' — attendu l'url de l'event form_reached")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    args = parser.parse_args()

    try:
        data = json.loads(args.data.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"check": "input_json_parse", "ok": False, "detail": str(e)[:200]}))
        sys.exit(1)

    validate(data)
    ok = not ERRORS
    print(json.dumps({"validation": "READY" if ok else "BLOCKED",
                      "errors": ERRORS}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
