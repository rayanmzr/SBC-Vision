# Contrôleur local et raccordement HTTP — SBV-016

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

## Faire passer les images par Python

Le sélecteur **Analyse des images** distingue désormais deux chemins. **Dans le
navigateur** reste le mode initial : aucun envoi réseau. **API Python · Couleurs de
test** transmet chaque nouvelle image à la route de perception existante, puis le
contrôleur consomme exclusivement sa réponse JSON. Aucun échec ne déclenche de retour
automatique au traitement navigateur.

Dans un terminal depuis la racine du dépôt :

```bash
source .venv/bin/activate
SBC_PERCEPTION_MODE=lab-colors \
uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8000
```

1. Garder Vite lancé et ouvrir la page de laboratoire.
2. Choisir **Analyse des images → API Python · Couleurs de test**. Ce choix seul
   n'envoie rien. Dans le popup Chrome, l'adresse est celle configurée dans Réglages ; les
   permissions et la connexion sont vérifiées au lancement si nécessaire.
3. Lancer observation, simulation ou exécution. Pour deux clics vérifiés, cinq images
   passent par l'API : la première, deux confirmations avant clic et deux vérifications
   après clic. Chaque requête contient le PNG binaire et un identifiant neuf.
4. Ouvrir **Voir le journal JSON**. Les observations enregistrées portent
   `model_name: lab-color-api-v1`, le modèle de test Python, au lieu de
   `local-color-baseline-v1`, le traitement navigateur.
5. Refaire les scénarios de budget et de divergence : ils emploient la même politique
   de contrôle, quelle que soit la source choisie.

Sans activation du pipeline, le serveur renvoie `503` et le contrôleur s'arrête sans
cliquer. Un repère absent ou ambigu produit `422`. Un autre nom de pipeline, une autre
capture ou des dimensions incompatibles sont refusés. Les erreurs ne sont jamais
converties en résultats fictifs réussis. Voir le [guide du pipeline HTTP](LAB_PERCEPTION_API.md).

Après la réponse HTTP, le contexte est à nouveau contrôlé. La date d'observation reste
celle de la capture : un long calcul ne rajeunit pas une image ancienne. Les limites
de huit secondes par opération et cinq secondes de fraîcheur continuent à s'appliquer.
L'API ne reçoit ni URL de page ni métadonnées Chrome, et aucune de ces images ne part
au solveur. Le détecteur de Saber et la politique du compte réel ne sont pas activés
par ce raccordement ; seules les trois couleurs de laboratoire sont prises en charge.

## Ce que fait chaque brique

| Fichier | Responsabilité |
| --- | --- |
| `frontend/src/ControllerLab.tsx` | Dessine les états fictifs et traite les clics de la page de test |
| `frontend/src/lib/lab-vision.ts` | Cherche les rectangles colorés dans les pixels et produit le contrat de perception |
| `frontend/src/lib/controller.ts` | Choisit une action depuis le JSON, borne le parcours et vérifie les transitions |
| `frontend/src/lib/lab-adapter.ts` | Capture/PNG et clic par coordonnées, via canevas ou API Chrome |
| `frontend/src/ControllerPanel.tsx` | Modes, budget, interruption, résultat et journal JSON |
| `frontend/src/ControllerWorkspace.tsx` | Choix de source et configuration du traitement des images |
| `frontend/src/lib/lab-api.ts` | Envoi PNG et contrôle de la provenance des réponses HTTP |
| `src/sbc_vision/perception/lab_colors.py` | Même protocole visuel exécuté dans le pipeline Python |

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
Chaque observation porte un identifiant neuf. Le journal conserve les JSON de l'image
initiale et des vérifications après action ; les confirmations avant clic sont aussi
contrôlées, sans dupliquer ces états inchangés dans le journal.
Ils ne contiennent pas le binaire des images et ne sont pas persistés.

Le budget est un entier de 1 à 5 tentatives de clic. Le journal distingue les tentatives
des envois confirmés : une interruption pendant un envoi ne permet pas d'affirmer si le
clic a eu lieu. Une opération ne peut attendre plus de huit
secondes. Une observation de plus de cinq secondes ou un identifiant de capture déjà
utilisé est refusé. Il n'y a aucun nouvel
essai automatique après un clic refusé, une divergence ou une erreur. Les actions de
soumission, d'achat et d'échange n'existent pas dans cette politique.

## Adaptateur Chrome : procédure encore à valider manuellement

Le même contrôleur est disponible dans **Réglages → Contrôleur local** du popup de l'extension.
Dans ce mode, les pixels viennent de `captureVisibleTab`, avec les contrôles du premier
lot. Les rectangles sont détectés dans la capture de l'onglet entier, pas dans un
export isolé du canevas.

1. Construire avec `pnpm run check`, puis recharger `frontend/dist` dans Chrome.
2. Ouvrir la page de laboratoire locale, puis le popup SBC Vision depuis son icône.
3. Choisir **Réglages → Contrôleur local**. Tester d'abord observation et simulation, puis
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

Le 14 novembre 2026, les parcours sur canevas ont été observés dans le navigateur,
avec le traitement navigateur puis la vraie API Python :

| Parcours | Résultat observé |
| --- | --- |
| Observation et simulation | Zéro clic, page inchangée |
| Exécution avec budget 2 | Deux clics et deux transitions vérifiées |
| Budget 1 | Un clic, sélection vérifiée, arrêt sans placement |
| Clic sans effet | Un clic, divergence, aucun second clic |
| Écran inattendu | Un clic, divergence malgré un état final visible |
| Serveur sans pipeline | Erreur de perception, zéro clic, aucun traitement de remplacement |
| Scène hors écran à 475 × 698 | Tentative refusée, zéro événement de clic confirmé |

L'exécution API a été validée à 1150 × 950, avec scène et commandes visibles ensemble.
Cela vérifie le parcours sur le canevas ; la capture native depuis le popup de Chrome
installé reste à valider, notamment le zoom et les permissions.

L'issue #16 reste ouverte jusqu'à cette validation native. Il reste ensuite à raccorder
le détecteur/OCR réels, les règles de navigation et les cibles issues de l'inventaire
et du solveur. Le laboratoire ne fournit pas une reconnaissance ou une autorisation
d'action sur le compte réel. Les capacités HTTP `controller` et `live_actions_enabled`
restent fausses : le prototype s'exécute uniquement côté navigateur, dans ce laboratoire.
