# SBC Vision

Assistant visuel de préparation des défis de création d'équipe (SBC) sur la **Web App EA FC 27**. Projet Computer Vision Epitech 2026-2027, sujet 2 : « Vision pour piloter une interface ».

Le modèle transforme une capture en une liste JSON d'éléments et d'actions possibles. Un contrôleur exploite ce résultat pour inventorier le club, préparer une composition et vérifier les écrans. Le solveur cherche à réduire les dépenses et la valeur des cartes sacrifiées, en préservant les cartes protégées.

**Avancement sur cette branche :** socle du dépôt et route de réception des captures avec
validation et tests de transport. Le détecteur et l'OCR ne sont pas encore raccordés à
l'API ; une analyse valide renvoie donc `503`, sans prédictions fictives. Voir le
[guide de la première étape API](docs/API.md). Les développements non fusionnés des
autres membres ne sont pas inclus dans cet état de `main`.

## Équipe

| Membre | Compte | Responsabilité principale | Document de travail |
| --- | --- | --- | --- |
| Saber Kasri | [@saberkasri](https://github.com/saberkasri) | Données, annotations, détection, entraînement, évaluation | [Vision](docs/roles/saber.md) |
| Rayan Mazri | [@rayanmzr](https://github.com/rayanmzr) | OCR, inventaire, données FUTBIN, optimisation SBC | [OCR et solveur](docs/roles/rayan.md) |
| Samy Allali | [@SamyALlali](https://github.com/SamyALlali) | Application, contrôleur, API, Docker, cloud, secours local | [Application et intégration](docs/roles/samy.md) |

Chaque membre prend en charge sa partie et participe aux revues des autres.

## Démarrage local

Python **3.11 ou 3.12**. Depuis la racine du dépôt :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev]'
uvicorn sbc_vision.api.main:app --reload
```

- Santé : <http://127.0.0.1:8000/health>
- Documentation API : <http://127.0.0.1:8000/docs>
- Capacités implémentées : <http://127.0.0.1:8000/api/v1/capabilities>
- Schéma de perception : <http://127.0.0.1:8000/api/v1/contracts/perception>
- Analyse : `POST /api/v1/perception/analyze` (PNG/JPEG binaire ; `503` avant raccordement).

```bash
make check
```

La commande lance le lint, les tests hors ligne et la vérification du schéma JSON.

## Docker

```bash
docker compose up --build
```

L'API est exposée sur `127.0.0.1:8000`. Les modèles seront intégrés dans les prochaines étapes.

## Organisation

```text
src/sbc_vision/      API, contrats et emplacements des briques Python
frontend/           Périmètre de l'application React à construire
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

La récupération des données FUTBIN a été testée sur 60 cartes, dont un appel JSON par lots. L'import complet reste à développer. Voir [DATA.md](docs/DATA.md) pour les champs, la provenance et les conditions d'utilisation.

Le développement commence sur nos machines. Le cloud et le budget de calcul seront choisis en équipe.

La licence de notre code reste à choisir en équipe. Les bibliothèques, modèles et données conservent leurs propres licences ; aucun droit de redistribution général des contenus EA ou FUTBIN n'est supposé.
