# Rayan Mazri - OCR, inventaire et solveur

Compte : [rayanmzr](https://github.com/rayanmzr).

Code regroupé dans [src/sbc_vision/sbc_engine](../../src/sbc_vision/sbc_engine/README.md), sur la branche `feat/rayan-sbc-engine`. Les étapes vérifiées sont poussées sur cette branche.

## But

Transformer les lectures visuelles en un inventaire fiable et en une composition qui respecte le SBC, tout en limitant les dépenses et la valeur sacrifiée.

## Responsabilités

- Extraire et normaliser les textes des cartes et des conditions avec provenance et confiance.
- Identifier les versions, quantités et cartes protégées ; gérer les ambiguïtés.
- Développer l'import FUTBIN reproductible, le cache SQLite et la gestion des prix inconnus.
- Documenter les règles exactes de l'édition 27 : note, collectif, éligibilité, postes et restrictions prises en charge.
- Comparer une sélection simple à un solveur OR-Tools, avec vérificateur indépendant des contraintes.
- Proposer directement des cartes exactes et des alternatives ; recalculer la composition entière après un remplacement.

## Interfaces avec l'équipe

Saber fournit les régions et scores ; Rayan produit des attributs normalisés. Le solveur reçoit club, protections, règles et candidats datés ; il retourne solution, coût, achats et statut. Samy affiche ces résultats et exécute les actions visuelles prévues.

## Livrables attendus

Schémas d'inventaire et de défi, pipeline OCR, importeur et provenance des données, règles documentées, solveur, cas valides/invalides et comparaison de coût. Un échec de lecture ou une règle non prise en charge reste explicite.

## Premières tâches

Voir `SBV-002`, `SBV-009` à `SBV-013` et les tâches communes de restitution. La première résolution peut utiliser un petit club synthétique dont les résultats sont vérifiables à la main.
