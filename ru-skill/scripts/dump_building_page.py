#!/usr/bin/env python3
"""
dump_building_page.py — Découverte complète de l'étape /building.

Charge le draft via storage_state, click sur "Construction : <denom>" pour
expand le panel, puis dump TOUT l'inventaire DOM utile (buttons, inputs,
headings, dialogs, role=tab, structure visible).

Objectif : identifier en UN run tous les selectors nécessaires au flow
add_unit / parking / next, sans itérer patch-relance.

Usage:
    python dump_building_page.py --session /tmp/ru-test --draft-id <hex>
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

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


def list_buttons(page, label):
    items = []
    try:
        for b in page.get_by_role("button").all():
            try:
                if b.is_visible(timeout=200):
                    items.append({
                        "name": (b.inner_text(timeout=300) or "").strip()[:120],
                        "id": b.get_attribute("id"),
                        "class": (b.get_attribute("class") or "")[:80],
                        "aria-expanded": b.get_attribute("aria-expanded"),
                        "aria-controls": b.get_attribute("aria-controls"),
                        "disabled": b.is_disabled(),
                    })
            except Exception:
                pass
    except Exception:
        pass
    emit(f"BUTTONS [{label}] ({len(items)})", items)


def list_inputs(page, label):
    items = []
    try:
        for inp in page.locator("input, select, textarea").all():
            try:
                if inp.is_visible(timeout=200):
                    items.append({
                        "tag": inp.evaluate("el => el.tagName.toLowerCase()"),
                        "id": inp.get_attribute("id"),
                        "name": inp.get_attribute("name"),
                        "type": inp.get_attribute("type"),
                        "placeholder": inp.get_attribute("placeholder"),
                        "value": safe(lambda: inp.input_value(timeout=200)),
                        "required": inp.get_attribute("required"),
                    })
            except Exception:
                pass
    except Exception:
        pass
    emit(f"INPUTS [{label}] ({len(items)})", items)


def list_headings(page, label):
    items = []
    try:
        for h in page.locator("h1, h2, h3, h4, h5, h6").all():
            try:
                if h.is_visible(timeout=200):
                    items.append({
                        "tag": h.evaluate("el => el.tagName.toLowerCase()"),
                        "text": (h.inner_text(timeout=300) or "").strip()[:120],
                    })
            except Exception:
                pass
    except Exception:
        pass
    emit(f"HEADINGS [{label}] ({len(items)})", items)


def list_tabs_and_panels(page, label):
    tabs, panels = [], []
    try:
        for t in page.get_by_role("tab").all():
            try:
                tabs.append({
                    "text": (t.inner_text(timeout=300) or "").strip()[:120],
                    "aria-selected": t.get_attribute("aria-selected"),
                    "aria-controls": t.get_attribute("aria-controls"),
                    "id": t.get_attribute("id"),
                })
            except Exception:
                pass
    except Exception:
        pass
    try:
        for p in page.get_by_role("tabpanel").all():
            try:
                panels.append({
                    "id": p.get_attribute("id"),
                    "aria-labelledby": p.get_attribute("aria-labelledby"),
                    "hidden": p.get_attribute("hidden"),
                    "visible": p.is_visible(timeout=200),
                })
            except Exception:
                pass
    except Exception:
        pass
    emit(f"TABS [{label}]", tabs)
    emit(f"TABPANELS [{label}]", panels)


def list_links(page, label):
    items = []
    try:
        for a in page.get_by_role("link").all():
            try:
                if a.is_visible(timeout=200):
                    items.append({
                        "text": (a.inner_text(timeout=300) or "").strip()[:80],
                        "href": (a.get_attribute("href") or "")[:120],
                    })
            except Exception:
                pass
    except Exception:
        pass
    emit(f"LINKS [{label}] ({len(items)})", items[:30])


def find_construction_button(page, denomination):
    """Tente plusieurs stratégies pour identifier le button de la construction."""
    import re
    strategies = [
        ("role=tab + name", lambda: page.get_by_role("tab", name=denomination).first),
        ("role=button regex 'Construction:.*denom'",
         lambda: page.get_by_role("button",
                                  name=re.compile(rf"Construction\s*:\s*.*{re.escape(denomination)}", re.I)).first),
        ("role=button name=denom",
         lambda: page.get_by_role("button", name=re.compile(re.escape(denomination), re.I)).first),
        ("text=denom",
         lambda: page.get_by_text(denomination).first),
    ]
    results = []
    for label, fn in strategies:
        try:
            loc = fn()
            count = loc.count() if hasattr(loc, "count") else "n/a"
            visible = safe(lambda: loc.is_visible(timeout=300))
            text = safe(lambda: (loc.inner_text(timeout=300) or "").strip()[:100])
            results.append({"strategy": label, "count": count, "visible": visible, "text": text})
        except Exception as e:
            results.append({"strategy": label, "error": str(e)[:120]})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--denomination", default="Test recon smoke")
    args = parser.parse_args()

    storage = args.session / "storage_state.json"
    if not storage.is_file():
        print(f"storage_state.json not found at {storage}", file=sys.stderr)
        sys.exit(3)

    url = f"https://irisbox.irisnet.be/irisbox/urban-information/citizen/edit/{args.draft_id}/building"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=200)
        ctx = browser.new_context(**MOBILE_CONTEXT, storage_state=str(storage))
        page = ctx.new_page()

        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        # SPA Angular : attendre un signal que l'app a boot (bouton Suivant)
        try:
            page.wait_for_selector("#next", state="visible", timeout=20000)
        except Exception:
            pass
        time.sleep(1)
        emit("URL", page.url)

        # Détection session expirée
        body = page.locator("body").inner_text(timeout=3000)
        if "Session expirée" in body:
            emit("SESSION EXPIRED — RE-AUTH", body[:200])
            browser.close()
            sys.exit(4)

        # ─── PHASE 1: état initial (avant click sur construction) ───
        emit("PHASE", "BEFORE clicking construction button")
        list_headings(page, "before")
        list_tabs_and_panels(page, "before")
        list_buttons(page, "before")
        list_inputs(page, "before")
        list_links(page, "before")

        # Strategy probe
        emit("CONSTRUCTION FIND-BUTTON STRATEGIES", find_construction_button(page, args.denomination))

        page.screenshot(path=str(args.session / "dump_before.png"), full_page=True)
        emit("SCREENSHOT BEFORE", str(args.session / "dump_before.png"))

        # ─── PHASE 2: click sur la construction ───
        clicked_label = None
        import re
        for label, fn in [
            ("button 'Construction : <denom>'",
             lambda: page.get_by_role("button",
                                      name=re.compile(rf"Construction\s*:\s*.*{re.escape(args.denomination)}", re.I)).first),
            ("button name=denom",
             lambda: page.get_by_role("button", name=re.compile(re.escape(args.denomination), re.I)).first),
            ("text=denom",
             lambda: page.get_by_text(args.denomination).first),
        ]:
            try:
                loc = fn()
                if loc.is_visible(timeout=500):
                    loc.click(force=True)
                    clicked_label = label
                    break
            except Exception:
                pass
        emit("CLICKED CONSTRUCTION BUTTON", clicked_label or "NONE")

        if clicked_label:
            page.wait_for_timeout(1500)

            # ─── PHASE 3: état après click (expanded) ───
            emit("PHASE", "AFTER clicking construction button")
            list_headings(page, "after")
            list_tabs_and_panels(page, "after")
            list_buttons(page, "after")
            list_inputs(page, "after")
            list_links(page, "after")

            page.screenshot(path=str(args.session / "dump_after.png"), full_page=True)
            emit("SCREENSHOT AFTER", str(args.session / "dump_after.png"))

            # Probe spécifique pour "Ajouter une unité"
            unite_probes = []
            for pattern in [
                "Ajouter une unité",
                re.compile(r"Ajouter\s+une\s+unit", re.I),
                re.compile(r"Unit", re.I),
                re.compile(r"Étage", re.I),
            ]:
                try:
                    loc = page.get_by_role("button", name=pattern)
                    unite_probes.append({
                        "pattern": str(pattern),
                        "count": loc.count(),
                    })
                except Exception as e:
                    unite_probes.append({"pattern": str(pattern), "error": str(e)[:80]})
            emit("ADD UNITE PROBES", unite_probes)

        time.sleep(3)  # let user observe
        browser.close()


if __name__ == "__main__":
    main()
