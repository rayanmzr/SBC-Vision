# OCR de Rayan : vérification et raccord HTTP (#14)

## Ce qui a été vérifié

Le moteur `sbc_engine/ocr.py` lit les cartes et conditions depuis des régions d'image.

Le lecteur existant conserve textes, mots, boîtes et confiances ; il relit certains petits champs, normalise les cartes, cherche les versions candidates et interprète les conditions. Ses commandes `demo` et `evaluate` sont exécutables sans compte EA. Une lecture ne confirme pas un exemplaire possédé.

La route **`POST /api/v1/ocr/analyze`** appelle les fonctions `analyze` et `challenge_from_ocr` avec des régions fournies. Le mode `detector` de `/api/v1/perception/analyze` produit désormais les régions des cartes puis appelle le même lecteur.

## Frontière avec la détection

La route OCR séparée attend l'image et un `OcrInput` avec les régions. Le pipeline automatique les dérive des cartes détectées avec `card_regions`, selon le profil `card` ou `club-list`. Les régions des conditions et des postes doivent encore être fournies explicitement. Les textes attendus ne sont jamais transmis au lecteur.

La route séparée annonce `region_source: "provided"` et `automatic_detection: false` ; le pipeline détecteur annonce `detected` et `true`. Le bouton d'analyse de l'extension utilise ce dernier quand il est activé. Aucun clic, scan de compte, ajout d'exemplaire ni appel du solveur n'est effectué par l'analyse OCR. L'ajout au club local passe ensuite par une confirmation explicite, décrite dans [SBC_API.md](SBC_API.md).

## Installation et activation

```bash
source .venv/bin/activate
uv pip install --python .venv/bin/python -c requirements.lock -e '.[dev,data,solver,ocr]'
# macOS : brew install tesseract
# Debian/Ubuntu : apt-get install tesseract-ocr
SBC_OCR_MODE=tesseract-regions SBC_OCR_LANG=eng \
  uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8026
```

L'image Docker installe déjà Tesseract et ses données anglaises. Pour d'autres langues, installer leurs données puis configurer par exemple `SBC_OCR_LANG=eng+fra`. Un moteur ou une langue absents provoquent une erreur de démarrage explicite quand ce mode est demandé. Le mode par défaut reste `disabled`.

`/api/v1/capabilities` expose `ocr`, `ocr_mode` et `ocr_regions_required`. En mode détecteur, les régions de cartes sont produites automatiquement et `ocr_regions_required` vaut faux. Activer seulement l'OCR ne charge aucun détecteur.

## Premier essai sans compte

Dans un autre terminal avec le même environnement :

```bash
# Démo existante de Rayan : données, régions et confirmations explicitement fictives.
python -m sbc_vision.sbc_engine demo --directory data/processed/ocr_http_demo

# Relire son image, cette fois à travers l'API.
python scripts/analyze_ocr.py data/processed/ocr_http_demo/ocr_demo.png \
  --regions data/processed/ocr_http_demo/ocr_demo.regions.json \
  --url http://127.0.0.1:8026 --budget 2000 \
  --output data/processed/ocr_http_demo/http-report.json
```

Sans catalogue configuré, l'OCR lit les attributs et les règles indépendantes du catalogue, avec `candidate_ids: []`. La démo utilise des cibles numériques pour ses pays/ligues et peut être interprétée sans rapprochement de noms de catalogue. Si `SBC_ENGINE_MODE` et `SBC_ENGINE_DATABASE` désignent une base existante, la route la consulte **en lecture seule** pour les candidats et les noms de pays/ligues/clubs ; elle n'importe rien depuis FUTBIN et ne modifie ni inventaire ni protections. Les confirmations de la commande `demo` sont une simulation distincte, pas un effet de l'appel HTTP.

Pour une image publique déjà collectée, utiliser le fichier `*.regions.json` créé lors du diagnostic dans `data/processed/ocr_public_2026-11-16/`. Le [manifeste du diagnostic](../data/manifests/ocr-public-probe-2026-11-16.json) contient les coordonnées et les textes de référence séparés de l'entrée OCR. Il ne faut pas réutiliser ces coordonnées sur une autre image.

## Contrat et limites

- Requête multipart : fichier `image` PNG/JPEG et champ `metadata` contenant un `OcrAnalysisRequest` encodé en JSON : dimensions, `specification` au format `OcrInput`, seuil, marché et budget facultatifs.
- Schémas versionnés : `contracts/ocr-request.schema.json`, `contracts/ocr-response.schema.json`. Le schéma d'entrée est aussi accessible à `/api/v1/contracts/ocr-request` et le multipart est documenté dans OpenAPI.
- Limites : corps complet de 5 Mio avec l'enveloppe multipart, métadonnées de 64 Kio, 128 régions, identifiant de 128 caractères, 4 millions de pixels, 4 096 pixels par côté. La limite de pixels tient compte des agrandissements internes du lecteur. Les dimensions déclarées doivent correspondre au fichier, et toutes les régions doivent y tenir.
- Réponse : moteur/version/langue, régions brutes et mots, cartes normalisées ou incertaines, candidats à confirmer, conditions et `challenge_ready`. Ce dernier décrit seulement l'interprétation des conditions, jamais la validité d'une équipe ou la possession de cartes. Une confiance Tesseract n'est pas une probabilité calibrée de lecture correcte.
- `422` : régions invalides ou mauvaise taille déclarée ; `429 ocr_busy` : lecteur occupé ; `502 ocr_failed` : problème du moteur ou du catalogue ; `503 ocr_unavailable` : mode non activé ; `504 ocr_timeout` : délai de 15 secondes dépassé. Les erreurs du décodeur PNG/JPEG restent distinctes. L'authentification et les limites globales du service s'appliquent aussi à cette route.
- Une seule lecture par processus serveur. Un timeout HTTP ne tue pas le thread ni le sous-processus Tesseract en cours ; le verrou reste détenu jusqu'à leur fin. Ne pas multiplier les workers sans mesurer mémoire et latence. Pour un cloud plus exposé, prévoir un worker isolé annulable avant d'augmenter la charge.
- Aucun chemin de fichier du serveur n'est accepté dans la requête. Le parseur multipart et Tesseract peuvent utiliser des fichiers temporaires système ; aucun original ni rapport n'est conservé par la route. Le client n'écrit un rapport que si `--output` est fourni. Les images/lectures ne sont pas journalisées. Le client accepte la clé via `SBC_API_KEY` ou `SBC_API_KEY_FILE`, jamais comme argument de ligne de commande.

## Résultats du 16 novembre 2026

Sur ce Mac, Tesseract était absent ; les anciens tests qui en dépendaient étaient donc ignorés. Installation de Tesseract **5.5.4**, langue `eng`, puis exécution réelle des tests et de la démo. Les versions système de Docker peuvent produire des lectures différentes ; le test du conteneur exécute désormais lui aussi l'OCR par HTTP.

La démo fictive de Rayan lit cinq conditions et trois exemplaires simulés, puis vérifie une proposition à coût économique 2 100, dont 1 300 d'achats et 800 de valeur sacrifiée. Ce sont des valeurs de fixture, pas un résultat sur un compte EA.

Un diagnostic distinct passe par la route HTTP avec **trois images publiques, 14 champs et 65 caractères de référence** : deux vues FC25 d'un même fil EA Forums et une liste des transferts FC27. Les cadrages ont été contrôlés à l'écran et corrigés pendant la préparation. Ce lot est du développement, pas un test indépendant et pas une mesure du détecteur.

| Mesure sur ce petit lot, seuil 0,75 | Résultat |
| --- | --- |
| Champs exacts acceptés | 7 / 14 |
| Erreurs de caractères | 11 / 65, soit CER 16,9 % |
| Champs inconnus selon le seuil | 5 / 14 |
| Appels HTTP locaux | 0,43–0,56 s via TestClient, puis 0,48–0,66 s via TCP sur localhost ; pas une mesure cloud |

Exemples : `Thuram`, `van der Sar`, `Rogers`, `Gabriel Jesus` et deux notes `89` sont correctement lus ; deux petites notes `88` et une note `85` sont vides ; un poste `ST` devient `STZ` malgré une confiance d'environ 0,76 ; l'accent de `García` est perdu. Il reste donc des erreurs au-dessus du seuil. Aucune des cinq cartes explorées ne présente à la fois nom, note et tous ses champs fournis exactement lus et acceptés. Ne pas abaisser le seuil pour transformer cet essai en réussite.

Les images et rapports complets restent locaux et ignorés par Git, dans `data/raw/public_references_2026-11-16/` et `data/processed/ocr_public_2026-11-16/`. Les coordonnées et références textuelles sont versionnées dans le manifeste, avec l'empreinte des images. La [collecte publique](PUBLIC_CAPTURES_AUDIT.md) conserve les URL et crédits. Ces résultats complètent les essais de Rayan ; ils ne les remplacent pas par un score directement comparable, car le corpus diffère.

## Suite du raccordement

La détection des cartes, les profils de régions, l'affichage des lectures et la confirmation locale des exemplaires sont raccordés. Le profil `club-list` a été réglé sur une capture EA privée : trois lectures exploitables, dont une version ambiguë. La ponctuation finale des pictogrammes est retirée du nom normalisé, avec texte brut conservé. Ce résultat de développement ne remplace pas les mesures indépendantes ci-dessus. Il reste à extraire automatiquement toutes les conditions et à fiabiliser les emplacements sur EA, puis à gérer le suivi des copies lors d'un scan réel.
