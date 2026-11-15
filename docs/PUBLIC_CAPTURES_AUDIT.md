# Captures publiques et audit de la consigne — 16 novembre 2026

Préparation du parcours de l'[issue #19](https://github.com/rayanmzr/SBC-Vision/issues/19), à partir de la branche `feat/15-extension-design`, commit `5875798`. Cette collecte complète le travail de données de Saber ; elle ne termine ni la collecte, ni le benchmark, ni l'intégration.

## Résultat de la recherche

14 fichiers téléchargés, décodés et examinés visuellement : **3 candidats FC27 sans ajout tiers repéré, 5 références d'anciennes éditions, 5 références auxiliaires et 1 capture console écartée**. Cela représente environ 3,1 Mo. Aucun fichier n'a été retouché. « Sans ajout repéré » ne garantit pas l'authenticité de la publication ni l'absence d'une modification discrète.

Les images restent dans `data/raw/public_references_2026-11-16/`, ignoré par Git. Le [manifeste](../data/manifests/public-references-2026-11-16.json) versionne URL, auteur/source, format réellement décodé, dimensions, empreinte SHA-256, édition annoncée/observée, regroupement et limites. Le fichier local `index.html` permet de parcourir les images. Les droits de réutilisation et de redistribution ne sont pas établis : cette sélection est un lot de recherche à examiner avant intégration au dataset ou diffusion.

Tous les splits restent **non attribués**, sans annotation et sans score annoncé. Ces images déjà examinées peuvent servir au développement ; ne pas les présenter comme un test final aveugle. Une édition ancienne n'est jamais renommée FC27 dans les métadonnées.

## Images à utiliser en premier

| Référence locale | Ce qui est visible et utile | Limite |
| --- | --- | --- |
| `ea-forum25-club-filters.jpg` | Champs nom/note, interrupteurs, menus qualité/rareté, boutons Search/Reset | FC25 selon le fil ; panneau recadré, pas un écran FC27 |
| `ea-forum25-club-results.jpg` | Liste de joueurs, notes, postes, attributs, menu de carte, pagination | FC25 selon le fil ; joueur partiellement visible, pas d'inventaire exhaustif |
| `ea-forum25-club-league.jpg` | Cartes variées, caractères accentués, précédent/suivant | Même fil que les deux précédentes : à garder dans le même groupe de split |
| `ea-forum24-sbc.png` | Terrain vide, onze emplacements, filtres de recherche et boutons | Logo FC24 visible ; barre navigateur incluse ; les conditions du défi ne sont pas dépliées |
| `pcgames27-transfer-list.jpg` | Carte, note, poste, prix, lien de biographie et navigation | FC27 visible ; liste des transferts, pas liste du club ; image compressée |
| `pcgames27-reward-modal.jpg` | Fenêtre modale, fermeture, bouton actif et fond assombri | Utile pour distinguer un élément visible d'un élément réellement actionnable |
| `pcgames27-welcome.jpg` | Texte dense et bouton de progression d'une autre modale | Même publication/club que les deux précédentes ; ordre chronologique non établi |
| `millenium26-home.png` | Accueil français et tuiles DCE/évolutions | FC26 selon la source ; image recadrée, navigation latérale absente |

Sources : [captures du club publiées par UnsafestPlacebo sur EA Forums](https://forums.ea.com/idea/fc-25-bug-reports-en/club-search-in-web-app-doesnt-show-all-players/12223980), [SBC FC24 publié sur EA Forums](https://forums.ea.com/discussions/fc-24-technical-issues-en/search-on-transfer-market-does-not-work-for-sbcs-on-web-app-and-companion-app/7987686), [galerie PC Games FC27](https://www.pcgames.de/EA-Sports-FC-27-Spiel-78781/News/Web-App-Companion-Start-Ulimate-Team-Vorbereitung-1554117/), [accueil FC26, Millenium](https://www.millenium.org/guide/427194.html). Les pages PC Games et du fil FC24 ont refusé leur lecture automatisée pendant cette recherche ; les fichiers image publics ont été accessibles et inspectés. Ne pas en déduire une vérification complète des articles.

## Références à traiter séparément

- `alloparadise27-starter.webp` et `alloparadise27-objectives.webp` : écrans FC27 avec webcam et habillage d'Abuelonchos recouvrant le coin supérieur droit. Navigation, texte et boutons exploitables pour des essais de robustesse ; aucune annotation de ce qui est masqué. [Article et crédits des captures](https://blog.alloparadise.fr/guides/web-app-companion-fc-27/).
- `futgenie27-sbc-set.png` et `futgenie27-preview.png` : conditions de SBC et cartes visibles, mais boutons, prix et options ajoutés par FUTGenie. Édition non confirmée par l'image. Références d'interface modifiée, exclues du lot principal EA ; ne pas apprendre qu'« Auto Complete set » est un bouton natif EA. [Source de l'auteur](https://www.futgenie.gg/posts/auto-complete-set).
- `ea27-access-comparison.jpg` : montage officiel réunissant accueil et absence de club. Référence d'état d'erreur, pas capture unique d'un navigateur. [Source EA](https://help.ea.com/en/articles/ea-sports-fc/early-web-and-companion-app-start/).
- `futbin26-player-bio.jpg` : **écarté de la cible web** après inspection. Les commandes L1/R1 et les indications de manette montrent une fiche dans le jeu. [Source FUTBIN](https://www.futbin.com/news/articles/1609/fc-26-84-omar-marmoush-player-review).

Deux vidéos originales sont référencées par l'article Alloparadise : [Abuelonchos](https://www.youtube.com/watch?v=DxaUiE3fWq4) et [SwepixTV](https://www.youtube.com/watch?v=WkBuan5xNx4). Elles restent des **pistes non visionnées**, sans extraction ni timestamp validé. Une session filmée pourrait apporter plusieurs états d'un même club ; il faudra vérifier la résolution, les écrans couverts et les superpositions avant de la retenir.

## Couverture encore insuffisante

| Besoin du parcours | Couverture actuelle | À obtenir |
| --- | --- | --- |
| Recherche et liste du club | Références FC25 d'un même fil | Session FC27 propre avec filtres et plusieurs pages |
| Fiche détaillée d'un joueur web | Carte résumée et menu, pas fiche complète | Identité, version, postes, statut de l'exemplaire ; champs réellement visibles |
| Conditions d'un SBC | Visibles sur une interface modifiée | Écran natif avec toutes les conditions, sans extension tierce |
| Terrain vide / rempli | Vide en FC24 ; aucun rempli natif retenu | Deux états FC27 du même défi et contrôle des emplacements |
| Erreur / modale | Deux modales FC27 et montage d'accès | Échec de lecture, recherche vide et divergence après action |
| Autres sites | Source de corpus identifiée, aucun exemple téléchargé ici | Corpus générique et domaines réservés à l'évaluation |

Pour le corpus générique, [WebUI et ses scripts officiels](https://github.com/js0nwu/webui) correspondent à la note de cadrage : captures et métadonnées, avec splits regroupés par domaine. Harmoniser ses classes avec les nôtres et lire `COPYRIGHT.txt`. Ne pas utiliser les métadonnées DOM comme entrée à l'inférence : l'entrée du système évalué reste l'image.

Une carte visible ne prouve ni sa possession actuelle, ni son caractère utilisable, ni sa quantité. Par exemple, un petit compteur de prêt ne doit pas devenir un nombre d'exemplaires. Des captures de comptes différents ne forment pas un club réel cohérent. Un inventaire assemblé pour la démonstration doit être explicitement fictif.

## Audit : ce que demande le cours et ce que nous avons choisi

Source relue : **Consigne – Projet Computer Vision · Epitech 2026-2027**, quatre pages, notamment les pages 1 à 3. Le PDF de cours n'est pas republié dans le dépôt.

| Origine | Attendu |
| --- | --- |
| Consigne, p. 1 | Python pour préparation/entraînement/évaluation/inférence ; API Flask/FastAPI ; Docker et cloud ; application consommatrice de l'API, sans modèle embarqué |
| Consigne, p. 2 | Travail CV significatif ; plusieurs approches essayées et comparées objectivement ; MLflow ; explicabilité Deep-SHAP ou équivalent ; séparation train/val/test, matrice de confusion et analyse des erreurs |
| Sujet 2, p. 3 | Actions possibles d'une interface web/mobile en JSON, y compris sur des sites jamais vus ; construction/annotation du dataset et évaluation de la sortie structurée |
| Livrables, p. 3 | README reproductible, notebooks d'exploration/entraînement/évaluation, modèles entraînés accessibles, backend/frontend et slides PDF |
| Consigne, p. 2 | Uniquement le dépôt généré par Epitech, avec historique des contributions |
| Choix du groupe | Application SBC, EA FC27, vraie Web App comme cible, secours local à faire valider |
| Objectifs du groupe | 300–500 captures ; test d'au moins 50 captures de 5 domaines ; OpenCV + OCR face à un détecteur affiné + OCR ; OmniParser optionnel |

Les nombres de captures et de domaines viennent du cadrage du groupe, pas d'un seuil imposé dans le PDF du cours. Acheter FC27 ou soumettre un vrai SBC EA n'est pas une obligation énoncée par ce PDF. Abandonner la cible réelle du cadrage ou modifier son protocole demanderait toutefois un arbitrage du groupe et du superviseur.

## État vérifiable sur la branche examinée

**Base solide :** extension de capture/inspection, API Python, contrats JSON séparant perception et solveur, moteur SBC, tests et préparation Docker. Le solveur n'a pas besoin de recevoir les images. Voir [architecture](ARCHITECTURE.md), [données](DATA.md) et [évaluation](EVALUATION.md).

**Risque principal :** l'avance sur le visuel et l'infrastructure ne démontre pas encore la vision demandée. `src/sbc_vision/api/main.py` ne sélectionne que `disabled` ou `lab-colors`, et annonce `model_loaded: false`. Le paquet `perception/` contient le contrat de pipeline et le détecteur de couleurs du laboratoire. Le contrôleur reconnaît la séquence `lab-select` → `lab-place` → `lab-done`. Ce n'est pas une preuve de détection de cartes ni de placement sur EA.

Les résultats OCR du 12 novembre documentés dans `EVALUATION.md` concernent des régions fournies et des lots ayant servi aux corrections : ils ne mesurent pas le détecteur et ne constituent pas un test indépendant. Les dossiers locaux `data/raw/ea_2026-11-12/` et `data/processed/ea_2026-11-12/` sont absents des deux worktrees locaux examinés ; récupérer ces originaux et annotations auprès de leur détenteur, s'ils sont encore disponibles, sera plus utile que les recréer à partir d'images Internet moins fidèles.

Aucun notebook ni raccordement à des poids entraînés n'est présent dans l'arbre examiné. Des fichiers ignorés ou travaux sur une autre machine peuvent exister : cet audit ne conclut pas à l'absence de travail de Saber ou Rayan. Il manque ici les preuves reproductibles d'une comparaison CV, les runs MLflow, l'explicabilité et la mesure hors domaine.

Un seul remote est configuré, `https://github.com/rayanmzr/SBC-Vision.git`. **Vérifier qu'il s'agit bien du dépôt généré par Epitech** ; son nom seul ne permet pas de trancher. Ne pas changer le remote ni perdre l'historique sans accord de l'équipe. La capacité du cloud gratuit à exécuter notre modèle et ses dépendances reste à vérifier avec le modèle réel.

## Suite recommandée

1. **Samy + Saber, #14 :** récupérer le premier détecteur/baseline disponible, figer les classes et brancher sa sortie dans `PerceptionPipeline`. Montrer une vraie capture → éléments détectés → JSON, avec superposition des boîtes et refus des lectures incertaines. Éviter de nouvelles retouches visuelles avant cette preuve.
2. **Saber + Rayan, #3–#9 :** sélectionner et annoter un petit lot pilote couvrant cartes, boutons, champs, menus et erreurs. Garder les sources corrélées ensemble, puis réserver de nouvelles sessions/domaines avant les ajustements. Faire passer les mêmes images dans OpenCV + OCR et le détecteur + OCR, sans changer les données entre approches.
3. **Samy + Rayan, #14/#19 :** transformer les lectures fiables en candidats d'inventaire et règles normalisées, puis appeler le solveur avec du JSON. Distinguer identité de version et exemplaire possédé ; laisser les informations non observables à `null`/à confirmer.
4. **Samy, #16/#17/#19 :** terminer un parcours interactif local limité, piloté par observation, avec nouvelle capture après chaque action. Tester réussite, aucune solution, prix inconnu et mauvaise lecture. Un défilement manuel d'images ne valide pas l'exécution de clics sur EA.
5. **Groupe :** obtenir une baseline montrable pour le **21 novembre**, puis consolider comparaison, confusion, erreurs, MLflow, explicabilité, notebooks et modèles. Déployer l'API cloud avec le vrai pipeline et mesurer la latence ; finaliser les slides pour décembre. Confirmer au superviseur extension, secours et protocole hors domaine.

Les captures publiques permettent d'avancer sans acheter le jeu, mais ce lot ne couvre pas encore toutes les étapes ni la validation du service réel. La meilleure priorité actuelle est de démontrer et mesurer la chaîne visuelle avant d'étendre le produit.
