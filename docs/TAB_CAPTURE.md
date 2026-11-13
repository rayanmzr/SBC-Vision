# Capture d'onglet — premier lot SBV-016

Cette branche ajoute la capture manuelle de l'onglet actif à l'extension Chrome.
Cette fonction d'observation ne réalise aucun clic. Le [deuxième lot du contrôleur](LOCAL_CONTROLLER.md)
ajoute observation, simulation et exécution avec vérification sur une page locale distincte.
L'issue [#16](https://github.com/rayanmzr/SBC-Vision/issues/16) reste ouverte pour la
validation native dans Chrome et le raccordement aux observations de l'API.

## Comprendre les étapes

1. L'utilisateur ouvre le popup SBC Vision depuis l'icône de l'extension sur une page
   HTTP ou HTTPS. Ce geste donne l'accès temporaire `activeTab` à cette page.
2. **Capturer l'onglet actif** relève l'identifiant de l'onglet, du document et la
   géométrie de la zone visible. Un petit script lit seulement URL, dimensions,
   défilement, échelles et visibilité. Aucun texte, joueur, sélecteur ou inventaire
   n'est lu dans le DOM.
3. `chrome.tabs.captureVisibleTab` produit le PNG de la zone visible de cet onglet.
   Ce n'est ni une capture du bureau entier ni une capture de la page entière.
4. L'extension relève à nouveau le contexte. Si le document, l'onglet, l'URL,
   le défilement, la taille ou l'échelle diffèrent, elle rejette cette capture.
5. Le PNG est décodé et contrôlé avec les mêmes limites que les images importées :
   5 Mio, 8 192 pixels par côté, 20 millions de pixels. L'aperçu affiche l'origine
   de la page et la différence entre pixels de capture et pixels CSS.
6. L'image reste en mémoire. Seul **Envoyer à l'API** transmet son binaire à la
   perception, avec un identifiant de requête neuf. Ni l'URL de la page ni les
   métadonnées Chrome ne sont jointes à cet envoi.
7. Le JSON retourné est validé et dessiné sur cette même image. Si elle provient
   d'un onglet, le centre de chaque boîte est aussi affiché en pixels CSS.
   C'est une indication d'observation, sans exécution d'action.

L'API de perception conserve son comportement réel : `503 perception_unavailable`
tant que le détecteur/OCR n'est pas raccordé. La capture ne crée ni inventaire,
ni lecture OCR, ni proposition de solveur. Le solveur reste alimenté par des données
structurées, pas par des images.

## Pourquoi deux repères ?

Une capture de 2 000 × 1 200 pixels peut représenter une zone de 1 000 × 600 pixels
CSS, notamment sur un écran Retina. Utiliser directement les coordonnées du PNG
pour un clic déplacerait la cible.

Pour une boîte `(x, y, largeur, hauteur)` dans l'image :

```text
x_css = (x + largeur / 2) × largeur_viewport / largeur_image
y_css = (y + hauteur / 2) × hauteur_viewport / hauteur_image
```

Exemple : `(200, 100, 100, 80)` dans l'image de 2 000 × 1 200 donne le centre
`(125, 70)` dans la page. On n'ajoute pas le défilement : le point désigne le
viewport visible, pas le document entier. Le facteur est mesuré depuis l'image
réelle ; `devicePixelRatio` seul n'est pas utilisé pour convertir les coordonnées.
Un zoom tactile qui décale le viewport est refusé dans ce premier prototype.

Le contexte ne garantit pas que le contenu est immobile : une animation ou une
modification du DOM peut se produire sans changer la géométrie. Un futur clic devra
donc revalider une observation récente puis contrôler visuellement son résultat.
La capture ne constitue jamais à elle seule une autorisation de cliquer.

## Permissions et mémoire

- `activeTab` donne l'accès temporaire après invocation de l'extension.
- `scripting` permet la lecture des seules mesures du cadre principal.
- `storage` conserve uniquement l'adresse de l'API.
- Aucun accès global `<all_urls>`, permission `tabs`, `debugger` ou lecture de cookies.
- Pas de script de contenu permanent ni de capture automatique en arrière-plan.

Deux demandes de capture sont espacées d'au moins 600 ms et les appels concurrents
sont refusés. Chrome borne cette API à deux appels par seconde.
**Annuler** retire l'attente de l'interface ; une réponse tardive est ignorée et
son aperçu libéré. Cela ne peut pas annuler une capture native déjà commencée.
Fermer le popup perd l'image ; elle n'est pas sauvegardée sur le disque.

## Vérification manuelle dans Chrome

La suite automatisée utilise des doublures des API Chrome. L'aperçu web valide
l'affichage et l'import d'images ; il ne dispose pas de `chrome.tabs` et ne peut
pas valider une capture native. Le scénario suivant reste à exécuter dans Chrome
installé, notamment après toute modification des permissions :

1. Construire avec `cd frontend && pnpm run check`, puis recharger le dossier
   `frontend/dist` depuis `chrome://extensions`.
2. Ouvrir une page de test locale, par exemple l'aperçu sur `http://127.0.0.1:5173`.
3. Cliquer l'icône SBC Vision, puis **Capturer l'onglet actif**. L'aperçu doit
   montrer la page sous le popup, et indiquer l'origine et les dimensions CSS.
4. Vérifier qu'aucune requête de perception ne part avant **Envoyer à l'API**.
   Le serveur sans détecteur doit ensuite répondre `503`, avec le PNG toujours visible.
5. Essayer un zoom navigateur de 125 % et un écran Retina. L'aperçu doit garder les
   bonnes proportions ; un désaccord de dimensions doit provoquer un refus.
6. Sur `chrome://extensions`, la capture est refusée par notre application.
7. Fermer le popup, puis le rouvrir : l'ancienne capture ne doit pas être restaurée.

**Ouvrir dans un onglet** sert à examiner l'interface sur une grande surface.
Ce n'est pas un sélecteur d'autres onglets : revenir au popup sur la page cible
pour obtenir la permission et effectuer une nouvelle capture.

Références officielles : [activeTab](https://developer.chrome.com/docs/extensions/develop/concepts/activeTab),
[captureVisibleTab](https://developer.chrome.com/docs/extensions/reference/api/tabs#method-captureVisibleTab),
[scripting](https://developer.chrome.com/docs/extensions/reference/api/scripting).
