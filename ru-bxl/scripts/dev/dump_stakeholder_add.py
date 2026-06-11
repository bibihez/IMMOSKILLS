#!/usr/bin/env python3
"""
dump_stakeholder_add.py — Capture le DOM de la page /stakeholder/add (qui est
en fait une route dédiée, pas un modal Bootstrap). On y arrive depuis l'étape 1
mandataire en cliquant #add.
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))  # _selectors vit dans scripts/
from _selectors import MOBILE_CONTEXT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--draft-id", required=True)
    args = parser.parse_args()

    storage = args.session / "storage_state.json"
    base_url = f"https://irisbox.irisnet.be/irisbox/urban-information/citizen/edit/{args.draft_id}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(**MOBILE_CONTEXT, storage_state=str(storage))
        page = ctx.new_page()

        # Naviguer vers /requester pour set le state mandataire
        page.goto(f"{base_url}/requester", wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_selector("#next", state="visible", timeout=15000)
        except Exception:
            pass

        # Coche "Non" + select REAL_ESTATE_AGENT (state idempotent)
        try:
            page.locator("#isLandlordNo").check(force=True)
            page.wait_for_timeout(1000)
        except Exception:
            pass
        try:
            page.locator("#quality").select_option(value="REAL_ESTATE_AGENT")
            page.wait_for_timeout(1000)
        except Exception:
            pass

        # Click Ajouter intervenant
        page.locator("#add").click(force=True)
        page.wait_for_load_state("domcontentloaded", timeout=10000)
        try:
            page.wait_for_selector("#firstName", state="visible", timeout=10000)
        except Exception:
            pass
        page.wait_for_timeout(1500)

        snap = {"url": page.url}

        # Tous les inputs visibles
        inputs = []
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
                        "required": inp.get_attribute("required") is not None,
                    }
                    if tag == "select":
                        item["options"] = inp.evaluate(
                            "el => Array.from(el.options).map(o => ({value: o.value, text: o.text}))"
                        )
                    inputs.append(item)
            except Exception:
                pass
        snap["inputs"] = inputs

        # Boutons visibles
        buttons = []
        for b in page.get_by_role("button").all():
            try:
                if b.is_visible(timeout=200):
                    buttons.append({
                        "name": (b.inner_text(timeout=300) or "").strip()[:80],
                        "id": b.get_attribute("id"),
                        "class": (b.get_attribute("class") or "")[:60],
                    })
            except Exception:
                pass
        snap["buttons"] = buttons

        # Headings
        headings = []
        for h in page.locator("h1, h2, h3, h4, h5, h6").all():
            try:
                if h.is_visible(timeout=200):
                    headings.append({
                        "tag": h.evaluate("el => el.tagName.toLowerCase()"),
                        "text": (h.inner_text(timeout=300) or "").strip()[:120],
                        "id": h.get_attribute("id"),
                    })
            except Exception:
                pass
        snap["headings"] = headings

        out = args.session / "stakeholder_add_dump.json"
        out.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"DUMP → {out}")
        page.screenshot(path=str(args.session / "stakeholder_add.png"), full_page=True)
        browser.close()


if __name__ == "__main__":
    main()
