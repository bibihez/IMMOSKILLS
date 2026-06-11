"""
Locators IRISbox / CSAM / itsme pour le skill RU Bxl.

Recon effectuée 2026-05-04 sur IRISbox version 23.0.5-105.
Browser: Chromium en mode iPhone (UA + viewport mobile) — itsme ne propose
le mode téléphone que pour un UA mobile, sinon QR-only.

Pattern de durcissement: locators sémantiques (get_by_role / get_by_label /
get_by_text) en priorité, IDs stables (#floor, #destination...) en backup
quand le DOM Bootstrap modal n'est pas pris dans l'accessibility tree.
"""

from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Mobile UA spoofing (Playwright context)
# ---------------------------------------------------------------------------
# Sans UA mobile, itsme affiche QR-only et le scénario phone-form n'existe pas.
# À appliquer via `browser.new_context(**MOBILE_CONTEXT)` ou via
# `playwright.devices['iPhone 14']` directement.

MOBILE_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.5 Mobile/15E148 Safari/604.1"
)
MOBILE_VIEWPORT = {"width": 390, "height": 844}
MOBILE_CONTEXT = {
    "user_agent": MOBILE_USER_AGENT,
    "viewport": MOBILE_VIEWPORT,
    "is_mobile": True,
    "has_touch": True,
    "device_scale_factor": 3,
    "locale": "fr-BE",
}

# ---------------------------------------------------------------------------
# URLs
# ---------------------------------------------------------------------------

URL_LANDING = "https://irisbox.irisnet.be/irisbox/urban-information/landing"

# Pattern URL post-validation itsme = on est sur le formulaire RU étape 1
# Forme: /irisbox/urban-information/citizen/edit/<HEX_REQUEST_ID>/requester
URL_PATTERN_FORM_REACHED = re.compile(
    r"/irisbox/urban-information/citizen/edit/[0-9a-f]+/requester"
)

# Patterns par étape (utiles pour assert step après Next)
# Pas de `$` strict : tolère query strings (?foo=bar) et fragments (#section)
URL_PATTERN_STEP = {
    "requester": re.compile(r"/edit/[0-9a-f]+/requester(?:[?#]|$)"),
    "building":  re.compile(r"/edit/[0-9a-f]+/building(?:[?#]|$)"),
    "documents": re.compile(r"/edit/[0-9a-f]+/documents(?:[?#]|$)"),
    "summary":   re.compile(r"/edit/[0-9a-f]+/summary(?:[?#]|$)"),
    "signature": re.compile(r"/edit/[0-9a-f]+/signature(?:[?#]|$)"),
}

# Référence draft: format `RUSI-YYMMDD-NNNNNNN` (visible dès l'étape 1).
# Attention: c'est l'ID de brouillon, pas le numéro post-submit officiel.
RE_DRAFT_REFERENCE = re.compile(r"RUSI-\d{6}-\d{7}")

# ---------------------------------------------------------------------------
# IRISbox landing → dialog auth → CSAM
# ---------------------------------------------------------------------------

# Bouton CTA principal landing — substring suffit, accent FR géré par get_by_role
LANDING_CTA_NAME = "Introduire"

# Mode --session-only : entrée par "Mon espace" (dashboard) — affiche le même
# dialogue "Me connecter" SANS créer de demande (sondé 2026-06-11). Sert à
# ré-authentifier pour reprendre un draft existant sans créer de draft orphelin.
URL_DASHBOARD = "https://irisbox.irisnet.be/irisbox/dashboard"
# Session acquise = retour post-SSO sur n'importe quelle page irisbox
URL_PATTERN_SESSION_READY = re.compile(
    r"irisbox\.irisnet\.be/irisbox/(dashboard|my-box|urban-information)")

# Modale d'annonce "Information" (aria-labelledby="communication-modal") qu'IRISbox
# peut afficher au chargement de la landing. Elle intercepte le clic sur le CTA
# (modal-container intercepts pointer events). Apparue côté IRISbox courant 2026,
# absente du recon de mai. Un seul bouton de fermeture : croix `aria-label="Close"`.
LANDING_COMM_MODAL_SELECTOR = "modal-container[aria-modal='true'].show, .modal.show"
# ⚠️ aria-label dépend de la locale ("Close" en EN, "Fermer" en fr-BE mobile) →
# sélecteur par CLASSE uniquement. Fallback Escape prouvé efficace (2026-06-10).
LANDING_COMM_MODAL_CLOSE_SELECTOR = (
    "modal-container.show button.close, .modal.show button.close"
)

# Dialog auth obligatoire (apparaît au clic du CTA si non authentifié)
DIALOG_AUTH_TITLE = "Authentification obligatoire"
# UI bilingue selon locale: FR='Me connecter', EN='Connect me'
DIALOG_AUTH_CONNECT_RE = re.compile(r"^(Me connecter|Connect me)$")

# CSAM: tile itsme (toujours en mode desktop côté CSAM, le mobile c'est itsme.SPA)
# Heading "Log in" niveau 3 + texte adjacent "via itsme"
# Pattern Playwright: page.get_by_role("heading", name="Log in")
#   .filter(has=page.get_by_text("via itsme"))
# OU plus simple: page.get_by_text("via itsme").click() (heading clickable)
CSAM_ITSME_TEXT = "via itsme"

# ---------------------------------------------------------------------------
# itsme SPA (idp.prd.itsme.services)
# ---------------------------------------------------------------------------

# Form téléphone (UA mobile uniquement) — UI bilingue FR/EN
ITSME_PHONE_HEADING_RE = re.compile(r"(Utilisez votre numéro de téléphone|Use your phone number)")
ITSME_PHONE_COUNTRY_BUTTON = "+32"           # role=button, par défaut Belgique
ITSME_PHONE_TEXTBOX_ROLE = "textbox"          # un seul textbox visible sur la page
ITSME_PHONE_SEND_RE = re.compile(r"^(Envoyer|Send)\s*$")   # disabled tant que numéro invalide

# Écran "Prove it's you" (icône à matcher)
# Apparaît après click Send. Signal `icon_ready`.
# FR='Prouvez que c'est bien vous' (à confirmer au premier vrai run)
# EN='Prove it's you' (avec apostrophe typographique U+2019)
ITSME_PROVE_HEADING_RE = re.compile(r"(Prouvez|Prove it.s you)")
# alt text de l'icône: FR='Icône numéro N' / EN='Icon number N'
ITSME_ICON_NAME_RE = re.compile(r"(?:Icône numéro|Icon number)\s+(\d+)")
# Extraction Python:
#   icon = page.get_by_role("img", name=ITSME_ICON_NAME_RE)
#   alt = icon.get_attribute("alt")              # "Icon number 15"
#   number = int(ITSME_ICON_NAME_RE.match(alt).group(1))
#   icon.screenshot(path="icon.png")

# Timeout itsme: 3 minutes affichés, 10 min de marge côté skill
ITSME_TIMEOUT_SECONDS = 600

# Texte d'erreur si numéro refusé / inconnu / annulé
# (à durcir au premier vrai run, pas observé en recon)

# ---------------------------------------------------------------------------
# Étape 1/6 — Demandeur (/requester)
# ---------------------------------------------------------------------------
# L'identité (prénom, nom, NRN, adresse, locality, phone, email) est
# pré-remplie en lecture seule depuis le profil CSAM.
# Pour la modifier, l'utilisateur doit aller sur /irisbox/userProfile
# en dehors de la skill.

STEP1_OWNER_GROUP = "Etes-vous le propriétaire ?*"
STEP1_OWNER_OUI = "Oui"
STEP1_OWNER_NON = "Non"
STEP1_ADD_INTERVENANT_BUTTON = "Ajouter"   # leading space dans le label réel
STEP1_NEXT_BUTTON = "Next"                  # leading/trailing space, match préfixe

# IDs stables découverts via dump 2026-05-06
STEP1_LANDLORD_YES_ID = "isLandlordYes"
STEP1_LANDLORD_NO_ID = "isLandlordNo"
STEP1_QUALITY_SELECT_ID = "quality"  # required quand isLandlordNo coché
STEP1_ADD_INTERVENANT_BUTTON_ID = "add"  # ouvre modal Intervenant
STEP1_STAKEHOLDERS_HEADING_ID = "stakeholders"  # h3 section "Liste des intervenants"

# Options du select #quality côté PAGE PARENT /requester (rôle de l'agent demandeur)
QUALITY_REAL_ESTATE_AGENT = "REAL_ESTATE_AGENT"  # Agent immobilier (default ImmoClaw)
QUALITY_LAWYER = "LAWYER"
QUALITY_MANDATARY = "MANDATARY"
QUALITY_OTHER = "OTHER"

# Options du select #quality côté ROUTE /stakeholder/add (rôle de l'intervenant ajouté)
# Inclut LANDLORD en plus — option à utiliser pour les vrais propriétaires.
INTERVENANT_QUALITY_LANDLORD = "LANDLORD"           # Propriétaire (default ImmoClaw)
INTERVENANT_QUALITY_REAL_ESTATE_AGENT = "REAL_ESTATE_AGENT"
INTERVENANT_QUALITY_LAWYER = "LAWYER"
INTERVENANT_QUALITY_MANDATARY = "MANDATARY"
INTERVENANT_QUALITY_OTHER = "OTHER"

# Modal Intervenant — IDs des champs (h3#stakeholder-title)
INTERVENANT_TYPE_PHYSICAL_RADIO_ID = "physical-person"  # value=PHYSICAL (default)
INTERVENANT_TYPE_MORAL_RADIO_ID = "moral-people"        # value=MORAL (non implémenté)
INTERVENANT_FIRSTNAME_ID = "firstName"   # required
INTERVENANT_LASTNAME_ID = "lastName"     # required
INTERVENANT_EMAIL_ID = "email"           # optionnel
INTERVENANT_PHONE_ID = "phone"           # optionnel
INTERVENANT_STREET_NAME_ID = "streetName"    # required
INTERVENANT_STREET_NUMBER_ID = "streetNumber"  # required
INTERVENANT_BOX_ID = "box"               # optionnel
INTERVENANT_ZIPCODE_ID = "zipCode"       # required
INTERVENANT_CITY_ID = "city"             # required
INTERVENANT_COUNTRY_ID = "country"       # required, default "Belgique"
INTERVENANT_SAVE_BUTTON_ID = "save-stakeholder"
INTERVENANT_CANCEL_BUTTON_ID = "cancel"  # ⚠️ même ID que le bouton Précédent page parent

# Note: si Oui sélectionné, l'intervenant courant est ajouté automatiquement
# en type "Citoyen". Si Non, un dropdown rôle apparaît (à reconfirmer au
# premier vrai run pour un mandataire/avocat).

# ---------------------------------------------------------------------------
# Étape 2/6 — Bien (/building)
# ---------------------------------------------------------------------------

STEP2_ADD_ZONE_BUTTON = "Ajouter une zone géographique"
# Bouton qui ouvre la modale de localisation. ID stable. ⚠️ Clic NORMAL requis :
# force=True ne déclenche pas le handler Angular d'ouverture de la modale.
STEP2_ADD_ZONE_BUTTON_ID = "address-select"

# Modal "Localisation du bien" (apparaît au clic Ajouter une zone)
# Refonte IRISbox 2026 : la modale est `#mapModal` (carte OpenLayers). IDs stables
# observés en live 2026-06-10, remplacent les anciens selectors par-nom EN ("Search").
DIALOG_LOCALISATION_TITLE = "Localisation du bien"
LOCALISATION_MODAL_SELECTOR = "#mapModal, modal-container:has(#capa-key-finder)"
LOCALISATION_ADDR_INPUT_ID = "addr-map-finder"        # combobox adresse (autocomplete)
LOCALISATION_CAPAKEY_INPUT_ID = "capa-key-finder"     # textbox parcelle (capakey)
LOCALISATION_SEARCH_ADDR_ID = "search-address"        # bouton Rechercher (adresse)
LOCALISATION_SEARCH_CAPAKEY_ID = "search-capa-key"    # bouton Rechercher (capakey)
LOCALISATION_SAVE_ID = "save-map"                     # bouton Confirmer
LOCALISATION_CANCEL_ID = "cancel-map"                 # bouton Annuler
LOCALISATION_CLOSE_ID = "cross-close"                 # croix fermeture

# noms conservés pour compat / autocomplete adresse (combobox = role=combobox)
LOCALISATION_ADRESSE_COMBOBOX_NAME = "Adresse"
LOCALISATION_PARCELLE_TEXTBOX_NAME = "Parcelle"
# Capakey format: 5 chiffres + 1 lettre + 4 chiffres + / + 5 caractères + nnA
RE_CAPAKEY = re.compile(r"^\d{5}[A-Z]\d{4}/\d{2}[A-Z]\d{3}$")
# Ex: "21013B0029/00A005"

LOCALISATION_CONFIRMER_BUTTON = "Confirmer"

# IMPORTANT: Le combobox Adresse passe à `[expanded]` quand l'autocomplete
# est prêt. La suggestion bleue est dans `role=listbox > role=option`.
# Pattern Python:
#   combo = page.get_by_role("combobox", name="Adresse")
#   combo.fill("Avenue de la Toison d'Or 79")
#   page.wait_for_selector('role=listbox')   # attente expansion
#   page.get_by_role("option").first.click()
# Effet: la textbox Parcelle est remplie automatiquement avec la capakey.

# Tableau parcelle sélectionnée (post-Confirmer)
PARCELLE_TABLE_ROW_SELECTED = "Sélectionnée"
PARCELLE_MODIFY_BUTTON = "Modifier l'adresse"

# Section "Descriptif sommaire"
STEP2_TYPE_GROUP = "Le bien sélectionné est*"
STEP2_TYPE_TERRAIN_NU_PREFIX = "un terrain non-bâti"
STEP2_TYPE_CONSTRUCTION_PREFIX = "Un terrain avec construction"

# Si type = construction → bouton "Ajouter une construction"
STEP2_ADD_CONSTRUCTION_BUTTON = "Ajouter une construction"

# Modal construction (Détails de la construction)
DIALOG_CONSTRUCTION_TITLE = "Détails de la construction"
CONSTRUCTION_DENOMINATION_LABEL = "Dénomination de la construction"
CONSTRUCTION_DESCRIPTION_LABEL = "Description détaillée de la construction"
CONSTRUCTION_SAVE_BUTTON = "Sauvegarder"
CONSTRUCTION_CANCEL_BUTTON = "Cancel"

# Sub-section construction (par tab) — IDs stables sur la page parente
STEP2_TOTAL_HOUSING_INPUT_ID = "totalHousingNumber"   # readonly, calculé
STEP2_TOTAL_PARKING_INPUT_ID = "totalParkingNumber"   # required manuel
STEP2_ADD_UNITE_BUTTON = "Ajouter une unité"
# IDs stables découverts via dump_building_page.py (2026-05-05)
STEP2_ADD_UNITE_BUTTON_ID = "add-area-unit"
STEP2_ADD_CONSTRUCTION_BUTTON_ID = "building-add"
STEP2_EDIT_ADDRESS_BUTTON_ID = "edit-address"
STEP2_TYPE_BUILDING_RADIO_ID = "building-area"   # value=BUILDING
STEP2_TYPE_LAND_RADIO_ID = "land-area"           # value=LAND
STEP2_NEXT_BUTTON_ID = "next"
STEP2_CANCEL_BUTTON_ID = "cancel"
# L'accordion construction utilise class='accordion-toggle' avec aria-expanded
STEP2_ACCORDION_TOGGLE_CLASS = "accordion-toggle"

# Modal unité (Bootstrap modal — pas dans accessibility tree, scope au dialog)
# Pattern Python:
#   modal = page.get_by_role("dialog").filter(has_text="Détails de l'unité")
#   modal.locator('#floor').fill(...)
DIALOG_UNITE_TITLE = "Détails de l'unité comprise dans la construction"
UNITE_FLOOR_INPUT_ID = "floor"                # text required, ex "5", "0,5", "1 et 2"
UNITE_DESTINATION_SELECT_ID = "destination"   # required
UNITE_DESCRIPTION_TEXTAREA_ID = "description" # optional, dupliqué côté parent
UNITE_SAVE_BUTTON_ID = "save-area-modal"
UNITE_CANCEL_BUTTON_ID = "close-area-modal"
UNITE_CLOSE_BUTTON_ID = "cross-close"

# Options du dropdown Usage actuel
UNITE_DESTINATIONS = (
    "Activité productive",
    "Bureau",
    "Commerce",
    "Emplacement de stationnement",
    "Entrepôt",
    "Equipement",
    "Hôtel",
    "Logement",
    "Autre",
)

# ---------------------------------------------------------------------------
# Étape 3/6 — Documents (/documents)
# ---------------------------------------------------------------------------
# Catégories. Le label exact en français est utilisé comme ancre via heading.
# Pattern Python:
#   section = page.get_by_role("heading", name=DOC_TITRE).locator("..").locator("..")
#   section.get_by_role("button", name="Add").click()  # ouvre file chooser
#   page.set_input_files(...)  via Playwright fileChooser

DOC_REPORTAGE_PHOTO     = "Reportage photographique"
DOC_CROQUIS_PLANS       = "Croquis ou plans"
DOC_COPIE_MANDAT        = "Copie du mandat"           # obligatoire si non-propriétaire
DOC_TITRE_PROPRIETE     = "Renseignements relatifs au titre de propriété"  # OBLIGATOIRE
DOC_PLAN_PARCELLAIRE    = "Extrait du plan parcellaire cadastral"
DOC_MATRICE_CADASTRALE  = "Extrait de la matrice cadastrale"
DOC_AUTRE               = "Autre document pertinent"

# IDs stables des boutons upload (dump 2026-05-06).
# Pattern IRISbox: `button-upload-RU_<KEY>` où KEY est l'enum interne.
DOC_UPLOAD_BUTTON_ID_BY_LABEL = {
    DOC_REPORTAGE_PHOTO:     "button-upload-RU_PHOTO",
    DOC_CROQUIS_PLANS:       "button-upload-RU_CROQUISOUPLANS",
    DOC_COPIE_MANDAT:        "button-upload-RU_UNECOPIEDUMANDAT",
    DOC_TITRE_PROPRIETE:     "button-upload-RU_RENSEIGNEMENTSRELATIFSAUTITREDEPROPRIETE",
    DOC_PLAN_PARCELLAIRE:    "button-upload-RU_EXTRAITDUPLANPARCELLAIRECADASTRAL",
    DOC_MATRICE_CADASTRALE:  "button-upload-RU_UNEXTRAITDELAMATRICECADASTRALE",
    DOC_AUTRE:               "button-upload-RU_AUTREREMARQUE",
}

DOC_CATEGORIES_REQUIRED = (DOC_TITRE_PROPRIETE,)
DOC_CATEGORIES_REQUIRED_IF_MANDATAIRE = (DOC_COPIE_MANDAT,)
DOC_CATEGORIES_OPTIONAL = (
    DOC_REPORTAGE_PHOTO,
    DOC_CROQUIS_PLANS,
    DOC_PLAN_PARCELLAIRE,
    DOC_MATRICE_CADASTRALE,
    DOC_AUTRE,
)

# Contraintes upload (extraites de l'alert "Caractéristiques des documents")
DOC_ALLOWED_EXTENSIONS = ("pdf", "jpg", "png", "jpeg")
DOC_MAX_FILENAME_CHARS = 255
DOC_MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024
DOC_MAX_TOTAL_SIZE_BYTES = 100 * 1024 * 1024
DOC_MAX_FILES_PER_CATEGORY = 10

# Détection erreur de validation: le bouton Add reçoit
# `aria-describedby` qui pointe vers un message "This field is required".
# Pattern Python:
#   btn = section.get_by_role("button", name="Add")
#   desc_id = btn.get_attribute("aria-describedby")
#   if desc_id:
#       err = page.locator(f"#{desc_id}").inner_text()
#       # → "Une erreur est survenue. This field is required."

# ---------------------------------------------------------------------------
# Étape 4/6 — Récapitulatif (/summary)
# ---------------------------------------------------------------------------
# Vue agrégée. Section par étape avec status.
# Texte attendu si étape OK: "Les informations de cette étape sont complètes."
# Bouton "Aller à l'étape X" pour revenir corriger.

STEP4_SECTION_HEADINGS = ("1 - Demandeur", "2 - Bien", "3 - Documents")
STEP4_OK_TEXT = "Les informations de cette étape sont complètes."

# ---------------------------------------------------------------------------
# Étape 5/6 — Signature (/signature)
# ---------------------------------------------------------------------------
# ⚠️ Dernière étape avant submit. NE JAMAIS cliquer Send sans confirmation
# explicite utilisateur (cf. règle non-négociable de la skill OpenClaw).

STEP5_SIGNATURE_HEADING_PREFIX = "Signature -"   # suivi de "{Firstname} {Lastname}"

STEP5_ARTICLE7_CHECKBOX_PREFIX = (
    "J’ai compris que la validation de la demande vaut signature"
)
# Match avec apostrophe typographique U+2019 — utiliser
# get_by_role("checkbox", name=re.compile(r"^J.ai compris que la validation"))
# pour résister aux variantes d'apostrophe.

# ⚠️ Bouton submit. Texte "Send " (UI bilingue, ne PAS supposer "Envoyer").
# Toujours matcher avec un regex tolérant aux deux langues:
SUBMIT_BUTTON_NAME_RE = re.compile(r"^(Send|Envoyer|Verzenden)\s*$")

# Badge "Saved" adjacent à la référence — confirme que le draft est sync
# côté backend. Présent à partir de l'étape 5.
SAVED_BADGE_TEXT = "Saved"

# ---------------------------------------------------------------------------
# Étape 6/6 — Confirmation (NON RECONNUE EN RECON)
# ---------------------------------------------------------------------------
# Page post-Send. Probablement: référence officielle + paiement (Molenbeek)
# + lien export. À durcir au premier run réel en prod.
# Format de référence officielle attendu (à confirmer): probablement le même
# `RUSI-YYMMDD-NNNNNNN` mais sans le badge "draft".

# ---------------------------------------------------------------------------
# Locators globaux (header / sidebar)
# ---------------------------------------------------------------------------

GLOBAL_REFERENCE_TEXT_PREFIX = "Reference:"
GLOBAL_PDF_EXPORT_BUTTON = "PDF Export"
GLOBAL_SAVE_BUTTON = "Save"
GLOBAL_CLOSE_BUTTON = "Close"   # ferme le formulaire et retourne à la liste
GLOBAL_SHARE_BUTTON = "Share"   # apparaît parfois (étape 4 récap)

# Indicateur étape courante: <text>STEP {N}/6</text>
RE_STEP_INDICATOR = re.compile(r"STEP (\d)/6")

# ---------------------------------------------------------------------------
# Communes exclues IRISbox
# ---------------------------------------------------------------------------
# Si la commune du bien est dans cette liste, abort avant de lancer le flow:
# la demande doit se faire directement en commune (pas via IRISbox).

COMMUNES_EXCLUES = frozenset({
    "Evere",
    "Forest",
    "Koekelberg",
    "Watermael-Boitsfort",
})
# Note: l'UI orthographie "Watermael-Boisfort" (sans le 't' final).
# La forme officielle est "Watermael-Boitsfort". Le check doit être tolérant:
def is_excluded_commune(name: str) -> bool:
    """Tolère les variantes Watermael-Boi(t)sfort et la casse."""
    norm = name.strip().lower()
    return norm in {c.lower() for c in COMMUNES_EXCLUES} or norm in {
        "watermael-boisfort",
    }
