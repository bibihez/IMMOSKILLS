# RU Bxl scripts (Python + Playwright)

Trois fichiers, deux scripts CLI, zero submit.

## Setup

```bash
cd ru-skill/scripts
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Run

### Phase 1 — Auth + itsme

```bash
python auth_irisbox.py \
  --data example_input.json \
  --output-dir /tmp/ru-session-abc
```

Stream JSON sur stdout. OpenClaw lit `icon_ready`, envoie l'icône à l'utilisateur via Telegram, puis le script bloque jusqu'à `form_reached` (URL `/requester` détectée).

À la fin : `output-dir/storage_state.json` + `output-dir/icon.png`.

### Phase 2 — Pré-remplissage étapes 1-3

```bash
# Récupérer resume_url depuis l'event form_reached de la phase 1
# et l'ajouter dans le JSON d'input avant ce run
python prefill_form.py \
  --session /tmp/ru-session-abc \
  --data example_input.json
```

Stream `step_completed` × 3 puis `draft_ready`. Le script s'arrête au draft, étape 4 ou 5 selon `--include-summary`.

## Architecture

```
auth_irisbox.py        prefill_form.py
       │                       │
       └──── _selectors.py ────┘
       (locators IRISbox/CSAM/itsme,
        recon 2026-05-04 v23.0.5-105)
```

## Pourquoi pas `submit_form.py`

Décision produit : la skill ne submit jamais. L'agent immobilier reprend le draft depuis son ordi via "Mes demandes" sur IRISbox, coche l'Article 7 et clique Send manuellement. Signature humaine intentionnelle, paiement Molenbeek géré côté humain.

## Re-recon si IRISbox change

Si une montée de version IRISbox casse les locators :

```bash
playwright codegen --device "iPhone 14" https://irisbox.irisnet.be/irisbox/urban-information/landing
```

Et mettre à jour `_selectors.py` avec les nouveaux noms/IDs observés.
