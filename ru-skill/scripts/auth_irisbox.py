#!/usr/bin/env python3
"""
auth_irisbox.py — Phase 1 du flow RU Bxl.

Lance Chromium en mode iPhone (UA + viewport mobile, condition sine qua non
pour qu'itsme propose le form téléphone au lieu du QR), navigue jusqu'au
form itsme, soumet le numéro, screenshote l'icône à matcher, et attend la
validation utilisateur (URL `/requester`).

Stream les events JSON sur stdout (un objet JSON par ligne) pour qu'OpenClaw
orchestre le côté Telegram en temps réel.

Usage:
    python auth_irisbox.py --data input.json --output-dir /tmp/ru-session-abc

Sortie:
    {"event": "mobile_context_ready", ...}
    {"event": "csam_reached", ...}
    {"event": "itsme_phone_form_ready", ...}
    {"event": "icon_ready", "icon_number": 15, "icon_path": "...", "expires_in": 180}
    {"event": "form_reached", "url": "...", "request_id": "RUSI-260504-...", "draft_id": "ec16f2..."}

Codes de sortie:
    0  succès (form_reached émis)
    1  timeout itsme (user n'a pas validé)
    2  itsme refusé (numéro invalide ou rejet user)
    3  IRISbox indisponible
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
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

from _selectors import (
    CSAM_ITSME_TEXT,
    DIALOG_AUTH_CONNECT_RE,
    ITSME_ICON_NAME_RE,
    ITSME_PHONE_HEADING_RE,
    ITSME_PHONE_SEND_RE,
    ITSME_PROVE_HEADING_RE,
    ITSME_TIMEOUT_SECONDS,
    LANDING_CTA_NAME,
    MOBILE_CONTEXT,
    RE_DRAFT_REFERENCE,
    URL_LANDING,
    URL_PATTERN_FORM_REACHED,
)


def emit(event: str, **payload: Any) -> None:
    """Stream un event JSON sur stdout, flushé immédiatement."""
    line = json.dumps({"event": event, "ts": time.time(), **payload}, ensure_ascii=False)
    print(line, flush=True)


def emit_error_and_exit(code: int, message: str, **extra: Any) -> None:
    emit("error", code=code, message=message, **extra)
    sys.exit(code)


def force_french_ui(page) -> None:
    """Click le bouton 'fr' de la navbar IRISbox pour stabiliser les locators."""
    fr_button = page.get_by_role("button", name="fr").first
    if fr_button.is_visible():
        fr_button.click()
        page.wait_for_load_state("networkidle", timeout=5000)


def navigate_to_itsme_phone_form(page, phone_number: str) -> None:
    """Landing → CTA → dialog auth → CSAM → tile itsme → form téléphone (iPhone UA)."""
    page.goto(URL_LANDING, wait_until="domcontentloaded")
    page.get_by_role("link", name=LANDING_CTA_NAME).first.click()

    dialog = page.get_by_role("dialog")
    dialog.get_by_role("button", name=DIALOG_AUTH_CONNECT_RE).click()

    page.wait_for_url(re.compile(r"idp\.iamfas\.belgium\.be"), timeout=15000)
    emit("csam_reached", url=page.url)

    page.get_by_text(CSAM_ITSME_TEXT, exact=False).first.click()
    page.wait_for_url(re.compile(r"idp\.prd\.itsme\.services"), timeout=15000)

    page.get_by_role("heading", name=ITSME_PHONE_HEADING_RE).wait_for(timeout=10000)
    emit("itsme_phone_form_ready")

    textbox = page.get_by_role("textbox").first
    textbox.fill(phone_number)

    send = page.get_by_role("button", name=ITSME_PHONE_SEND_RE)
    send.wait_for(state="visible")
    if send.is_disabled():
        emit_error_and_exit(2, "itsme Send button stayed disabled — phone number rejected",
                            phone=phone_number)
    send.click()


def capture_icon(page, output_dir: Path) -> tuple[int, Path]:
    """Attend l'écran 'Prouvez que c'est vous', extrait le numéro d'icône, screenshote.

    L'icône est un <svg role="img"> dont le accessible name vient d'un <title>
    enfant (ex: 'Icône numéro 12'). On cherche d'abord dans les SVG titles,
    puis fallback sur attributs alt/aria-label/title des <img>.
    """
    page.get_by_role("heading", name=ITSME_PROVE_HEADING_RE).wait_for(timeout=15000)
    page.wait_for_timeout(500)

    icon_locator = None
    icon_text = None

    # 1) SVG inline avec <title> enfant — text_content (pas inner_text, SVG title n'est pas HTMLElement)
    svgs = page.locator("svg[role='img']")
    for i in range(svgs.count()):
        el = svgs.nth(i)
        title_loc = el.locator("title")
        if title_loc.count() == 0:
            continue
        text = title_loc.first.text_content() or ""
        if ITSME_ICON_NAME_RE.search(text):
            icon_locator = el
            icon_text = text
            break

    # 2) Fallback: <img> ou [role='img'] avec attributs alt/aria-label/title
    if not icon_locator:
        candidates = page.locator("img, [role='img']:not(svg)")
        for i in range(candidates.count()):
            el = candidates.nth(i)
            for attr in ("alt", "aria-label", "title"):
                value = el.get_attribute(attr) or ""
                if ITSME_ICON_NAME_RE.search(value):
                    icon_locator = el
                    icon_text = value
                    break
            if icon_locator:
                break

    if not icon_locator:
        debug_path = output_dir / "debug-prove.html"
        debug_path.write_text(page.locator("main").inner_html(), encoding="utf-8")
        emit_error_and_exit(3, "icon not found", debug_html=str(debug_path))

    match = ITSME_ICON_NAME_RE.search(icon_text)
    icon_number = int(match.group(1))
    icon_path = output_dir / "icon.png"
    icon_locator.screenshot(path=str(icon_path))

    return icon_number, icon_path


def auto_handle_post_itsme_popups(page) -> None:
    """Après validation itsme, IRISnet affiche en cascade :
       1. Popup cookie 'Got it' (idp.irisnet.be)
       2. Page OAuth consent 'irisbox.iris... wants to access your account'
          avec bouton Approve/Allow/Accepter en bas.
       Auto-clic sans bloquer si pas visible."""
    # 1) Cookie consent
    for name in ("Got it", "Accept all", "Accepter tout", "OK"):
        try:
            btn = page.get_by_role("button", name=name).first
            if btn.is_visible(timeout=200):
                btn.click(timeout=2000)
                emit("cookie_dismissed", button=name)
                page.wait_for_timeout(500)
                break
        except Exception:
            pass

    # 2) OAuth consent — bouton souvent en bas, doit scroll d'abord pour le voir
    if "consent" in page.url:
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(300)
        except Exception:
            pass
        for pattern in (r"^Approve$", r"^Allow$", r"^Accept$", r"^Continue$", r"^Confirm$",
                        r"^Approuver$", r"^Autoriser$", r"^Accepter$", r"^Confirmer$",
                        r"^Continuer$", r"^Suivant$"):
            try:
                btn = page.get_by_role("button", name=re.compile(pattern, re.I)).first
                if btn.is_visible(timeout=200):
                    btn.click(timeout=2000)
                    emit("oauth_consent_approved", button=pattern)
                    page.wait_for_timeout(800)
                    return
            except Exception:
                pass


def wait_for_form_and_extract_ids(page, output_dir: Path | None = None) -> tuple[str, str]:
    """Bloque jusqu'à ce que l'URL match /requester. Retourne (request_id, draft_id).

    Polling URL toutes les 2s + auto-click cookie/OAuth-consent popups en chemin
    + screenshot+url emit toutes les 30s pour diag."""
    poll_interval_ms = 2000
    diag_every_n = 15  # 15 * 2s = 30s
    elapsed = 0
    n = 0
    form_reached_seen = False
    while elapsed < ITSME_TIMEOUT_SECONDS * 1000:
        if URL_PATTERN_FORM_REACHED.search(page.url):
            form_reached_seen = True
            break
        # Tente de gérer cookie + OAuth consent à chaque tick (no-op si pas visible)
        auto_handle_post_itsme_popups(page)
        page.wait_for_timeout(poll_interval_ms)
        elapsed += poll_interval_ms
        n += 1
        if n % diag_every_n == 0:
            shot_path = None
            if output_dir:
                shot_path = output_dir / f"wait_diag_{elapsed // 1000}s.png"
                try:
                    page.screenshot(path=str(shot_path), full_page=False)
                except Exception:
                    shot_path = None
            emit("waiting_for_form", elapsed_seconds=elapsed // 1000,
                 current_url=page.url[:200],
                 screenshot=str(shot_path) if shot_path else None)
    if not form_reached_seen:
        emit_error_and_exit(1, "user did not complete itsme validation in time",
                            timeout_seconds=ITSME_TIMEOUT_SECONDS)

    url = page.url
    draft_match = re.search(r"/edit/([0-9a-f]+)/requester", url)
    draft_id = draft_match.group(1) if draft_match else ""

    # IRISbox a un keepalive long-poll qui empêche networkidle d'arriver.
    # On utilise domcontentloaded + un wait sur la référence draft (h1/h2 avec RUSI-...).
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10000)
    except PlaywrightTimeoutError:
        pass

    request_id = ""
    for _ in range(20):  # poll 200ms × 20 = 4s max
        try:
            page_text = page.locator("body").inner_text(timeout=2000)
            ref_match = RE_DRAFT_REFERENCE.search(page_text)
            if ref_match:
                request_id = ref_match.group(0)
                break
        except Exception:
            pass
        page.wait_for_timeout(200)

    return request_id, draft_id


def run(playwright: Playwright, data: dict, output_dir: Path, headed: bool = False) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    phone = data.get("phone_number", "").strip()
    if not phone:
        emit_error_and_exit(4, "phone_number missing in input")
    phone = re.sub(r"^(\+32|0032|0)", "", phone)
    phone = re.sub(r"\s+", "", phone)
    if not re.fullmatch(r"\d{8,9}", phone):
        emit_error_and_exit(4, "phone_number format invalid", phone=phone)

    browser = playwright.chromium.launch(
        headless=not headed,
        slow_mo=200 if headed else 0,
    )
    context = None
    storage_path = output_dir / "storage_state.json"
    try:
        context = browser.new_context(**MOBILE_CONTEXT)
        emit("mobile_context_ready",
             ua=MOBILE_CONTEXT["user_agent"],
             viewport=MOBILE_CONTEXT["viewport"])

        page = context.new_page()
        try:
            navigate_to_itsme_phone_form(page, phone)
        except PlaywrightTimeoutError as e:
            emit_error_and_exit(3, "IRISbox/CSAM/itsme navigation timed out", detail=str(e))

        icon_number, icon_path = capture_icon(page, output_dir)
        emit("icon_ready",
             icon_number=icon_number,
             icon_path=str(icon_path),
             expires_in=180)

        request_id, draft_id = wait_for_form_and_extract_ids(page, output_dir)
        emit("form_reached",
             url=page.url,
             request_id=request_id,
             draft_id=draft_id)
    finally:
        # Sauvegarde de session AVANT de fermer le browser, même en cas d'exception
        # post-itsme (ex: timeout networkidle). Sans ça on perd les 44s d'interaction
        # itsme du user et il faut refaire de zéro.
        if context is not None:
            try:
                context.storage_state(path=str(storage_path))
                emit("storage_state_saved", path=str(storage_path))
            except Exception as e:
                emit("storage_state_save_failed", error=str(e))
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="IRISbox RU phase 1 — auth + itsme")
    parser.add_argument("--data", required=True, type=Path,
                        help="Path to JSON input file (phone_number + dossier metadata)")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="Where to write icon.png, storage_state.json, logs")
    parser.add_argument("--headed", action="store_true",
                        help="Run browser visible (debug mode). Default = headless (prod).")
    args = parser.parse_args()

    if not args.data.is_file():
        emit_error_and_exit(4, f"input data file not found: {args.data}")

    data = json.loads(args.data.read_text(encoding="utf-8"))

    with sync_playwright() as pw:
        run(pw, data, args.output_dir, headed=args.headed)


if __name__ == "__main__":
    main()
