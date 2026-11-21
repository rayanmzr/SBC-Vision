# Kit de références pour reconstruire la Web App

Ce dossier fournit les écrans rendus de la Web App **EA FC 27**, en anglais, sur
ordinateur. Il permet de travailler sans jeu et sans compte EA. Il contient les
structures HTML, les CSS, les polices, les images, les dessins des cartes issus
des canvas et des descriptions JSON. Les états ont été relevés le 21 novembre 2026.

**Commencer par `index.html`.** L'aperçu relie certains écrans entre eux. Il ne
contient pas le moteur EA : rechercher arbitrairement, filtrer, placer des cartes,
calculer les conditions et soumettre un défi restent à programmer localement.

Pour transmettre le kit, télécharger `simulations.zip` dans ce dossier puis
l'extraire. L'archive contient le dossier autonome `simulations/` et ses ressources ;
elle n'inclut pas sa propre copie.

## Ouvrir l'aperçu

Depuis la racine du dépôt, avec Python 3 et sans installer de dépendance :

```bash
python3 -m http.server 8765 --bind 127.0.0.1 --directory simulations
```

Ouvrir <http://127.0.0.1:8765/>. Le serveur sert uniquement ce dossier. Toutes les
ressources de rendu sont locales ; aucune connexion ni API EA n'est nécessaire.
Le contrôle `?reference=1` sur une page masque le bandeau d'aperçu pour les captures.
La touche de retour du navigateur fonctionne aussi entre les pages.

## Fichiers à utiliser

| Chemin | Utilisation |
| --- | --- |
| `index.html` | Index des états consultables |
| `pages/*.html` | DOM rendu nettoyé, avec les classes et la structure EA |
| `assets/ea.css` | Règles CSS exportées dans l'ordre d'origine |
| `assets/*` | Polices, icônes, fonds, miniatures et canvas sauvegardés en PNG |
| `viewer.js`, `viewer.css` | Petit lecteur local ; ne contient pas les règles SBC |
| `data/<écran>.json` | Titre, viewport, boutons, lignes et emplacements observés |
| `data/club-demo.json` | Scénario fictif à 40 lignes, identifiants locaux, attributs publics |
| `references/*.png` | Rendus locaux vérifiés, données de compte remplacées |
| `manifest.json` | Liste des écrans, provenance des ressources et éventuels téléchargements absents |
| `verify.py` | Contrôle hors ligne des liens, des fichiers et du nettoyage |
| `verification.json` | Résultat du contrôle Chrome : rendu des 16 écrans, navigation et zéro requête externe |

Les chemins d'assets sont hachés pour éviter les collisions. `manifest.json` relie
leurs URL publiques d'origine à leurs fichiers locaux. Ne pas rétablir ces URL dans
le simulateur : les copies locales servent précisément au fonctionnement hors ligne.
Les visuels et marques restent ceux de leurs ayants droit ; ce kit sert de référence
au projet pédagogique de l'équipe.

## Écrans fournis

| État | Contenu et transitions de référence |
| --- | --- |
| `home` | Accueil et navigation latérale |
| `club` | Tuiles du club, notamment Players |
| `club-joueurs` | Première page, 20 lignes, sélection et bouton Next |
| `club-joueurs-page-2` | Deuxième échantillon, Previous et Next |
| `club-filtres` | Recherche du club : qualité, rareté, poste, pays, ligue, club |
| `joueur-fiche` | Player Bio : rareté et détails du joueur |
| `sbc-liste` | Tuiles de défis et catégories |
| `sbc-groupe` | Groupe LALIGA & Liga F, détails et Start Challenge |
| `sbc-score` | Variante de sélection par score, distincte d'une équipe à onze postes |
| `sbc-quotidien` | Daily Login Upgrade : une case ouverte et dix verrouillées |
| `sbc-cinq-joueurs` | 2x 80+ Upgrade : cinq cases ouvertes, qualité minimum or |
| `sbc-onze-joueurs` | 10x 82+ Upgrade : onze cartes, note minimum et TOTW |
| `sbc-case-vide` | Case sélectionnée : Add Player et recherche sur le marché |
| `sbc-recherche` | Filtres du club dans le panneau latéral du SBC |
| `sbc-resultats` | Résultats avec boutons +, recherche limitée au poste sélectionné |
| `sbc-zone-travail` | Work Area, distincte des onze emplacements de l'équipe |

Les liens de l'aperçu montrent ces états précis. Ouvrir une autre case ne régénère
pas un nouveau résultat : les résultats et la fiche sont des exemples figés. Le
défilement des listes est réel, mais seule une pagination à deux pages est fournie
pour le club. Les autres tuiles et onglets n'ont pas tous un état correspondant.
Les compteurs et dates d'expiration sont des références de présentation, pas des
informations actuelles sur le jeu.

## Instructions pour le Codex qui développe le simulateur

Construire un simulateur local dans un dossier distinct, par exemple `simulator/`,
en gardant ce kit comme référence de comparaison. Il doit fonctionner sans identifiant
EA, sans cookie et sans requête vers EA. Réutiliser les assets locaux et les classes
de présentation plutôt que redessiner les cartes de mémoire.

1. Lire ce guide, `manifest.json`, les HTML et les JSON avant de choisir l'architecture.
   Comparer d'abord les captures de `references/` à un navigateur au même viewport.
   `data/<écran>.json` donne le viewport de chaque état ; ne pas déduire des pixels de
   capture une taille CSS sans tenir compte du pixelRatio.
   Les PNG de `references/` ont été rendus à une échelle de 1 : un pixel PNG y correspond
   à un pixel CSS, indépendamment du pixelRatio de 2 du poste de capture d'origine.
2. Reproduire le cadre commun : navigation latérale, barre supérieure, fond, polices,
   liste et panneau droit. Les règles responsive et les pseudo-éléments sont dans
   `assets/ea.css`. Les `<canvas data-sim-canvas>` sont restaurés par `viewer.js` ;
   copier seulement leur HTML sans leur PNG produit des cartes vides.
3. Remplacer la navigation figée par un état explicite : écran, défi, page, filtre,
   joueur sélectionné, case sélectionnée, composition et zone de travail.
   `viewer.js` sert uniquement à consulter les références et peut être remplacé.
4. Créer un club fictif reproductible à partir de `data/club-demo.json`, puis ajouter
   des cartes bronze/argent/or, TOTW, prêt, doublons et joueurs actifs fictifs. Les
   données fournies ne constituent pas un inventaire EA : les identifiants `demo-*`,
   la disponibilité et les états actif/prêt sont des paramètres du scénario.
5. Implémenter les parcours décrits ci-dessous et vérifier les conditions après chaque
   action. Conserver l'HTML visible pour tester l'intégration DOM ; garder aussi un
   parcours testable uniquement par capture, OCR, coordonnées et défilement.
6. Comparer les rendus au même viewport sur les états à une, cinq et onze cases.
   Vérifier aussi les panneaux latéraux, les listes longues, les boutons désactivés
   et l'état sans résultat. Le bon rendu d'une page figée ne valide pas ces transitions.

### Parcours et sélecteurs à conserver

| Fonction | Structure observée et comportement attendu |
| --- | --- |
| Club | `button.ut-tab-bar-item.icon-club` → `.players-tile` → `h1.title` = My Club Players |
| Pagination | `ul.paginated > li.listFUTItem`, `button.pagination.prev` / `.next` ; une page contient aussi des lignes sous la zone visible |
| Joueur | `.entityContainer > .name`, `.playerOverview .rating`, `.position`, six `.player-stats-data-component li` avec `.label` et `.value` |
| Sélection | `.selected` indique la ligne sélectionnée ; ce n'est pas l'appartenance à l'équipe |
| Équipe active | `.is-active` ou `.ut-list-active-tag-view` ; produire ces marqueurs depuis le scénario fictif |
| Prêt | `.player.item.loan` ; exclu des compositions utilisables |
| Fiche | Player Bio → `.ut-player-bio-view` ; ligne `.ut-item-bio-row-view` dont `h1` = Rarity et `h2` porte le type |
| Conditions | `.sbc-requirements-checklist` ; textes courants de chaque défi, pas une règle codée selon son nom |
| Emplacements | `.ut-squad-slot-view[index]`, `.ut-squad-slot-pedestal-view .label` ; indices 0 à 10 pour le terrain |
| Verrouillage | `.locked` interdit l'ajout ; les indices physiques des cases ouvertes doivent rester stables |
| Ajout | Case vide → Add Player → `.ut-club-search-filters-view.sbc` → Search → `.ut-club-search-results-view.sbc` → `button.btnAction.add` |
| Filtre de poste | `.ut-search-filter-control` avec label Position ; l'ouvrir et l'effacer doit être possible |
| Zone de travail | Indices au-delà de 10 ; les cartes qui y sont posées ne sont pas celles soumises au défi |

L'extension actuelle limite volontairement ses actions au domaine EA. Elle refusera
un simulateur sur localhost tant qu'un mode de test explicite n'aura pas été ajouté.
Ne pas détourner le domaine EA ni désactiver globalement ces gardes : prévoir une
configuration de développement locale limitée à l'origine du simulateur.

### Règles métier à simuler

- Sans condition de collectif, accepter les cartes hors poste. Pour « cinq cartes or »
  sans autre condition, un gardien or peut occuper une case d'attaquant.
- Vérifier qualité, nombre de joueurs, rareté, minimum/maximum/exact, note et collectif
  selon le défi courant. Les variantes par score utilisent un autre modèle d'état.
- Ne pas réutiliser deux fois le même exemplaire ; distinguer une version de carte
  de ses éventuels doublons. Prêts et équipe active fictive restent séparés de la sélection.
- Le clic + remplit uniquement la case ouverte sélectionnée. Retirer, vider, changer
  de page et revenir à la recherche doivent mettre l'état à jour.
- Un échange de démonstration peut consommer les exemplaires fictifs et afficher un
  résultat local. Il doit rester entièrement séparé d'un service réel et demander
  une confirmation locale. Aucun script EA original n'est fourni ni nécessaire.

Pour les contrats et contraintes déjà utilisés par le projet, consulter
`../frontend/src/lib/club-scan.ts`, `../frontend/src/lib/sbc-fill.ts`,
`../src/sbc_vision/sbc_engine/models.py` et `../docs/SBC_API.md` dans le dépôt complet.
Ces fichiers aident à reproduire l'intégration ; ils ne sont pas requis pour ouvrir
ce dossier autonome. Une réutilisation des contraintes du solveur est préférable à
un indicateur vert qui ne vérifierait que le nombre de cartes.

## Données et limites de l'export

Le kit contient des états DOM nettoyés et des ressources publiques de présentation.
Le nom du club, les soldes et la date du compte sont remplacés par des exemples ;
les statistiques historiques des fiches sont neutralisées et les marqueurs d'équipe
réels retirés. Seuls deux échantillons de liste sont fournis. Ne pas les interpréter
comme le club complet ni comme une vérité de disponibilité pour le solveur.

Aucun script EA, cookie, token, stockage du navigateur, identifiant d'exemplaire,
base SQLite ou endpoint privé n'est exporté. Le CSP des pages refuse les connexions
réseau et l'envoi de formulaires. Il reste volontairement du contenu public EA
(noms des joueurs, notes, logos, visuels et libellés). Ce n'est pas une anonymisation
des attributs publics des joueurs.

L'export ne contient ni serveur EA, ni gestionnaires d'événements de l'application,
ni état interne JavaScript. Le rendu est une référence fidèle aux états capturés ;
le fonctionnement complet doit être reconstruit. Les événements, erreurs réseau,
transitions et règles non montrés dans ce dossier ne doivent pas être présentés
comme vérifiés sur EA.

## Vérifier le dossier

```bash
python3 simulations/verify.py
```

Le contrôle vérifie les fichiers locaux, les liens et l'absence de dépendance réseau
dans les HTML/CSS. Le manifeste garde les URL publiques de provenance ; elles ne sont
pas des ressources appelées par l'aperçu. Les captures PNG servent de contrôle visuel,
pas de jeu d'évaluation indépendant du modèle.

### Message à donner au Codex

> Lis `simulations/README.md` et `simulations/manifest.json`. Lance l'aperçu local,
> examine les pages et les captures, puis construis dans `simulator/` un simulateur
> de la Web App à partir de ces références. Réutilise les assets locaux et les classes
> HTML pour conserver le rendu. Implémente club paginé, filtres, fiche joueur, sélection
> de SBC, ajout/retrait des cartes et vérification des conditions avec des données
> fictives. Le simulateur doit fonctionner sans compte ni réseau EA. Distingue les
> états capturés des comportements que tu implémentes, et vérifie les parcours à
> une, cinq et onze cases, y compris les cartes hors poste sans collectif.
