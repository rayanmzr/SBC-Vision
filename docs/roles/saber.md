# Saber Kasri - Données et vision

Compte : [saberkasri](https://github.com/saberkasri).

## But

Construire et évaluer la perception des interfaces. La livraison principale est un détecteur capable de localiser les éléments génériques et les régions utiles à EA FC, avec une évaluation sur des sites non vus.

## Responsabilités

- Collecter manuellement de vraies captures du club, des fiches et des SBC, puis préparer des captures web complémentaires.
- Définir les classes et les consignes d'annotation avec Rayan et Samy.
- Versionner les manifestes, définir les splits, éviter les fuites et les quasi-doublons.
- Construire la baseline OpenCV, affiner un détecteur et tracer les runs MLflow.
- Comparer les approches sur les mêmes données ; analyser erreurs, latence et explicabilité.

## Interfaces avec l'équipe

Entrée : captures et annotations. Sortie : régions, classes, scores et métadonnées du modèle. Le modèle fournit le format convenu dans `contracts/`, et Rayan complète la lecture des régions. Samy fournit l'API et le client de capture.

## Livrables attendus

Manifestes et guide d'annotation, notebooks reproductibles, code d'entraînement/inférence, poids accessibles selon leur licence, runs MLflow, tableau d'évaluation et cas d'échec. Les images privées et les poids lourds ne vont pas directement dans Git.

## Premières tâches

Voir les cartes `SBV-003` à `SBV-008` et `SBV-020` dans le backlog. Commencer par les données et le protocole, avant d'optimiser un score sur un split non maîtrisé.
