# API Docker et préparation du partage — issue #18

Ce lot prépare et vérifie le service **en local**. Aucun hébergeur n'a été choisi,
aucun service payant ni déploiement public n'a été créé. Le choix du fournisseur,
du budget, du domaine et du proxy HTTPS reste à faire avec l'équipe.

## 1. Construire le service

Depuis la racine du dépôt, avec Docker et Compose disponibles :

```bash
docker compose up --build -d
```

Compose publie uniquement `127.0.0.1:8000`. `/health` vérifie le processus HTTP ;
`/api/v1/capabilities` indique les fonctions réellement activées. Par défaut, la vision
et l'inventaire sont désactivés : installer les dépendances ne charge pas de modèle.
Le développement local reste accessible sans clé.

L'image contient l'API, Pillow, le moteur SQLite/OR-Tools et Tesseract anglais.
Elle s'exécute avec l'utilisateur `10001`. Compose rend son système de fichiers
en lecture seule, fournit `/tmp` en mémoire et réserve un volume pour les données.
Les limites locales sont de 2 CPU, 2 Gio et 128 processus. Les captures du poste,
les bases personnelles, `.env*`, `.secrets/` et les modèles locaux sont exclus du build.
Seules deux fixtures JSON fictives sont intégrées pour la démonstration.

Python et les dépendances applicatives sont versionnés avec le tag et
`requirements.lock`. Les paquets système et outils de build peuvent évoluer : un
rebuild n'est pas garanti identique octet par octet. Le test enregistre l'identifiant
exact de l'image ; le déploiement devra publier et utiliser son digest.

## 2. Activer une démonstration explicite

```bash
docker compose -f compose.yaml -f compose.demo.yaml up --build -d
```

`demo-init` prépare trois exemplaires fictifs dans le volume. S'ils existent déjà,
`--if-missing` les conserve, y compris leurs protections. Un dossier partiellement
initialisé est refusé. Le mode `lab-colors` reconnaît seulement les rectangles de
la page de laboratoire ; **il ne reconnaît pas les cartes EA**.

Dans l'interface React, vérifier la connexion, ouvrir **Composition SBC**, charger
l'inventaire et lancer le calcul. Pour un budget d'achat de 2 000, le solveur trouve
une solution vérifiée de 2 100 : 1 300 d'achats et 800 de valeur sacrifiée. Le budget
porte sur les achats ; le coût total inclut aussi les cartes du club utilisées.

## 3. Exiger une clé avant de partager

```bash
python scripts/prepare_shared_env.py
docker compose -f compose.yaml -f compose.demo.yaml -f compose.shared.yaml up --build -d
```

Le script crée `.env.shared` avec une clé aléatoire, lisible uniquement par son
propriétaire sur les systèmes POSIX (`0600`), sans l'afficher ni remplacer un fichier
existant. Ce fichier est ignoré par Git et par le build. Le lire localement pour
copier la valeur dans **Clé API (si demandée)**, puis vérifier la connexion.
Sans clé ou avec une mauvaise clé, les routes métier répondent `401` avant de lire
le corps de la requête.

La clé est transmise dans `Authorization: Bearer …`. Le client la garde uniquement
en mémoire, pour l'adresse exacte du serveur. Changer l'adresse ou fermer la page
l'efface ; changer la clé invalide les résultats et la connexion. Il faut la saisir
à nouveau après réouverture. Elle n'est placée ni dans l'URL ni dans le stockage du
navigateur. Les redirections HTTP sont refusées.

`/health`, `/docs`, `/redoc` et `/openapi.json` restent publics. Dans `/docs`, le bouton
**Authorize** permet d'entrer la clé pour essayer les routes protégées.

Variables du serveur :

| Variable | Fonction |
| --- | --- |
| `SBC_ACCESS_MODE=local` | Développement ; la clé est facultative. Une clé fournie est tout de même exigée. |
| `SBC_ACCESS_MODE=shared` | Refuse de démarrer sans clé valide. |
| `SBC_ENV=production` | Choisit `shared` par défaut si le mode n'est pas précisé. C'est le défaut de l'image seule. |
| `SBC_API_KEY` | Clé de 32 à 256 caractères alphanumériques, `_` ou `-`. |
| `SBC_API_KEY_FILE` | Alternative exclusive : chemin d'un fichier contenant la clé, lisible par l'utilisateur `10001`. |
| `SBC_MAX_INFLIGHT` | Requêtes métier simultanées par processus : 4 par défaut, de 1 à 16. |

Pour un hébergement, utiliser le gestionnaire de secrets du fournisseur. Un secret
injecté en variable d'environnement reste lisible par les administrateurs Docker.
Pour renouveler une clé, modifier le secret puis recréer le service ; les clients
doivent se reconnecter avec la nouvelle clé. Il s'agit d'une clé commune à un service
et à son inventaire, pas encore de comptes utilisateurs séparés.

L'overlay partagé conserve le port sur la boucle locale. **Ajouter le proxy HTTPS
avant tout accès distant** : la clé seule ne chiffre pas la connexion. Le client
extension demande aussi l'autorisation de joindre l'adresse HTTPS choisie.

## 4. Comprendre les limites et les données

Toutes les routes métier ont une limite de corps de 5 Mio, vérifiée également pendant
la lecture, et un délai global de 30 secondes. Quand le nombre de requêtes simultanées
est atteint, le serveur renvoie `429 api_busy` avec `Retry-After: 2`, sans mise en file.
Ce plafond est local à chaque processus ; ce n'est pas un quota par utilisateur ou
un limiteur distribué. La santé reste disponible quand le service est occupé.

L'analyse d'image conserve ses limites plus strictes : 8 192 pixels par côté,
20 millions de pixels, 10 secondes de réception et 15 secondes d'inférence. Le
solveur garde son propre verrou et son budget de calcul. L'annulation ne peut pas
tuer arbitrairement un thread de calcul : l'adaptateur du futur modèle devra prévoir
son isolation. Voir [le contrat HTTP](API.md).

Les images sont traitées en mémoire, sans écriture par la route d'analyse. Le solveur
reçoit les données structurées ; il ne reçoit pas les captures. Uvicorn désactive les
logs d'accès dans l'image pour ne pas journaliser les URL et identifiants de capture.
Les réponses métier utilisent `Cache-Control: no-store`. Ces choix devront aussi être
appliqués aux logs et à la rétention du futur proxy/hébergeur.

## 5. Tester l'image et mesurer la latence

```bash
docker build -t sbc-vision:local .
python scripts/smoke_docker.py --image sbc-vision:local --output artifacts/docker/smoke.json
```

Le Python du poste doit disposer de Pillow (présent dans les dépendances du projet).
Le script crée un conteneur, un port local, une clé temporaire et un volume distincts.
Il vérifie : santé, refus sans clé, utilisateur non root, Tesseract installé, PNG → JSON,
calcul réel CP-SAT, protections conservées après initialisation conditionnelle et
redémarrage, absence de clé et d'identifiant de capture dans les logs du test.
Il supprime uniquement ses propres ressources, même en cas d'échec.

Le rapport contient les temps HTTP observés et l'identifiant de l'image. Ce sont des
mesures locales sur données fictives, sans réseau cloud ni modèle entraîné : elles ne
prédisent pas la latence finale. La CI exécute le même test Docker à chaque push.

## 6. Redémarrer et conserver les données

```bash
docker compose -f compose.yaml -f compose.demo.yaml -f compose.shared.yaml restart api
```

SQLite et les conditions restent dans `service-data`, à
`/app/data/processed/api_demo`. Un `down` sans `-v` conserve ce volume ; `down -v`
le détruit. Ne pas partager ce volume entre plusieurs réplicas d'API.
Pour sauvegarder une vraie base, utiliser la sauvegarde SQLite ou arrêter le service
avant de copier les fichiers ; copier seulement le fichier principal pendant des
écritures ne suffit pas toujours.

La suite de #18 est le choix du fournisseur et du budget, puis le proxy HTTPS,
l'injection des secrets, le déploiement de l'image validée et les mesures à distance.
Le détecteur entraîné et l'OCR automatique de l'écran restent des travaux distincts.
