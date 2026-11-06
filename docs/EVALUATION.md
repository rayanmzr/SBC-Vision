# Protocole d'évaluation

## Question principale

Le modèle retrouve-t-il les éléments interactifs et produit-il une sortie exploitable sur des domaines absents de l'entraînement ? La réussite d'un seul SBC ne suffit pas à répondre à cette question.

## Splits

- Conserver un manifeste figé avec les IDs, domaines, sessions et empreintes des images.
- Grouper toutes les pages d'un même domaine dans un seul split du corpus web.
- Réserver au moins 5 domaines et 50 captures pour le test hors domaine, sans ajustement d'hyperparamètres sur ce test.
- Séparer les sessions EA FC et éliminer les quasi-doublons entre splits.
- Documenter l'origine des pré-entraînements. Pour une référence tierce, ne pas garantir l'absence de contamination inconnue.

## Approches comparées

| Approche | Objectif |
| --- | --- |
| OpenCV + OCR | Baseline classique explicable |
| Détecteur affiné + OCR | Méthode adaptée aux annotations du groupe |
| OmniParser sans adaptation | Référence optionnelle selon matériel et temps |

Même jeu de test, même ontologie harmonisée, même protocole et matériel indiqué. Les cartes et emplacements propres à EA FC peuvent être évalués séparément des classes génériques communes aux sites.

## Métriques

| Niveau | Mesure |
| --- | --- |
| Détection | mAP@0,5 globale, par classe et par domaine ; précision/rappel |
| OCR | CER, exactitude des champs métier et taux de champs inconnus |
| JSON | Validité du schéma et F1 des éléments appariés par type, action et IoU ≥ 0,5 |
| Latence | Capture, réseau, inférence, OCR et total mesurés séparément ; p50/p95 |
| Solveur | Taux de compositions valides, coût, durée, statut faisable/optimal/inconnu |
| Parcours | Taux de placement correct et détection des divergences après action |

La validité syntaxique du JSON ne mesure pas sa justesse. La preuve d'optimalité du solveur ne vaut que pour les candidats et les prix connus.

## MLflow et résultats

Chaque entraînement enregistre commit Git, version du manifeste, paramètres, seed, métriques, environnement et artefacts utiles. Conserver un exemple réussi et plusieurs cas d'échec commentés. Pour l'explicabilité, comparer des visualisations de régions sensibles et documenter ce qui influence la détection.

Les résultats seront ajoutés après les premières mesures, avec les liens vers les runs correspondants.

Les explorations pourront être regroupées dans `notebooks/` : corpus et splits, baseline, entraînement, évaluation et cas synthétique du solveur. Les fonctions réutilisables restent dans `src/` ; retirer les sorties privées des notebooks avant commit.

## Premier cas de solveur fictif

La démo `python -m sbc_vision.sbc_engine solve --demo` compare les deux méthodes sur trois emplacements et des prix inventés. Elle vérifie un coût économique de 2 600 pour la sélection simple et de 2 100 pour CP-SAT. Une énumération exhaustive du petit pool confirme le résultat dans les tests. Ces valeurs servent à contrôler l'algorithme, pas à annoncer une performance sur les SBC EA FC.
