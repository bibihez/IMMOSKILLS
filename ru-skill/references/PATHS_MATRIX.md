# IRISbox RU — Matrice des paths conditionnels

Cartographie exhaustive du formulaire IRISbox v23.0.5 dérivée des dumps `dump_*_page.py` + `explore_paths.py` + `watch_explore.py` du 2026-05-06.

Cette matrice est la **source de vérité** pour :
1. Identifier les selectors stables à utiliser dans `prefill_form.py` (préférer aux accessible names fragiles)
2. Dériver les questions intake OpenClaw (ce qu'il faut demander à l'agent immo avant de remplir)
3. Documenter les paths non couverts pour la roadmap future

---

## Étape 1 — `/requester` (Demandeur)

L'identité du demandeur (`Identité`, `Données de contact`) est **read-only**, pré-remplie depuis CSAM.

### Question principale : "Êtes-vous le propriétaire ?"

| Path | Selectors stables | Comportement |
|---|---|---|
| **Oui** (rare) | `#isLandlordYes` (radio name=landlord) | Le demandeur est ajouté auto comme intervenant Propriétaire. Pas d'autre action. |
| **Non** (95% agents immo) | `#isLandlordNo` | Apparition d'un `<select id="quality">` required + section "Liste des intervenants" devient obligatoire |

### Si `Non` : dropdown `#quality` (required)

| value | text |
|---|---|
| `REAL_ESTATE_AGENT` | Agent immobilier 🎯 |
| `LAWYER` | Avocat |
| `MANDATARY` | Mandataire |
| `OTHER` | Autre |

### Section "Liste des intervenants" (`h3#stakeholders`)

Bouton `#add` → ouvre modal "Intervenant" (`h3#stakeholder-title`).

#### Modal Intervenant — type Personne PHYSIQUE (default)

Radios `name="type"` :
- `#physical-person` value=PHYSICAL ← default checked
- `#moral-people` value=MORAL

| Champ | ID | Required |
|---|---|---|
| Prénom | `#firstName` | ✓ |
| Nom | `#lastName` | ✓ |
| Email | `#email` | optionnel |
| Téléphone | `#phone` | optionnel |
| Rue | `#streetName` | ✓ |
| N° | `#streetNumber` | ✓ |
| Boîte | `#box` | optionnel |
| Code postal | `#zipCode` | ✓ |
| Ville | `#city` | ✓ |
| Pays | `#country` | ✓ |

Boutons modal : `#cancel` (Annuler) / `#save-stakeholder` (Sauvegarder).

#### Modal Intervenant — type Personne MORALE *(non dumpé — TODO)*

À mapper si besoin. Probablement champs : raison sociale, BCE, forme juridique, adresse siège, contact.

### Boutons étape 1
- `#next` (Suivant) — disabled tant que required manquant
- `#btn-action-save` (Sauvegarder draft)
- `#btn-action-export` (Exporter PDF récap)
- `#btn-action-close` (Fermer + retour à la liste)

---

## Étape 2 — `/building` (Bien)

### Adresse / parcelle

Bouton `Ajouter une zone géographique` → ouvre modal "Localisation du bien" (déjà mappé).

Une fois parcelle confirmée :
- Bouton remplacé par `#edit-address` (Modifier l'adresse)
- **Pas de support multi-parcelles** : 1 parcelle = 1 dossier RU. Confirmé par dump `multi_parcelle.json`.

### Type du bien (radios `name="areaType"`)

| Path | Selector | Affecte |
|---|---|---|
| **Terrain non-bâti** | `#land-area` value=LAND | Cache section "Constructions". Section "Liste des unités" + `#add-area-unit` reste accessible (?) |
| **Construction** | `#building-area` value=BUILDING | Affiche section "Constructions" + bouton `#building-add` |

### Si BUILDING : section "Constructions"

Bouton `#building-add` → ouvre modal "Détails de la construction" (`h2#mapModal`).

#### Modal Construction

| Champ | ID | Type |
|---|---|---|
| Dénomination | `#name` | text |
| Description détaillée | `#description` | textarea |

Boutons : `#cross-close` (X) / `#cancel-area-modal` (Annuler) / `#save-area-modal` (Sauvegarder).

**Multi-construction supporté** : N constructions par parcelle. Chaque construction crée un accordion `button.accordion-toggle` nommé "Construction : <denomination>" avec `aria-expanded`.

#### Section unités (sous accordion construction)

Une fois la construction sauvée + accordion expanded :
- Bouton `#add-area-unit` → ouvre modal "Détails de l'unité"
- Actions par construction : `#edit_<idx>`, `#delete_<idx>`, `#accordion_<idx>`

#### Modal Unité

| Champ | ID | Type | Required |
|---|---|---|---|
| Étage | `#floor` | text | ✓ |
| Destination | `#destination` | select | ✓ |
| Description | `#description` (scope modal) | textarea | optionnel |

Options du select `#destination` (UNITE_DESTINATIONS) :
- Activité productive
- Bureau
- Commerce
- Emplacement de stationnement
- Entrepôt
- Equipement
- Hôtel
- Logement *(le plus fréquent)*
- Autre

⚠️ **Sous-champs conditionnels par destination NON confirmés** — probablement aucun (modal stable, on ne fait pas de re-render visible). À valider à l'usage si un agent rapporte un champ manquant.

Boutons modal : `#close-area-modal` (X) / `#cancel-area-modal` (Annuler) / `#save-area-modal` (Sauvegarder).

### Champs au niveau page /building

| Champ | ID | Notes |
|---|---|---|
| Nombre total de logements | `#totalHousingNumber` | **Calculé auto** (read-only) — somme des unités Logement |
| Nombre total de stationnements | `#totalParkingNumber` | **Manuel** (text) — l'agent saisit le nombre de places de parking |

### Boutons étape 2
- `#next` (Suivant) / `#cancel` (Précédent)
- `#edit-address`, `#building-add`
- `#add-area-unit` (visible si BUILDING + construction sélectionnée OU LAND)
- `#btn-action-save`, `#btn-action-export`, `#btn-action-close`

---

## Étape 3 — `/documents`

Pattern d'ID stable pour TOUS les boutons d'upload : `button-upload-RU_<KEY>`.

| Catégorie | ID upload | Required |
|---|---|---|
| Renseignements relatifs au titre de propriété | `#button-upload-RU_RENSEIGNEMENTSRELATIFSAUTITREDEPROPRIETE` | ✓ |
| Copie du mandat | `#button-upload-RU_UNECOPIEDUMANDAT` | ✓ si non-propriétaire |
| Reportage photographique | `#button-upload-RU_PHOTO` | optionnel |
| Croquis ou plans | `#button-upload-RU_CROQUISOUPLANS` | optionnel |
| Extrait du plan parcellaire cadastral | `#button-upload-RU_EXTRAITDUPLANPARCELLAIRECADASTRAL` | optionnel |
| Extrait de la matrice cadastrale | `#button-upload-RU_UNEXTRAITDELAMATRICECADASTRALE` | optionnel |
| Autre document pertinent | `#button-upload-RU_AUTREREMARQUE` | optionnel |

Contraintes upload : `.pdf, .jpg, .png, .jpeg`, max 20MB/fichier, 100MB total, 10 fichiers/catégorie, 255 chars/filename.

Pattern d'upload : click le bouton → Playwright `expect_file_chooser()` → `set_files()` → attendre que le filename apparaisse dans le DOM. Délai post-upload de 3s avant `#next` (probable scan async côté serveur).

---

## Étape 4 — `/summary` (Récapitulatif)

Vue agrégée. Pour chaque section (Demandeur, Bien, Documents) : badge OK + bouton "Aller à l'étape X" pour revenir corriger. Texte attendu si OK : `"Les informations de cette étape sont complètes."`.

Pas d'input. Bouton `#next` mène à `/signature`.

---

## Étape 5 — `/signature` (LIMITE DU SKILL)

⚠️ **Le skill ne click JAMAIS Send.** Décision produit : signature humaine = exigence légale + l'agent valide à la fin pour facturation.

Selectors documentés dans `_selectors.py` pour référence (`STEP5_ARTICLE7_CHECKBOX_PREFIX`, `SUBMIT_BUTTON_NAME_RE`).

---

## Format PDF de récap (`#btn-action-export`)

L'agent peut exporter à tout moment via `#btn-action-export`. Le PDF généré contient :

```
Page 1
─────────────────────────────────────────
Demande de Renseignements Urbanistiques
Nos références : RUSI-YYMMDD-NNNNNNN
Au collège des bourgmestre et échevins de : A.C. <commune>   ← auto-déterminée par parcelle

Adresse du bien
   Cadastré : <capakey>
   • <adresse texte>
   Demande urgente : Non

Coordonnées des intervenants
   Qualité       Détails
   Propriétaire  Nom, Prénom : ...
                 Adresse : <rue> <n°>/<box>, <zip> <city>
                 Téléphone : <...>
                 Adresse mail : <...>
   [+ rangs additionnels si plusieurs intervenants]

   En ma qualité de demandeur, moi <Nom Prénom> j'accepte ...

Description du bien
   Construction : <denom>
   • Description : ...
   • Nombre de logement : <calculé>
   • Nombre de stationnement : <totalParkingNumber>
   [+ Liste des unités avec étage/destination/description]

Page 2
─────────────────────────────────────────
Documents joints à la demande
   Catégorie                              Nom
   <label catégorie>                      • <filename>
```

Note : le PDF est utilisable comme **preuve serveur** que les données ont bien été reçues et persistées. Utile à archiver côté ImmoClaw post-prefill.

---

## Paths NON couverts (roadmap)

1. **Modal Intervenant MORAL** — champs raison sociale + BCE + forme juridique probablement. À mapper quand un agent rencontre un propriétaire SCI/SPRL.
2. **Sous-champs conditionnels par destination unité** — supposé inexistant, à valider si un agent rapporte un blocage sur une destination spécifique (Hôtel ? Activité productive ?).
3. **Étape 6 confirmation post-Send** — non reconnu en recon (skill ne submit pas).
4. **Communes exclues** (Evere, Forest, Koekelberg, Watermael-Boitsfort) → IRISbox refuse probablement la création du draft. À tester pour gérer un message d'erreur clair côté OpenClaw.
5. **Fix bug "step1 sur draft déjà avancé"** : workaround actuel = pointer `resume_url` directement vers la dernière étape utile.

---

## → Questions intake OpenClaw dérivées

L'agent immo doit fournir AVANT que `prefill_form.py` ne tourne :

### Toujours requis
- **Mandat** (PDF scanné) — obligatoire pour Doc + source d'extraction propriétaires
- **Adresse complète du bien** : rue + n° + zip + ville (pour autocomplete IRISbox → capakey)
- **Type du bien** : terrain nu OU construction
- **Titre de propriété** (PDF) — peut venir du dossier ou de notre skill `titre-propriete` en amont

### Si construction (cas dominant)
- **Description courte de la construction** (1 phrase) — ex: "Immeuble 5 étages, façade brique"
- **Pour chaque unité** : étage + destination + (description optionnelle)
- **Nombre total de places de parking** (souvent 0 ou 1)

### Pour chaque propriétaire (extrait du mandat ou demandé)
- Type : Personne physique / Personne morale (à mapper plus tard)
- Si PHYSIQUE : Prénom, Nom, Adresse complète (rue/n°/box/zip/city/country), Email/Téléphone (optionnels)

### Optionnels (gain de qualité du dossier)
- Reportage photographique
- Croquis ou plans existants
- Extrait du plan parcellaire cadastral *(probablement extrait par notre skill `titre-propriete`)*
- Extrait de la matrice cadastrale

### Stratégies d'extraction
- **Si mandat fourni** : extraire propriétaires (nom, adresse) → préfill modal intervenant → ne demander que si manquant
- **Si fiche bien (Whise/Hektor/manuel)** : extraire adresse, type bien, unités, parking → préfill étape 2
- **Sinon** : intake conversationnel Telegram (questions vocales OK)

### Validation pré-flow
- Commune ∈ communes exclues ? → abort + message clair
- Mandat valide ? (signature, date) → à challenger côté OpenClaw
- Document obligatoire titre_propriete présent ? sinon prompter le notaire en amont
