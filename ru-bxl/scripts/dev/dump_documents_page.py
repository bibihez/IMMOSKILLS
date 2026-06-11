#!/usr/bin/env python3
"""
dump_documents_page.py — Découverte complète de l'étape /documents.

Charge le draft via storage_state, dump tous les buttons / inputs / headings
de la page /documents pour identifier les selectors d'upload de documents.

Usage:
    python dump_documents_page.py --session /tmp/ru-test --draft-id <hex>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

import sys as _sys, pathlib as _pl
_sys.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent))  # _selectors vit dans scripts/
from _selectors import MOBILE_CONTEXT


def emit(label: str, payload: Any) -> None:
    print(f"\n=== {label} ===", flush=True)
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, ensure_ascii=False, indent=2), flush=True)
    else:
        print(payload, flush=True)


def safe(fn, default=None):
    try:
        return fn()
    except Exception as e:
        return f"<err {type(e).__name__}: {str(e)[:120]}>"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--draft-id", required=True)
    args = parser.parse_args()

    storage = args.session / "storage_state.json"
    if not storage.is_file():
        print(f"storage_state.json not found at {storage}", file=sys.stderr)
        sys.exit(3)

    url = f"https://irisbox.irisnet.be/irisbox/urban-information/citizen/edit/{args.draft_id}/documents"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        ctx = browser.new_context(**MOBILE_CONTEXT, storage_state=str(storage))
        page = ctx.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_selector("#next", state="visible", timeout=20000)
        except Exception:
            pass
        time.sleep(1)
        emit("URL", page.url)

        body = page.locator("body").inner_text(timeout=3000)
        if "Session expirée" in body:
            emit("SESSION EXPIRED", body[:200])
            browser.close()
            sys.exit(4)

        # Headings (sections de catégories de documents)
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
        emit(f"HEADINGS ({len(headings)})", headings)

        # Tous les buttons
        buttons = []
        for b in page.get_by_role("button").all():
            try:
                if b.is_visible(timeout=200):
                    buttons.append({
                        "name": (b.inner_text(timeout=300) or "").strip()[:80],
                        "id": b.get_attribute("id"),
                        "class": (b.get_attribute("class") or "")[:80],
                        "aria-label": b.get_attribute("aria-label"),
                        "aria-describedby": b.get_attribute("aria-describedby"),
                        "title": b.get_attribute("title"),
                    })
            except Exception:
                pass
        emit(f"BUTTONS ({len(buttons)})", buttons)

        # File inputs (souvent cachés mais utilisables via setInputFiles)
        file_inputs = []
        for inp in page.locator("input[type='file']").all():
            try:
                file_inputs.append({
                    "id": inp.get_attribute("id"),
                    "name": inp.get_attribute("name"),
                    "accept": inp.get_attribute("accept"),
                    "multiple": inp.get_attribute("multiple"),
                    "visible": inp.is_visible(timeout=200),
                })
            except Exception:
                pass
        emit(f"FILE INPUTS ({len(file_inputs)})", file_inputs)

        # Détection structure : pour chaque heading "document", chercher le bouton/input
        # le plus proche
        doc_categories = [
            "Renseignements relatifs au titre de propriété",
            "Reportage photographique",
            "Croquis ou plans",
            "Copie du mandat",
            "Extrait du plan parcellaire cadastral",
            "Extrait de la matrice cadastrale",
            "Autre document pertinent",
        ]
        for cat in doc_categories:
            try:
                heading = page.get_by_role("heading", name=cat).first
                if not heading.is_visible(timeout=300):
                    emit(f"CAT '{cat}'", "heading not visible")
                    continue
                # Walk up parents and find first button + first file input
                parent_html = heading.evaluate("""el => {
                    let p = el.parentElement;
                    for (let i = 0; i < 5 && p; i++) {
                        const buttons = Array.from(p.querySelectorAll('button')).map(b => ({
                            text: (b.innerText||'').trim().slice(0,60),
                            id: b.id || null,
                            class: (b.className||'').slice(0,60),
                        }));
                        const fileInputs = Array.from(p.querySelectorAll('input[type=file]')).map(i => ({
                            id: i.id || null,
                            name: i.name || null,
                        }));
                        if (buttons.length > 0 || fileInputs.length > 0) {
                            return {depth: i, buttons: buttons.slice(0,5), fileInputs};
                        }
                        p = p.parentElement;
                    }
                    return null;
                }""")
                emit(f"CAT '{cat}'", parent_html)
            except Exception as e:
                emit(f"CAT '{cat}'", f"err: {str(e)[:120]}")

        page.screenshot(path=str(args.session / "dump_documents.png"), full_page=True)
        emit("SCREENSHOT", str(args.session / "dump_documents.png"))

        time.sleep(2)
        browser.close()


if __name__ == "__main__":
    main()
