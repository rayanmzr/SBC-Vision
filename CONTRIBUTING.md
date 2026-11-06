# Contribuer

## Organisation

1. Choisir une issue du Project et confirmer le responsable principal.
2. Déplacer la carte vers `In Progress` et créer une branche courte, par exemple `feat/12-ocr-cartes`.
3. Faire des commits ciblés avec son propre compte Git.
4. Ouvrir une pull request liée à l'issue (`Closes #12` si tous ses critères sont atteints).
5. Demander une revue à un autre membre, attendre la CI puis fusionner.

Éviter les modifications directes de `main` après l'initialisation du dépôt. Ne pas changer les règles de protection ou les droits du dépôt sans accord de l'équipe.

## Conventions

- Documentation et issues en français ; identifiants Python en anglais.
- Python 3.11/3.12, format et lint avec Ruff.
- Les notebooks d'exploration ne remplacent pas le code réutilisable dans `src/`.
- Les règles SBC doivent être documentées et couvertes par des exemples valides et invalides. Une moyenne naïve des notes ne vaut pas implémentation vérifiée de la note d'équipe.
- Les nouvelles dépendances doivent être nécessaires et annoncées dans la PR ; les briques lourdes restent optionnelles.
- Les scores de benchmark doivent indiquer données, split, version du modèle, matériel et latence mesurée.

## Définition de terminé

- Les critères d'acceptation de l'issue sont atteints.
- Le comportement est reproductible et les limites sont documentées.
- Les contrats et la documentation ont été mis à jour si nécessaire.
- Les tests pertinents passent, ainsi que `make check`.
- La PR a une revue et n'inclut aucun secret, capture privée ou artefact lourd.

## Commandes

```bash
python -m pip install -c requirements.lock -e '.[dev,data,solver,ocr]'
make check
```

Pour mettre à jour les schémas après une modification des contrats :

```bash
python scripts/export_contracts.py
```

Les responsabilités se trouvent dans [docs/roles](docs/roles). La licence du code sera décidée avant une réutilisation ou publication sous licence ouverte ; ne pas copier du code tiers sans conserver sa licence et son attribution.
