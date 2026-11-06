# Moteur SBC — partie Rayan

Ce dossier rassemble l'OCR, les données FUTBIN, l'inventaire et le solveur. Les fonctions restent en Python ; Samy pourra les appeler depuis l'API.

| Fichier | Contenu |
| --- | --- |
| `players.py` | Catalogue FUTBIN, prix, cache SQLite et exemplaires du club. |
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

Le fichier des régions contient `capture_id` et une liste `regions`, avec `element_id`, `field` et `bbox` (`x`, `y`, `width`, `height` en pixels). Le [schéma SBC](../../../contracts/sbc.schema.json) rassemble les formats dans `$defs` : `OcrInput`, `CardReading`, `ClubItem`, `Challenge` et `SolverResult`. Les régions viennent du détecteur de Saber ou d'une annotation de test ; aucun emplacement de carte n'est fixé dans le code.

L'image est agrandie et passée en niveaux de gris. Un passage Tesseract lit tous les mots, puis leurs coordonnées les rattachent aux régions. Le texte brut et les confiances sont conservés. Les noms et notes incertains restent à relire ; aucune lecture OCR n'ajoute automatiquement un exemplaire au club.

`club list` affiche le club confirmé. `club protect IDENTIFIANT` protège un exemplaire ; `--remove` retire cette protection. `club add FICHIER --confirm` ajoute un exemplaire après vérification. Une nouvelle observation du même exemplaire ne crée pas de doublon et conserve sa protection.

### Enregistrer un lot de lectures

`club sync` relie un rapport OCR aux versions choisies et aux identifiants stables des exemplaires. Par exemple, pour les identifiants fictifs des tests, `choices.json` peut contenir :

```json
{
  "card-1": {"instance_id": "copy-1", "card_id": 900001, "protected": true},
  "card-2": {"instance_id": "copy-2", "card_id": 900001}
}
```

```bash
python -m sbc_vision.sbc_engine club sync data/processed/ocr.json data/processed/choices.json --confirm
```

Seules les lectures sélectionnées sont enregistrées. Chaque version est rapprochée à nouveau du catalogue ; une lecture incertaine doit être corrigée avant confirmation. Le lot est enregistré ensemble ou annulé entièrement si un exemplaire pose problème. Un rapport incomplet ne supprime aucune carte du club.

`element_id` désigne une région dans une capture ; `instance_id` désigne un exemplaire physique entre les captures. Le contrôleur de Samy doit conserver ce suivi, sans inventer un nouvel exemplaire à chaque écran. L'API pourra appeler directement `players.confirm_readings(db, report, choices, confirmed=True)` après validation des choix. La provenance et l'Item Score viennent de la lecture ; les protections et états échangeables existants sont conservés.

## Conditions dynamiques

Le solveur reçoit les conditions de la capture courante. Aucun nom ou identifiant de SBC n'est présent dans son algorithme. Une formation est une liste de postes ; une condition est un type, un opérateur (`min`, `max`, `exact`) et une valeur. Les exemples sont uniquement des fixtures de test.

```bash
python -m sbc_vision.sbc_engine ocr capture.png regions.json --market pc --budget 2000
python -m sbc_vision.sbc_engine solve --reading data/processed/ocr.json
```

Le fichier des régions peut inclure `positions`, issus du détecteur, et `attributes`, des IDs de pays/ligue/club ou une rareté visuelle par `element_id`. Ces attributs complètent l'OCR. Samy transmettra les captures et régions de Saber à `ocr.analyze`, puis le rapport à `ocr.challenge_from_ocr`.

Pour tester uniquement un texte déjà lu : `conditions FICHIER --positions CAM CM ST --market pc --budget 2000`. Cela écrit `data/processed/conditions.json`, consommable par `solve --reading`. Un JSON structuré peut aussi être donné avec `solve --challenge FICHIER`.

```text
Number of players: 3
Player rating: Min 82
Leagues: Exact 2
```

Passer `Leagues: Exact 2` à `Leagues: Exact 1` change la composition avec le même moteur. Des libellés français courants sont reconnus. Un libellé inconnu, une valeur incertaine ou une cible absente du catalogue donne `ready: false` et bloque la résolution. L'OCR des interfaces réelles devra être évalué sur les captures annotées du groupe.

## Mesurer l'OCR

```bash
python -m sbc_vision.sbc_engine evaluate --demo
```

Cette commande génère une image de six champs fictifs, passe Tesseract et calcule les mesures. L'image, les lectures et les annotations sont conservées sous `data/processed/ocr_demo.*`, avec le bilan dans `ocr_metrics.json`. Ces fichiers locaux sont ignorés par Git. La démo vérifie le calcul ; la qualité sur les interfaces EA doit être mesurée sur le lot annoté du groupe.

Pour un rapport OCR existant :

```bash
python -m sbc_vision.sbc_engine evaluate --reading data/processed/ocr.json --expected data/processed/expected.json
```

Les annotations contiennent les textes attendus avec les mêmes `capture_id`, `element_id` et `field` que les régions évaluées :

```json
{
  "capture_id": "screen-1",
  "regions": [
    {"element_id": "card-1", "field": "name", "text": "Alex Exemple"},
    {"element_id": "card-1", "field": "rating", "text": "83"}
  ]
}
```

Pour plusieurs captures, chaque fichier peut contenir un tableau de ces objets. Les références doivent être complètes pour le lot évalué, avec des textes non vides. `--min-confidence` règle le seuil, à fixer sur la validation avant les mesures de test.

- **CER** : nombre minimal d'insertions, suppressions et substitutions, divisé par le nombre total de caractères attendus. Un résultat plus bas est meilleur ; les insertions peuvent le faire dépasser 100 %.
- **Champs exacts** : texte identique et confiance suffisante, rapportés au total des champs annotés.
- **Champs inconnus** : régions absentes, textes vides ou confiances sous le seuil.

Les espaces et les formes Unicode équivalentes sont harmonisés ; la casse, les accents et la ponctuation restent évalués. Le CER utilise tous les textes bruts, y compris les lectures incertaines. Le bilan détaille chaque champ, regroupe les scores par type et compte les régions manquantes ou inattendues. La détection et la validité métier sont évaluées séparément.

## Règles et profils

- Composition : postes, notes individuelles, qualité, rareté, quotas et nombres distincts ou communs de pays/ligues/clubs.
- Note d'équipe : correction des notes au-dessus de la moyenne et arrondi, limitée aux formations de onze emplacements. Une autre taille est refusée tant qu'elle n'est pas vérifiée.
- Collectif : seuils standard de club, pays et ligue, plafonnés à trois points par joueur. Les héros, icônes et bonus particuliers ne sont pas modélisés ; leurs profils sont exclus quand un collectif est demandé. Seuls les minima de collectif sont acceptés. Les liens particuliers entre clubs restent à vérifier sur l'interface.
- Item Score : total minimum ou exact, progression acquise, filtre de qualité/note et doublons jusqu'aux quantités disponibles. Un exemplaire possédé vaut toujours une unité ; une offre vaut une unité tant qu'une autre quantité n'a pas été renseignée. Le score vient d'une lecture confirmée ou du catalogue, jamais de la seule note.

Le moteur ne couvre pas tous les libellés et bonus de FC 27. Une règle inconnue est signalée et bloque la proposition. La lecture de l'état final dans la Web App reste nécessaire avant confirmation de soumission. Les identités `base_id` et les métadonnées de rareté du fournisseur doivent aussi être vérifiées sur l'édition ciblée.

Références : [formats SBC de FC 27](https://help.ea.com/en/articles/ea-sports-fc/sbcs/), [Item Score](https://www.ea.com/games/ea-sports-fc/fc-27/news/pitch-notes-fc27-launch-update), [collectif standard](https://www.ea.com/ea-play/news/pitch-notes-fifa-23-fut-chemistry-update) et [combinaisons de notes FUTBIN](https://www.futbin.com/sbc-rating-combinations). Les tests numériques ne remplacent pas une validation sur les captures réelles.

Le coût économique additionne achats et valeur des cartes du club sacrifiées. Les exemplaires protégés et prix inconnus ou anciens sont exclus. Les séries `ps` et `pc` du fournisseur restent distinctes. Les identités de joueurs sont provisoirement groupées selon `base_id` FUTBIN.

La proposition est écrite dans `data/processed/solution.json`. `optimal` signifie optimal sur le pool et les règles connus ; `infeasible` signifie sans solution sur ce pool ; `unknown` ne permet pas de conclure. Aucun achat ni placement n'est exécuté par ce dossier.

Deux alternatives sont recherchées par défaut en écartant des versions retenues et en recalculant toute la composition. `--alternatives 0` les désactive ; la limite est de trois recalculs, deux secondes chacun. Le JSON conserve leurs plans et les sources/prix des cartes proposées.

## Accès aux données

Le 6 novembre, un appel FUTBIN local a répondu HTTP 403. L'import s'arrête et garde le cache. `import --file FICHIER --db BASE` lit un export normalisé obtenu par un accès autorisé : une liste `cards` avec les champs du catalogue, ses sources, ses dates et ses prix `ps`/`pc` éventuellement nuls. Les dates ne sont pas rajeunies et les données fictives restent dans des bases séparées.

## Ordre de lecture pour expliquer le code

1. `models.py` vérifie la forme des données.
2. `players.py` sauvegarde les versions et prix, compte les exemplaires et garde les protections.
3. `ocr.py` lit les pixels et traduit les conditions reconnues.
4. `solver.py` crée les variables, impose les contraintes, minimise le coût et vérifie le résultat.
5. `__main__.py` relie les fonctions pour les essais en terminal.
