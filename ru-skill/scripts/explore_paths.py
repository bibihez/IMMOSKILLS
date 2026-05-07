#!/usr/bin/env python3
"""
explore_paths.py — Cartographie exhaustive des paths conditionnels d'IRISbox.

Charge le draft existant via storage_state, navigue vers une étape, exécute
une séquence d'actions pour révéler les champs cachés (radios, dropdowns,
modals), puis dump tout l'inventaire DOM dans un fichier JSON.

Usage:
    python explore_paths.py --session /tmp/ru-test --draft-id <hex> \\
                            --path mandataire | terrain_nu | unit_destinations \\
                                  | multi_parcelle | multi_construction

Sorties :
    /tmp/ru-test/paths/<path_name>.json     (dump structuré)
    /tmp/ru-test/paths/<path_name>.png      (screenshot full page)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

from _selectors import MOBILE_CONTEXT


def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return f"<err {type(e).__name__}: {str(e)[:120]}>"


def dump_buttons(page):
    items = []
    for b in page.get_by_role("button").all():
        try:
            if b.is_visible(timeout=200):
                items.append({
                    "name": (b.inner_text(timeout=300) or "").strip()[:120],
                    "id": b.get_attribute("id"),
                    "class": (b.get_attribute("class") or "")[:80],
                    "aria-label": b.get_attribute("aria-label"),
                    "aria-expanded": b.get_attribute("aria-expanded"),
                })
        except Exception:
            pass
    return items


def dump_inputs(page):
    items = []
    for inp in page.locator("input, select, textarea").all():
        try:
            if inp.is_visible(timeout=200):
                tag = inp.evaluate("el => el.tagName.toLowerCase()")
                item = {
                    "tag": tag,
                    "id": inp.get_attribute("id"),
                    "name": inp.get_attribute("name"),
                    "type": inp.get_attribute("type"),
                    "placeholder": inp.get_attribute("placeholder"),
                    "value": safe(lambda: inp.input_value(timeout=200)),
                    "required": inp.get_attribute("required") is not None,
                    "checked": inp.get_attribute("checked") is not None,
                }
                # Pour les <select>, lister les options
                if tag == "select":
                    options = inp.evaluate("""el => Array.from(el.options).map(o => ({
                        value: o.value, text: o.text, selected: o.selected
                    }))""")
                    item["options"] = options
                items.append(item)
        except Exception:
            pass
    return items


def dump_headings(page):
    items = []
    for h in page.locator("h1, h2, h3, h4, h5, h6").all():
        try:
            if h.is_visible(timeout=200):
                items.append({
                    "tag": h.evaluate("el => el.tagName.toLowerCase()"),
                    "text": (h.inner_text(timeout=300) or "").strip()[:200],
                    "id": h.get_attribute("id"),
                })
        except Exception:
            pass
    return items


def dump_radios_grouped(page):
    """Dump radios groupés par name (pour identifier les options par question)."""
    radios = {}
    for r in page.locator("input[type=radio]").all():
        try:
            name = r.get_attribute("name") or "_unnamed"
            if name not in radios:
                radios[name] = []
            # Trouver le label associé (parent ou aria-labelledby ou label[for=id])
            rid = r.get_attribute("id")
            label_text = ""
            if rid:
                try:
                    label = page.locator(f"label[for='{rid}']").first
                    if label.is_visible(timeout=100):
                        label_text = (label.inner_text(timeout=300) or "").strip()[:120]
                except Exception:
                    pass
            radios[name].append({
                "id": rid,
                "value": r.get_attribute("value"),
                "checked": r.is_checked(),
                "label": label_text,
            })
        except Exception:
            pass
    return radios


def full_dump(page, label):
    return {
        "label": label,
        "url": page.url,
        "headings": dump_headings(page),
        "buttons": dump_buttons(page),
        "inputs": dump_inputs(page),
        "radios_grouped": dump_radios_grouped(page),
    }


def navigate_and_wait(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=20000)
    try:
        page.wait_for_selector("#next", state="visible", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(1000)


# ─────────────── Path explorers ───────────────

def explore_mandataire(page, base_url) -> list[dict]:
    """Click 'Non' propriétaire, sélectionne quality=Agent immobilier,
    puis click '#add' pour ouvrir le modal intervenant et dump sa structure."""
    snapshots = []

    navigate_and_wait(page, f"{base_url}/requester")
    snapshots.append(full_dump(page, "step1_initial"))

    # Click "Non" propriétaire (selectors stables)
    try:
        page.locator("#isLandlordNo").check(force=True)
        page.wait_for_timeout(1500)
    except Exception as e:
        snapshots.append({"label": "step1_click_non_FAILED", "error": str(e)[:200]})
        return snapshots
    snapshots.append(full_dump(page, "step1_after_non"))

    # Sélectionner quality=REAL_ESTATE_AGENT pour activer le bouton Ajouter
    try:
        page.locator("#quality").select_option(value="REAL_ESTATE_AGENT")
        page.wait_for_timeout(1500)
        snapshots.append(full_dump(page, "step1_after_quality_selected"))
    except Exception as e:
        snapshots.append({"label": "step1_select_quality_FAILED", "error": str(e)[:200]})
        return snapshots

    # Click le bouton "Ajouter" de la section intervenants (#add)
    try:
        page.locator("#add").click(force=True)
        page.wait_for_timeout(2000)
        snapshots.append(full_dump(page, "step1_intervenant_modal_opened"))
        # Si une dialog est visible, dump son contenu spécifique
        try:
            dialogs = page.get_by_role("dialog").all()
            for d in dialogs:
                if d.is_visible(timeout=300):
                    snapshots.append({
                        "label": "step1_intervenant_modal_inner",
                        "modal_text_first_500": (d.inner_text(timeout=1000) or "")[:500],
                        "modal_inputs": dump_inputs(d),
                        "modal_radios": dump_radios_grouped(d),
                        "modal_buttons": dump_buttons(d),
                    })
                    break
        except Exception:
            pass
        # Fermer le modal sans sauvegarder
        try:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
        except Exception:
            pass
    except Exception as e:
        snapshots.append({"label": "step1_ajouter_intervenant_FAILED", "error": str(e)[:200]})

    return snapshots


def explore_terrain_nu(page, base_url) -> list[dict]:
    """Click radio 'terrain non-bâti' → dump les champs résultants."""
    snapshots = []
    navigate_and_wait(page, f"{base_url}/building")
    snapshots.append(full_dump(page, "step2_initial_construction_state"))
    try:
        page.locator("#land-area").check(force=True)
        page.wait_for_timeout(1500)
    except Exception as e:
        snapshots.append({"label": "click_land_FAILED", "error": str(e)[:200]})
        return snapshots
    snapshots.append(full_dump(page, "step2_after_terrain_nu"))
    return snapshots


def explore_unit_destinations(page, base_url) -> list[dict]:
    """Ouvre le modal 'Ajouter une unité' et dump le dropdown destinations
    + check si chaque destination ouvre des sous-champs spécifiques."""
    snapshots = []
    navigate_and_wait(page, f"{base_url}/building")
    # S'assurer construction est sélectionnée
    try:
        page.locator("#building-area").check(force=True)
        page.wait_for_timeout(1500)
    except Exception:
        pass
    # Force expand de l'accordion construction si présent (sinon #add-area-unit absent)
    try:
        toggles = page.locator("button.accordion-toggle").all()
        for t in toggles:
            try:
                if t.get_attribute("aria-expanded") == "false":
                    t.click(force=True)
                    page.wait_for_timeout(800)
            except Exception:
                pass
    except Exception:
        pass
    snapshots.append({"label": "before_open_unit_modal",
                      "add_area_unit_visible": safe(
                          lambda: page.locator("#add-area-unit").is_visible(timeout=2000))})
    # Click "Ajouter une unité"
    try:
        page.locator("#add-area-unit").wait_for(state="visible", timeout=10000)
        page.locator("#add-area-unit").click(force=True)
        page.wait_for_timeout(1500)
    except Exception as e:
        snapshots.append({"label": "open_unit_modal_FAILED", "error": str(e)[:200]})
        return snapshots
    snapshots.append(full_dump(page, "unit_modal_initial"))

    # Récupérer toutes les options du select destination
    try:
        dest_options = page.locator("#destination").evaluate(
            "el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))")
        snapshots.append({"label": "unit_destination_options", "options": dest_options})
    except Exception as e:
        snapshots.append({"label": "destination_dropdown_FAILED", "error": str(e)[:200]})

    # Pour chaque destination, sélectionner et dump les inputs/radios visibles
    # (peut révéler des champs conditionnels, ex: superficie pour Commerce)
    try:
        all_dest = page.locator("#destination").evaluate(
            "el => Array.from(el.options).map(o => o.text).filter(t => t)")
        for dest_text in all_dest[:9]:  # 9 destinations connues max
            try:
                page.locator("#destination").select_option(label=dest_text)
                page.wait_for_timeout(600)
                snapshots.append({
                    "label": f"unit_modal_after_destination_{dest_text}",
                    "inputs_in_modal": dump_inputs(page),
                    "radios_in_modal": dump_radios_grouped(page),
                })
            except Exception as e:
                snapshots.append({
                    "label": f"select_dest_{dest_text}_FAILED",
                    "error": str(e)[:200],
                })
    except Exception as e:
        snapshots.append({"label": "iterate_destinations_FAILED", "error": str(e)[:200]})

    # Fermer le modal sans sauvegarder
    try:
        page.locator("#close-area-modal").click(force=True)
        page.wait_for_timeout(500)
    except Exception:
        pass

    return snapshots


def explore_multi_parcelle(page, base_url) -> list[dict]:
    """Click 'Ajouter une zone géographique' une 2e fois pour voir le comportement multi-parcelles."""
    snapshots = []
    navigate_and_wait(page, f"{base_url}/building")
    snapshots.append(full_dump(page, "before_add_2nd_parcelle"))
    try:
        # Le bouton est nommé "Ajouter une zone géographique"
        btn = page.get_by_role("button", name=re.compile(r"Ajouter une zone", re.I)).first
        btn.click(force=True)
        page.wait_for_timeout(1500)
    except Exception as e:
        snapshots.append({"label": "click_add_zone_FAILED", "error": str(e)[:200]})
        return snapshots
    snapshots.append(full_dump(page, "modal_2nd_parcelle_opened"))
    # Fermer le modal sans sauvegarder
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass
    return snapshots


def explore_multi_construction(page, base_url) -> list[dict]:
    """Click 'Ajouter une construction' une 2e fois pour voir le comportement multi-constructions."""
    snapshots = []
    navigate_and_wait(page, f"{base_url}/building")
    # S'assurer construction est sélectionnée
    try:
        page.locator("#building-area").check(force=True)
        page.wait_for_timeout(800)
    except Exception:
        pass
    snapshots.append(full_dump(page, "before_add_2nd_construction"))
    try:
        page.locator("#building-add").click(force=True)
        page.wait_for_timeout(1500)
    except Exception as e:
        snapshots.append({"label": "click_add_construction_FAILED", "error": str(e)[:200]})
        return snapshots
    snapshots.append(full_dump(page, "modal_2nd_construction_opened"))
    # Fermer le modal sans sauvegarder
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass
    return snapshots


PATH_EXPLORERS = {
    "mandataire": explore_mandataire,
    "terrain_nu": explore_terrain_nu,
    "unit_destinations": explore_unit_destinations,
    "multi_parcelle": explore_multi_parcelle,
    "multi_construction": explore_multi_construction,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--path", required=True, choices=list(PATH_EXPLORERS.keys()) + ["all"])
    parser.add_argument("--keep-open", action="store_true",
                        help="Leave browser open after exploration (Ctrl+C to close)")
    args = parser.parse_args()

    storage = args.session / "storage_state.json"
    if not storage.is_file():
        print(f"storage_state.json not found at {storage}", file=sys.stderr)
        sys.exit(3)

    out_dir = args.session / "paths"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_url = f"https://irisbox.irisnet.be/irisbox/urban-information/citizen/edit/{args.draft_id}"
    paths_to_run = list(PATH_EXPLORERS.keys()) if args.path == "all" else [args.path]

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        ctx = browser.new_context(**MOBILE_CONTEXT, storage_state=str(storage))
        page = ctx.new_page()

        try:
            for path_name in paths_to_run:
                print(f"\n>>> Exploring: {path_name}", flush=True)
                snapshots = PATH_EXPLORERS[path_name](page, base_url)
                out_json = out_dir / f"{path_name}.json"
                out_json.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
                # Screenshot état final
                shot_path = out_dir / f"{path_name}.png"
                try:
                    page.screenshot(path=str(shot_path), full_page=True)
                except Exception:
                    pass
                print(f"<<< Done {path_name} → {out_json}", flush=True)
        finally:
            if args.keep_open:
                print("\n[browser kept open — Ctrl+C to close]", flush=True)
                try:
                    while True:
                        time.sleep(60)
                except KeyboardInterrupt:
                    pass
            browser.close()


if __name__ == "__main__":
    main()
