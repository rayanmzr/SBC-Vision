# Première étape de SBV-014 : transporter une capture

Les routes d'inventaire, protections et résolution sont décrites dans [SBC_API.md](SBC_API.md).
Elles utilisent le moteur de Rayan et ne modifient pas le raccordement encore attendu
du détecteur à cette route d'analyse d'image.

Cette branche prépare l'API de perception. Le détecteur de Saber et l'OCR de Rayan ne sont
pas encore raccordés. **Une installation normale renvoie donc HTTP 503 à une analyse valide.**
Les tests utilisent un pipeline fictif clairement nommé ; ils ne mesurent aucune performance
de vision. L'issue #14 reste ouverte jusqu'au raccordement et à son évaluation.

## Comprendre le trajet de l'image

1. Le contrôleur capture le viewport du navigateur, c'est-à-dire la zone visible.
2. Il envoie les octets PNG ou JPEG à `POST /api/v1/perception/analyze`.
3. L'API vérifie le format annoncé, la taille reçue, puis ouvre réellement l'image pour
   contrôler son intégrité et ses dimensions. Changer seulement l'extension ne suffit pas.
4. Le pipeline reçoit une image RGB et son identifiant. L'API ne la redimensionne pas et
   ne change pas son orientation : les coordonnées concernent les pixels du fichier reçu.
5. Le pipeline devra enchaîner détection, OCR et normalisation vers `PerceptionResponse`.
6. L'API revalide le JSON : identifiants uniques, coordonnées dans l'image, même taille
   et même identifiant de capture que la demande. Un résultat incohérent est refusé.
7. Le contrôleur reçoit le JSON. L'inventaire et les règles structurées alimenteront le
   solveur ; cette route ne lui transmet aucune capture et ne réalise aucun clic.

La validation du JSON vérifie la cohérence des données, pas leur vérité visuelle. Une
mauvaise lecture peut respecter le schéma ; les annotations servent à mesurer ce problème.
Le lien entre pixels de capture et coordonnées de clic reste à traiter dans #16.

## Requête et réponse

Le corps est le **fichier binaire brut**, sans enveloppe JSON, base64 ou multipart.
`Content-Type` vaut `image/png` ou `image/jpeg`. Le paramètre de requête `capture_id`
est facultatif, non vide et limité à 128 caractères ; sinon l'API génère un UUID.
Utiliser un identifiant technique sans information personnelle.

```bash
source .venv/bin/activate
uvicorn sbc_vision.api.main:app --reload
```

Dans un autre terminal, depuis la même racine et avec le même environnement :

```bash
python scripts/analyze_image.py data/fixtures/perception.synthetic.png \
  --url http://127.0.0.1:8000 --capture-id synthetic-screen-001
```

Équivalent sans le client Python :

```bash
curl --fail-with-body -X POST \
  'http://127.0.0.1:8000/api/v1/perception/analyze?capture_id=synthetic-screen-001' \
  -H 'Content-Type: image/png' \
  --data-binary @data/fixtures/perception.synthetic.png
```

La réponse attendue **avant raccordement** est une erreur `503` avec
`detail.code = "perception_unavailable"`, jamais le contenu de la fixture JSON.
La documentation interactive `/docs` et le fichier `/openapi.json` décrivent la route.

Après raccordement, la réponse `200` suit le contrat déjà versionné dans
`contracts/perception.schema.json` : `capture_id`, taille de l'image, nom du modèle et
éléments avec boîtes `{x, y, width, height}`, texte, confiance et actions possibles.
Une liste `elements: []` signifie que l'analyse a réussi sans élément détecté ; elle ne
remplace jamais une erreur technique.

## Limites et erreurs

Valeurs du socle dans `AnalysisLimits` : 5 Mio reçus, 8 192 pixels au maximum par côté,
20 millions de pixels au total, 10 secondes pour recevoir le corps et 15 secondes pour
l'inférence. Aucun fichier image n'est écrit sur disque et aucun octet d'image n'est journalisé
par cette route. Pillow est ajouté aux dépendances du service pour décoder les captures.

| Statut | Signification |
| --- | --- |
| 400 | Fichier vide, invalide ou tronqué |
| 408 | Délai de réception dépassé |
| 413 | Trop d'octets ou trop de pixels |
| 415 | Format non pris en charge, animé, ou différent du type annoncé |
| 422 | Paramètres de requête invalides, selon la validation standard FastAPI |
| 502 | Échec du pipeline ou résultat incompatible avec la capture |
| 503 | Pipeline non configuré |
| 504 | Délai d'inférence dépassé |

Les erreurs applicatives contiennent `detail.code` et `detail.message` ; les erreurs
de paramètres `422` conservent la liste de détails standard FastAPI. Aucun résultat du
pipeline n'est renvoyé en cas d'échec.

Le délai d'inférence est une annulation **coopérative** de la coroutine : le pipeline doit
être asynchrone et non bloquant. Un calcul synchrone lourd doit être isolé dans un worker
avec ses propres limites. Ce délai ne tue pas un thread ni un GPU bloqué ; la gestion
de concurrence et l'isolation seront à vérifier avec les véritables modèles avant partage cloud.

## Raccordement avec Saber et Rayan

`src/sbc_vision/perception/pipeline.py` définit le point d'entrée commun :
`async analyze(capture: Capture) -> PerceptionResponse`.
L'adaptateur de détection/OCR sera chargé au démarrage, puis affecté à
`app.state.perception_pipeline`. Les erreurs du moteur restent distinctes des détections.
Cette affectation ne charge aucun modèle à elle seule.

`/health` et `/api/v1/capabilities` continuent à signaler l'absence de modèle du socle.
La readiness devra refléter le véritable chargement dans le prochain lot d'intégration.

À terminer pour #14 : intégrer le détecteur #6 et l'OCR #9, vérifier leurs sorties sur
une image partageable, mesurer la latence réelle et éprouver leur comportement en cas
d'annulation. Les régions OCR préparées à la main sur la branche de Rayan ne constituent
pas encore une détection automatique de l'écran entier.

## Vérification locale

`make check` vérifie le style, les tests et l'absence de dérive du schéma existant.
`tests/test_perception_api.py` teste le succès du transport, une détection vide, le modèle
absent, les formats, les limites, les délais et les résultats incohérents. Le pipeline
fictif est injecté uniquement dans les tests ; l'API normale n'active aucun mode de simulation.
