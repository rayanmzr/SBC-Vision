# Contrôleur local — deuxième lot SBV-016

Ce prototype relie une image, un JSON de perception, un clic et une nouvelle image.
Il est limité à une page de laboratoire et à une carte fictive. Ce n'est pas encore
le contrôleur de la Web App EA ni le démonstrateur de secours de #17.

Le détecteur de Saber et l'OCR restent à raccorder dans l'API Python. Ici, un petit
détecteur de couleurs déterministe permet de tester le contrôleur sans inventer une
réponse réseau ou prétendre mesurer la reconnaissance des joueurs. Le solveur n'est
pas appelé et ne reçoit aucune image.

## Essayer sans compte ni serveur Python

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm run dev
```

Ouvrir <http://127.0.0.1:5173/controller-lab.html>. Le parcours a deux étapes :
sélectionner une carte fictive, puis la placer. L'état final est matérialisé par un
repère vert. Les rectangles sont pleins pour que la détection reste reproductible.

1. Choisir **Observation**, puis **Observer le laboratoire**. Le canevas est exporté
   en PNG et décodé ; le contrôleur reçoit le JSON calculé à partir de ses pixels.
   La carte reste disponible et le journal indique zéro clic.
2. Choisir **Simulation sans clic**, puis **Simuler la prochaine action**. Le journal
   montre le point du prochain clic et l'état attendu. La page ne change pas. Cette
   simulation n'invente pas les écrans futurs et ne prouve pas une réussite.
3. Choisir **Exécution locale**, garder un budget de **2**, puis **Exécuter sur le
   laboratoire**. Les deux clics sont envoyés. Le succès n'est affiché qu'après
   reconnaissance de chaque transition et de l'état final dans de nouvelles images.
4. Réinitialiser la page et mettre le budget à **1**. Le contrôleur sélectionne la
   carte, vérifie ce résultat, puis s'arrête : **Budget atteint · Parcours incomplet**.
5. Réinitialiser et choisir **Le clic ne change rien**. Un seul clic est envoyé ;
   le contrôleur ne constate pas le changement attendu et s'arrête en divergence.
6. Choisir **L'écran suivant est inattendu**. La page passe directement à l'état final
   après le premier clic, mais le contrôleur attendait une sélection : il refuse aussi
   ce parcours au lieu d'annoncer un succès.
7. **Interrompre** ou **Échap** arrête l'attente. Le journal distingue l'interruption
   d'une réussite. Un clic déjà envoyé peut avoir modifié la page ; il ne peut pas être
   rappelé. Les tests couvrent les réponses tardives et les captures bloquées.

La surface de test doit rester visible. Si la page défile, si le canevas est masqué ou
si sa position change pendant le parcours, l'actionneur refuse le clic. Sur une petite
fenêtre, le défilement vers les commandes peut masquer la scène : agrandir la fenêtre
pour l'essai d'exécution. L'observation et la simulation restent sans effet sur la page.

## Ce que fait chaque brique

| Fichier | Responsabilité |
| --- | --- |
| `frontend/src/ControllerLab.tsx` | Dessine les états fictifs et traite les clics de la page de test |
| `frontend/src/lib/lab-vision.ts` | Cherche les rectangles colorés dans les pixels et produit le contrat de perception |
| `frontend/src/lib/controller.ts` | Choisit une action depuis le JSON, borne le parcours et vérifie les transitions |
| `frontend/src/lib/lab-adapter.ts` | Capture/PNG et clic par coordonnées, via canevas ou API Chrome |
| `frontend/src/ControllerPanel.tsx` | Modes, budget, interruption, résultat et journal JSON |

La politique est volontairement une machine à états :

```text
lab-select --clic--> lab-place --clic--> lab-done
```

Une couleur connue associe un état à une boîte détectée. Les dimensions et positions
de la boîte viennent des pixels ; le contrôleur ne reprend pas les coordonnées de
dessin de la scène et ne lit pas le statut React pour décider. La confiance `1` est
un indicateur déterministe du protocole de couleurs, pas une probabilité calibrée.
Plusieurs états, un repère masqué ou une forme incohérente provoquent un refus.

Le centre de la boîte est converti selon le [repère image/viewport](TAB_CAPTURE.md).
Avant chaque clic, une seconde capture doit confirmer la cible, sa géométrie et ses
éléments. Après le clic, une nouvelle capture doit contenir exactement l'état attendu.
Chaque observation porte un identifiant neuf et les journaux conservent son JSON.
Ils ne contiennent pas le binaire des images et ne sont pas persistés.

Le budget est un entier de 1 à 5 tentatives de clic. Le journal distingue les tentatives
des envois confirmés : une interruption pendant un envoi ne permet pas d'affirmer si le
clic a eu lieu. Une opération ne peut attendre plus de huit
secondes. Une observation de plus de cinq secondes ou un identifiant de capture déjà
utilisé est refusé. Il n'y a aucun nouvel
essai automatique après un clic refusé, une divergence ou une erreur. Les actions de
soumission, d'achat et d'échange n'existent pas dans cette politique.

## Adaptateur Chrome : procédure encore à valider manuellement

Le même contrôleur est disponible dans **Contrôleur local** du popup de l'extension.
Dans ce mode, les pixels viennent de `captureVisibleTab`, avec les contrôles du premier
lot. Les rectangles sont détectés dans la capture de l'onglet entier, pas dans un
export isolé du canevas.

1. Construire avec `pnpm run check`, puis recharger `frontend/dist` dans Chrome.
2. Ouvrir la page de laboratoire locale, puis le popup SBC Vision depuis son icône.
3. Choisir **Contrôleur local**. Tester d'abord observation et simulation, puis
   l'exécution à deux clics sur les seules cartes fictives.
4. Vérifier les coordonnées à 100 % puis 125 % de zoom et, si disponible, sur Retina.
5. Répéter les scénarios sans changement et écran inattendu ; aucun second clic ne doit
   partir après divergence. Vérifier aussi le budget d'un clic et l'interruption.

L'actionneur accepte uniquement `http://localhost` ou `http://127.0.0.1`, ports 5173/4173,
chemin exact `/controller-lab.html`, sans paramètres, fragment ou identifiants.
L'injection vise le `documentId` observé et expire après une seconde. Elle contrôle
encore URL, dimensions, défilement, échelle et visibilité au moment d'envoyer l'événement.
Le point doit désigner le canevas marqué du laboratoire ; aucune recherche de joueur
ou lecture de texte DOM ne remplace la vision.

Le clic est un `MouseEvent` synthétique (`isTrusted: false`), accepté par notre page de
test. Cela ne valide ni un clic système ni sa compatibilité avec EA. Voir les références
[scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting) et
[isTrusted](https://developer.mozilla.org/en-US/docs/Web/API/Event/isTrusted).

## Validation et suite

Les tests vérifient le contrôleur, la localisation dans les pixels, l'actionneur injecté,
les URL autorisées, l'interruption, les délais et l'interface avec des doublures Chrome.
Le build produit aussi `dist/controller-lab.html` pour `pnpm run preview` sur le port 4173.
L'accès au navigateur local étant indisponible pendant ce lot, le parcours complet dans
un navigateur et la capture native du popup n'ont pas été observés ici.

L'issue #16 reste ouverte jusqu'à cette validation native. Il reste ensuite à brancher
les observations de l'API, les règles de navigation et les cibles issues de l'inventaire
et du solveur. Le laboratoire ne fournit pas une reconnaissance ou une autorisation
d'action sur le compte réel. Les capacités HTTP `controller` et `live_actions_enabled`
restent fausses : le prototype s'exécute uniquement côté navigateur, dans ce laboratoire.
