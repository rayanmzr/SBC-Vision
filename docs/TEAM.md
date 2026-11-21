# Répartition du projet

Les tâches et leurs critères sont suivis dans le [GitHub Project](https://github.com/users/rayanmzr/projects/5). Les trois membres participent aux revues et à la restitution.

## Saber — données et vision

Compte : [saberkasri](https://github.com/saberkasri). Cartes : SBV-003 à SBV-008 et SBV-020.

- Collecter les captures réelles et web, retirer les informations personnelles et annoter les éléments.
- Figer les manifestes et les splits par domaine/session, sans quasi-doublons entre les jeux.
- Comparer OpenCV et le détecteur affiné, tracer les runs MLflow et analyser erreurs et latence. OmniParser reste optionnel.
- Fournir les régions, classes, confiances et métadonnées du modèle selon le contrat de perception.

Le code de détection ira dans `src/sbc_vision/perception/`. Les coordonnées restent celles de la capture d'origine après les recadrages et redimensionnements. Rayan complète la lecture des régions ; Samy expose l'inférence dans l'API.

Livrables : manifeste, guide d'annotation, entraînement/inférence, poids accessibles selon leur licence, mesures et cas d'échec. Voir [le protocole](EVALUATION.md).

## Rayan — OCR, cartes et résolution

Compte : [rayanmzr](https://github.com/rayanmzr). Cartes : SBV-001, SBV-002, SBV-009 à SBV-013 et SBV-021.

- Extraire les noms, notes et conditions en conservant le texte brut, la confiance et la provenance.
- Rapprocher les lectures des versions du catalogue ; conserver exemplaires, quantités, protections et ambiguïtés.
- Importer les données FUTBIN et les prix datés, avec cache et gestion des prix inconnus.
- Résoudre les conditions du SBC courant avec OR-Tools, vérifier séparément la composition et proposer des alternatives.

Le code est regroupé dans [sbc_engine](../src/sbc_vision/sbc_engine/README.md), sur `feat/rayan-sbc-engine`. Saber fournit les régions ; le moteur renvoie à Samy les lectures, la composition, les coûts et le statut. Aucun défi précis n'est codé dans l'algorithme.

Livrables : OCR, inventaire, importeur, formats des données, règles documentées, solveur et tests synthétiques. La qualité sur les interfaces réelles reste à mesurer.

## Samy — extension, API et intégration

Compte : [SamyALlali](https://github.com/SamyALlali). Cartes : SBV-014 à SBV-019.

- Construire l'extension Chrome Manifest V3 et son interface React dans `frontend/`, avec URL d'API configurable et permissions documentées.
- Relier les images aux fonctions Python de Saber et Rayan, avec contrôles de taille, délais et erreurs.
- Capturer l'écran, choisir une action à partir du JSON puis vérifier une nouvelle capture ; prévoir observation, simulation, limite d'étapes et interruption.
- Afficher inventaire, protections, conditions, achats et coût, avec les états chargement, lecture incertaine, règle inconnue, absence de solution et confirmation en attente.
- Préparer Docker, CI et cloud ; construire un secours local minimal uniquement si le repli est validé et nécessaire.

Le prototype du contrôleur tourne dans l'extension, dans `frontend/src/lib/controller.ts`,
avec ses adaptateurs de navigateur. Cette localisation réutilise les permissions Chrome
et le repère de capture ; le répertoire Python initialement prévu n'est pas créé pour
dupliquer ce code. Le [laboratoire local](LOCAL_CONTROLLER.md) teste la boucle avant le
raccordement à l'API. Le contrôleur signale une divergence sans inventer de coordonnées
ni afficher une réussite après une erreur réseau. Les modèles réels et le solveur restent
côté Python. Pour les essais sur le compte de Rayan, la soumission d'un SBC reste exclusivement
à Rayan : aucun clic automatisé de confirmation ou d'échange.

Livrables : client, API documentée, parcours reproductible, tests d'intégration, conteneur et guide de lancement. Distinguer la vraie Web App du démonstrateur local.
