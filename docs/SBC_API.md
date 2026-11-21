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
par défaut, 30 maximum). Le budget concerne les achats, pas la somme économique totale.
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
- `422` : requête invalide, budget négatif, type incorrect ou délai supérieur à 30 secondes.
- `429` : un calcul est déjà en cours dans ce processus ; attendre sa fin.
- `503` : configuration, dépendances ou données locales indisponibles.

Une seule résolution CP-SAT est autorisée à la fois par processus. La limite de calcul
est transmise au moteur ; l'accueil demande 20 secondes au maximum pour les compositions
complexes, avec un délai HTTP de 45 secondes. L'annulation HTTP côté navigateur ne garantit pas d'arrêter
instantanément ce calcul ; une réponse tardive ne doit pas être affichée par le client.
Les routes synchrones utilisent les workers de FastAPI ; elles ne bloquent pas la boucle
asynchrone qui reçoit les autres requêtes.

Le service de développement écoute uniquement sur `127.0.0.1`. L'authentification et
la préparation du partage sont décrites dans le guide de déploiement ; le cloud reste à choisir.
La note d'équipe et le collectif conservent
les limites du profil standard documentées par Rayan ; une proposition n'est pas une
confirmation par EA. Le détecteur alimente l'OCR ; le scan est raccordé et le placement
est testé sur des scènes fictives. Sa validation réelle reste ouverte.

## Scan hybride du club EA

L'accueil rejoint automatiquement `Club → Players` (interface anglaise), puis revient
à la première page. Le diagnostic conserve aussi son bouton de scan. L'extension capture la zone visible pour l'OCR, lit les
lignes HTML déjà rendues, puis utilise seulement `Next`. Le parcours est borné entre
1 et 500 pages (100 par défaut), s'arrête sur page répétée ou changement d'onglet et
peut être interrompu. Aucune requête vers une API privée EA n'est effectuée.
Une capture native expire après huit secondes et l'annulation n'attend pas son retour.
Si elle échoue, les pages suivantes restent lisibles en HTML ; `ocr_error` conserve
l'échec et aucun résultat OCR n'est inventé.

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

Seuls les emplacements ouverts du terrain sont transmis : les cases verrouillées et
la zone de travail sont exclues. L'extension conserve leurs indices EA pour le placement.
Un nombre de cartes incompatible avec les conditions bloque la lecture. Sans condition
de collectif, `/read` choisit `position_mode: "any"` : une carte peut être hors poste.
Avec collectif, le profil reste limité aux postes préférés ; les anciens JSON gardent
ce comportement par défaut. Le contrôleur retire le filtre de poste pour une recherche libre.

L'accueil demande `prefer_club: true` à `/solve`. Le moteur consacre au plus la moitié du
temps demandé à une recherche limitée aux cartes autorisées du club, sous le même plafond
de valeur. Si elle n'aboutit pas, il utilise le temps restant pour le pool avec achats.
Le champ `report.selection_scope` indique `club` ou `club_and_market` : le statut optimal
porte sur le pool retenu, pas sur une comparaison globale entre ces deux stratégies.
Les appels sans cette préférence conservent l'optimisation économique du pool complet.

Dans cette recherche limitée au club, les défis sans collectif privilégient la somme
des notes la plus basse parmi les cartes admissibles, puis le coût économique à note
totale égale. Le plafond par carte et toutes les conditions restent appliqués. Les deux
étapes partagent le délai de recherche ; si la seconde expire, une solution conservée
reste `feasible`. `selection_priority: "rating_then_value"` indique cette préférence.
Avec collectif ou dans le pool incluant les achats, la priorité reste le coût.

Le scan conserve la protection d'une version présente en un exemplaire unique avant et
après le relevé. Les nouvelles versions et les doublons redeviennent protégés, puisque
le DOM ne fournit pas ici leur identité EA persistante. Le bilan `protected` compte les
cartes protégées parmi les versions identifiées du nouveau relevé.

L'accueil automatique du scan confirme seulement le comptage local des versions
uniques d'un parcours complet ; il n'échange aucune carte sur EA. Les prix et
protections restent ceux du moteur. Le diagnostic conserve le parcours manuel.

Après l'actualisation du catalogue, le même relevé privé a été rapproché de nouveau :
119 copies hors prêt ont été enregistrées dans le club local, toutes protégées. Les
six prêts, sept ambiguïtés et 31 absences restent hors du pool confirmé. Le solveur
a reçu les sept conditions et onze postes du SBC courant via `/sbc/read` ; avec un
budget de 5 000 et un plafond par carte de 1 000, le pool observé ne fournit aucune
solution. Aucune condition n'est assouplie et aucune carte n'est placée.

## Plan de placement du club

La réponse de `/solve` ajoute `placement`, facultatif. Pour une composition vérifiée,
ses cartes relient chaque emplacement à la lecture DOM du dernier scan confirmé :
nom, note, poste, six statistiques et identifiants de pays, championnat et club.
Le serveur rapproche de nouveau cette lecture du catalogue. Une copie protégée,
plusieurs copies identiques, une donnée manquante ou un achat nécessaire renvoient
des `issues` et un plan vide. Aucun plan n'est construit à partir de la démo.

Un nouveau scan change aussi la révision. `/club-scan` renvoie `expected_revision`
pour la confirmation suivante ; une réponse ancienne ne doit pas réutiliser sa révision.

Dans l'extension, le contrôleur compare l'onglet, le document, le titre, les conditions
et la composition avant d'agir. Il n'écrase aucune case. Il cherche uniquement dans
le club, refuse prêts et joueurs de l'équipe active, compare la version complète,
puis vérifie la note et les trois identifiants dans la case remplie. Chaque mutation
est tentée une fois ; une divergence arrête le parcours. Les protections et la révision
sont relues avant chaque carte et juste avant son placement. Un arrêt après un placement
conserve les cartes déjà posées ; il faut contrôler la composition manuellement.

Les tests de placement sont fictifs. La navigation réelle peut être vérifiée en lecture,
sans cliquer sur le bouton d'ajout d'un joueur. Le contrôleur ne contient aucune action
Submit, Exchange, achat ou confirmation finale. Ce parcours DOM ne mesure pas la
qualité du détecteur ou de l'OCR.
