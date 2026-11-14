# Kit graphique A1 — Stade (issue #15)

Direction retenue : **A1, la colonne de gauche** de
[la planche de référence](references/piste-a-board.png). Le terrain vert et les cartes
dorées occupent le centre ; le détail du joueur, les coûts et l'action viennent ensuite.
Les accents vert citron, les onglets inclinés et les textures au crayon reprennent le croquis.

## Voir le résultat assemblé

Depuis `frontend/` :

```bash
pnpm dev
```

- Kit et catalogue : <http://127.0.0.1:5173/design-assets.html>
- Popup isolé : <http://127.0.0.1:5173/design-assets.html?view=popup>

Le sélecteur du catalogue propose 440 ou 360 pixels. Les onze cartes sont sélectionnables :
le nom, le poste et l'origine du joueur s'affichent sous le terrain. **Voir les achats**
déplie les deux achats fictifs. Les valeurs sont calculées à partir des données de cet
aperçu : 4 200 d'achats + 6 800 de valeur du club = 11 000 au total.
Ce scénario graphique ne contacte aucune API et n'exécute pas le solveur.

La page est incluse dans le build de l'extension. Le popup fonctionnel conserve son
point d'entrée `index.html?view=popup` pendant la préparation du kit.

## Les pièces du rendu

Tous les assets consommés sont locaux, dans `frontend/src/design-a1/assets/`.

| Fichier | Rôle | Format |
| --- | --- | --- |
| `charcoal-surface.png` | Texture sombre du cadre et des panneaux | 1 254 × 1 254, opaque |
| `pitch-grass.png` | Matière du terrain, éclaircie au rendu pour retrouver A1 | 1 122 × 1 402, opaque |
| `card-gold.png` | Fond doré vierge, sans nom, note ni portrait | 1 093 × 1 439, alpha transparent |
| `card-mask.svg` | Contour net et forme commune à la carte et à sa sélection | Vectoriel |
| `player-silhouette.svg` | Portrait générique de remplacement | Vectoriel |
| `pitch-lines.svg` | Lignes blanches en perspective | Vectoriel |
| `brand-mark.svg` | Marque originale : doubles diagonales et ballon | Vectoriel |
| `fonts/BarlowCondensed-SemiBold.ttf` | Libellés et texte droit | Police locale |
| `fonts/Barlow-ExtraBoldItalic.ttf` | Titres, notes, chiffres et marque | Police locale |

Les trois matières ont été produites avec l'outil intégré `image_gen`, à partir de la
planche comme référence de style. Les requêtes exactes retenues sont conservées dans
[generated-assets.json](prompts/generated-assets.json). Un essai de nettoyage de carte
non retenu n'est pas intégré au dépôt. Les premières requêtes de matières mentionnent
A3 ; ces matières communes ont été conservées, puis l'assemblage a été réalisé pour
**A1**, conformément à la précision de l'utilisateur.

Les SVG et les règles CSS sont des sources modifiables. Les icônes de sac, d'agrandissement,
de capture et de flèche sont disponibles dans `StadiumIcon`. Aucun logo officiel EA ou
FUTBIN ni portrait de joueur réel n'est intégré.

Les polices viennent du dépôt officiel [Google Fonts — Barlow](https://github.com/google/fonts/tree/main/ofl/barlow)
et [Barlow Condensed](https://github.com/google/fonts/tree/main/ofl/barlowcondensed).
Le commit exact et les chemins sont inscrits dans `fonts/SOURCE.json` ; les licences
sont jointes dans `fonts/OFL.txt` et `fonts/OFL-Barlow.txt`.

`assets/manifest.json` donne les dimensions, tailles et empreintes SHA-256 des fichiers.
Les PNG de travail totalisent environ 6,7 Mo : ils gardent la matière du dessin en haute
définition. La compression de livraison pourra se faire une fois le rendu validé.
La carte possède un vrai canal alpha ; le masque SVG stabilise son contour à petite taille.

## Réutiliser le kit

Importer `design-a1/StadiumKit.tsx`, puis placer les composants sous un conteneur
`.stadium-kit`. Le style est limité à cette classe : il n'écrase pas les autres écrans.

- `StadiumBrand` assemble le symbole et le nom en texte.
- `StadiumCard` affiche une carte et sa sélection, avec un nom accessible au clavier.
- `StadiumPitch` reçoit les joueurs, leurs coordonnées en pourcentage et le libellé de
  formation. Il affiche les données reçues sans décider des placements du solveur.
- `stadium-kit.css` fournit les onglets, panneaux, coûts, bouton principal et états visuels.

Les noms, notes, postes, origines et montants restent des textes HTML. La texture ne
contient aucune information métier. Les lignes du terrain restent vectorielles et la
carte utilise le même masque pour son fond et son contour de sélection. Cela permet de
reproduire le style sans figer toute l'interface dans une capture d'écran.

Palette principale : anthracite `#141b16`, vert citron `#d0ff22`, texte `#f6f5ed` et
or `#f4da87`. Les principales valeurs sont centralisées dans les variables
`--stadium-*`. Les polices sont servies avec le build : aucune requête Google Fonts
n'est nécessaire à l'ouverture de l'extension.

Le croquis sert de référence de direction ; ses lettres dessinées à la main sont
reconstruites avec les polices locales. La validation visuelle porte sur le résultat
réel assemblé, puis sur sa déclinaison dans les écrans fonctionnels.
