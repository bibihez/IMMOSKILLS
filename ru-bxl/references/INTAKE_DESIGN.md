# RU skill — Intake conversationnel OpenClaw V1

Spec du flow Telegram qui collecte les infos de l'agent immo et lance `auth_irisbox.py` + `prefill_form.py`.

> ⚠️ **2026-06-10 — SKILL.md est canonique en cas de divergence.** Deltas depuis ce design :
> 1. Mandat + **titre de propriété demandés ensemble au Tour 1** (pas le titre au récap).
> 2. Le **capakey extrait du titre de propriété est la localisation primaire** (chemin
>    prouvé E2E) ; l'autocomplete adresse n'est que le fallback. Dans le mapping ci-dessous,
>    `cadastral_reference` doit être rempli depuis le titre, pas laissé vide.
> 3. **`validate_input.py` tourne avant le récap pré-flight** (fail-fast, erreurs relayables).
> 4. Mapper le langage naturel vers l'enum destinations ("appartement" → Logement).

## Scope V1

**In** :
- Chat Telegram only (pas de bouton dashboard web)
- Upload mandat direct dans le chat (pas de Google Drive)
- Propriétaire = personne physique uniquement
- 1 propriétaire (le mandat peut en mentionner plusieurs, on traite le 1er en V1)
- Bruxelles 19 communes (- les 4 exclues IRISbox)

**Out** (V2+) :
- Bouton dashboard web ImmoClaw
- Google Drive / Whise / Hektor extraction de fiche bien
- Propriétaire personne morale (SCI / SPRL)
- Multi-propriétaires
- Wallonie / Flandre

## Flow conversationnel

### État 0 — Idle

Détection intent dans n'importe quel message agent. Triggers :
- "j'ai besoin d'un RU pour [adresse]" / "demande un RU" / "renseignement urbanistique"
- L'agent envoie un PDF qui ressemble à un mandat (détection heuristique du type doc)

→ Transition à **État 1**.

### État 1 — Demande du mandat

```
OpenClaw : Pour faire la demande de RU à IRISbox, j'ai besoin du
mandat signé. Envoie-moi le PDF (ou photo nette si scanné).
```

Validation : extension .pdf ou image. Sinon : *"Format non supporté. Envoie un PDF ou une photo (.jpg/.png)."*

→ Transition à **État 2** dès réception du fichier.

### État 2 — Extraction du mandat (Claude API vision)

Backend (pas de message agent pendant ce temps) :
- Upload du PDF à Claude API (model: `claude-opus-4-7`, vision activée)
- Prompt structuré qui extrait JSON :
  ```json
  {
    "owner": {
      "type": "PHYSICAL",
      "firstName": "...", "lastName": "...",
      "streetName": "...", "streetNumber": "...", "box": "...",
      "zipCode": "...", "city": "...", "country": "Belgique",
      "email": "...", "phone": "..."
    },
    "property_address": "Rue X 12, 1060 Saint-Gilles",
    "property_commune": "Saint-Gilles",
    "moral_detected": false,   // true si SCI/SPRL/société détectée
    "extraction_confidence": "high"|"medium"|"low",
    "extraction_notes": "..."
  }
  ```

**Branches d'erreur** :
- Si `moral_detected=true` → message *"Le mandat mentionne une société (SCI/SPRL). Je ne gère pas encore ce cas en V1, contacte le support."* + abort.
- Si `property_commune` ∈ {Evere, Forest, Koekelberg, Watermael-Boitsfort} → message *"La commune [X] ne passe pas par IRISbox, il faut faire la demande directement à l'administration communale. Voici le contact : [..]"* + abort.
- Si `extraction_confidence=low` → message *"Je n'arrive pas à lire le mandat correctement. Renvoie-moi une photo plus nette ou tape les infos en chat."* (passage manuel)

→ Transition à **État 3** sinon.

### État 3 — Confirmation extraction

```
OpenClaw : Voici ce que j'ai trouvé dans le mandat :

  Propriétaire : Jean Dupont
  Adresse : Rue Royale 15, 1000 Bruxelles
  Email : jean.dupont@example.com (optionnel)
  Téléphone : 0470123456 (optionnel)

  Bien à renseigner : Avenue de la Toison d'Or 79, 1060 Saint-Gilles

C'est correct ? (Oui / corrige X)
```

Si "Oui" → État 4. Si "corrige" → re-prompt sur le champ pointé (chat libre, l'agent corrige).

### État 4 — Description du bien

Questions séquentielles, courtes :

```
OpenClaw : Type de bien ?
   1. Terrain non bâti
   2. Construction (immeuble, maison, appartement, etc.)
```

Si **terrain non bâti** → on saute à État 5 (parking_count = 0).

Si **construction** :

```
OpenClaw : Décris-moi la construction (1 phrase suffit, ex:
"Immeuble 5 étages façade brique").

[agent répond, libre, vocal OK]

OpenClaw : Combien d'unités dans ce bien ?

[agent : "1 appartement au 5e étage" / "3 unités: 1 commerce RDC, 2 appts 1er+2e"]

OpenClaw extrait via Claude API les units[] structurés (étage,
destination, description). Confirme rapidement :

OpenClaw : OK donc :
   • Étage 5 — Logement — Appartement
C'est ça ? (Oui / non)

OpenClaw : Combien de places de parking au total ?
```

→ Transition à **État 5**.

### État 5 — Récap pré-flight

```
OpenClaw : Récap avant lancement :

  📍 Bien : Avenue Toison d'Or 79, 1060 Saint-Gilles
  🏠 Construction : Immeuble 5 étages façade brique
     • Étage 5 — Logement
  🅿️ Parking : 0
  👤 Propriétaire : Jean Dupont (Rue Royale 15, 1000 Bxl)

  Documents à joindre :
  ✓ Mandat (déjà reçu)
  ✗ Titre de propriété (manquant)

OpenClaw : Il me manque le titre de propriété. Tu l'as ?
```

Si l'agent l'envoie → État 6.
Si l'agent dit "non, je ne l'ai pas" → suggestion : *"Veux-tu que je le demande au notaire à ta place ?"* (hook futur skill `titre-propriete`, V1 : on fail proprement avec consigne *"obtiens le titre puis reviens"*).

```
OpenClaw : Tout est OK. Je vais maintenant me connecter à IRISbox
avec ton compte itsme. Donne-moi ton numéro de téléphone (format
04XXXXXXXX). Tu recevras une notification itsme à valider sur ton tel.
```

L'agent envoie son numéro. → État 6.

### État 6 — Auth itsme

OpenClaw lance `auth_irisbox.py --data input.json --output-dir /tmp/<session_id>`.

Sur l'event `mobile_context_ready` → silencieux (log seulement).
Sur `csam_reached` / `itsme_phone_form_ready` → silencieux.
Sur `icon_ready` :

```
OpenClaw : [📎 icon.png attached]
Tape cette icône sur ton app itsme (3 min pour valider).
```

⚠️ **Attachment image, jamais de description texte** (cf mémoire `feedback_send_screenshots_not_descriptions.md`).

Sur `cookie_dismissed` / `oauth_consent_approved` → silencieux (auto-handlé).

Sur `form_reached` :

```
OpenClaw : Auth validée ✓ Je remplis le formulaire IRISbox...
(durée : ~30s)
```

Sur `error` (timeout itsme, etc.) → message clair + abort.

### État 7 — Prefill

OpenClaw lance `prefill_form.py --session /tmp/<session_id> --data input.json`.

Stream les events JSON. Pour chaque event significatif (step_completed, intervenant_added, document_uploaded), update un message Telegram pinné en mode "progress" :

```
OpenClaw : Progression :
  ✓ Étape 1 — Demandeur (mandataire ajouté)
  ✓ Étape 2 — Bien (parcelle, construction, unité)
  ⏳ Étape 3 — Documents...
```

Sur `validation_error` → message clair pointant vers le champ + abort + clean (pas de draft orphelin sans contenu).

### État 8 — Livraison

Sur `draft_ready` :
- OpenClaw click `#btn-action-export` programmatiquement (déjà testé via watch_explore.py)
- Récupère le PDF récap IRISbox
- Envoie en attachment Telegram :

```
OpenClaw : ✅ Brouillon prêt sur IRISbox.

📎 [recap.pdf]

Référence : RUSI-260507-XXXXXXX

Pour finaliser :
1. Connecte-toi sur irisbox.irisnet.be
2. Va dans "Mes demandes"
3. Ouvre ce brouillon, vérifie les infos
4. Click "Envoyer" et signe avec itsme

⚠️ Je ne peux pas signer à ta place (exigence légale).
```

**FIN** du flow OpenClaw. Le draft reste sur IRISbox côté serveur — le skill ne fait jamais de submit.

## Mapping data → input.json (contrat avec prefill_form.py)

```python
{
  "phone_number": agent.phone,                        # de l'agent immo (lui qui itsme)
  "address": extracted.property_address,
  "cadastral_reference": "",                          # autocomplete IRISbox
  "commune": extracted.property_commune,
  "is_owner": False,                                   # toujours false en V1 (agent immo)
  "quality": "REAL_ESTATE_AGENT",
  "intervenants": [extracted.owner],                   # le propriétaire physique
  "type": "construction" or "terrain_nu",
  "constructions": [{"denomination": "Construction", "description": ..., "units": [...]}],
  "parking_count": <int>,
  "documents": {
    "titre_propriete": "/path/to/uploaded.pdf",
    "mandat": "/path/to/uploaded.pdf"
  },
  "resume_url": "<set after form_reached event>"
}
```

## Limites V1 + roadmap V2

| Cas | V1 | V2 |
|---|---|---|
| Société propriétaire | ❌ abort + msg | Implem `add_intervenant_moral()` |
| Multi-propriétaires | 1er seulement | Boucler sur `intervenants[]` (déjà supporté côté prefill_form) |
| Communes exclues | ❌ abort + msg | Skill `ru-bxl-commune-direct` (mailto) |
| Wallonie / Flandre | ❌ "non supporté" | Skill RU régional dédié |
| Bouton dashboard | ❌ chat only | API endpoint POST + bouton sur immoclaw.be |
| Drive / Whise / Hektor | ❌ upload direct | Composio Drive intégration |
| Auto-demande titre au notaire | suggestion | Skill `titre-propriete` chained |
| Multiples constructions | ✓ supporté | OK (boucle existe déjà) |

## TODO codage côté OpenClaw

1. **Détection intent** : prompt système OpenClaw qui détecte les triggers RU (cf État 0)
2. **Extraction mandat via Claude API vision** : helper `extractMandatPDF(pdfBuffer): MandatData`
3. **Parser réponse agent → units[]** : helper `extractUnits(naturalLanguage): UnitArray`
4. **Webhook handler dispatch** : routing State Machine côté OpenClaw (state stocké en Postgres par chat_id)
5. **Spawn process auth_irisbox.py + prefill_form.py + parse stdout JSON** : helper `runRuSkill(input)` qui stream les events vers le webhook Telegram
6. **PDF récap fetch** : appeler `#btn-action-export` après `draft_ready` (prefill_form.py doit ajouter cette action en fin de flow OU on lance un script séparé `export_pdf.py`)

## Validation requise avant codage

- [ ] User valide ce design global
- [ ] User valide les wordings français (les messages OpenClaw cités sont des drafts — sa voix > la mienne)
- [ ] Décision : où vit la State Machine côté OpenClaw ? Prompt système qui gère les états, ou code Python explicit qui dispatche ? Ma préférence = **prompt système** (LLM gère le flow naturellement, plus tolérant aux digressions de l'agent).
