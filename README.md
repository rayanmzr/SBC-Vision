# SBC Vision

Assistant visuel de préparation des défis de création d'équipe (SBC) sur la **Web App EA FC 27**. Projet Computer Vision Epitech 2026-2027, sujet 2 : « Vision pour piloter une interface ».

Le client prévu est une **extension Chrome avec interface React**, reliée à l'API Python pour la vision, l'OCR et le solveur.

Le modèle transforme une capture en une liste JSON d'éléments et d'actions possibles. Un contrôleur exploite ce résultat pour inventorier le club, préparer une composition et vérifier les écrans. Le solveur cherche à réduire les dépenses et la valeur des cartes sacrifiées, en préservant les cartes protégées.

**Avancement :** API de démarrage, contrats JSON, import FUTBIN, inventaire SQLite et solveur expérimental sur un défi fictif. La détection, l'OCR, les règles SBC réelles et l'extension restent à raccorder.

## Équipe

| Membre | Compte | Responsabilité principale | Document de travail |
| --- | --- | --- | --- |
| Saber Kasri | [@saberkasri](https://github.com/saberkasri) | Données, annotations, détection, entraînement, évaluation | [Vision](docs/roles/saber.md) |
| Rayan Mazri | [@rayanmzr](https://github.com/rayanmzr) | OCR, inventaire, données FUTBIN, optimisation SBC | [OCR et solveur](docs/roles/rayan.md) |
| Samy Allali | [@SamyALlali](https://github.com/SamyALlali) | Application, contrôleur, API, Docker, cloud, secours local | [Application et intégration](docs/roles/samy.md) |

Chaque membre prend en charge sa partie et participe aux revues des autres.

La partie de Rayan est regroupée dans [sbc_engine](src/sbc_vision/sbc_engine/README.md) : catalogue FUTBIN, inventaire, OCR et optimisation. Une seule commande permet de tester les fonctions : `python -m sbc_vision.sbc_engine --help`.

## Démarrage local

Python **3.11 ou 3.12**. Depuis la racine du dépôt :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev,data,solver,ocr]'
uvicorn sbc_vision.api.main:app --reload
```

- Santé : <http://127.0.0.1:8000/health>
- Documentation API : <http://127.0.0.1:8000/docs>
- Capacités implémentées : <http://127.0.0.1:8000/api/v1/capabilities>
- Schéma de perception : <http://127.0.0.1:8000/api/v1/contracts/perception>

```bash
make check
```

La commande lance le lint, les tests hors ligne et la vérification du schéma JSON.

## Catalogue FUTBIN

```bash
# Premier essai limité à deux pages, puis réutilisation du cache à la relance.
python -m sbc_vision.sbc_engine import --pages 2

# Actualiser seulement une version de carte avant un calcul.
python -m sbc_vision.sbc_engine import --ids 107 --refresh
```

Les cartes et l'historique des prix restent dans `data/processed/futbin_fc27.sqlite3`, ignoré par Git. Le [guide du moteur](src/sbc_vision/sbc_engine/README.md) explique les six fichiers et les options. Si FUTBIN refuse l'accès, le cache est conservé et un export normalisé peut être importé.

## Inventaire du club

```bash
# Démo hors ligne : trois exemplaires fictifs, dont un protégé.
python -m sbc_vision.sbc_engine club demo

# Consulter seulement les exemplaires non protégés de cette démo.
python -m sbc_vision.sbc_engine club --db data/processed/club_demo.sqlite3 list --unprotected
```

L'inventaire distingue les versions et les exemplaires, conserve les protections et recherche les versions candidates d'une lecture OCR. Le [guide du moteur](src/sbc_vision/sbc_engine/README.md) décrit les commandes et les régions attendues. La démo utilise une base distincte du catalogue réel ; aucun club EA n'est encore scanné.

## Solveur expérimental

```bash
python -m sbc_vision.sbc_engine solve --demo
```

Sur le petit défi fictif, la sélection simple coûte 2 600 crédits en valeur économique ; OR-Tools trouve 2 100 crédits, dont 1 300 d'achats et 800 de valeur sacrifiée. Les exemplaires protégés sont exclus et chaque proposition est vérifiée séparément. Le rapport reste dans `data/processed/solution.json`.

Le moteur reçoit les conditions de chaque capture : aucun nom de SBC n'est codé dans l'algorithme. Il prend en charge les compositions et l'Item Score, des contraintes minimum/maximum/exactes, la note à onze joueurs et un profil de collectif standard. Les lectures ou règles non prises en charge bloquent la proposition. Voir le [guide du moteur](src/sbc_vision/sbc_engine/README.md) pour les limites et les commandes OCR.

## Docker

```bash
docker compose up --build
```

L'API est exposée sur `127.0.0.1:8000`. Les modèles seront intégrés dans les prochaines étapes.

## Organisation

```text
src/sbc_vision/      API, contrats et emplacements des briques Python
frontend/           Périmètre de l'extension Chrome et de son interface React
contracts/          Schémas JSON générés et versionnés
data/fixtures/      Exemples synthétiques, sans compte réel
data/raw/           Captures locales, ignorées par Git
notebooks/          Exploration, entraînement et évaluation à produire
docs/               Cadrage, architecture, données, protocole, décisions, rôles
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
- [Répartition des tâches](planning/ISSUES.md)
- [Feuille de route](planning/ROADMAP.md)
- [Backlog source](planning/backlog.json)
- [Note de cadrage](docs/cadrage/note-cadrage.pdf)
- [Architecture et contrats](docs/ARCHITECTURE.md)
- [Contribution](CONTRIBUTING.md)

## Données et budget

L'importeur FUTBIN découvre les identifiants, récupère les cartes par lots et conserve les prix dans SQLite. L'essai initial porte sur 60 versions de cartes ; le catalogue complet n'a pas encore été importé. Voir [DATA.md](docs/DATA.md) pour les champs, la provenance et les conditions d'utilisation.

Le développement commence sur nos machines. Le cloud et le budget de calcul seront choisis en équipe.

La licence de notre code reste à choisir en équipe. Les bibliothèques, modèles et données conservent leurs propres licences ; aucun droit de redistribution général des contenus EA ou FUTBIN n'est supposé.
