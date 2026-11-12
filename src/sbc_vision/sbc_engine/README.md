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
python -m sbc_vision.sbc_engine import --quality silver --pages 5
python -m sbc_vision.sbc_engine import --quality bronze --pages 5
python -m sbc_vision.sbc_engine club demo
python -m sbc_vision.sbc_engine solve --demo
```

Les démos utilisent des données fictives dans des bases séparées. Les données réelles restent dans `data/processed/futbin_fc27.sqlite3`, ignoré par Git.

## Tester le parcours complet

```bash
python -m sbc_vision.sbc_engine demo
```

La commande dessine une capture fictive, lit les cartes, la formation et les conditions avec Tesseract, confirme les versions prévues dans les fixtures et alimente l'inventaire avant la résolution. Les régions sont annotées et les confirmations sont simulées. La détection de Saber et le contrôleur de Samy restent à raccorder pour le parcours réel.

Les fichiers restent dans `data/processed/pipeline_demo/` : image, annotations, lecture OCR, choix simulés, mesures, base du club et proposition. `--directory` change ce dossier ; `--max-card-value` règle le plafond par carte, fixé à 1 000 dans cette démo. La date des prix fictifs reste celle de la fixture. Une base contenant des données réelles est refusée.

Le résultat attendu est trois exemplaires et une composition à 2 100 crédits, dont 1 300 d'achats. Relancer conserve les identifiants et protections, sans ajouter de copies. Une condition ou une lecture obligatoire incertaine bloque le parcours et retire la proposition d'un précédent essai dans ce dossier de démonstration. Les détails restent dans `reading.json`.

Pour onze joueurs avec davantage de contraintes :

```bash
python -m sbc_vision.sbc_engine demo --complex
```

Ce deuxième scénario fictif combine dix conditions : onze joueurs, qualité or minimum, deux nationalités, au plus deux ligues, trois clubs, au plus quatre joueurs d'un club, au moins six d'un même pays, trois rares minimum, note d'équipe de 83 minimum et collectif de 30 minimum. Un candidat moins cher viole les quotas. La sélection simple se bloque ; CP-SAT trouve 1 100 crédits, dont 200 d'achats et 900 de valeur sacrifiée. Les fichiers sont séparés dans `data/processed/pipeline_complex_demo/`. Les tests ajoutent aussi des contraintes contradictoires pour vérifier le statut impossible. Ce scénario ne prouve pas la validité de nos calculs sur un SBC réel.

## Lire une capture

Installer Tesseract (`brew install tesseract` sur macOS), puis l'option Python `.[ocr]`. `ocr CAPTURE REGIONS_JSON` lit une image locale et écrit `data/processed/ocr.json`. `--lang` choisit une langue installée dans Tesseract, `eng` par défaut. `--min-confidence` règle le seuil (0,75 par défaut).

Le fichier des régions contient `capture_id` et une liste `regions`, avec `element_id`, `field` et `bbox` (`x`, `y`, `width`, `height` en pixels). Le [schéma SBC](../../../contracts/sbc.schema.json) rassemble les formats dans `$defs` : `OcrInput`, `CardReading`, `ClubItem`, `Challenge` et `SolverResult`. Les régions viennent du détecteur de Saber ou d'une annotation de test ; aucun emplacement de carte n'est fixé dans le code.

L'image est agrandie et passée en niveaux de gris. Un premier passage Tesseract lit tous les mots, puis leurs coordonnées les rattachent aux régions. Un champ de carte ou de condition sous 0,75 de confiance est relu isolément, à plus grande échelle : mode ligne pour une carte, mode bloc pour une condition pouvant occuper plusieurs lignes. Le rapport indique `method: global` ou `region`. La confiance n'est pas augmentée artificiellement et les coordonnées reviennent dans la capture originale. Le texte brut et les confiances sont conservés. Les noms et notes incertains restent à relire ; aucune lecture OCR n'ajoute automatiquement un exemplaire au club.

Les petites notes sont relues à six fois leur taille avec une marge de cinq pixels pour les fonds décorés. Une note mal formée est relue même si Tesseract lui donne une forte confiance ; la nouvelle lecture doit toujours respecter le format 1–99 et le seuil choisi. Les coordonnées compensent la marge ajoutée. L'import affiche aussi les versions ambiguës quand plusieurs cartes restent compatibles.

Une région facultative `field: "stats"` peut contenir les six intitulés anglais puis les six nombres de la carte : `PAC SHO PAS DRI DEF PHY`, ou `DIV HAN KIC REF SPD POS` pour un gardien. Ils complètent `CardReading.stats` et filtrent les versions ayant le même nom et la même note. Une statistique absente du catalogue ne prouve pas une correspondance ; un bloc présent mais incertain ou mal formé bloque la confirmation. Aucun emplacement n'est fixé dans le code.

Pour chercher les cartes manquantes directement depuis un rapport OCR :

```bash
python -m sbc_vision.sbc_engine import --reading data/processed/ocr.json
```

La commande réutilise les correspondances locales et interroge le filtre public de nom FUTBIN pour les autres lectures sans alerte. Elle télécharge les versions trouvées, puis recalcule les candidats ; elle n'ajoute aucun exemplaire au club. `--refresh` force la recherche et l'actualisation ; `--pages` limite les pages par nom (deux par défaut). Une absence de résultat ne lance jamais l'import de l'index entier. Les caches des index or/argent/bronze restent séparés de ces recherches. Une base de démonstration est refusée pour éviter le mélange avec les données réelles.

Le rapport local `data/processed/catalogue_matches.json` conserve les textes, les candidats et `catalogue_searches`. `complete: false` indique qu'une recherche dépasse la limite de pages ; même une recherche terminée ne prouve pas l'exhaustivité du catalogue EA. `--output` change ce chemin. Le rapport peut être transmis à `club sync` avec des versions et des identifiants d'exemplaires vérifiés ; aucune sélection n'est confirmée automatiquement. Pour l'API, utiliser `players.import_readings(db, source, report)` après l'OCR.

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

Le rapprochement accepte le nom complet et les noms courts fournis par FUTBIN (`playerName` et `statsCard.cardname`), conservés dans `aliases`. Accents et ponctuation sont harmonisés, mais aucun nom approchant n'est deviné. La note doit correspondre ; le poste et les attributs connus restent des filtres supplémentaires. Toutes les versions compatibles restent proposées à confirmation. Les anciens exports sans `aliases` fonctionnent avec le nom complet. Pour enrichir une carte déjà en cache, utiliser `import --ids IDENTIFIANT --refresh`. Une évolution absente du catalogue reste sans version identifiée.

`element_id` désigne une région dans une capture ; `instance_id` désigne un exemplaire physique entre les captures. Le contrôleur de Samy doit conserver ce suivi, sans inventer un nouvel exemplaire à chaque écran. L'API pourra appeler directement `players.confirm_readings(db, report, choices, confirmed=True)` après validation des choix. La provenance et l'Item Score viennent de la lecture ; les protections et états échangeables existants sont conservés.

### Réunir plusieurs captures

```bash
python -m sbc_vision.sbc_engine club scan --demo
```

Cette démo assemble deux rapports fictifs avec des choix et un suivi simulés : quatre observations donnent trois exemplaires, dont deux copies de la même version. L'exemplaire revu sur les deux écrans ne compte qu'une fois. La base et le bilan sont séparés sous `data/processed/club_scan_demo.*` ; relancer conserve trois exemplaires. La démo ne capture ni ne parcourt la Web App.

Pour les rapports collectés, un fichier de scan contient une liste d'entrées avec `report` (rapport OCR intégré ou chemin relatif au fichier de scan) et `choices` (même format que `club sync`). Exemple de structure avec des identifiants fictifs :

```json
[
  {"report": "page-1.json", "choices": {"card-1": {"instance_id": "copy-1", "card_id": 900001}}},
  {"report": "page-2.json", "choices": {"card-2": {"instance_id": "copy-1", "card_id": 900001}}}
]
```

```bash
python -m sbc_vision.sbc_engine club scan data/processed/scan.json
python -m sbc_vision.sbc_engine club scan data/processed/scan.json --confirm
```

La première commande prépare un bilan sans modifier les exemplaires ; `--confirm` enregistre le lot dans l'inventaire local. Cette confirmation concerne les données du club, jamais une soumission de SBC. Le bilan distingue observations, exemplaires retenus, nouvelles identités, observations répétées, écritures et lectures `pending`. `--output` change son chemin.

Les versions sont revérifiées depuis chaque lecture. Un identifiant répété entre captures fusionne les vues ; deux identifiants distincts conservent deux copies, même avec le même nom et la même version. Une contradiction de version, de score ou d'état échangeable dans le lot bloque toute écriture. Les protections se cumulent ; seule la commande `club protect --remove` peut les retirer. Les cartes absentes d'un lot partiel restent en base.

Samy pourra appeler `players.sync_scan(db, captures, confirmed=False)` pour préparer le bilan puis `confirmed=True` après validation des choix. Le contrôleur doit fournir des identifiants stables et vérifier la fin de navigation ; ce bilan ne prouve pas que tout le club a été parcouru. Les lectures sans choix restent en attente et ne créent aucun exemplaire.

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

Les libellés `Players from the same Countries/Regions`, `Leagues in Squad` et `Silver: Min. 5 Players` sont reconnus. Le dernier exige cinq cartes de qualité argent ; des cartes or ne satisfont pas ce quota. Une condition peut occuper plusieurs lignes dans sa région. L'essai réel à sept conditions produit une proposition locale après ajout des cartes argent et bronze. Le club réel reste à inventorier ; les cartes proposées sont donc considérées comme des achats.

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
- Qualité de chaque carte : minimum, maximum ou exacte, dans l'ordre bronze, argent, or. Ainsi, `Player Quality: Min. Silver` accepte argent et or, et `Max. Silver` accepte bronze et argent. `card_level_op` précise l'opérateur ; le défaut `exact` conserve le comportement des premiers exemples.
- Note d'équipe : correction des notes au-dessus de la moyenne et arrondi, limitée aux formations de onze emplacements. Une autre taille est refusée tant qu'elle n'est pas vérifiée.
- Collectif : seuils standard de club, pays et ligue, plafonnés à trois points par joueur. Les héros, icônes et bonus particuliers ne sont pas modélisés ; leurs profils sont exclus quand un collectif est demandé. Seuls les minima de collectif sont acceptés. Les liens particuliers entre clubs restent à vérifier sur l'interface.
- Item Score : total minimum ou exact, progression acquise, filtre de qualité/note et doublons jusqu'aux quantités disponibles. Un exemplaire possédé vaut toujours une unité ; une offre vaut une unité tant qu'une autre quantité n'a pas été renseignée. Le score vient d'une lecture confirmée ou du catalogue, jamais de la seule note.

Le moteur ne couvre pas tous les libellés et bonus de FC 27. Une règle inconnue est signalée et bloque la proposition. La lecture de l'état final dans la Web App reste nécessaire avant confirmation de soumission. Les identités `base_id` et les métadonnées de rareté du fournisseur doivent aussi être vérifiées sur l'édition ciblée.

Références : [formats SBC de FC 27](https://help.ea.com/en/articles/ea-sports-fc/sbcs/), [Item Score](https://www.ea.com/games/ea-sports-fc/fc-27/news/pitch-notes-fc27-launch-update), [collectif standard](https://www.ea.com/ea-play/news/pitch-notes-fifa-23-fut-chemistry-update) et [combinaisons de notes FUTBIN](https://www.futbin.com/sbc-rating-combinations). Les tests numériques ne remplacent pas une validation sur les captures réelles.

Le coût économique additionne achats et valeur des cartes du club sacrifiées. Les exemplaires protégés et prix inconnus ou anciens sont exclus. Les séries `ps` et `pc` du fournisseur restent distinctes. Les identités de joueurs sont provisoirement groupées selon `base_id` FUTBIN.

`solve --budget 5000` remplace explicitement le budget du rapport lu, sans modifier ce rapport. Le budget et le plafond par carte sont affichés et conservés dans la proposition. Changer le budget ne lance aucun achat.

`solve --max-card-value 1000` exclut toutes les cartes estimées à plus de 1 000 crédits, y compris celles du club. Cette préférence utilisateur est indépendante du budget total d'achat et ne modifie pas les protections enregistrées. Elle peut aussi être définie dans le JSON du défi via `max_card_value` ; l'option de commande prend la priorité. Par défaut, aucun plafond par carte n'est ajouté. La résolution et le vérificateur appliquent tous deux cette limite ; si elle empêche de remplir le SBC sur le pool connu, le moteur le signale sans la relever automatiquement.

```bash
python -m sbc_vision.sbc_engine solve --demo --max-card-value 1000
```

La proposition est écrite dans `data/processed/solution.json`. `optimal` signifie optimal sur le pool et les règles connus ; `infeasible` signifie sans solution sur ce pool ; `unknown` ne permet pas de conclure. Aucun achat ni placement n'est exécuté par ce dossier.

Deux alternatives sont recherchées par défaut en écartant des versions retenues et en recalculant toute la composition. `--alternatives 0` les désactive ; la limite est de trois recalculs, deux secondes chacun. Le JSON conserve leurs plans et les sources/prix des cartes proposées.

Le champ `shopping_list` donne les achats de la composition et de chaque alternative : version exacte, quantité, postes possibles, IDs de pays/ligue/club, qualité, rareté et provenance du prix. Les exemplaires déjà possédés restent dans la composition. Le coût estimé et le budget restant sont indiqués séparément.

Le prix plafond par carte est le prix unitaire utilisé pour le calcul. La marge du budget n'est pas affectée à plusieurs achats en même temps. Une offre plus chère impose un nouveau calcul ; les prix relevés ne garantissent pas une offre disponible. La composition est revérifiée avant de produire cette liste, qui reste une recommandation. Samy pourra appeler `solver.shopping_list(challenge, pool, solution)` ; aucune transaction n'est exécutée.

Le champ `verification` du rapport détaille chaque condition : libellé, opérateur, valeur demandée, valeur obtenue et résultat. Il est aussi présent pour les alternatives. Ces valeurs sont recalculées depuis les cartes retenues en Python, sans lire les variables d'OR-Tools. Le contrôle complet vérifie également postes, exemplaires, protections et budget. Une proposition absente donne `verification: null` ; une composition incorrecte ne reçoit pas un rapport valide.

La commande affiche ces contrôles après les achats. Par exemple : cinq joueurs d'un même pays pour un minimum de cinq, trois d'une ligue pour un maximum de trois et collectif standard de 17 pour un minimum de 16. `valid: true` signifie conforme à nos règles et données connues, sans validation par EA. Pour l'API, `solver.verification(challenge, pool, solution)` fournit le même détail ; le pool doit être rechargé pour prendre en compte prix et protections actuels.

## Accès aux données

Le 6 novembre, un appel FUTBIN local a répondu HTTP 403. Le 12 novembre, l'actualisation d'une version puis de deux pages a fonctionné : 60 versions actualisées, 62 en base locale. Le catalogue complet reste à importer et l'accès peut changer. En cas de refus, l'import s'arrête et garde le cache. `import --file FICHIER --db BASE` lit un export normalisé obtenu par un accès autorisé : une liste `cards` avec les champs du catalogue, ses sources, ses dates et ses prix `ps`/`pc` éventuellement nuls. Les dates ne sont pas rajeunies et les données fictives restent dans des bases séparées.

`--quality` choisit l'index `all`, `gold`, `silver` ou `bronze` à partir des filtres publics FUTBIN. Les pages sont mises en cache par qualité et numéro ; les cartes et les prix restent communs. L'ancien index est conservé dans `all` lors de la migration. Un lot d'une autre qualité que celle demandée est refusé. Le filtre s'applique aux pages, pas à `--ids` ni à `--file`.

L'essai étendu du 12 novembre contient 362 versions : 62 or, 150 argent et 150 bronze. Sur les sept conditions lues, `--budget 5000 --max-card-value 1000 --seconds 30` donne une proposition à 3 900 crédits dans le pool connu, avec cinq argent, six bronze, cinq ligues et un collectif standard calculé de 17. Le plafond retenu est de 550 crédits pour la carte la plus chère. Les prix ne garantissent pas une offre disponible ; la composition n'a été ni placée ni validée dans la Web App.

## Ordre de lecture pour expliquer le code

1. `models.py` vérifie la forme des données.
2. `players.py` sauvegarde les versions et prix, compte les exemplaires et garde les protections.
3. `ocr.py` lit les pixels et traduit les conditions reconnues.
4. `solver.py` crée les variables, impose les contraintes, minimise le coût et vérifie le résultat.
5. `__main__.py` relie les fonctions pour les essais en terminal.
