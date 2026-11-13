# API de l'inventaire et du moteur SBC — SBV-014

Cette couche HTTP réutilise le moteur de Rayan : `players.list_items`, `load_pool`,
`set_protected`, puis `solver.solve`, `verification`, `shopping_list` et `recheck`.
Elle ne contient ni nouveau solveur ni lecture du navigateur. La branche de Rayan
est intégrée à la branche API avec son historique ; cette intégration ne fusionne rien
dans `main` et ne vaut pas validation de la PR #23 par l'équipe.

## Parcours des données

1. L'extension demande l'inventaire confirmé et les conditions configurées.
2. L'API renvoie les exemplaires, les prix datés et une révision de l'état.
3. Modifier une protection écrit dans le même SQLite que le moteur de Rayan.
4. La révision change ; une ancienne proposition doit être retirée de l'interface.
5. Calculer envoie uniquement du JSON : révision et préférences de budget/plafond.
6. Python appelle CP-SAT et le vérificateur indépendant de Rayan.
7. L'API contrôle à nouveau les données avant de rendre le rapport.

La détection et l'OCR ne sont pas activés par cette couche. Le solveur ne reçoit aucune
capture et l'API n'exécute aucun achat, placement ou échange.

## Essai local entièrement fictif

Depuis la racine de cette branche :

```bash
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev,data,solver,ocr]'
python scripts/prepare_api_demo.py
SBC_ENGINE_MODE=demo \
SBC_ENGINE_DATABASE=data/processed/api_demo/inventory.sqlite3 \
SBC_ENGINE_CHALLENGE=data/processed/api_demo/challenge.json \
uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8000
```

L'initialisation ne télécharge rien. Elle prépare une base distincte et un fichier de
conditions à partir des fixtures. Les données restent sous `data/processed`, hors Git.
Les cartes sont fictives mais **le calcul CP-SAT et les écritures de protection sont réels**.
La date fictive permet de rejouer les mêmes prix sans les présenter comme des prix actuels.
Le service refuse le mélange entre ces données et une base configurée en mode local.

Le scénario initial coûte 2 100 crédits : 1 300 d'achats et 800 de valeur sacrifiée.
Protéger `demo-002` exclut l'exemplaire utilisé. Avec le budget d'achat de 2 000, aucune
solution n'est trouvée sur ce petit pool ; porter explicitement le budget à 3 000 permet
une nouvelle proposition à 2 100, entièrement en achats.

## Routes et contrats

Toutes les routes sont visibles dans `/docs` et `/openapi.json`.

| Méthode et route | Entrée | Sortie |
| --- | --- | --- |
| `GET /api/v1/sbc/workspace` | Aucune image | Mode, révision, exemplaires, conditions et lectures à confirmer |
| `PUT /api/v1/sbc/protections` | `instance_id`, `protected`, `expected_revision` | Nouvel état complet de l'inventaire |
| `POST /api/v1/sbc/solve` | `expected_revision`, préférences facultatives | Mode, révision et rapport du véritable moteur |

Les préférences facultatives sont `budget`, `max_card_value` et `seconds` (3 secondes
par défaut, 5 maximum). Le budget concerne les achats, pas la somme économique totale.
Le plafond par carte s'applique aussi à la valeur sacrifiée, selon le moteur de Rayan.
Les autres contraintes viennent exclusivement du fichier de conditions du serveur.

La révision couvre les cartes, exemplaires, protections, conditions et valeurs encore
utilisables selon `load_pool`. Ainsi, la péremption d'un prix peut changer la révision
même sans écriture dans la base. Un calcul relit la révision et revérifie la proposition
avant réponse. Une modification pendant le calcul entraîne un refus `409`, sans rapport.

Les schémas `workspace.schema.json` et `solve-response.schema.json` sont générés par
`python scripts/export_contracts.py`. Le rapport interne conserve le format du moteur.

## Utiliser des données locales confirmées

Configurer `SBC_ENGINE_MODE=local`, un `SBC_ENGINE_DATABASE` existant, puis
`SBC_ENGINE_CHALLENGE` vers un fichier de `Challenge` ou un rapport OCR contenant
`challenge`. Les chemins sont configurés côté serveur ; ils ne viennent jamais de la
requête web. Les prix sont alors évalués à la date courante et les données fictives sont
refusées. Une lecture `ready: false` permet de consulter les cartes mais bloque le calcul.

Sans configuration, le service renvoie `503 sbc_unavailable`. Il ne crée pas une base
vide à la place d'un inventaire absent et n'active pas une démo automatiquement.
Le conteneur de base peut servir la perception sans les options `data,solver` ; pour le
moteur, ces dépendances devront être installées et la base montée lors du lot #18.

## Erreurs et limites pratiques

- `404` : exemplaire absent de l'inventaire.
- `409` : données modifiées, prix périmés ou conditions encore incertaines ; recharger.
- `422` : requête invalide, budget négatif, type incorrect ou délai supérieur à 5 secondes.
- `429` : un calcul est déjà en cours dans ce processus ; attendre sa fin.
- `503` : configuration, dépendances ou données locales indisponibles.

Une seule résolution CP-SAT est autorisée à la fois par processus. La limite de calcul
est transmise au moteur. L'annulation HTTP côté navigateur ne garantit pas d'arrêter
instantanément ce calcul ; une réponse tardive ne doit pas être affichée par le client.
Les routes synchrones utilisent les workers de FastAPI ; elles ne bloquent pas la boucle
asynchrone qui reçoit les autres requêtes.

Le service de développement écoute uniquement sur `127.0.0.1`. L'authentification et
l'hébergement partagé restent dans le lot #18. La note d'équipe et le collectif conservent
les limites du profil standard documentées par Rayan ; une proposition n'est pas une
confirmation par EA. Le détecteur, le scan réel et le contrôleur restent à raccorder.
