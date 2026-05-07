# Session resume — RU smoke test (continued 2026-05-06 PM)

## Mise à jour 2026-05-06 PM

### Cartographie exhaustive IRISbox terminée
- **`ru-skill/PATHS_MATRIX.md`** créé : source de vérité unique pour tous les paths conditionnels du formulaire IRISbox v23.0.5. Contient selectors stables par étape, format PDF récap, paths NON couverts, et questions intake OpenClaw dérivées.
- 7 dumps réalisés (`/tmp/ru-test/paths/*.json` + `/tmp/ru-test/manual/*.json` + 1 PDF export)
- Mémoire : `project_ru_paths_matrix.md` ajoutée avec pointer vers la matrice

### Paths étape 1 + 2 implémentés (non testés E2E)
- `_selectors.py` : 12 nouveaux IDs stables (`STEP1_LANDLORD_*`, `STEP1_QUALITY_*`, `INTERVENANT_*`, `QUALITY_*`)
- `prefill_form.py` :
  - `fill_step1_demandeur` : path mandataire complet (is_owner=false → quality select + boucle intervenants)
  - `add_intervenant()` : nouvelle fonction, 10 champs PHYSICAL (firstName, lastName, email, phone, streetName/Number/box, zipCode, city, country)
  - `_intervenant_already_present()` : idempotency check par nom complet
  - `fill_step2_bien` : branche `terrain_nu` (LAND) qui saute les constructions
  - `fill_step3_documents` : validation `mandat` required si `is_owner=false`
- `example_input.json` réécrit avec schéma complet (mandataire + intervenants + docs.mandat) + commentaires `_doc_*`

### Outils de cartographie créés (réutilisables)
- `dump_building_page.py` / `dump_documents_page.py` : dump exhaustif d'une étape (buttons/inputs/headings/IDs)
- `explore_paths.py --path <name>` : 5 explorations paramétrables (mandataire, terrain_nu, unit_destinations, multi_parcelle, multi_construction)
- `watch_explore.py` : exploration interactive — user pilote browser, envoie des labels via named pipe (`echo 'label' > /tmp/ru-test/manual/cmd`), capture DOM + screenshot. Commande spéciale `_export` pour le PDF récap IRISbox.

### À faire prochaine session

1. **Tester E2E le path mandataire** (besoin re-auth itsme 44s sauf si storage_state encore valide < 30min)
2. **Mapper modal Intervenant MORAL** (Personne morale / SCI / SPRL) — pas dumpé. Lance `watch_explore.py`, click "Non" + quality + Ajouter intervenant + radio "Personne morale" + `echo "modal_intervenant_moral" > /tmp/ru-test/manual/cmd`
3. **Designer le flow intake conversationnel OpenClaw** à partir de la section "Questions intake" de `PATHS_MATRIX.md`

---

# Session resume — RU smoke test (E2E green 2026-05-06)

## ✅ Statut : draft_ready end-to-end validé

**Draft `RUSI-260506-2753446`** (id `2a941989de8245f789d704515d04ecbf21160064`) poussé jusqu'à `/summary` sans intervention humaine hors itsme (44s côté téléphone).

Sortie finale `prefill_form.py` :
```json
{"event": "draft_ready", "request_id": "RUSI-260506-2753446",
 "step_reached": "summary",
 "url": "https://irisbox.irisnet.be/.../edit/2a941989de8245f789d704515d04ecbf21160064/summary"}
```

## Ce qui a été ajouté/changé cette session (2026-05-05 → 2026-05-06)

### `auth_irisbox.py`
- `auto_handle_post_itsme_popups()` : auto-click cookie consent (`Got it`/`OK`/`Accepter tout`) + OAuth consent IRISnet (`Approve`/`Allow`/`Accepter`/`Continuer`/...). Polled à chaque tick de wait_for_form.
- `wait_for_form_and_extract_ids()` : remplacé `wait_for_url` strict par boucle de polling 2s avec screenshots de diag toutes les 30s (`wait_diag_<N>s.png`).
- `wait_for_load_state("networkidle")` retiré (IRISbox keepalive long-poll). Remplacé par `domcontentloaded` + polling textuel.
- `storage_state` désormais sauvé dans `finally` (avant l'exception `browser.close()`), pour ne pas perdre la session si une exception survient post-itsme.
- `headless=False, slow_mo=200` pour le smoke test (à remettre `True` pour OpenClaw prod).

### `prefill_form.py`
- `check_session_expired()` : détecte body "Session expirée" en haut de chaque étape → exit 2 propre.
- `click_next(page, step)` durci : `is_disabled()` check AVANT click + scrape `.invalid-feedback` + inputs `is-invalid` → exit 1 avec `validation_errors=[...]`. `force=True` est désormais un fallback (pas le défaut), seulement si Playwright timeout sur intercepted pointer.
- Idempotency unités : `add_construction_only()` n'ajoute plus les unités. `fill_step2_bien` boucle séparément avec `_unit_already_present(floor, destination)`.
- Idempotency documents : skip upload si filename déjà visible dans le DOM.
- `_select_construction_tab()` : utilise `button.accordion-toggle` + `aria-expanded` (pas `role=tab` WAI-ARIA).
- `add_unit()` : utilise `id="add-area-unit"` direct (selector stable).
- `upload_document()` : utilise `DOC_UPLOAD_BUTTON_ID_BY_LABEL` (IDs `button-upload-RU_<KEY>` stables).
- `_dump_failure_state()` : screenshot full_page + dump validation errors sur toute exception ou SystemExit.
- emit() intermédiaires : `parcelle_added`, `construction_added`, `unit_added`, `parking_filled`, `step1_owner_radio_checked`, `document_uploaded`, `document_already_uploaded`, etc.
- 3s wait + 30s timeout post-upload avant `click_next("documents")` (le serveur fait probablement un scan AV async).
- Flag `--keep-open` : laisse le browser ouvert après run (succès ou crash) pour inspection live. `time.sleep(60)` loop, Ctrl+C pour fermer.
- Wait absolu sur `#next` après `goto(resume_url)` (sinon DOM Angular SPA est vide).
- URL patterns sans `$` strict (tolère querystring/fragment).

### `_selectors.py`
- IDs stables découverts via `dump_*_page.py` :
  - `STEP2_ADD_UNITE_BUTTON_ID = "add-area-unit"`
  - `STEP2_ADD_CONSTRUCTION_BUTTON_ID = "building-add"`
  - `STEP2_TYPE_BUILDING_RADIO_ID = "building-area"` (value=BUILDING)
  - `STEP2_TYPE_LAND_RADIO_ID = "land-area"` (value=LAND)
  - `STEP2_NEXT_BUTTON_ID = "next"` / `STEP2_CANCEL_BUTTON_ID = "cancel"`
  - `STEP2_ACCORDION_TOGGLE_CLASS = "accordion-toggle"` avec `aria-expanded`
  - `DOC_UPLOAD_BUTTON_ID_BY_LABEL` : map des 7 catégories → `button-upload-RU_<KEY>`
- `URL_PATTERN_STEP` : `(?:[?#]|$)` au lieu de `$` strict.

### Nouveaux scripts
- `inspect_step2.py` : diagnostic interactif headless de l'étape 2 (page.pause-style mais scripté).
- `dump_building_page.py` : dump complet DOM de /building (buttons, inputs, headings, tabs, find-construction-strategies). Avant ET après click sur la construction.
- `dump_documents_page.py` : pareil pour /documents — révèle les `button-upload-RU_<KEY>` IDs.

## Bug connu non-résolu

**`fill_step1_demandeur` échoue sur draft déjà avancé**. Quand `resume_url` pointe sur `/requester` mais le draft a déjà passé l'étape 1 (radio Oui pré-coché côté serveur), `radio.check()` + `click_next` force échoue silencieusement (URL ne change pas vers /building, pas de validation_error visible).

**Workaround actuel** : pointer `resume_url` directement sur la dernière étape utile (/building, /documents, etc.). Pour OpenClaw prod, soit :
- Toujours stocker la "step la plus avancée" comme `resume_url`
- Soit detecter "radio déjà coché" (`radio.is_checked()`) et skip le check + click_next direct

À investiguer si OpenClaw doit supporter le resume from /requester sur draft existant.

## Comment reprendre maintenant

```bash
cd /Users/bibihez/Documents/Vibecoding/April_ClawWrapper-main/ru-skill/scripts
source .venv/bin/activate

# Phase 1 : auth (44s d'interaction itsme côté téléphone)
python3 auth_irisbox.py --data /tmp/ru-test/input.json --output-dir /tmp/ru-test
# Récupère draft_id du form_reached event, mets-le dans input.json:resume_url

# Phase 2 : prefill (browser visible, garde ouvert pour debug)
python3 prefill_form.py --session /tmp/ru-test --data /tmp/ru-test/input.json --keep-open
```

## TODO restant pour OpenClaw prod-readiness

1. Headless=True dans auth_irisbox.py + prefill_form.py (actuellement False pour smoke test)
2. Retirer slow_mo (actuellement 200ms / 150ms)
3. Branchement OpenClaw : spawn auth_irisbox.py + prefill_form.py + parse stdout JSON → Telegram I/O
4. Dockerfile OpenClaw : `playwright install chromium` + dépendances Python
5. Fix bug "step 1 on advanced draft" si supporté
6. Étape 4 (récap) avec `--include-summary` à tester (jamais lancé en smoke test)
7. Détection erreur Send post-soumission si user re-utilise le draft (out of scope skill)
