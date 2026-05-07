#!/usr/bin/env python3
"""
watch_explore.py — Exploration interactive : tu pilotes le browser, je capture.

Lance Chromium visible avec la storage_state existante. Toi tu navigues
librement dans IRISbox. Pour capturer un état (modal ouvert, page intéressante),
tu envoies un label via une named pipe :

    echo "modal_intervenant_moral" > /tmp/ru-test/manual/cmd
    echo "q" > /tmp/ru-test/manual/cmd  # pour quitter

Le script poll la pipe, dump (DOM + screenshot) sous le label, log le résultat
sur stdout. Possible de driver depuis n'importe quel shell (Claude inclus).

Usage:
    python watch_explore.py --session /tmp/ru-test --draft-id <hex>
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from _selectors import MOBILE_CONTEXT


def safe(fn):
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
    radios = {}
    for r in page.locator("input[type=radio]").all():
        try:
            name = r.get_attribute("name") or "_unnamed"
            if name not in radios:
                radios[name] = []
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


def capture(page, out_dir: Path, label: str):
    safe_label = re.sub(r"[^a-zA-Z0-9_-]", "_", label) or f"snap_{int(time.time())}"
    snap = {
        "label": label,
        "url": page.url,
        "ts": time.time(),
        "headings": dump_headings(page),
        "buttons": dump_buttons(page),
        "inputs": dump_inputs(page),
        "radios_grouped": dump_radios_grouped(page),
    }
    json_path = out_dir / f"{safe_label}.json"
    json_path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
    shot_path = out_dir / f"{safe_label}.png"
    try:
        page.screenshot(path=str(shot_path), full_page=True)
    except Exception:
        shot_path = None
    print(f"  → {json_path.name} "
          f"({len(snap['headings'])} headings, "
          f"{len(snap['buttons'])} buttons, "
          f"{len(snap['inputs'])} inputs"
          + (f", {shot_path.name}" if shot_path else "")
          + ")", flush=True)
    return json_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", required=True, type=Path)
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--start-on", default="requester",
                        choices=["requester", "building", "documents", "summary"],
                        help="Step to start on (default: requester)")
    args = parser.parse_args()

    storage = args.session / "storage_state.json"
    if not storage.is_file():
        print(f"storage_state.json not found at {storage}", file=sys.stderr)
        sys.exit(3)

    out_dir = args.session / "manual"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Named pipe pour recevoir les labels depuis n'importe quel shell.
    # Format: echo "<label>" > <pipe>   (label="q" pour quitter)
    pipe_path = out_dir / "cmd"
    if pipe_path.exists():
        pipe_path.unlink()
    os.mkfifo(str(pipe_path))
    print(f"PIPE ready: send labels via\n    echo '<label>' > {pipe_path}\n"
          f"    echo 'q' > {pipe_path}    # to quit", flush=True)

    base_url = f"https://irisbox.irisnet.be/irisbox/urban-information/citizen/edit/{args.draft_id}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False, slow_mo=50)
        ctx = browser.new_context(**MOBILE_CONTEXT, storage_state=str(storage))
        page = ctx.new_page()

        page.goto(f"{base_url}/{args.start_on}", wait_until="domcontentloaded", timeout=20000)
        try:
            page.wait_for_selector("#next", state="visible", timeout=20000)
        except Exception:
            pass
        print(f"BROWSER READY on {page.url}", flush=True)
        print(f"Listening on pipe {pipe_path}...", flush=True)

        try:
            while True:
                # blocking read jusqu'à un writer (echo)
                with open(str(pipe_path), "r") as f:
                    cmd = f.read().strip()
                if not cmd:
                    continue
                if cmd == "q":
                    print("RECEIVED q → closing browser", flush=True)
                    break
                print(f"RECEIVED label='{cmd}'", flush=True)
                if cmd == "_export":
                    # Click le bouton Exporter PDF + sauvegarde le download
                    pdf_path = out_dir / f"export_{int(time.time())}.pdf"
                    try:
                        with page.expect_download(timeout=30000) as dl_info:
                            page.locator("#btn-action-export").click(force=True)
                        dl_info.value.save_as(str(pdf_path))
                        print(f"  → {pdf_path.name} (PDF saved, "
                              f"{pdf_path.stat().st_size} bytes)", flush=True)
                    except Exception as e:
                        print(f"  ! export failed: {type(e).__name__}: "
                              f"{str(e)[:200]}", flush=True)
                    continue
                try:
                    capture(page, out_dir, cmd)
                except Exception as e:
                    print(f"  ! capture failed: {type(e).__name__}: {str(e)[:200]}", flush=True)
        except KeyboardInterrupt:
            pass
        finally:
            try:
                pipe_path.unlink()
            except Exception:
                pass
            browser.close()
            print(f"DONE. All captures in {out_dir}", flush=True)


if __name__ == "__main__":
    main()
