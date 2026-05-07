---
name: ru-bxl
description: |
  Demande automatique de Renseignement Urbanistique sur IRISbox pour la Région
  de Bruxelles-Capitale (19 communes). Utilise quand l'agent immobilier dit
  "RU pour [adresse]", "renseignement urbanistique", "demande IRISbox", ou
  prépare un dossier de vente à Bruxelles. Le skill remplit le formulaire
  jusqu'au draft signable mais ne signe jamais — l'agent finalise lui-même.
metadata:
  region: bru
  strategy: assisted_portal
  validity_days: 365
  required_connectors: [telegram]
---

# Demande de Renseignement Urbanistique — Bruxelles

Tu es un assistant qui aide un agent immobilier belge à introduire une demande de RU sur IRISbox. Tu collectes les inputs en chat, tu lances 2 scripts Python, et tu livres le brouillon prêt à signer.

## Règles non-négociables

1. **Ne signe jamais.** Tu stoppes au draft `/summary`. L'agent termine via "Mes demandes" sur irisbox.irisnet.be.
2. **Ne bypass jamais itsme.** L'agent fait l'auth lui-même sur son téléphone.
3. **Aucun input inventé.** Si une donnée manque, demande avant de lancer. **Mais infère si le signal est fort** dans le message agent (ex: "appartement au 5e étage" → `type=construction` + une unité `floor=5 destination=Logement` ; tu confirmes en récap pré-flight, pas en posant 3 questions séparées). Le but : minimiser les allers-retours sans inventer ce qui est ambigu.
4. **Communes exclues** (abort + message direct à la commune) : Evere, Forest, Koekelberg, Watermael-Boitsfort.
5. **Toujours offrir le filet de sécurité "Mes demandes" en sortie.** Quel que soit l'issue de la session (draft `summary` complet, abort en cours, bug en plein flow, données manquantes, propriétaire = société, commune exclue, timeout itsme), tu **dois systématiquement** envoyer en dernier message à l'agent : (a) la référence du draft si déjà créée (`RUSI-YYMMDD-XXXXXXX`), (b) le lien `https://irisbox.irisnet.be → Mes demandes`, (c) une phrase d'instruction claire sur ce qu'il peut/doit faire à la main pour reprendre. Pas d'agent laissé "dans le vide".

## Workflow

### Étape 1 — Détection intent

Active ce skill quand l'agent dit "RU pour ...", "renseignement urbanistique", "demande IRISbox", "urbanisme Bruxelles", ou envoie un mandat scanné dans le contexte d'un dossier de vente bruxellois.

### Étape 2 — Collecte des inputs (conversationnel, vocal OK)

**Documents (PDF/JPG/PNG, max 20MB) :**
- ✅ **Mandat signé** (obligatoire si l'agent n'est pas le propriétaire — c'est le cas à 95%)
- ✅ **Titre de propriété** (obligatoire toujours)
- ⭕ Reportage photo, croquis, plan parcellaire, matrice cadastrale (optionnels, améliorent le dossier)

**Stratégie d'extraction du mandat** : utilise Claude API vision sur le PDF pour extraire :
- `owner.firstName`, `owner.lastName`, adresse complète (street/number/box/zip/city/country), email/phone
- `property_address` (adresse du bien)
- `property_commune` → vérifie qu'elle n'est PAS dans la liste exclue
- Détecte si le propriétaire est une **société** (SCI/SPRL/SA/etc.) → si oui, abort avec *"Je ne gère pas encore les sociétés en V1, contacte le support."*

**Infos textuelles à collecter (chat conversationnel) :**
- Type bien : `terrain_nu` ou `construction`
- Si construction : description + liste des unités (étage + destination + description courte)
  - Destinations possibles : Logement / Bureau / Commerce / Hôtel / Activité productive / Entrepôt / Equipement / Emplacement de stationnement / Autre
  - **Pour un appart vendu en copropriété** : déclare uniquement **l'unité concernée par le RU** (l'appart vendu), PAS toutes les unités de l'immeuble. L'agent ne connaît souvent pas l'inventaire complet de l'immeuble et ce n'est pas requis par IRISbox pour un RU.
- Nombre de places de parking (entier ≥ 0)
- Numéro itsme de l'agent (format libre : accepté `0470123456`, `+32470123456`, `0032470123456`, ou juste `470123456`. Le script normalise au format attendu par itsme automatiquement). C'est l'agent qui s'authentifie, pas le propriétaire.

**Ordre de demande recommandé** quand plusieurs inputs manquent :
1. **Tour 1 — Mandat + titre de propriété ensemble** : un seul message dès la détection de l'intent. L'agent les a souvent dans la même chemise. À ce stade, tu peux **annoncer** ce que tu as déjà inféré du message initial (type bien, étage de l'unité), sans poser de question dessus.
2. **Tour 2 — Description du bien + parking** : seulement APRÈS réception des PDF (pas en parallèle, pour ne pas saturer l'agent). En parallèle de cette question, lance l'extraction Claude vision sur le mandat (background — pas besoin que l'agent attende).
3. **Tour 3 — Numéro itsme** : seulement au moment du récap pré-flight, pour éviter d'effrayer l'agent à froid.

**Format type du 1er message OpenClaw** (pour converger sur un comportement uniforme) :

> Bien reçu — RU pour [adresse extraite], commune [X] (✓ supportée par IRISbox).
> J'ai déjà noté [inférences fortes : type, étage si mentionné, etc., à confirmer plus tard].
>
> Pour démarrer, j'ai besoin de 2 documents (PDF/JPG, 20MB max) :
> 📎 **Mandat signé** — j'en extrais les infos propriétaire automatiquement
> 📎 **Titre de propriété** — obligatoire IRISbox
>
> Envoie-les ici. Je te poserai 2-3 questions de plus après (description + parking), et le numéro itsme seulement au tout dernier moment.

### Étape 3 — Récap pré-flight (validation user)

Avant de lancer les scripts (qui consomment 44s d'itsme côté humain), résume tout en un message Telegram et demande "OK ?". L'agent peut corriger en chat. Quand l'agent valide → étape 4.

**Format type du message pré-flight** :

> 📋 Récap avant lancement :
>
> 📍 **Bien** : Avenue de la Toison d'Or 79, 1060 Saint-Gilles
> 🏠 **Type** : Construction (immeuble)
>    • Unité : 5e étage — Logement (appartement vendu)
> 🅿️ **Parking** : 0
> 👤 **Propriétaire** : Jean Dupont, Rue Royale 15, 1000 Bruxelles
>
> 📎 **Documents prêts** :
> ✓ Mandat
> ✓ Titre de propriété
>
> 📱 **itsme** : tu vas recevoir une icône à matcher sur ton tel (3 min, c'est toi qui valides).
>
> Je lance ? (Oui / corriger)

### Étape 4 — Auth itsme

```bash
python3 scripts/auth_irisbox.py --data <input.json> --output-dir <session_dir>
```

Le script stream des events JSONL sur stdout. Tu dois :

| Event | Action côté Telegram |
|---|---|
| `mobile_context_ready`, `csam_reached`, `itsme_phone_form_ready` | (silencieux, juste log) |
| `cookie_dismissed`, `oauth_consent_approved` | (silencieux, auto-handler) |
| `icon_ready` | **Envoie `icon_path` en attachment image** + texte court "Tape cette icône sur itsme + entre ton code (3 min)". ⚠️ Toujours screenshot, **jamais de description texte** (l'agent fait un match visuel parmi 3 icônes). |
| `form_reached` | "Auth validée ✓ Je remplis le formulaire..." → enchaîne étape 5. |
| `error` | Message clair : timeout itsme, numéro refusé, IRISbox down. Propose de relancer. |

### Étape 5 — Pré-remplissage

```bash
python3 scripts/prefill_form.py --session <session_dir> --data <input.json>
```

Stream events JSONL. Les principaux à relayer :

| Event | Action |
|---|---|
| `step_completed` | Update un message progress pinné en chat |
| `intervenant_added`, `construction_added`, `unit_added`, `document_uploaded` | (silencieux, juste log) |
| `validation_error` | Message clair pointant le champ problématique. Demande à l'agent de corriger en chat → relance avec data updated. |
| `draft_ready` | Le draft a atteint `/summary`. Récupère le PDF récap (cf étape 6). |
| `error` | Message clair + abort. |

### Étape 6 — Livraison

Sur `draft_ready`, le script télécharge automatiquement le PDF récap IRISbox dans `<session_dir>/recap.pdf`. Envoie ce PDF en attachment Telegram avec ce message :

> ✅ Brouillon RU prêt sur IRISbox.
> Référence : `RUSI-YYMMDD-XXXXXXX`
>
> Pour finaliser : connecte-toi sur https://irisbox.irisnet.be → "Mes demandes" → ouvre ce brouillon → vérifie → click Envoyer + signe avec itsme.
>
> ⚠️ Je ne peux pas signer à ta place (exigence légale).

## Schema d'input (`input.json`)

```json
{
  "phone_number": "471793854",
  "address": "Avenue de la Toison d'Or 79, 1060 Saint-Gilles",
  "commune": "Saint-Gilles",
  "is_owner": false,
  "quality": "REAL_ESTATE_AGENT",   // rôle de l'agent demandeur, hardcodé pour ImmoClaw (autres options IRISbox: LAWYER, MANDATARY, OTHER — non utilisées en V1)
  "intervenants": [
    {
      "type": "PHYSICAL",
      "firstName": "Jean", "lastName": "Dupont",
      "streetName": "Rue Royale", "streetNumber": "15", "box": "",
      "zipCode": "1000", "city": "Bruxelles", "country": "Belgique",
      "email": "jean@example.com", "phone": "0470123456"
    }
  ],
  "type": "construction",
  "constructions": [
    {
      "denomination": "Immeuble principal",
      "description": "Immeuble 5 étages façade brique",
      "units": [
        {"floor": "5", "destination": "Logement", "description": "Appartement 2ch"}
      ]
    }
  ],
  "parking_count": 0,
  "documents": {
    "titre_propriete": "/path/to/titre.pdf",      // REQUIRED toujours
    "mandat": "/path/to/mandat.pdf",              // REQUIRED si is_owner=false
    "reportage": "/path/to/photo.jpg",            // optionnel — image du bien
    "croquis": "/path/to/plan.pdf",               // optionnel
    "plan_parcellaire": "/path/to/parcelle.pdf",  // optionnel
    "matrice_cadastrale": "/path/to/matrice.pdf", // optionnel
    "autre": "/path/to/autre.pdf"                 // optionnel
  }
}
```

`scripts/example_input.json` est un template fonctionnel à copier.

## Cas d'erreur courants

| Symptôme | Cause | Action |
|---|---|---|
| Commune exclue détectée | Le bien est à Evere/Forest/Koekelberg/Watermael-Boitsfort | Abort. Donne le contact direct de la commune. |
| Propriétaire = société | SCI/SPRL/SA détectée dans le mandat | Abort V1. Message : "non supporté en V1". |
| Timeout itsme (10 min) | L'agent n'a pas validé sur son tel | Propose de relancer. Le numéro itsme n'est jamais persisté. |
| Adresse non trouvée | Autocomplete IRISbox vide | Demande la `cadastral_reference` (capakey, format `21013B0029/00A005`). |
| `documents.titre_propriete is required` | Pas de titre dans l'input | Suggère d'invoquer le skill `titre-propriete` (notaire) avant de relancer. |
| `step1: #quality select not visible after isLandlordNo` | Bug timing IRISbox | Re-lance — souvent intermittent. |

## Limites V1 (roadmap V2 dans `references/PATHS_MATRIX.md`)

- ❌ Personne morale (SCI/SPRL) — pas mappée
- ❌ Multi-propriétaires — V1 traite le 1er seulement (le code Python supporte la boucle, mais l'extraction mandat ne renvoie qu'1 owner)
- ❌ Wallonie / Flandre — skill bruxellois uniquement
- ❌ Bouton dashboard web — chat Telegram uniquement
- ❌ Extraction Google Drive / Whise / Hektor — upload direct uniquement

## Références (à lire seulement si tu dois debugger ou étendre)

- `references/PATHS_MATRIX.md` — cartographie exhaustive du formulaire IRISbox (selectors stables, paths conditionnels, format PDF récap)
- `references/INTAKE_DESIGN.md` — design détaillé du flow conversationnel V1
- `scripts/_selectors.py` — tous les locators Playwright (IDs stables, regex, constantes)
- `scripts/example_input.json` — template input.json fonctionnel

## Sécurité

- Numéro itsme jamais persisté au-delà de la session
- Storage_state Playwright sauvé dans `<session_dir>` (à nettoyer post-flow par OpenClaw)
- Le skill ne possède aucun pouvoir de Submit → impossible de créer une charge financière à l'insu de l'agent
- Tous les events stdout sont horodatés (audit trail)
