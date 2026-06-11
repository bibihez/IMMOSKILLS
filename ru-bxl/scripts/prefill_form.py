#!/usr/bin/env python3
"""
prefill_form.py — Phase 2 du flow RU Bxl.

Reprend la session sauvegardée par auth_irisbox.py (via storage_state.json),
remplit les étapes 1-3 du formulaire IRISbox, uploade les documents, et
stoppe au draft. Ne clique JAMAIS Send.

Usage:
    python prefill_form.py --session /tmp/ru-session-abc --data input.json [--include-summary]

Stream JSON sur stdout. Codes de sortie:
    0  succès (draft_ready émis)
    1  validation_error non récupérable (champ obligatoire manquant)
    2  IRISbox indisponible / session expirée
    3  storage_state introuvable
    4  input invalide
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import (
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from _selectors import (
    DOC_AUTRE,
    DOC_COPIE_MANDAT,
    DOC_CROQUIS_PLANS,
    DOC_MATRICE_CADASTRALE,
    DOC_PLAN_PARCELLAIRE,
    DOC_REPORTAGE_PHOTO,
    DOC_TITRE_PROPRIETE,
    DOC_UPLOAD_BUTTON_ID_BY_LABEL,
    INTERVENANT_BOX_ID,
    INTERVENANT_CITY_ID,
    INTERVENANT_COUNTRY_ID,
    INTERVENANT_EMAIL_ID,
    INTERVENANT_FIRSTNAME_ID,
    INTERVENANT_LASTNAME_ID,
    INTERVENANT_PHONE_ID,
    INTERVENANT_SAVE_BUTTON_ID,
    INTERVENANT_STREET_NAME_ID,
    INTERVENANT_STREET_NUMBER_ID,
    INTERVENANT_QUALITY_LANDLORD,
    INTERVENANT_TYPE_MORAL_RADIO_ID,
    INTERVENANT_TYPE_PHYSICAL_RADIO_ID,
    INTERVENANT_ZIPCODE_ID,
    LANDING_COMM_MODAL_CLOSE_SELECTOR,
    LANDING_COMM_MODAL_SELECTOR,
    LOCALISATION_ADDR_INPUT_ID,
    LOCALISATION_CAPAKEY_INPUT_ID,
    LOCALISATION_MODAL_SELECTOR,
    LOCALISATION_SAVE_ID,
    LOCALISATION_SEARCH_ADDR_ID,
    LOCALISATION_SEARCH_CAPAKEY_ID,
    MOBILE_CONTEXT,
    QUALITY_REAL_ESTATE_AGENT,
    RE_CAPAKEY,
    RE_DRAFT_REFERENCE,
    STEP1_ADD_INTERVENANT_BUTTON_ID,
    STEP1_LANDLORD_NO_ID,
    STEP1_LANDLORD_YES_ID,
    STEP1_OWNER_NON,
    STEP1_OWNER_OUI,
    STEP1_QUALITY_SELECT_ID,
    STEP2_ADD_CONSTRUCTION_BUTTON,
    STEP2_ADD_UNITE_BUTTON,
    STEP2_ADD_ZONE_BUTTON,
    STEP2_ADD_ZONE_BUTTON_ID,
    STEP2_TOTAL_PARKING_INPUT_ID,
    STEP2_TYPE_CONSTRUCTION_PREFIX,
    STEP2_TYPE_TERRAIN_NU_PREFIX,
    STEP4_OK_TEXT,
    UNITE_DESCRIPTION_TEXTAREA_ID,
    UNITE_DESTINATION_SELECT_ID,
    UNITE_FLOOR_INPUT_ID,
    UNITE_SAVE_BUTTON_ID,
    URL_PATTERN_STEP,
)

# Map de la clé `documents.<key>` du JSON vers le label IRISbox exact
DOC_LABEL_BY_KEY = {
    "titre_propriete": DOC_TITRE_PROPRIETE,
    "mandat": DOC_COPIE_MANDAT,
    "reportage": DOC_REPORTAGE_PHOTO,
    "croquis": DOC_CROQUIS_PLANS,
    "plan_parcellaire": DOC_PLAN_PARCELLAIRE,
    "matrice_cadastrale": DOC_MATRICE_CADASTRALE,
    "autre": DOC_AUTRE,
}


def emit(event: str, **payload: Any) -> None:
    line = json.dumps({"event": event, "ts": time.time(), **payload}, ensure_ascii=False)
    print(line, flush=True)


def emit_error_and_exit(code: int, message: str, **extra: Any) -> None:
    emit("error", code=code, message=message, **extra)
    sys.exit(code)


def force_french_ui(page: Page) -> None:
    fr_button = page.get_by_role("button", name="fr").first
    if fr_button.is_visible():
        fr_button.click()
        page.wait_for_load_state("networkidle", timeout=5000)


def check_session_expired(page: Page, step: str) -> None:
    """IRISbox affiche 'Session expirée' dans le body si CSAM/itsme cookies expirés.
    Détection précoce → exit code 2 propre plutôt que faire échouer un locator plus loin."""
    body_snippet = page.locator("body").inner_text(timeout=3000)
    if "Session expirée" in body_snippet or "Session expired" in body_snippet:
        emit_error_and_exit(2, "IRISbox session expired — re-run auth_irisbox.py",
                            step=step, url=page.url)


def collect_validation_errors(page: Page) -> list[dict]:
    """Scrape les messages de validation visibles + inputs is-invalid."""
    errors: list[dict] = []
    try:
        for fb in page.locator(".invalid-feedback, .error-message, [role='alert']").all():
            try:
                if fb.is_visible(timeout=300):
                    txt = fb.inner_text(timeout=500).strip()
                    if txt:
                        errors.append({"type": "feedback", "text": txt[:200]})
            except Exception:
                pass
    except Exception:
        pass
    try:
        for inp in page.locator("input.is-invalid, select.is-invalid, textarea.is-invalid").all():
            try:
                errors.append({
                    "type": "invalid_input",
                    "id": inp.get_attribute("id"),
                    "name": inp.get_attribute("name"),
                    "value": inp.input_value(timeout=300),
                })
            except Exception:
                pass
    except Exception:
        pass
    return errors


def dismiss_communication_modal(page: Page) -> None:
    """IRISbox affiche une modale d'annonce ('Information', communication-modal) au
    chargement de ses pages (y compris /requester sur un nouveau contexte). Elle
    intercepte le clic sur #next (modal-container intercepts pointer events).
    Best-effort : ferme-la si présente, ne bloque pas si absente."""
    try:
        modal = page.locator(LANDING_COMM_MODAL_SELECTOR).first
        if not modal.is_visible(timeout=800):
            return
    except Exception:
        return
    try:
        close_btn = page.locator(LANDING_COMM_MODAL_CLOSE_SELECTOR).first
        if close_btn.is_visible(timeout=1000):
            close_btn.click(timeout=3000)
    except Exception:
        pass
    try:
        if page.locator(LANDING_COMM_MODAL_SELECTOR).first.is_visible(timeout=500):
            page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        page.locator(LANDING_COMM_MODAL_SELECTOR).first.wait_for(state="hidden", timeout=5000)
        emit("communication_modal_dismissed")
    except Exception:
        emit("communication_modal_dismiss_failed")


def click_next(page: Page, step: str) -> None:
    """Click le bouton Suivant. Si disabled, scrape les erreurs de validation
    et exit avec code 1 + détails. Si enabled mais intercepté par overlay,
    fallback sur force=True."""
    # La modale d'annonce IRISbox peut réapparaître à chaque page → la fermer
    # avant tout clic Suivant pour ne pas faire échouer la navigation.
    dismiss_communication_modal(page)
    next_btn = page.locator("#next")
    next_btn.wait_for(state="visible", timeout=5000)
    if next_btn.is_disabled():
        errors = collect_validation_errors(page)
        emit_error_and_exit(1, f"step '{step}': Suivant button disabled — validation blocked",
                            step=step, validation_errors=errors)
    try:
        next_btn.click(timeout=3000)
    except PlaywrightTimeoutError:
        # La modale d'annonce peut apparaître ~3s après le load (course de timing).
        # Re-dismiss + retry normal AVANT le force : force=True "traverse" la modale
        # sans effet et masque le vrai problème.
        dismiss_communication_modal(page)
        try:
            next_btn.click(timeout=3000)
        except PlaywrightTimeoutError:
            # Overlay mobile (ectz-shortcut, stakeholder-list) — dernier recours
            emit("click_next_fallback_force", step=step)
            next_btn.click(force=True)


def click_button_force(page: Page, name: str) -> None:
    """Click un bouton par accessible name avec force=True."""
    page.get_by_role("button", name=name).first.click(force=True)


def fill_step1_demandeur(page: Page, data: dict) -> None:
    """Étape 1 : Demandeur.

    Path 1 (is_owner=True, rare) : check #isLandlordYes, click Next.
    Path 2 (is_owner=False, 95% agents immo) :
        - check #isLandlordNo
        - select #quality (REAL_ESTATE_AGENT default)
        - pour chaque intervenant fourni : add_intervenant()
        - click Next
    """
    check_session_expired(page, "requester")
    is_owner = data.get("is_owner", True)

    if is_owner:
        page.locator(f"#{STEP1_LANDLORD_YES_ID}").check(force=True)
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        emit("step1_owner_radio_checked", is_owner=True)
    else:
        page.locator(f"#{STEP1_LANDLORD_NO_ID}").check(force=True)
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        emit("step1_owner_radio_checked", is_owner=False)

        # Sélection du rôle (default = Agent immobilier pour ImmoClaw)
        quality = data.get("quality", QUALITY_REAL_ESTATE_AGENT)
        quality_select = page.locator(f"#{STEP1_QUALITY_SELECT_ID}")
        try:
            quality_select.wait_for(state="visible", timeout=5000)
            current = quality_select.input_value()
            if current != quality:
                quality_select.select_option(value=quality)
                emit("step1_quality_selected", quality=quality)
            else:
                emit("step1_quality_already_set", quality=quality)
        except PlaywrightTimeoutError:
            emit_error_and_exit(1, "step1: #quality select not visible after isLandlordNo",
                                expected_quality=quality)

        # Ajouter chaque intervenant (idempotent : skip si déjà présent)
        intervenants = data.get("intervenants", [])
        if not intervenants:
            emit_error_and_exit(1, "step1: is_owner=false but no intervenants provided",
                                hint="data.intervenants must list at least 1 owner")
        for interv in intervenants:
            first_name = interv.get("firstName", "")
            last_name = interv.get("lastName", "")
            full_name = f"{first_name} {last_name}".strip()
            if _intervenant_already_present(page, first_name, last_name):
                emit("intervenant_already_present", name=full_name)
                continue
            add_intervenant(page, interv)
            emit("intervenant_added", name=full_name, type=interv.get("type", "PHYSICAL"))

    click_next(page, "requester")
    try:
        page.wait_for_url(URL_PATTERN_STEP["building"], timeout=15000)
    except PlaywrightTimeoutError:
        # Draft déjà avancé : l'étape 1 est validée côté serveur, le clic Suivant
        # ne déclenche pas la navigation (radio/champs déjà "soumis"). On navigue
        # directement vers /building — autorisé une fois l'étape franchie.
        if URL_PATTERN_STEP["requester"].search(page.url):
            building_url = re.sub(r"/requester(?=[/?#]|$)", "/building", page.url)
            emit("step1_advanced_draft_direct_nav", to=building_url)
            page.goto(building_url, wait_until="domcontentloaded")
            dismiss_communication_modal(page)
            page.wait_for_selector("#next", state="visible", timeout=15000)
        else:
            raise
    emit("step_completed", **{"from": "requester", "to": "building"})


def _intervenant_already_present(page: Page, first_name: str, last_name: str) -> bool:
    """Cherche l'intervenant dans la table 'Liste des intervenants'.
    ⚠️ La table a Prénom et Nom dans des cellules SÉPARÉES : chercher le nom
    complet comme un seul texte ne matche jamais (→ doublons à chaque re-run).
    On cherche donc une LIGNE contenant à la fois le prénom et le nom."""
    last_name = (last_name or "").strip()
    first_name = (first_name or "").strip()
    if not last_name:
        return False
    try:
        rows = page.locator("tr, [role=row]").filter(has_text=last_name)
        for i in range(rows.count()):
            txt = rows.nth(i).inner_text(timeout=300)
            if last_name in txt and (not first_name or first_name in txt):
                return True
        return False
    except Exception:
        return False


def add_intervenant(page: Page, interv: dict) -> None:
    """Click #add → IRISbox NAVIGUE vers /stakeholder/add (route dédiée, pas modal).
    Remplit type + rôle (#quality avec option LANDLORD pour propriétaires) +
    identité + adresse, puis #save-stakeholder → IRISbox renvoie sur /requester.

    interv schema (PHYSICAL) :
        {"type": "PHYSICAL",                            # default
         "role": "LANDLORD",                            # default = Propriétaire
         "firstName": str, "lastName": str,             # required
         "email": str, "phone": str,                    # optional
         "streetName": str, "streetNumber": str,        # required
         "box": str,                                    # optional
         "zipCode": str, "city": str, "country": str}   # required (country default Belgique)
    """
    interv_type = interv.get("type", "PHYSICAL")
    if interv_type == "MORAL":
        emit_error_and_exit(1, "intervenant type=MORAL not implemented yet",
                            hint="dump required: re-run watch_explore on /stakeholder/add "
                                 "with #moral-people checked")

    page.locator(f"#{STEP1_ADD_INTERVENANT_BUTTON_ID}").click(force=True)
    # IRISbox navigue vers /stakeholder/add — attendre l'URL ET le champ
    page.wait_for_url(re.compile(r"/stakeholder/add"), timeout=10000)
    page.wait_for_selector(f"#{INTERVENANT_FIRSTNAME_ID}", state="visible", timeout=10000)

    # Type physique (force pour garantir le default même si MORAL était sélectionné avant)
    page.locator(f"#{INTERVENANT_TYPE_PHYSICAL_RADIO_ID}").check(force=True)
    page.wait_for_timeout(300)

    # Rôle (REQUIRED) — sur /stakeholder/add, #quality a 5 options dont LANDLORD
    role = interv.get("role", INTERVENANT_QUALITY_LANDLORD)
    page.locator(f"#{STEP1_QUALITY_SELECT_ID}").select_option(value=role)

    # Champs required
    page.locator(f"#{INTERVENANT_FIRSTNAME_ID}").fill(interv["firstName"])
    page.locator(f"#{INTERVENANT_LASTNAME_ID}").fill(interv["lastName"])
    page.locator(f"#{INTERVENANT_STREET_NAME_ID}").fill(interv["streetName"])
    page.locator(f"#{INTERVENANT_STREET_NUMBER_ID}").fill(str(interv["streetNumber"]))
    page.locator(f"#{INTERVENANT_ZIPCODE_ID}").fill(str(interv["zipCode"]))
    page.locator(f"#{INTERVENANT_CITY_ID}").fill(interv["city"])
    page.locator(f"#{INTERVENANT_COUNTRY_ID}").fill(interv.get("country", "Belgique"))

    # Champs optionnels
    if interv.get("box"):
        page.locator(f"#{INTERVENANT_BOX_ID}").fill(str(interv["box"]))
    if interv.get("email"):
        page.locator(f"#{INTERVENANT_EMAIL_ID}").fill(interv["email"])
    if interv.get("phone"):
        page.locator(f"#{INTERVENANT_PHONE_ID}").fill(str(interv["phone"]))

    page.locator(f"#{INTERVENANT_SAVE_BUTTON_ID}").click(force=True)
    # IRISbox renvoie sur /requester avec la nouvelle ligne dans la liste intervenants
    page.wait_for_url(URL_PATTERN_STEP["requester"], timeout=10000)
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except PlaywrightTimeoutError:
        pass


def _check_radio_reliably(page: Page, selector: str, attempts: int = 3) -> None:
    """Coche un radio Angular de façon fiable. check(force=True) peut cliquer dans
    le vide (backdrop de modale en cours de fade → 'did not change its state').
    Stratégie : check normal → vérif is_checked → retry → dernier recours clic JS
    (déclenche les handlers Angular, insensible aux overlays)."""
    radio = page.locator(selector)
    for _ in range(attempts):
        try:
            radio.check(timeout=4000)
        except Exception:
            pass
        try:
            if radio.is_checked():
                return
        except Exception:
            pass
        page.wait_for_timeout(600)
    radio.evaluate("el => el.click()")
    page.wait_for_timeout(300)
    if not radio.is_checked():
        emit_error_and_exit(1, f"radio {selector} refuse de se cocher (3 retries + clic JS)")


def fill_step2_bien(page: Page, data: dict) -> None:
    """Étape 2 : Bien.

    Path 1 (type=construction, dominant) : ajoute parcelle + N constructions + N unités/construction.
    Path 2 (type=terrain_nu) : ajoute parcelle + saute la section constructions.
        Note dump 2026-05-06 : `#add-area-unit` reste visible même en LAND, mais on
        n'ajoute des unités que si data en fournit explicitement (cas rare).
    """
    check_session_expired(page, "building")

    # Idempotent: si une parcelle est déjà ajoutée au draft, skip le modal Localisation
    has_parcelle = page.get_by_role("button", name="Modifier l'adresse").count() > 0
    if not has_parcelle:
        _add_parcelle(page, data)
        emit("parcelle_added", capakey=data.get("cadastral_reference"))
    else:
        emit("parcelle_already_present")

    bien_type = data.get("type", "construction")
    if bien_type == "terrain_nu":
        # Path LAND — utilise l'ID stable au lieu du label texte (FR/EN tolérant)
        _check_radio_reliably(page, "#land-area")
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        emit("step2_type_set", type="terrain_nu")

        # Sur LAND, pas de constructions. Optionnellement ajouter des unités directement
        # (dump 2026-05-06 : #add-area-unit visible aussi en mode LAND).
        for unit in data.get("units", []):  # noter: data.units, pas data.constructions
            if _unit_already_present(page, unit):
                emit("unit_already_present", floor=unit["floor"],
                     destination=unit["destination"])
                continue
            add_unit(page, unit)
            emit("unit_added", floor=unit["floor"], destination=unit["destination"])
    else:
        # Path BUILDING (default)
        _check_radio_reliably(page, "#building-area")
        try:
            page.wait_for_load_state("networkidle", timeout=3000)
        except PlaywrightTimeoutError:
            pass
        emit("step2_type_set", type="construction")

        # Idempotent: pour chaque construction, ajoute-la si pas déjà présente comme tab,
        # PUIS dans tous les cas vérifie ses unités (un re-run après crash peut avoir
        # créé la construction sans avoir eu le temps d'ajouter ses unités)
        for c in data.get("constructions", []):
            tab_present = _construction_tab_exists(page, c["denomination"])
            if not tab_present:
                add_construction_only(page, c)
                emit("construction_added", denomination=c["denomination"])
            else:
                emit("construction_already_present", denomination=c["denomination"])

            # Sélectionne le tab de cette construction puis ajoute les unités manquantes
            _select_construction_tab(page, c["denomination"])
            for unit in c.get("units", []):
                if _unit_already_present(page, unit):
                    emit("unit_already_present", floor=unit["floor"],
                         destination=unit["destination"])
                    continue
                add_unit(page, unit)
                emit("unit_added", floor=unit["floor"], destination=unit["destination"])

    parking_value = str(data.get("parking_count", 0))
    page.locator(f"#{STEP2_TOTAL_PARKING_INPUT_ID}").fill(parking_value)
    emit("parking_filled", value=parking_value)

    click_next(page, "building")
    page.wait_for_url(URL_PATTERN_STEP["documents"], timeout=15000)
    emit("step_completed", **{"from": "building", "to": "documents"})


def _construction_tab_exists(page: Page, denomination: str) -> bool:
    """Cherche un tab dont le texte contient la dénomination."""
    try:
        for t in page.get_by_role("tab").all():
            try:
                if denomination in t.inner_text(timeout=500):
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _select_construction_tab(page: Page, denomination: str) -> bool:
    """S'assure que le panel accordion de la construction `denomination` est expanded.
    Sur IRISbox 23.0.5 le composant est un BUTTON.accordion-toggle nommé
    'Construction : <denom>' avec attribut aria-expanded.
    Idempotent : ne click QUE si aria-expanded='false'."""
    try:
        toggles = page.locator("button.accordion-toggle").all()
        for t in toggles:
            try:
                txt = (t.inner_text(timeout=400) or "")
                if denomination in txt:
                    if t.get_attribute("aria-expanded") == "false":
                        t.click(force=True)
                        page.wait_for_timeout(500)
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _unit_already_present(page: Page, unit: dict) -> bool:
    """Cherche une ligne de table d'unités matchant (floor, destination).
    IRISbox affiche les unités créées dans une table sous la construction sélectionnée."""
    floor = str(unit["floor"])
    dest = unit["destination"]
    try:
        # Les rows de table contiennent floor + destination concaténés dans le texte
        for row in page.get_by_role("row").all():
            try:
                row_text = row.inner_text(timeout=300)
                if floor in row_text and dest in row_text:
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def _add_parcelle(page: Page, data: dict) -> None:
    """Ouvre la modale 'Localisation du bien' (#mapModal, refonte IRISbox 2026) et
    localise le bien par capakey (dominant) ou adresse autocomplete. IDs stables.
    ⚠️ Le bouton d'ouverture exige un clic NORMAL : force=True ne déclenche pas le
    handler Angular et la modale ne s'ouvre pas."""
    page.locator(f"#{STEP2_ADD_ZONE_BUTTON_ID}").click()
    # La modale monte un textbox capakey (#capa-key-finder) + combobox adresse
    page.wait_for_selector(f"#{LOCALISATION_CAPAKEY_INPUT_ID}", state="visible", timeout=10000)

    capakey = (data.get("cadastral_reference") or "").strip()
    if capakey and RE_CAPAKEY.match(capakey):
        page.locator(f"#{LOCALISATION_CAPAKEY_INPUT_ID}").fill(capakey)
        page.locator(f"#{LOCALISATION_SEARCH_CAPAKEY_ID}").click()
    else:
        address = data.get("address", "").strip()
        if not address:
            emit_error_and_exit(4, "Neither cadastral_reference nor address provided")
        combo = page.locator(f"#{LOCALISATION_ADDR_INPUT_ID}")
        combo.fill(address)
        # Autocomplete : attendre la suggestion bleue puis sélectionner la 1re.
        # Fallback : bouton Rechercher adresse si pas de listbox.
        try:
            page.get_by_role("listbox").wait_for(timeout=5000)
            page.get_by_role("option").first.click()
        except PlaywrightTimeoutError:
            page.locator(f"#{LOCALISATION_SEARCH_ADDR_ID}").click()

    # Confirmer (#save-map) — activé après résolution backend (capakey→parcelle). Poll 10s.
    save = page.locator(f"#{LOCALISATION_SAVE_ID}")
    save.wait_for(state="visible", timeout=10000)
    for _ in range(50):
        if not save.is_disabled():
            break
        page.wait_for_timeout(200)
    else:
        emit_error_and_exit(1, "localisation: Confirmer (#save-map) stayed disabled after 10s",
                            capakey=capakey or None, address=data.get("address"))
    save.click()
    # Modale fermée = bouton Confirmer détaché du DOM
    save.wait_for(state="hidden", timeout=10000)
    # Le backdrop Bootstrap met ~300-500ms à disparaître (fade) APRÈS le contenu de
    # la modale — il avale les clics suivants (radio areaType). Attendre sa fin.
    try:
        page.locator(".modal-backdrop").last.wait_for(state="hidden", timeout=5000)
    except Exception:
        pass


def add_construction_only(page: Page, construction: dict) -> None:
    """Ajoute la construction (dénomination + description) SANS ses unités.
    Les unités sont gérées séparément par fill_step2_bien pour permettre
    une idempotency fine après crash.

    NOTE: après save, IRISbox a besoin de ~2s pour rendre l'accordion +
    `#add-area-unit` dans un état stable. Sans ce wait, le click suivant sur
    `#add-area-unit` redirige parfois vers /dashboard (état serveur instable)."""
    page.get_by_role("button", name=STEP2_ADD_CONSTRUCTION_BUTTON).first.click(force=True)
    modal = page.get_by_role("dialog").filter(has_text="Détails de la construction")
    modal.get_by_role("textbox", name="Dénomination").fill(construction["denomination"])
    modal.get_by_role("textbox", name="Description détaillée").fill(construction["description"])
    modal.get_by_role("button", name="Sauvegarder").click(force=True)
    page.get_by_role("dialog").wait_for(state="hidden", timeout=10000)
    try:
        page.wait_for_load_state("networkidle", timeout=3000)
    except PlaywrightTimeoutError:
        pass
    # Wait fixe pour stabilisation accordion + #add-area-unit côté serveur
    page.wait_for_timeout(2000)


def add_unit(page: Page, unit: dict) -> None:
    """Click le bouton 'Ajouter une unité' (id=add-area-unit) puis remplit le modal.
    Selector ID stable dump_building_page.py 2026-05-05."""
    btn = page.locator("#add-area-unit")
    try:
        btn.wait_for(state="visible", timeout=5000)
    except PlaywrightTimeoutError:
        emit_error_and_exit(1, "add_unit: #add-area-unit not visible — accordion collapsed?",
                            url=page.url)
    btn.click(force=True)
    # Le modal Bootstrap "Détails de l'unité" peut prendre 1-2s à monter ses inputs
    page.wait_for_selector(f"#{UNITE_FLOOR_INPUT_ID}", state="visible", timeout=10000)
    page.locator(f"#{UNITE_FLOOR_INPUT_ID}").fill(str(unit["floor"]))
    page.locator(f"#{UNITE_DESTINATION_SELECT_ID}").select_option(label=unit["destination"])
    if unit.get("description"):
        # `#description` existe aussi côté parent (construction) — scope au modal
        modal = page.get_by_role("dialog").filter(has_text="Détails de l'unité")
        modal.locator(f"#{UNITE_DESCRIPTION_TEXTAREA_ID}").fill(unit["description"])
    page.locator(f"#{UNITE_SAVE_BUTTON_ID}").click(force=True)
    page.wait_for_selector(f"#{UNITE_FLOOR_INPUT_ID}", state="hidden", timeout=10000)


def upload_document(page: Page, label: str, file_path: Path) -> None:
    """Click le bouton d'upload (id=button-upload-RU_<KEY>), set le file via
    file_chooser, attend que le filename apparaisse comme confirmation."""
    button_id = DOC_UPLOAD_BUTTON_ID_BY_LABEL.get(label)
    if not button_id:
        emit_error_and_exit(1, f"upload_document: no button ID known for label '{label}'")
    btn = page.locator(f"#{button_id}")
    btn.wait_for(state="visible", timeout=5000)
    with page.expect_file_chooser() as fc_info:
        btn.click(force=True)
    fc_info.value.set_files(str(file_path))
    # Attente du nom de fichier dans le DOM (signal upload reçu côté serveur)
    page.get_by_text(file_path.name).first.wait_for(timeout=15000)


def fill_step3_documents(page: Page, data: dict) -> None:
    check_session_expired(page, "documents")
    # Force un reload pour vider le cache DOM Angular : sans ça, des filenames
    # résiduels d'uploads invalidés par un retry précédent peuvent skip nos
    # checks d'idempotency (l'upload semble fait côté client mais pas serveur).
    page.reload(wait_until="domcontentloaded")
    try:
        page.wait_for_selector("#next", state="visible", timeout=15000)
    except PlaywrightTimeoutError:
        pass

    docs = data.get("documents") or {}
    titre = docs.get("titre_propriete")
    if not titre:
        emit_error_and_exit(1, "documents.titre_propriete is required")
    # Mandat obligatoire si l'agent n'est pas propriétaire (cf PATHS_MATRIX.md)
    if not data.get("is_owner", True) and not docs.get("mandat"):
        emit_error_and_exit(1, "documents.mandat is required when is_owner=false",
                            hint="Upload le PDF du mandat signé par le propriétaire")

    for key, value in docs.items():
        if not value:
            continue
        label = DOC_LABEL_BY_KEY.get(key)
        if not label:
            emit("validation_error", step="documents", field=key,
                 message=f"unknown document key '{key}'")
            continue
        # IRISbox accepte jusqu'à 10 fichiers/catégorie : string OU liste de paths
        file_paths = value if isinstance(value, list) else [value]
        for file_path_str in file_paths:
            path = Path(file_path_str)
            if not path.is_file():
                emit_error_and_exit(4, f"document file not found: {path}", key=key)
            # Idempotency : skip si le filename est déjà présent dans le DOM
            try:
                existing = page.get_by_text(path.name).first
                if existing.is_visible(timeout=300):
                    emit("document_already_uploaded", category=key, label=label, path=str(path))
                    continue
            except Exception:
                pass
            upload_document(page, label, path)
            emit("document_uploaded", category=key, label=label, path=str(path),
                 size=path.stat().st_size)

    # IRISbox effectue probablement un scan/validation async post-upload avant
    # d'autoriser le passage à /summary. On laisse 3s + log avant click.
    page.wait_for_timeout(3000)
    emit("documents_step_pre_next", url=page.url)

    click_next(page, "documents")
    page.wait_for_url(URL_PATTERN_STEP["summary"], timeout=30000)
    emit("step_completed", **{"from": "documents", "to": "summary"})


def verify_step4_summary(page: Page) -> None:
    """Si activé, vérifie que les 3 sections du récap affichent OK."""
    page.get_by_text(STEP4_OK_TEXT).first.wait_for(timeout=10000)
    ok_count = page.get_by_text(STEP4_OK_TEXT).count()
    if ok_count < 3:
        emit("validation_error", step="summary",
             message=f"only {ok_count}/3 sections complete")


def export_recap_pdf(page: Page, session_dir: Path) -> Path | None:
    """Click #btn-action-export, capture le download du PDF récap, sauve sous
    <session_dir>/recap.pdf. Retourne le path ou None si échec.

    Validé via watch_explore.py 2026-05-06 : génère un PDF complet avec
    référence, intervenants, description bien et liste des documents."""
    pdf_path = session_dir / "recap.pdf"
    try:
        with page.expect_download(timeout=30000) as dl_info:
            page.locator("#btn-action-export").click(force=True)
        dl_info.value.save_as(str(pdf_path))
        return pdf_path
    except Exception as e:
        emit("recap_pdf_export_failed", error=type(e).__name__, message=str(e)[:200])
        return None


def run(playwright: Playwright, session_dir: Path, data: dict,
        include_summary: bool, keep_open: bool = False, headed: bool = False) -> None:
    storage_path = session_dir / "storage_state.json"
    if not storage_path.is_file():
        emit_error_and_exit(3, f"storage_state.json not found in {session_dir}")

    # Mode prod = headless (rapide). --headed pour debug visuel.
    browser = playwright.chromium.launch(
        headless=not headed,
        slow_mo=100 if headed else 0,
    )
    context = None
    page = None
    try:
        context = browser.new_context(
            **MOBILE_CONTEXT,
            storage_state=str(storage_path),
        )
        page = context.new_page()

        resume_url = data.get("resume_url")
        if not resume_url:
            emit_error_and_exit(4, "resume_url missing — pass it via input data")

        page.goto(resume_url, wait_until="domcontentloaded")
        # IRISbox = SPA Angular : attendre que le bouton #next soit monté avant
        # de chercher des selectors (sinon body vide).
        try:
            page.wait_for_selector("#next", state="visible", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        # Fermer la modale d'annonce qui réapparaît sur un nouveau contexte navigateur.
        dismiss_communication_modal(page)
        force_french_ui(page)

        page_text = page.locator("body").inner_text(timeout=5000)
        ref_match = RE_DRAFT_REFERENCE.search(page_text)
        request_id = ref_match.group(0) if ref_match else ""

        # Étape 1
        if URL_PATTERN_STEP["requester"].search(page.url):
            fill_step1_demandeur(page, data)

        # Étape 2
        if URL_PATTERN_STEP["building"].search(page.url):
            fill_step2_bien(page, data)

        # Étape 3
        if URL_PATTERN_STEP["documents"].search(page.url):
            fill_step3_documents(page, data)

        # Étape 4 (optionnel)
        if include_summary and URL_PATTERN_STEP["summary"].search(page.url):
            verify_step4_summary(page)

        m_step = re.search(r"/(requester|building|documents|summary|signature)(?:[?#]|$)", page.url)
        step_reached = m_step.group(1) if m_step else "unknown"

        # Auto-export PDF récap si on a atteint summary (livrable agent)
        recap_pdf_path = None
        if step_reached == "summary":
            recap_pdf_path = export_recap_pdf(page, session_dir)
            if recap_pdf_path:
                emit("recap_pdf_ready", path=str(recap_pdf_path),
                     size=recap_pdf_path.stat().st_size)

        emit("draft_ready",
             request_id=request_id,
             step_reached=step_reached,
             url=page.url,
             recap_pdf=str(recap_pdf_path) if recap_pdf_path else None)
    except SystemExit:
        # emit_error_and_exit a déjà émis l'event — pas besoin de double-trace
        _dump_failure_state(page, session_dir, "system_exit")
        raise
    except Exception as e:
        _dump_failure_state(page, session_dir, type(e).__name__)
        emit("uncaught_exception", error=type(e).__name__, message=str(e)[:500])
        raise
    finally:
        if context is not None:
            try:
                context.storage_state(path=str(storage_path))
            except Exception:
                pass
        if keep_open:
            emit("browser_kept_open",
                 message="Press Ctrl+C in the script terminal to close. Page remains live for inspection.")
            try:
                # Boucle infinie tolérante au Ctrl+C
                while True:
                    time.sleep(60)
            except KeyboardInterrupt:
                emit("keyboard_interrupt_close")
        browser.close()


def _dump_failure_state(page: Page | None, session_dir: Path, tag: str) -> None:
    """Capture screenshot + URL + validation errors + dump DOM, puis émet un event
    `rescue_context` agrégé : tout ce qu'un agent LLM (OpenClaw) doit savoir pour
    reprendre l'étape à la main dans son propre navigateur (storage_state.json du
    session_dir + PATHS_MATRIX.md comme manuel), puis relancer ce script — qui
    reprendra idempotent là où le draft en est."""
    if page is None:
        return
    shot_path = None
    try:
        shot = session_dir / f"prefill_failure_{tag}.png"
        page.screenshot(path=str(shot), full_page=True)
        shot_path = str(shot)
        emit("failure_screenshot", path=shot_path, url=page.url)
    except Exception as se:
        emit("failure_screenshot_failed", error=str(se)[:200])
    errors = []
    try:
        errors = collect_validation_errors(page)
        emit("failure_validation_errors", errors=errors)
    except Exception:
        pass
    dom_path = None
    try:
        dom = session_dir / f"prefill_failure_{tag}.html"
        dom.write_text(page.content(), encoding="utf-8")
        dom_path = str(dom)
    except Exception:
        pass
    try:
        m = re.search(r"/(requester|building|documents|summary|signature)(?:[?#]|$)", page.url)
        emit("rescue_context",
             step=m.group(1) if m else "unknown",
             url=page.url,
             failure_tag=tag,
             screenshot=shot_path,
             dom_dump=dom_path,
             validation_errors=errors,
             storage_state=str(session_dir / "storage_state.json"),
             manual="references/PATHS_MATRIX.md",
             resume_hint="complète l'étape affichée à la main, puis relance "
                         "prefill_form.py tel quel — il saute ce qui est déjà fait")
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="IRISbox RU phase 2 — prefill steps 1-3")
    parser.add_argument("--session", required=True, type=Path,
                        help="Session dir from auth_irisbox.py (contains storage_state.json)")
    parser.add_argument("--data", required=True, type=Path,
                        help="JSON input (must include resume_url from form_reached event)")
    parser.add_argument("--include-summary", action="store_true",
                        help="Advance to step 4 and verify aggregate state")
    parser.add_argument("--keep-open", action="store_true",
                        help="Leave browser open after run (success or crash) for live inspection. "
                             "Press Ctrl+C in this terminal to close.")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser visible (debug mode). Default = headless (prod).")
    args = parser.parse_args()

    if not args.data.is_file():
        emit_error_and_exit(4, f"input data file not found: {args.data}")

    data = json.loads(args.data.read_text(encoding="utf-8"))

    with sync_playwright() as pw:
        run(pw, args.session, data, args.include_summary,
            keep_open=args.keep_open, headed=args.headed)


if __name__ == "__main__":
    main()
