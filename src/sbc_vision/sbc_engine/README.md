# Moteur SBC — partie Rayan

Ce dossier rassemble l'OCR, les données FUTBIN, l'inventaire et le solveur. Les fonctions restent en Python ; Samy pourra les appeler depuis l'API.

| Fichier | Contenu |
| --- | --- |
| `catalogue.py` | FUTBIN, SQLite et cache. |
| `inventory.py` | Exemplaires, protections et rapprochement avec les versions. |
| `ocr.py` | Lecture locale des régions d'une capture avec Tesseract. |
| `models.py` | Formats des données et des contraintes. |
| `solver.py` | Optimisation OR-Tools, comparaison simple et vérificateur. |
| `__main__.py` | Une commande commune pour essayer les fonctions. |

Depuis la racine du dépôt :

```bash
source .venv/bin/activate
python -m sbc_vision.sbc_engine import --pages 2
python -m sbc_vision.sbc_engine club demo
python -m sbc_vision.sbc_engine solve --demo
```

Les démos utilisent des données fictives dans des bases séparées. Les données réelles restent dans `data/processed/futbin_fc27.sqlite3`, ignoré par Git.

## Lire une capture

Installer Tesseract (`brew install tesseract` sur macOS), puis l'option Python `.[ocr]`. `ocr CAPTURE REGIONS_JSON` lit une image locale et écrit `data/processed/ocr.json`. `--lang` choisit une langue installée dans Tesseract, `eng` par défaut. `--min-confidence` règle le seuil (0,75 par défaut).

Le fichier des régions contient `capture_id` et une liste `regions`, avec `element_id`, `field` et `bbox` (`x`, `y`, `width`, `height` en pixels). Le [schéma](../../../contracts/ocr-input.schema.json) définit les champs possibles. Les régions viennent du détecteur de Saber ou d'une annotation de test ; aucun emplacement de carte n'est fixé dans le code.

L'image est agrandie et passée en niveaux de gris. Un passage Tesseract lit tous les mots, puis leurs coordonnées les rattachent aux régions. Le texte brut et les confiances sont conservés. Les noms et notes incertains restent à relire ; aucune lecture OCR n'ajoute automatiquement un exemplaire au club.

`club list` affiche le club confirmé. `club protect IDENTIFIANT` protège un exemplaire ; `--remove` retire cette protection. `club add FICHIER --confirm` ajoute un exemplaire après vérification. Une nouvelle observation du même exemplaire ne crée pas de doublon et conserve sa protection.

Le solveur reçoit les conditions de chaque défi au format JSON, avec `solve --challenge FICHIER`. Il ne connaît aucun SBC par son nom. Pour l'instant le contrat `prototype-v1` couvre les postes, le budget, les notes individuelles, la rareté et des quotas de pays/ligue. Les autres conditions sont rejetées jusqu'à leur implémentation.

Le coût économique additionne achats et valeur des cartes du club sacrifiées. Les exemplaires protégés et prix inconnus ou anciens sont exclus. Les séries `ps` et `pc` du fournisseur restent distinctes. Les identités de joueurs sont provisoirement groupées selon `base_id` FUTBIN.

La proposition est écrite dans `data/processed/solution.json`. `optimal` signifie optimal sur le pool et les règles connus ; `infeasible` signifie sans solution sur ce pool ; `unknown` ne permet pas de conclure. Aucun achat ni placement n'est exécuté par ce dossier.
