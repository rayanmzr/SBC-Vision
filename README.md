# SBC Vision

Assistant visuel de préparation des défis de création d'équipe (SBC) sur la **Web App EA FC 27**. Projet Computer Vision Epitech 2026-2027, sujet 2 : « Vision pour piloter une interface ».

Le client prévu est une **extension Chrome avec interface React**, reliée à l'API Python pour la vision, l'OCR et le solveur.

Le modèle transforme une capture en une liste JSON d'éléments et d'actions possibles. Un contrôleur exploite ce résultat pour inventorier le club, préparer une composition et vérifier les écrans. Le solveur cherche à réduire les dépenses et la valeur des cartes sacrifiées, en préservant les cartes protégées.

**Avancement :** l'extension, l'API, le détecteur ONNX, l'OCR, l'inventaire SQLite et le solveur sont raccordés. La cible du parcours est uniquement la vraie Web App EA. Les essais sur les captures EA montrent encore des versions ambiguës et des emplacements manqués : le scan hybride du club est implémenté ; le remplissage réel reste à raccorder. Voir le [guide API](docs/API.md).

## Équipe

| Membre | Compte | Responsabilité principale |
| --- | --- | --- |
| Saber Kasri | [@saberkasri](https://github.com/saberkasri) | Données, annotations, détection, entraînement, évaluation |
| Rayan Mazri | [@rayanmzr](https://github.com/rayanmzr) | OCR, inventaire, données FUTBIN, optimisation SBC |
| Samy Allali | [@SamyALlali](https://github.com/SamyALlali) | Extension, contrôleur, API, Docker et cloud |

La [répartition détaillée](docs/TEAM.md) précise les interfaces et livrables de chacun.

La partie de Rayan est regroupée dans [sbc_engine](src/sbc_vision/sbc_engine/README.md) : catalogue FUTBIN, inventaire, OCR et optimisation. Une seule commande permet de tester les fonctions : `python -m sbc_vision.sbc_engine --help`.

Les routes d'inventaire, de protections et de résolution sont maintenant raccordées à
ce moteur. Leur activation est explicite : voir le [guide API SBC](docs/SBC_API.md),
notamment le parcours de démonstration avec cartes fictives et véritable calcul CP-SAT.

## Extension Chrome

L'accueil contient deux actions : **Scanner mon club** et **Compléter ce SBC**.
Le scan combine l'OCR visible et les lignes HTML, puis enregistre les cartes identifiées
sous protection. L'action SBC lit les conditions de l'écran courant et lance le calcul ;
le placement automatique reste à raccorder et aucun échange n'est soumis.

Le budget, le plafond par carte, l'adresse et la clé du serveur sont dans **Options**.
Le lien « Diagnostic et protections des cartes » ouvre les anciennes vues Analyser,
Équipe et Réglages, utiles pour les lectures incertaines et les tests de l'équipe.
Les cartes sont protégées par défaut ; leur protection se règle explicitement dans ce diagnostic.

## Démarrage local

Python **3.11 ou 3.12**. Depuis la racine du dépôt :

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev,data,solver,ocr]'
uvicorn sbc_vision.api.main:app --reload
```

Avec Python 3.12, remplacer `python3.11` par `python3.12`. Pour l'OCR, installer aussi Tesseract 5 : `brew install tesseract` sur macOS ou `sudo apt install tesseract-ocr` sur Ubuntu.

- Santé : <http://127.0.0.1:8000/health>
- Documentation API : <http://127.0.0.1:8000/docs>
- Capacités implémentées : <http://127.0.0.1:8000/api/v1/capabilities>
- Schéma de perception : <http://127.0.0.1:8000/api/v1/contracts/perception>
- Analyse : `POST /api/v1/perception/analyze` (PNG/JPEG ; `503` sans modèle configuré).

```bash
make check
```

La commande lance le lint, les tests hors ligne et la vérification du schéma JSON.

## Moteur SBC

Le bouton **Scanner mon club** combine OCR des cartes visibles
et lecture du HTML des autres lignes, puis passe à `Next` sans défiler. Les observations
sont sauvegardées côté serveur. Un parcours complet importe uniquement
les versions identifiées, hors prêts, avec protection activée ; les autres restent en
attente. Voir les limites du comptage local et les essais dans [le guide API SBC](docs/SBC_API.md#scan-hybride-du-club-ea).


### Lecture d'une capture EA dans l'extension

Installer les options `.[dev,data,solver,ocr,vision,explain]`, Tesseract et construire l'extension avec `cd frontend && pnpm install --frozen-lockfile && pnpm build`. Télécharger les poids de la release `modeles-v1` et vérifier leur empreinte avec `SHA256SUMS` ; ils restent hors de Git.

```bash
SBC_PERCEPTION_MODE=detector \
SBC_DETECTOR=yolo:data/processed/models/yolo26s-easysbc-ft-s0.onnx \
SBC_CARD_LAYOUT=club-list SBC_OCR_MODE=tesseract-regions \
SBC_ENGINE_MODE=local SBC_ENGINE_DATABASE=data/processed/futbin_fc27.sqlite3 \
uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8000
```

Dans `chrome://extensions`, charger le dossier `frontend/dist` non empaqueté. Régler l'API sur `http://127.0.0.1:8000`, ouvrir Options → Diagnostic, puis Analyser et choisir une capture EA ou capturer l'onglet à la demande. Le serveur détecte les cartes, place leurs régions puis lance l'OCR. Les lectures incertaines restent visibles ; aucun exemplaire ni SBC n'est confirmé automatiquement. Les exemplaires ajoutés explicitement sont protégés par défaut. Les conditions ne passent au solveur que si elles sont disponibles et complètes.

Le poids livré par Saber sert de point de départ ; son entraînement initial ne constitue pas une validation sur EA. Sur une capture EA de développement, trois miniatures sont détectées et leurs lectures sont exploitables ; une version reste ambiguë. Sur une capture de composition, seuls quatre des onze emplacements sont détectés et les régions des conditions ne sont pas produites automatiquement. Les régions manuelles restent utilisables par la route OCR pour diagnostiquer ces erreurs. Ce petit lot a servi au réglage, pas à une évaluation indépendante. Ces limites doivent être corrigées et mesurées sur EA avant d'annoncer un parcours autonome.

```bash
# Import limité avec cache, si la source est accessible.
python -m sbc_vision.sbc_engine import --pages 2
# Compléter le pool avec les qualités utiles aux SBC.
python -m sbc_vision.sbc_engine import --quality silver --pages 5
python -m sbc_vision.sbc_engine import --quality bronze --pages 5
# Démonstrations hors ligne avec des cartes fictives.
python -m sbc_vision.sbc_engine club demo
python -m sbc_vision.sbc_engine solve --demo
```

`python -m sbc_vision.sbc_engine demo` essaie le parcours image → OCR → inventaire → conditions → solveur dans un dossier local distinct, avec régions annotées et confirmations simulées. Le [guide](src/sbc_vision/sbc_engine/README.md) décrit les fichiers produits et les limites.

Sur le petit défi fictif, la sélection simple coûte 2 600 crédits en valeur économique ; OR-Tools trouve 2 100 crédits, dont 1 300 d'achats et 800 de valeur sacrifiée. Les exemplaires protégés sont exclus et chaque proposition est vérifiée séparément. Le rapport reste dans `data/processed/solution.json`.

Le [guide du moteur](src/sbc_vision/sbc_engine/README.md) explique les cinq fichiers et les commandes, dont `demo --complex` à onze joueurs et dix conditions. Les bases restent dans `data/processed/`, ignoré par Git. Les démos utilisent des bases distinctes des données réelles. FUTBIN a répondu HTTP 403 le 6 novembre ; le 12 novembre, un nouvel essai ciblé et deux pages ont fonctionné. Le cache et l'import de fichier restent disponibles.

Le moteur reçoit les conditions de chaque capture : aucun nom de SBC n'est codé dans l'algorithme. Il prend en charge les compositions et l'Item Score, des contraintes minimum/maximum/exactes, la note à onze joueurs et un profil de collectif standard. Les lectures ou règles non prises en charge bloquent la proposition. Voir le [guide du moteur](src/sbc_vision/sbc_engine/README.md) pour les limites et les commandes OCR.

## Docker

```bash
docker compose up --build
```

L'API est exposée uniquement sur `127.0.0.1:8000`. L'image contient aussi OR-Tools
et Tesseract ; les fonctions métier restent activées explicitement. Compose utilise
le mode local sans clé. L'image seule utilise le mode production et exige une clé.
Le [guide Docker et partage](docs/DEPLOYMENT.md) explique la démonstration fictive,
la clé d'accès, les limites, la persistance et les vérifications. Aucun cloud n'est
déployé par ces commandes.

## Organisation

```text
src/sbc_vision/      API, contrats et briques Python
frontend/           Extension Chrome React, aperçu, tests et build MV3
contracts/          Schémas JSON : perception, formats SBC, inventaire et propositions
data/fixtures/      Exemples synthétiques et protocole enregistré anonymisé, sans compte réel
data/raw/           Captures locales, ignorées par Git
docs/               Cadrage, architecture, données, protocole et équipe
planning/           Backlog, jalons, responsables et suivi GitHub
scripts/            Export des contrats
.github/            CI et modèles d'issues / pull requests
```

## Parcours cible

1. L'utilisateur ouvre sa session, choisit un SBC, fixe un budget et protège ses cartes.
2. Le contrôleur parcourt le club ; les captures automatiques alimentent détection et OCR.
3. L'inventaire distingue les versions et les exemplaires de cartes.
4. Le solveur vérifie les règles prises en charge, puis propose une équipe et les achats éventuels, avec les cartes exactes et des alternatives.
5. Le contrôleur place les cartes et relit l'écran. L'utilisateur examine le récapitulatif avant toute confirmation finale.

La cible est la **vraie Web App**. L'exécution automatique sur le service réel dépend des autorisations d'EA. Un démonstrateur local minimal est le secours proposé au superviseur ; les captures réelles restent utilisées pour l'évaluation de la vision. Voir le [périmètre](docs/CONTEXT.md).

## Vision et évaluation

- 300 à 500 captures annotées prévues, incluant des captures réelles obtenues lors de navigations manuelles et un sous-ensemble WebUI.
- Comparaison OpenCV + OCR / détecteur affiné + OCR ; référence OmniParser optionnelle.
- Au moins 50 captures de 5 domaines exclus de l'entraînement et de la validation.
- mAP@0,5, erreur OCR, F1 des éléments JSON, validité du schéma, latence et taux de réussite du parcours.

Les résultats ne sont pas encore mesurés. Le [protocole](docs/EVALUATION.md) précise les splits et les métriques.

## Planning et liens

- [GitHub Project](https://github.com/users/rayanmzr/projects/5)
- [Issues](https://github.com/rayanmzr/SBC-Vision/issues)
- [Répartition des tâches](docs/TEAM.md)
- [Feuille de route](planning/ROADMAP.md)
- [Backlog source](planning/backlog.json)
- [Note de cadrage](docs/cadrage/note-cadrage.pdf)
- [Architecture et contrats](docs/ARCHITECTURE.md)

## Travail en équipe

Choisir une issue, déplacer sa carte dans `In Progress`, créer une branche et faire des commits ciblés avec son compte. Ouvrir une PR liée à l'issue, faire relire par un membre puis fusionner après la CI. Une tâche est terminée quand ses critères sont remplis, ses limites documentées et ses changements intégrés.

Documentation et commentaires en français, identifiants Python en anglais. Garder les dépendances nécessaires et le code réutilisable dans `src/`. Lancer `make check` avant un push ; après modification des formats, régénérer les deux schémas avec `python scripts/export_contracts.py`. Les métriques indiquent le split, le matériel et le run MLflow.

Les tokens, cookies, captures privées, inventaires réels et poids lourds restent hors de Git. Pour un signalement sensible, contacter le propriétaire du dépôt par un canal privé. La connexion EA reste dans le navigateur de l'utilisateur et toute soumission exige sa confirmation. Voir les [consignes de données](docs/DATA.md).

## Données et budget

L'importeur FUTBIN découvre les identifiants, récupère les cartes par lots et conserve les prix dans SQLite. L'essai initial porte sur 60 versions de cartes ; le catalogue complet n'a pas encore été importé. Voir [DATA.md](docs/DATA.md) pour les champs, la provenance et les conditions d'utilisation.

Le développement commence sur nos machines. Le cloud et le budget de calcul seront choisis en équipe.

Le projet est publié sous licence GNU AGPL v3 ([LICENSE](LICENSE)), choisie en équipe : les détecteurs dérivent des poids YOLO d'Ultralytics, eux-mêmes sous AGPL-3.0. Les bibliothèques et données tierces conservent leurs propres licences ; aucun droit de redistribution général des contenus EA ou FUTBIN n'est supposé.

### Catalogue local avec Chrome

Si l'import HTTP répond 403, ouvrir normalement [le catalogue FUTBIN](https://www.futbin.com/27/players)
dans Chrome sur macOS, puis utiliser `import --browser --pages 2`. Cette option garde
le même protocole, le cache et les délais ; elle ne résout aucun CAPTCHA et s'arrête
sur un refus du navigateur. Chrome doit autoriser JavaScript dans les événements
AppleScript. Aucun cookie ni identifiant de session n'est exporté.

`import --browser --scan chemin/releve.json` actualise les versions recherchées depuis
les noms d'un scan sauvegardé ; les prêts sont ignorés. Le catalogue reste local et
les prix absents restent inconnus. Voir [DATA.md](docs/DATA.md).
