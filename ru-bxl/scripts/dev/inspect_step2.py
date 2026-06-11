#!/usr/bin/env python3
"""
inspect_step2.py — diagnostic du draft IRISbox étape /building.

But: comprendre pourquoi click_next ne mène pas à /documents.
Lance Chromium en headed (visible), reprend la session storage_state,
goto /building du draft, dump l'état pertinent en JSON sur stdout
puis tente un click sur #next sans force et observe le résultat.

Usage:
    python inspect_step2.py --session /tmp/ru-test --draft-id <hex>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))  # _selectors vit dans scripts/
from _selectors import MOBILE_CONTEXT, URL_PATTERN_STEP


def emit(event: str, **payload: Any) -> None:
    print(json.dumps({"event": event, "ts": time.time(), **payload}, ensure_ascii=False), flush=True)


def safe_get(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return f"<error: {type(e).__name__}: {e}>"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--draft-id", required=True)
    args = parser.parse_args()

    storage = args.session / "storage_state.json"
    if not storage.is_file():
        emit("error", message=f"storage_state.json not found at {storage}")
        sys.exit(3)

    url = f"https://irisbox.irisnet.be/irisbox/urban-information/citizen/edit/{args.draft_id}/building"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=100)
        ctx = browser.new_context(**MOBILE_CONTEXT, storage_state=str(storage))
        page = ctx.new_page()

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
        except PlaywrightTimeoutError as e:
            emit("error", message="goto timeout", detail=str(e))
            browser.close()
            sys.exit(2)

        time.sleep(2)
        current_url = page.url
        emit("page_loaded", url=current_url)

        # Détection redirection (session expirée)
        if "landing" in current_url or "iamfas" in current_url or "itsme" in current_url:
            emit("session_expired", url=current_url)
            browser.close()
            sys.exit(4)

        if not URL_PATTERN_STEP["building"].search(current_url):
            emit("wrong_step", url=current_url, expected="building")
            browser.close()
            sys.exit(5)

        # ─── DUMP de l'état ───
        page.wait_for_load_state("networkidle", timeout=10000)

        # Référence draft
        body_text = safe_get(lambda: page.locator("body").inner_text(timeout=3000))
        emit("body_first_chars", text=(body_text or "")[:500])

        # Tabs (constructions ajoutées)
        tabs = []
        try:
            tab_locators = page.get_by_role("tab").all()
            for t in tab_locators:
                try:
                    tabs.append({"text": t.inner_text(timeout=1000), "selected": t.get_attribute("aria-selected")})
                except Exception:
                    pass
        except Exception as e:
            tabs = [{"error": str(e)}]
        emit("tabs", tabs=tabs)

        # Parcelle (présence du bouton "Modifier l'adresse")
        modify_count = safe_get(lambda: page.get_by_role("button", name="Modifier l'adresse").count())
        emit("parcelle_added", modify_button_count=modify_count)

        # Champ totalParkingNumber
        parking = page.locator("#totalParkingNumber")
        emit("parking_field",
             count=safe_get(lambda: parking.count()),
             value=safe_get(lambda: parking.input_value(timeout=2000)),
             visible=safe_get(lambda: parking.is_visible(timeout=2000)),
             disabled=safe_get(lambda: parking.is_disabled(timeout=2000)))

        # Champ totalHousingNumber (calculé)
        housing = page.locator("#totalHousingNumber")
        emit("housing_field",
             count=safe_get(lambda: housing.count()),
             value=safe_get(lambda: housing.input_value(timeout=2000)))

        # Bouton #next
        next_btn = page.locator("#next")
        emit("next_button",
             count=safe_get(lambda: next_btn.count()),
             visible=safe_get(lambda: next_btn.is_visible(timeout=2000)),
             disabled=safe_get(lambda: next_btn.is_disabled(timeout=2000)),
             text=safe_get(lambda: next_btn.inner_text(timeout=2000)))

        # Messages de validation déjà visibles
        invalid_feedbacks = []
        try:
            fbs = page.locator(".invalid-feedback, .error-message, [role='alert']").all()
            for fb in fbs:
                try:
                    if fb.is_visible(timeout=500):
                        invalid_feedbacks.append({
                            "text": fb.inner_text(timeout=1000)[:200],
                            "class": fb.get_attribute("class"),
                        })
                except Exception:
                    pass
        except Exception as e:
            invalid_feedbacks = [{"error": str(e)}]
        emit("validation_messages_pre_click", messages=invalid_feedbacks)

        # Inputs avec is-invalid class
        invalid_inputs = []
        try:
            inputs = page.locator("input.is-invalid, select.is-invalid, textarea.is-invalid").all()
            for inp in inputs:
                try:
                    invalid_inputs.append({
                        "id": inp.get_attribute("id"),
                        "name": inp.get_attribute("name"),
                        "value": inp.input_value(timeout=500),
                    })
                except Exception:
                    pass
        except Exception:
            pass
        emit("invalid_inputs_pre_click", inputs=invalid_inputs)

        # ─── TENTATIVE: click Suivant SANS force pour voir le vrai comportement ───
        emit("click_next_attempt", mode="not_forced")
        try:
            next_btn.click(timeout=5000)  # pas de force
            time.sleep(2)
            emit("click_next_result_url", url=page.url)
        except PlaywrightTimeoutError as e:
            emit("click_next_intercepted_or_disabled", detail=str(e)[:300])
        except Exception as e:
            emit("click_next_error", error=type(e).__name__, detail=str(e)[:300])

        # Re-dump validation après click
        time.sleep(1)
        invalid_feedbacks_post = []
        try:
            fbs = page.locator(".invalid-feedback, .error-message, [role='alert']").all()
            for fb in fbs:
                try:
                    if fb.is_visible(timeout=500):
                        invalid_feedbacks_post.append({
                            "text": fb.inner_text(timeout=1000)[:200],
                            "class": fb.get_attribute("class"),
                        })
                except Exception:
                    pass
        except Exception:
            pass
        emit("validation_messages_post_click", messages=invalid_feedbacks_post)

        invalid_inputs_post = []
        try:
            inputs = page.locator("input.is-invalid, select.is-invalid, textarea.is-invalid").all()
            for inp in inputs:
                try:
                    invalid_inputs_post.append({
                        "id": inp.get_attribute("id"),
                        "name": inp.get_attribute("name"),
                        "value": inp.input_value(timeout=500),
                    })
                except Exception:
                    pass
        except Exception:
            pass
        emit("invalid_inputs_post_click", inputs=invalid_inputs_post)

        # Screenshot final pour inspection visuelle
        screenshot_path = args.session / "inspect_step2_final.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        emit("screenshot", path=str(screenshot_path))

        emit("done", final_url=page.url)
        time.sleep(3)  # laisse 3s pour observer visuellement
        browser.close()


if __name__ == "__main__":
    main()
