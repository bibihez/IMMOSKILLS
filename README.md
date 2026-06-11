# IMMOSKILLS

Skills ImmoClaw (agent runtime OpenClaw) — un dossier par skill, format
[Anthropic Agent Skills](https://agentskills.io) : `<slug>/SKILL.md` + `references/` + `scripts/`.

## Skills

| Skill | Description | Statut |
|---|---|---|
| [`ru-bxl`](ru-bxl/) | Demande de Renseignements Urbanistiques sur IRISbox (Bruxelles, 19 communes). Remplit le formulaire jusqu'au brouillon signable — ne signe jamais. Résilience 3 couches : script déterministe + rescue LLM par étape + fallback email commune. | 5 runs E2E verts (2026-06-11) |

## Setup (ru-bxl)

```bash
cd ru-bxl/scripts
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
python3 preflight_check.py   # 20s — vérifie que les sélecteurs IRISbox n'ont pas dérivé
```
