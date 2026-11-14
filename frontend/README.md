# Extension Chrome SBC Vision — SBV-015

Responsable : Samy Allali. Cette version permet de capturer l'onglet actif depuis le popup,
de joindre l'API, d'envoyer manuellement une image et d'examiner son JSON.
L'espace **Composition SBC** charge l'inventaire de
l'API, enregistre les protections et lance le véritable solveur de Rayan. Il ouvre aussi
des rapports JSON locaux. Le scan et le placement dans le navigateur restent à raccorder
avec #16 : **le parcours de l'issue #15 n'est pas encore terminé**.

L'espace **Contrôleur local** prépare le deuxième lot de #16. Il propose observation,
simulation et clics vérifiés sur une page locale dédiée : [guide du laboratoire](../docs/LOCAL_CONTROLLER.md).
Cette page se teste aussi sans API sur <http://127.0.0.1:5173/controller-lab.html>.
Son sélecteur **Analyse des images** permet aussi le parcours par la vraie API Python,
activée explicitement avec `SBC_PERCEPTION_MODE=lab-colors` : [guide HTTP du laboratoire](../docs/LAB_PERCEPTION_API.md).
Ce mode reste limité aux repères colorés du test ; il n'active pas la reconnaissance EA.

## Comprendre ce premier lot

React construit les champs, boutons et résultats. TypeScript vérifie les types pendant
le développement. Vite sert l'aperçu et produit les fichiers installables. Manifest V3
décrit l'extension à Chrome. Le modèle de vision restera dans l'API Python.

Le parcours est : image choisie → requête HTTP → API Python → JSON → affichage.

Pour un serveur partagé, saisir **Clé API (si demandée)** avant de vérifier la
connexion. La clé reste uniquement en mémoire pour l'adresse exacte de l'API ;
changer de serveur ou fermer la page l'efface. La modifier invalide aussi la connexion
et l'inventaire affiché. Les routes métier la reçoivent dans l'en-tête `Authorization`.
Voir le [guide Docker et partage](../docs/DEPLOYMENT.md).

Le [kit graphique A1 — Stade](../docs/design/ASSETS_A1.md) prépare le visuel retenu :
assets séparés, polices locales et aperçu de onze cartes sur
<http://127.0.0.1:5173/design-assets.html>. Cet aperçu utilise uniquement des données
fictives et conserve le point d'entrée du popup fonctionnel.
Sans pipeline configuré, un PNG valide provoque une erreur `503 perception_unavailable`.
Ce retour vérifie le transport de la capture et la gestion des erreurs, pas la vision.

## Lancer l'aperçu local

Prérequis : Node.js **24.15 ou plus récent dans la série 24**, pnpm **11.25.0**, et
l'environnement Python du README principal. Les paquets sont verrouillés dans
`pnpm-lock.yaml`.

Depuis la racine du dépôt, dans un premier terminal :

```bash
source .venv/bin/activate
uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8000
```

Dans un second terminal :

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

Ouvrir <http://127.0.0.1:5173>. Cet aperçu navigateur utilise l'API
`http://127.0.0.1:8000` via le proxy Vite `/__api`, sans modifier la politique CORS du
serveur. Une autre adresse API se teste dans l'extension installée.

## Charger l'extension Chrome

```bash
cd frontend
pnpm run build
```

1. Ouvrir `chrome://extensions` dans Chrome et activer le mode développeur.
2. Choisir **Charger l'extension non empaquetée**, puis le dossier `frontend/dist`.
3. Ouvrir SBC Vision depuis le menu des extensions.
4. Le popup fait 440 px de large. **Ouvrir dans un onglet** offre davantage de place.

Après modification, reconstruire puis recharger l'extension. La vérification de l'aperçu
ne remplace pas celle des autorisations dans Chrome installé. Aucun compte EA n'est
nécessaire pour ce premier lot.

## Rôle des fichiers

| Fichier                                 | Rôle                                                        |
| --------------------------------------- | ----------------------------------------------------------- |
| `public/manifest.json`                  | Déclaration MV3, popup et permissions                       |
| `src/main.tsx`                          | Démarrage de React et taille propre au popup                |
| `src/App.tsx`                           | Interface et déroulement des opérations                     |
| `src/SbcWorkspace.tsx`                  | Lecture des propositions et états du solveur                |
| `src/SbcApiPanel.tsx`                   | Inventaire serveur, protections et calcul                   |
| `src/lib/sbc-api.ts`                    | Contrats et appels JSON du moteur SBC                       |
| `src/lib/sbc-report.ts`                 | Validation des rapports locaux et présentation des coûts    |
| `src/lib/platform.ts`                   | Adresse, stockage et permissions Chrome                     |
| `src/lib/tab-capture.ts`                | Capture, contexte de l'onglet et conversion des coordonnées |
| `src/lib/api.ts`                        | HTTP, délais, image et validation des réponses              |
| `scripts/generate-contract.mjs`         | Compilation du schéma Python partagé                        |
| `src/generated/perception-validator.js` | Validateur généré, à ne pas modifier à la main              |
| `src/style.css`, `src/tokens.css`       | Mise en page et couleurs                                    |
| `src/*.test.ts*`, `src/lib/api.test.ts` | Tests de l'interface et du transport                        |

Dans React, `connection` décrit le serveur, `selection` décrit le fichier et `result`
associe un JSON à son image et sa source. Modifier l'adresse ou le fichier retire
l'ancien résultat. Chaque analyse possède un identifiant neuf ; l'identifiant et les
dimensions de la réponse doivent correspondre à la demande.

## Vérifier le parcours

1. Avant de lancer Python, **Vérifier la connexion** doit afficher un échec.
2. Après lancement, **Serveur joignable** apparaît. **Vision à raccorder** indique que
   le serveur n'annonce pas de modèle prêt : ces états restent distincts.
3. Choisir `data/fixtures/perception.synthetic.png` depuis la racine du dépôt.
4. **Envoyer à l'API** produit actuellement `503`, puisque le pipeline reste à brancher.
5. **Voir un exemple synthétique** affiche deux éléments et leurs rectangles avec le
   bandeau **Données fictives**. L'image et le JSON sont préparés à la main ; ce bouton
   n'appelle pas le serveur et n'effectue aucune inférence.
6. Déplier le JSON pour retrouver identifiants, types, textes, boîtes, scores et actions.

Dans Analyse d'image et Composition SBC, les actions du JSON sont seulement décrites.
Les clics synthétiques sont réservés à **Contrôleur local** et à sa page de test.
Aucun achat ou soumission n'est exécuté. La capture d'onglet est le premier lot de #16 : le [guide de capture](../docs/TAB_CAPTURE.md)
explique le popup, les permissions et la vérification manuelle dans Chrome.

## Stockage et permissions

`storage` mémorise seulement l'adresse API. Images et résultats restent en mémoire.
Fermer le popup ou l'onglet perd donc la sélection. L'envoi se produit uniquement après
le clic sur **Envoyer à l'API**, avec `credentials: omit` et redirections refusées.

Les accès HTTP requis se limitent à `localhost` et `127.0.0.1`. Pour une API HTTPS,
l'extension demande l'accès au seul hôte choisi au moment de vérifier la connexion.
Les permissions Chrome couvrent le schéma et l'hôte, pas seulement un port ou un chemin.
Le motif optionnel `https://*/*` permet de choisir un futur fournisseur cloud ; aucun
accès global n'est accordé automatiquement.

`activeTab` donne un accès temporaire à la page depuis laquelle l'utilisateur invoque
l'extension. `scripting` sert à relever les dimensions et le défilement du cadre principal,
sans lire le contenu des cartes ou les textes de l'interface. Ces mesures encadrent
la capture ; elles ne remplacent pas la vision. Le laboratoire utilise aussi `scripting`
pour envoyer un clic au canevas local à partir des coordonnées observées, dans le
document précis de la capture. Aucune nouvelle permission et aucun script de contenu permanent.

Aucune permission `tabs`, `debugger` ou `cookies` n'est déclarée. Ouvrir la page propre
à l'extension dans un onglet ne lit pas les autres onglets ; la capture s'effectue depuis
le popup sur la page cible. L'aperçu Vite affiche ce bouton désactivé.

## Contrôles et limites

```bash
pnpm run check
```

Cette commande vérifie le schéma partagé, le formatage, les types, les tests et le build.
Depuis la racine : `make extension-check`. `make check` conserve les contrôles Python.
La CI ajoute un job pour l'extension.

Ajv compile le schéma au développement. Le bundle contient le validateur obtenu, sans
`eval` ou `new Function` dans Chrome. Après une évolution du contrat Python, exécuter
`pnpm run schema`. Des contrôles supplémentaires rejettent boîtes hors image, identifiants
dupliqués et réponses associées à une autre capture.

Limites : PNG/JPEG, 5 Mio, 8 192 px par côté, 20 millions de pixels. Les requêtes de
connexion attendent au plus 5 secondes chacune, l'analyse 30 secondes côté client.
**Annuler** abandonne l'attente et empêche d'afficher une réponse tardive ; cela ne garantit
pas l'arrêt immédiat d'un calcul déjà commencé sur le serveur.

## Espace Composition SBC

Cet espace utilise le moteur intégré depuis la branche de Rayan, en conservant son
historique. Cette intégration sur nos branches ne fusionne pas sa PR #23 dans `main`.
Trois sources sont proposées : **Depuis l'API**, **Rapport local** et **Exemple fictif**.

### Inventaire et calcul par l'API

Activer d'abord les routes SBC selon le [guide API SBC](../docs/SBC_API.md). Un serveur
lancé sans configuration reste joignable mais renvoie `503 sbc_unavailable` pour ces routes.
Pour tester sans compte EA, utiliser la base de démonstration du guide : cartes fictives,
véritable calcul et protections réellement enregistrées dans une base distincte.

1. Ouvrir **Composition SBC → Depuis l'API → Charger l'inventaire**. La connexion et,
   dans Chrome, les permissions de l'hôte sont vérifiées si nécessaire.
2. Les lignes représentent tous les exemplaires possédés. `club:demo-001` et
   `club:demo-002` sont deux copies de la même version : leur protection est indépendante.
3. Cliquer une protection envoie `PUT /api/v1/sbc/protections`. La case change uniquement
   après confirmation du serveur. Toute ancienne proposition est retirée dès la demande.
4. Régler le **budget d'achat**, puis **Calculer une proposition**. Le navigateur envoie
   `POST /api/v1/sbc/solve` avec un JSON contenant seulement `expected_revision` et `budget`.
   Le solveur reçoit les cartes et conditions structurées depuis la base ; aucune image.
5. Lire la composition, les conditions, les achats et les coûts du rapport retourné.
   Avec la démo initiale : 1 300 d'achats + 800 sacrifiés = 2 100 crédits au total.
6. Protéger `club:demo-002`, puis recalculer avec 2 000 de budget : aucune solution sur
   ce pool. Porter le budget à 3 000 : une équipe à 2 100, entièrement en achats, est proposée.
7. Recharger la page puis l'inventaire pour constater que la protection est conservée.
   La décocher permet de retrouver le scénario initial.

La **révision** est une empreinte des données du serveur. Elle évite de calculer ou
modifier une protection sur un état dépassé. Si les données changent (`409`), l'interface
retire l'ancien résultat et exige de recharger l'inventaire. Changer le budget, la source
ou l'adresse retire aussi la proposition concernée ; une réponse tardive est ignorée.

Le plafond par carte provient des conditions configurées sur le serveur et est affiché.
L'interface n'édite pas encore ces conditions ni ce plafond. Elle affiche au plus 50
exemplaires à la fois, avec un bouton pour en afficher davantage.

### Rapports locaux et exemples

Choisir **Rapport local → Ouvrir un rapport JSON**. Le fichier est lu
dans le navigateur, sans être envoyé au serveur ni enregistré dans le stockage Chrome.
Taille maximale : 2 Mio. Un fichier invalide retire l'ancien résultat et affiche une erreur.

Sur la branche du moteur, `python -m sbc_vision.sbc_engine solve --demo` écrit normalement
`data/processed/solution.json`. Choisir ce rapport dans l'extension.
Un rapport OCR avec `ready: false` et une liste `issues` affiche une lecture à confirmer,
sans réutiliser une éventuelle ancienne proposition.

L'interface distingue :

- les candidats retenus du rapport et l'inventaire complet chargé depuis l'API ;
- un exemplaire du club et une version proposée à l'achat ;
- les achats, la valeur sacrifiée et leur somme économique ;
- un prix inconnu et un prix nul ;
- une solution faisable, optimale sur le pool connu, impossible sur ce pool ou inconnue ;
- une vérification annoncée dans un fichier et une vérification actuelle par EA.

Le schéma `contracts/sbc-report.schema.json` reprend `Challenge`, `SolverResult` et
`Candidate` du commit `e244b8ecfa6bdbd8ad4a64f7a50929aa3c2ca75d` de Rayan. Une enveloppe
de lecture décrit les champs de `run_solver` utilisés dans l'interface. Les métadonnées
supplémentaires restent autorisées, mais ne sont pas exécutées. Le moteur Python n'est
pas copié dans l'extension. Le validateur est compilé, comme celui de perception.

Les contrôles frontend refusent notamment les cartes affectées absentes, protégées ou
sans prix, les emplacements dupliqués, les quantités dépassées, les postes incompatibles
et les coûts incohérents. Ils protègent l'affichage ; ils ne remplacent ni le vérificateur
Python, ni les règles complètes, ni la relecture de la Web App.

Le scénario fictif est préparé à la main depuis les fixtures de Rayan : **aucun solveur
n'est exécuté dans le navigateur**. Il comprend des cartes supplémentaires pour montrer
une protection et un prix inconnu. Une case de protection dans cet exemple ne modifie
que sa copie en mémoire ; tout changement retire la composition et les coûts.
Recharger l'exemple réinitialise ces choix. Les cartes du rapport restent en lecture seule
quand il est importé ou reçu de l'API. Pour modifier la base, utiliser les cases de
l'inventaire **Depuis l'API**.

La fixture `data/fixtures/workspace-api.synthetic.json` enregistre de vraies réponses de
l'adaptateur et de CP-SAT sur les cartes fictives. Dates et durée sont normalisées pour
les tests ; ce fichier ne constitue pas une mesure de performance. Les tests vérifient
aussi les échecs d'enregistrement, les révisions incompatibles et les réponses tardives.

À terminer pour #15 : alimentation par le scan réel, relecture des conditions et
intégration du parcours avec le contrôleur #16. L'interface n'effectue encore aucun
clic, achat, placement ou soumission dans la Web App.

Références : [réseau des extensions](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests),
[permissions optionnelles](https://developer.chrome.com/docs/extensions/reference/api/permissions).
