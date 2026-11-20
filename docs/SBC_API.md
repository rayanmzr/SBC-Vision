# API de l'inventaire et du moteur SBC — SBV-014

Cette couche HTTP réutilise le moteur de Rayan : `players.list_items`, `load_pool`,
`set_protected`, puis `solver.solve`, `verification`, `shopping_list` et `recheck`.
Elle réutilise aussi `confirm_readings` pour enregistrer les exemplaires choisis après OCR.
Elle ne contient ni nouveau solveur ni lecture du navigateur.

## Parcours des données

1. L'extension demande l'inventaire confirmé et les conditions configurées.
2. L'API renvoie les exemplaires, les prix datés et une révision de l'état.
3. Modifier une protection écrit dans le même SQLite que le moteur de Rayan.
4. La révision change ; une ancienne proposition doit être retirée de l'interface.
5. Calculer envoie du JSON : révision, conditions courantes et préférences de budget/plafond.
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
| `POST /api/v1/sbc/inventory` | Rapport OCR, choix par élément, `confirmed: true`, `expected_revision` | Inventaire après confirmation locale des exemplaires |
| `POST /api/v1/sbc/solve` | `expected_revision`, préférences facultatives | Mode, révision et rapport du véritable moteur |

Les préférences facultatives sont `budget`, `max_card_value` et `seconds` (3 secondes
par défaut, 5 maximum). Le budget concerne les achats, pas la somme économique totale.
Le plafond par carte s'applique aussi à la valeur sacrifiée, selon le moteur de Rayan.
La requête accepte aussi `challenge` au contrat dynamique du moteur ; il remplace les
conditions configurées pour ce calcul uniquement. Sans lui, le fichier du serveur est utilisé.
L'extension transmet les conditions OCR complètes après le choix explicite de l'utilisateur.

Pour `/inventory`, chaque choix contient `instance_id`, `card_id` et `protected` (vrai
par défaut). La version doit appartenir aux candidats recalculés depuis le catalogue et
les champs lisibles. Les écritures sont atomiques ; réobserver le même identifiant ne
crée pas une seconde copie et conserve ses protections. Des copies distinctes exigent
des identifiants distincts. L'identité entre écrans reste à fournir par le contrôleur ;
l'extension la demande manuellement dans ce premier raccord. Cette confirmation modifie
l'inventaire local uniquement : aucune action EA n'est exécutée.

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
Le conteneur contient les options `data,solver,ocr,vision` ; la base et les poids restent
à monter et les fonctions à activer explicitement, voir [DEPLOYMENT.md](DEPLOYMENT.md).

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
la préparation du partage sont décrites dans le guide de déploiement ; le cloud reste à choisir.
La note d'équipe et le collectif conservent
les limites du profil standard documentées par Rayan ; une proposition n'est pas une
confirmation par EA. Le détecteur alimente l'OCR ; le scan réel et le contrôleur restent à raccorder.

## Scan hybride du club EA

L'extension ajoute « Scanner le club EA » sur Analyser. Depuis la première page de
`Club → Players` (interface anglaise), elle capture la zone visible pour l'OCR, lit les
lignes HTML déjà rendues, puis utilise seulement `Next`. Le parcours est borné entre
1 et 500 pages (100 par défaut), s'arrête sur page répétée ou changement d'onglet et
peut être interrompu. Aucune requête vers une API privée EA n'est effectuée.

`POST /api/v1/sbc/club-scan` accepte `capture_id`, `pages`, `complete`, `expected_revision`
et `confirmed` (faux par défaut). Chaque page contient les cartes DOM, leur visibilité,
leur état de prêt, les indicateurs de pagination et le rapport OCR éventuel. Les
observations sont sauvegardées dans `club_scans` en SQLite, même lorsque le catalogue
ne retrouve pas la version. Les cartes DOM ne reçoivent aucune confiance OCR. `GET /api/v1/sbc/club-scan`
permet de rouvrir le dernier relevé depuis le popup après sa fermeture.

Après examen, la confirmation d'un scan complet remplace uniquement le précédent
comptage DOM dans `club_items`. Les versions uniques hors prêt sont importées ; les
ambiguïtés et absences du catalogue restent en attente. Les identifiants `dom:version:n`
sont des ordinaux locaux, sans équivalence revendiquée avec les exemplaires EA. Un
rescan conserve les quantités observées sans les additionner et remet toutes les
cartes importées sous protection. Les copies manuelles provoquent un refus : leur
rapprochement avec le comptage DOM doit être explicite. Un scan partiel ne remplace
pas cet inventaire. Les cartes évoluées absentes du catalogue restent en attente.

Les prêts sont détectés dans le HTML et exclus de l'import utilisable en SBC. Les
attributs de logos restent confrontés strictement au catalogue : un identifiant
EA différent ne doit pas être assimilé à un identifiant fournisseur sans table de
correspondance vérifiée. Les prix absents ou périmés restent inconnus.

Le 20 novembre, un parcours réel en lecture a relevé neuf pages et 163 cartes, dont
six prêts. Treize lectures OCR exploitables concordent en nom/note avec les lignes
visibles. Le petit catalogue local ne permettait d'identifier sans ambiguïté qu'une
version utilisable ; les autres observations restent sauvegardées, sans fausse
confirmation. Ces chiffres décrivent un essai de développement avec contrôle DOM,
pas un benchmark OCR indépendant. L'essai public FUTBIN du même jour a répondu 403.
Les captures, rapports et détails du club restent locaux et ignorés par Git.

Essai supplémentaire depuis le popup de l'extension chargée dans Chrome : neuf pages,
163 observations sauvegardées via HTTP ; neuf lectures OCR exploitables dont huit
concordent avec des lignes entièrement visibles. Ce second passage utilise la capture
native de l'onglet et ne remplace pas le premier relevé par capture du bureau. Les deux
comptages OCR restent séparés ; aucun score indépendant de précision n'est annoncé.

## Accueil simplifié et SBC courant

`POST /api/v1/sbc/read` reçoit `source: "dom"`, le texte des conditions de l'écran,
les postes, le budget et la série de marché. Le parseur dynamique refuse les règles
non reconnues et ne leur attribue aucune confiance OCR. L'extension envoie ensuite
le Challenge au solveur. Les valeurs ne sont pas codées pour un nom de défi.

L'accueil automatique du scan confirme seulement le comptage local des versions
uniques d'un parcours complet ; il n'échange aucune carte sur EA. Les prix et
protections restent ceux du moteur. Le diagnostic conserve le parcours manuel.

Après l'actualisation du catalogue, le même relevé privé a été rapproché de nouveau :
119 copies hors prêt ont été enregistrées dans le club local, toutes protégées. Les
six prêts, sept ambiguïtés et 31 absences restent hors du pool confirmé. Le solveur
a reçu les sept conditions et onze postes du SBC courant via `/sbc/read` ; avec un
budget de 5 000 et un plafond par carte de 1 000, le pool observé ne fournit aucune
solution. Aucune condition n'est assouplie et aucune carte n'est placée.
