# Contacts RU — communes hors IRISbox (fallback email/courrier)

Contacts **vérifiés sur les sites officiels des communes le 2026-06-11** (chaque
info est sourcée — ne jamais utiliser une adresse non listée ici sans la
re-vérifier sur le site officiel). Sert la couche 3 de résilience : demande de
RU par écrit au collège des bourgmestre et échevins.

> ⚠️ **La liste d'exclusion est peut-être périmée.** Forest affirme désormais que
> les RU se font *« uniquement via IRISbox »* (depuis l'arrêté du 3 mai 2018 cité
> par la commune). Le recon de mai 2026 excluait Forest — **à re-tester en live**
> (essayer une adresse de Forest dans la modale de localisation IRISbox). Si ça
> passe, retirer Forest de `COMMUNES_EXCLUES` dans `_selectors.py`.

---

## Evere (1140)

- **Email** : `evere@evere.brussels` (email général — seul email publié sur la page RU ; `urbanisme@evere.brussels` circule en résultat de recherche mais N'EST CONFIRMÉ sur aucune page officielle, ne pas l'utiliser)
- **Adresse** : Square S. Hoedemaekers 10, 1140 Evere (service Urbanisme et Environnement)
- **Téléphone** : 02 247 62 22
- **Formulaire propre** : OUI — formulaire Word 2026 à télécharger sur la page RU et à joindre à la demande
- **Spécificités** : base légale citée CoBAT art. 275-276 ; "à demander dès le début de la mise en vente" ; guichet lun-ven 8h-12h30, mar 16h-19h30
- **Redevance / délai publiés** : non trouvés
- Sources : [page RU](https://evere.brussels/fr/demarches/urbanisme-et-environnement/renseignements-urbanistiques), [service urbanisme](https://evere.brussels/fr/demarches/urbanisme-et-environnement)

## Forest (1190) — ⚠️ se dit IRISbox-only

- **Email** : `ru@forest.brussels` (email dédié RU du service Urbanisme-Environnement)
- **Adresse** : Administration communale de Forest, Rue du Curé 2, 1190 Forest
- **Téléphone** : 02 348 17 26 (ligne RU) ; urbanisme général 02 370 22 28 / 02 348 17 21
- **Spécificités** : la commune indique que les demandes se font **uniquement via IRISbox** ; délai légal 30 jours — passé ce délai, la publicité de vente doit mentionner la date de la demande et la preuve d'envoi ; horaires lun-jeu 8h30-12h + 13h-16h, ven 8h30-12h
- **Redevance publiée** : non trouvée
- Sources : [page RU](https://forest.brussels/fr/demarches/urbanisme-travaux/demande-de-renseignements-urbanistiques), [contact urbanisme](https://forest.brussels/fr/themes/proprete-espace-public-urbanisme/urbanisme/contacter-le-service-urbanisme-environnement)

## Koekelberg (1081)

- **Email** : `ru@koekelberg.brussels` (dédié RU) ; général : `urbanisme@koekelberg.brussels`
- **Adresse** : Service Urbanisme (Gestion du territoire), Place Henri Vanhuffel 6, 1081 Koekelberg
- **Téléphone** : 02 600 15 26
- **Formulaire propre** : OUI — PDF communal à compléter/signer, envoi par courrier ou email
- **Pièces requises** : preuve de propriété/mandat, extrait du plan cadastral, brève description du bien (datée/signée), **preuve de paiement de la redevance** — "seules les demandes complètes seront traitées"
- **Redevance** : 103,70 € (tarif 2026), doublée en urgence (vente judiciaire uniquement) ; compte BE49 0910 1669 7971 (BIC GKCCBEBB), communication = adresse du bien
- **Délai** : 30 jours ; 5 jours ouvrables en urgence (vente judiciaire)
- Sources : [page RU](https://www.koekelberg.be/w/index.php?cont=2899&lgn=1), [page urbanisme](https://www.koekelberg.be/w/index.php?cont=2727&lgn=1)

## Watermael-Boitsfort (1170)

- **Email** : `urbanisme@wb1170.brussels` (service compétent — préférer) ; général : `information@wb1170.brussels`
- **Adresse** : Service Urbanisme, Maison Haute — 1er étage, Place Antoine Gilson 2, 1170 Bruxelles
- **Téléphone** : 02 674 74 32 (urbanisme) ; général 02 674 74 11
- **Formulaire propre** : OUI — formulaire Word basé sur l'annexe 1 de l'AG du 29/03/2018, à télécharger sur la page RU
- **Spécificités** : guichet urbanisme le lundi uniquement (sept-juin 9h30-12h + 13h30-15h30 ; juil-août 8h30-13h)
- **Redevance / délai publiés** : non trouvés
- Sources : [page RU](https://watermael-boitsfort.be/fr/vivre-a-watermael-boitsfort/urbanisme/renseignements-urbanistiques), [page urbanisme](https://watermael-boitsfort.be/fr/vivre-a-watermael-boitsfort/urbanisme)

---

## Mode d'emploi (agent)

1. **Formulaire communal d'abord** : 3 communes sur 4 publient leur propre
   formulaire (Evere, Koekelberg, Watermael-Boitsfort) — le télécharger, le
   remplir avec les données de l'input.json, le joindre. La lettre libre est le
   fallback du fallback.
2. **Koekelberg exige le paiement AVANT** : la demande n'est traitée qu'avec la
   preuve de paiement de la redevance (103,70 € en 2026). Donner les coordonnées
   de paiement à l'agent immobilier et attendre sa preuve avant d'envoyer.
3. Joindre systématiquement : mandat signé + titre de propriété (+ extrait
   cadastral pour Koekelberg).
4. Demander un accusé de réception ; relancer à J+15 sans réponse ; rappeler à
   l'agent que le délai légal est de 30 jours et que passé ce délai la publicité
   peut mentionner la date de demande + preuve d'envoi (règle citée par Forest).
