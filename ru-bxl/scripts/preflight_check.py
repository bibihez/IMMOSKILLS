"""Préflight RU — vérifie que les sélecteurs IRISbox critiques existent AVANT
d'engager l'utilisateur (itsme = 44s de son temps). Headless, ~20s, zéro auth.

    python3 preflight_check.py                     # surface publique (landing)
    python3 preflight_check.py --session /tmp/X --draft-url <url>   # + pages authées

Sortie : une ligne JSON par check {check, ok, detail}. Exit 0 = tout vert,
exit 1 = au moins une dérive → lancer dump_*_page.py et patcher _selectors.py
AVANT la session avec l'utilisateur."""
import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from _selectors import (
    DIALOG_AUTH_CONNECT_RE,
    LANDING_COMM_MODAL_CLOSE_SELECTOR,
    LANDING_COMM_MODAL_SELECTOR,
    LANDING_CTA_NAME,
    MOBILE_CONTEXT,
    URL_LANDING,
)

RESULTS = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(ok)
    print(json.dumps({"check": name, "ok": ok, "detail": detail}, ensure_ascii=False),
          flush=True)


def dismiss_comm_modal(page) -> bool:
    try:
        if not page.locator(LANDING_COMM_MODAL_SELECTOR).first.is_visible(timeout=2500):
            return False
        page.locator(LANDING_COMM_MODAL_CLOSE_SELECTOR).first.click(timeout=3000)
        page.locator(LANDING_COMM_MODAL_SELECTOR).first.wait_for(state="hidden", timeout=5000)
        return True
    except Exception:
        return False


def preflight_public(page) -> None:
    page.goto(URL_LANDING, wait_until="domcontentloaded", timeout=30000)
    check("landing_loads", "urban-information" in page.url, page.url)

    dismissed = dismiss_comm_modal(page)

    # ⚠️ La modale apparaît parfois ~3s après le load → retry clic + re-dismiss
    cta = page.get_by_role("link", name=LANDING_CTA_NAME).first
    try:
        cta.wait_for(state="visible", timeout=8000)
        try:
            cta.click(timeout=5000)
        except Exception:
            dismissed = dismiss_comm_modal(page) or dismissed
            cta.click(timeout=8000)
        check("comm_modal_handled", True, "dismissed" if dismissed else "not present")
        check("landing_cta_clickable", True)
    except Exception as e:
        check("comm_modal_handled", True, "dismissed" if dismissed else "not present")
        check("landing_cta_clickable", False, str(e)[:150])
        return

    # Session valide → le CTA navigue direct vers /requester (pas de dialogue d'auth).
    try:
        dialog = page.get_by_role("dialog")
        dialog.get_by_role("button", name=DIALOG_AUTH_CONNECT_RE).wait_for(timeout=8000)
        check("auth_dialog_or_logged_in", True, "auth dialog shown")
    except Exception:
        if "/citizen/" in page.url or "/requester" in page.url:
            check("auth_dialog_or_logged_in", True, "session valide, navigation directe")
        else:
            check("auth_dialog_or_logged_in", False, f"ni dialog ni form: {page.url}")


def preflight_authed(page, draft_url: str) -> None:
    """Vérifie les IDs stables des étapes sur un draft existant (session valide requise)."""
    page.goto(draft_url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("#next", state="visible", timeout=15000)
        check("draft_page_boots", True)
    except Exception:
        check("draft_page_boots", False, "session expirée ou draft inaccessible")
        return
    dismiss_comm_modal(page)

    building_url = draft_url.rsplit("/", 1)[0] + "/building"
    page.goto(building_url, wait_until="domcontentloaded", timeout=30000)
    try:
        page.wait_for_selector("#next", state="visible", timeout=15000)
    except Exception:
        pass
    dismiss_comm_modal(page)
    for sel, name in [
        ("#land-area", "step2_land_radio"),
        ("#building-area", "step2_building_radio"),
        ("#building-add", "step2_add_construction"),
    ]:
        present = page.locator(sel).count() > 0
        check(name, present, sel)

    # Localisation : draft vierge → #address-select ; parcelle déjà ajoutée →
    # bouton "Modifier l'adresse". L'un des deux doit exister.
    has_add = page.locator("#address-select").count() > 0
    has_edit = page.get_by_role("button", name="Modifier l'adresse").count() > 0
    check("step2_localisation_entry", has_add or has_edit,
          "address-select" if has_add else ("modifier-adresse" if has_edit else "aucun"))

    # Modale localisation : ouvrable seulement sur draft vierge (sans toucher au draft)
    if has_add:
        try:
            page.locator("#address-select").click(timeout=5000)
            page.wait_for_selector("#capa-key-finder", state="visible", timeout=8000)
            for sel, name in [
                ("#capa-key-finder", "map_capakey_input"),
                ("#addr-map-finder", "map_addr_input"),
                ("#search-capa-key", "map_search_capakey"),
                ("#save-map", "map_confirm"),
            ]:
                check(name, page.locator(sel).count() > 0, sel)
            page.locator("#cancel-map").click(timeout=3000)
        except Exception as e:
            check("map_modal_opens", False, str(e)[:150])
    else:
        check("map_modal_opens", True, "skip — parcelle déjà présente sur ce draft")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", type=Path, help="Dossier session (storage_state.json)")
    parser.add_argument("--draft-url", help="URL d'un draft existant pour les checks authés")
    args = parser.parse_args()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        state = None
        if args.session and (args.session / "storage_state.json").is_file():
            state = str(args.session / "storage_state.json")
        ctx = browser.new_context(storage_state=state, **MOBILE_CONTEXT)
        page = ctx.new_page()
        preflight_public(page)
        if state and args.draft_url:
            preflight_authed(page, args.draft_url)
        ctx.close()
        browser.close()

    ok = all(RESULTS)
    print(json.dumps({"preflight": "GREEN" if ok else "DRIFT_DETECTED",
                      "checks": len(RESULTS), "failed": RESULTS.count(False)}))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
