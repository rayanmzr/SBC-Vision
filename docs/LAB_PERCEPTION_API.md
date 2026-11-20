# Pipeline HTTP du laboratoire — SBV-014 / SBV-016

Le contrôleur peut envoyer ses images à la route de perception existante et consommer
le JSON retourné. Ce raccordement utilise le même `PerceptionPipeline` que le futur
adaptateur du détecteur de Saber. Les images ne passent jamais au solveur.

## Activation explicite

```bash
source .venv/bin/activate
SBC_PERCEPTION_MODE=lab-colors \
uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8000
```

Ce mode n'installe aucun poids et ne reconnaît pas les joueurs EA. Il identifie les
trois rectangles colorés de `controller-lab.html`, à partir des pixels reçus. C'est
un outil de test du transport et du contrôleur, pas une mesure de qualité du détecteur.
Il ne télécharge rien et n'enregistre aucune capture sur disque.

Avec `SBC_PERCEPTION_MODE=disabled`, ou sans variable, l'analyse conserve son erreur
`503 perception_unavailable` si aucun autre pipeline n'a été injecté. Une valeur
inconnue provoque un échec au démarrage ; elle n'active jamais la démonstration.

## Parcours

1. Le navigateur capture le canevas local, ou le popup capture la zone visible de l'onglet.
2. Le client envoie le binaire PNG avec un nouvel identifiant à
   `POST /api/v1/perception/analyze?capture_id=...`.
3. L'API contrôle le fichier et ses dimensions, puis le décode en RGB en mémoire.
4. Le pipeline calcule des masques colorés dans un worker, sans bloquer la boucle HTTP.
   La boîte est mesurée dans l'image d'origine, sans coordonnées de dessin codées en dur.
5. Une scène reconnue produit le JSON `PerceptionResponse`, avec le même identifiant
   et les mêmes dimensions. Le client vérifie ces correspondances.
6. Le contrôleur décide depuis ce JSON. Les clics restent limités à la page locale.
   Il envoie ensuite de nouvelles images pour vérifier le résultat de l'action.

Une scène absente, masquée ou ambiguë produit `422 scene_unrecognized`, sans proposition
d'action. Les autres limites HTTP restent celles du [guide API](API.md), notamment
5 Mio, 20 millions de pixels, délais et validation du résultat du pipeline.

Le protocole du laboratoire conserve `lab-select → lab-place → lab-done` et le nom
`lab-color-api-v1`. La confiance `1` signale un masque conforme à ce protocole ; ce n'est
pas une probabilité calibrée sur des captures EA. Le traitement navigateur du lot précédent
reste disponible séparément, sans retour automatique vers lui après une erreur HTTP.

## Comprendre les capacités

| Champ | Mode désactivé | Laboratoire activé |
| --- | --- | --- |
| `/health` → `status` | `ok` | `ok` |
| `/health` → `model_loaded` | `false` | `false`, aucun modèle entraîné |
| `/api/v1/capabilities` → `perception` | `false` | `true` |
| `perception_mode` | `disabled` | `lab-colors` |
| `ocr`, `controller`, `live_actions_enabled` | `false` | `false` |

Un pipeline personnalisé injecté par l'application est annoncé comme `custom`. Les
capacités décrivent le pipeline disponible via HTTP ; elles ne prétendent pas que la
Web App a été reconnue ni que le serveur peut agir sur le navigateur.

Le [guide du contrôleur sur la branche #16](https://github.com/rayanmzr/SBC-Vision/blob/feat/16-tab-capture-controller/docs/LOCAL_CONTROLLER.md) décrit le sélecteur
**Analyse des images → API Python · Couleurs de test** et les essais navigateur.
Pour vérifier le serveur seul : `python -m pytest tests/test_lab_perception.py`.
Les tests utilisent la vraie route et des images générées, y compris aux dimensions ×2.
