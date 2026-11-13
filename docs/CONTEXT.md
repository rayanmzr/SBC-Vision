# Contexte et décisions confirmées

## Objectif pédagogique

Projet Computer Vision Epitech 2026-2027 en groupe de trois. Le sujet 2 attend un système capable de donner à un agent la liste des actions possibles sur une interface web/mobile, en JSON, y compris sur des sites absents de l'entraînement.

L'application métier choisie est la préparation économique des SBC sur la **Web App EA FC 27**. Le jeu PC/console et l'application mobile Companion sont hors du périmètre de pilotage.

Le 30 octobre, le superviseur a donné son accord pour commencer et demandé de préciser le format du client. Le groupe retient une **extension Chrome avec interface React**, reliée à l'API Python ; ce choix doit encore lui être confirmé.

## Produit visé

- Inventorier automatiquement le club par captures, détection et OCR.
- Lire les conditions et les emplacements du SBC.
- Protéger les cartes importantes ; comparer valeur sacrifiée et achats nécessaires.
- Suggérer directement des cartes exactes, avec leur version, prix, plafond d'achat et alternatives.
- Rechercher et placer les cartes via les éléments visuellement détectés.
- Vérifier le résultat et présenter un récapitulatif avant confirmation finale.

Le solveur optimise la composition entière, pas chaque poste indépendamment. Une carte déjà au club n'est pas forcément sans coût d'opportunité.

## Frontière entre les briques

La vision repère les éléments. L'OCR lit les textes. Le contrôleur scripté consomme le JSON et choisit les interactions. OR-Tools recherche une composition respectant les règles que nous programmons explicitement ; il ne connaît pas EA FC à l'origine.

Les données de marché sont un complément du solveur, pas une substitution au travail de vision. L'évaluation hors domaine porte sur le parseur d'interface générique ; la logique SBC reste propre à EA FC.

## Périmètre et arbitrages

- Cible principale : la vraie Web App.
- Les captures d'entraînement incluent de vraies captures collectées lors de navigations manuelles.
- L'exécution automatisée sur le service réel dépend des autorisations d'EA. Le superviseur valide le périmètre pédagogique, pas les droits d'utilisation du service.
- À défaut, un démonstrateur local minimal reproduit uniquement les écrans nécessaires ; Samy en est responsable. Il ne constitue pas une reproduction complète du produit EA.
- Premier parcours : un SBC à composition d'équipe, un club limité et un sous-ensemble de règles documenté.
- Troisième référence OmniParser optionnelle selon les ressources ; aucune API LLM payante n'est imposée.

## Points encore ouverts

- Confirmation du format extension auprès du superviseur et des modalités du test hors domaine et du secours local.
- Règles et formats de SBC réellement pris en charge dans l'édition 27.
- Licence du code, compatibilité des modèles et droits de diffusion des données.
- Fournisseur cloud, capacité de calcul, budget et limites de service.

## Calendrier de référence

| Date | Attendu |
| --- | --- |
| 30 octobre 2026, soir | Note de cadrage d'une page |
| 13 novembre | Pitch de deux minutes |
| 21 novembre | Soutenance intermédiaire, baseline fonctionnelle |
| 27 novembre | Séance déploiement, explicabilité, drift, optimisation |
| 12 / 19 décembre | Soutenance finale ; créneau du groupe à confirmer |

Les dates proviennent de la consigne fournie au groupe. Ne pas publier le PDF de cours sans autorisation. Notre note est disponible dans [cadrage](cadrage/).
