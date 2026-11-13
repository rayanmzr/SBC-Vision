# Extension Chrome SBC Vision — premier lot de SBV-015

Responsable : Samy Allali. Cette version permet de joindre l'API, d'envoyer manuellement
une image et d'examiner son JSON. L'inventaire, les protections, le solveur et les actions
restent à raccorder : **l'issue #15 n'est pas terminée**.

## Comprendre ce premier lot

React construit les champs, boutons et résultats. TypeScript vérifie les types pendant
le développement. Vite sert l'aperçu et produit les fichiers installables. Manifest V3
décrit l'extension à Chrome. Le modèle de vision restera dans l'API Python.

Le parcours est : image choisie → requête HTTP → API Python → JSON → affichage.
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

| Fichier                                 | Rôle                                           |
| --------------------------------------- | ---------------------------------------------- |
| `public/manifest.json`                  | Déclaration MV3, popup et permissions          |
| `src/main.tsx`                          | Démarrage de React et taille propre au popup   |
| `src/App.tsx`                           | Interface et déroulement des opérations        |
| `src/lib/platform.ts`                   | Adresse, stockage et permissions Chrome        |
| `src/lib/api.ts`                        | HTTP, délais, image et validation des réponses |
| `scripts/generate-contract.mjs`         | Compilation du schéma Python partagé           |
| `src/generated/perception-validator.js` | Validateur généré, à ne pas modifier à la main |
| `src/style.css`, `src/tokens.css`       | Mise en page et couleurs                       |
| `src/*.test.ts*`, `src/lib/api.test.ts` | Tests de l'interface et du transport           |

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

Les actions du JSON sont seulement décrites. Aucun clic EA, achat ou soumission n'est
exécuté. La capture d'onglet fera partie de #16.

## Stockage et permissions

`storage` mémorise seulement l'adresse API. Images et résultats restent en mémoire.
Fermer le popup ou l'onglet perd donc la sélection. L'envoi se produit uniquement après
le clic sur **Envoyer à l'API**, avec `credentials: omit` et redirections refusées.

Les accès HTTP requis se limitent à `localhost` et `127.0.0.1`. Pour une API HTTPS,
l'extension demande l'accès au seul hôte choisi au moment de vérifier la connexion.
Les permissions Chrome couvrent le schéma et l'hôte, pas seulement un port ou un chemin.
Le motif optionnel `https://*/*` permet de choisir un futur fournisseur cloud ; aucun
accès global n'est accordé automatiquement.

Aucune permission `tabs`, `activeTab`, `scripting`, `debugger` ou `cookies` n'est déclarée.
Ouvrir la page propre à l'extension dans un onglet ne lit pas les autres onglets.

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

À terminer pour #15 : inventaire, protections, conditions, achats, coûts et états du
solveur, en consommant les véritables contrats de Rayan.

Références : [réseau des extensions](https://developer.chrome.com/docs/extensions/develop/concepts/network-requests),
[permissions optionnelles](https://developer.chrome.com/docs/extensions/reference/api/permissions).
