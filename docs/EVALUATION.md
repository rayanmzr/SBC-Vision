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

`python -m sbc_vision.sbc_engine evaluate --reading RAPPORT --expected ANNOTATIONS` mesure le CER et l'exactitude des textes sur les régions annotées. Le bilan conserve les détails, les scores par champ, les régions absentes et les régions inattendues. Les textes attendus sont annotés manuellement, avec les mêmes identifiants de capture et de région. Le seuil de confiance est fixé sur la validation, sans ajustement sur le test. Le [guide du moteur](../src/sbc_vision/sbc_engine/README.md) précise le format et les conventions.

`evaluate --demo` crée une petite image fictive pour contrôler le calcul. Ses scores ne sont pas des résultats sur EA FC ; les mesures sur le corpus réel restent à effectuer.

## MLflow et résultats

Chaque entraînement enregistre commit Git, version du manifeste, paramètres, seed, métriques, environnement et artefacts utiles. Conserver un exemple réussi et plusieurs cas d'échec commentés. Pour l'explicabilité, comparer des visualisations de régions sensibles et documenter ce qui influence la détection.

Les résultats seront ajoutés après les premières mesures, avec les liens vers les runs correspondants.

Les explorations pourront être regroupées dans `notebooks/` : corpus et splits, baseline, entraînement, évaluation et cas synthétique du solveur. Les fonctions réutilisables restent dans `src/` ; retirer les sorties privées des notebooks avant commit.

## Premier cas de solveur fictif

La démo `python -m sbc_vision.sbc_engine solve --demo` compare les deux méthodes sur trois emplacements et des prix inventés. Elle vérifie un coût économique de 2 600 pour la sélection simple et de 2 100 pour CP-SAT. Une énumération exhaustive du petit pool confirme le résultat dans les tests. Ces valeurs servent à contrôler l'algorithme, pas à annoncer une performance sur les SBC EA FC.

`demo --complex` ajoute onze joueurs et dix conditions combinées, avec un candidat moins cher qui viole les quotas. L'équipe vérifiée coûte 1 100 crédits dans ce jeu fictif. Des variantes rendent les règles incompatibles pour vérifier le refus d'une fausse solution.

## Premier essai OCR réel — 12 novembre

Trois captures et 26 champs annotés manuellement ont servi au diagnostic et aux corrections. Les régions sont fournies, sans évaluer le détecteur : noms, notes, postes, score de carte et conditions. Le seuil de confiance est resté à 0,75.

| Mesure sur ces mêmes 26 champs | Avant correction | Après correction |
| --- | --- | --- |
| Erreurs / caractères attendus | 23 / 162 | 7 / 162 |
| CER | 14,2 % | 4,3 % |
| Champs exacts acceptés | 19 / 26 | 22 / 26 |
| Champs inconnus | 5 / 26 | 2 / 26 |

Ces chiffres décrivent le lot utilisé pour corriger le code, pas un test indépendant ni une performance générale sur EA FC. Des accents/icônes perturbent encore les noms et deux petits champs d'une carte restent incertains. L'écran de SBC est interprété, et le score de la fiche est lu ; l'inventaire complet et les règles réelles de collectif ne sont pas validés. Un lot séparé reste nécessaire avant la soutenance.

Un quatrième écran, un SBC réel à sept conditions, a ensuite été annoté sur 18 régions (sept conditions et onze postes). Avant correction : 1 erreur sur 235 caractères, 17 champs exacts et un champ incertain. Après relecture de ce champ et adaptation des libellés : 0 erreur, 18 champs exacts et aucune lecture inconnue. Ce deuxième lot a lui aussi servi au développement, sans constituer un test indépendant. Le parseur produit les sept conditions ; le moteur les vérifie ensemble sur des joueurs fictifs et refuse les variantes qui violent les quotas. La résolution sur les données réelles échoue sur le pool actuel, qui ne contient aucune carte argent ni aucun exemplaire confirmé du compte.
