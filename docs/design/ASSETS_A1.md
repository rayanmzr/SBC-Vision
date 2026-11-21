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

La page est incluse dans le build de l'extension. Le popup fonctionnel
`index.html?view=popup` utilise maintenant cette direction sur **Analyser**, **Équipe**
et **Réglages**.

## Pages fonctionnelles

- **Analyser** : capture d'onglet ou choix d'un fichier, envoi manuel, affichage de l'image,
  des rectangles de détection, des éléments et du JSON. La connexion se configure dans
  Réglages. Une capture est conservée lorsqu'on change de page. Après le choix d'une
  image, l'aperçu passe au premier plan ; **Changer de capture** retrouve les sources
  et **Retirer** rétablit l'écran d'import. Les étapes Capture, Analyse et Lecture
  suivent l'état réel du parcours. Sélectionner un élément dans la liste ou son rectangle
  synchronise leur surbrillance, sans déclencher de clic dans l'onglet. Les coordonnées
  du repère et le JSON se déplient à la demande.
- **Équipe** : inventaire, protections, conditions, propositions et achats. Le terrain
  utilise les cartes et les postes du rapport validé, de 1 à 11 cartes. Les petits défis
  à trois cartes ont une présentation plus compacte. Pour les postes inconnus, les
  formations trop denses ou le mode Item Score, la liste reste la présentation de référence.
  Une proposition valide place le terrain au premier plan, avec la fiche du joueur,
  le bandeau **Achats / Valeur club / Total**, le budget et **Voir les achats**.
  **Sources et inventaire** permet de retrouver les entrées ; conditions, protections
  et vérification du rapport se déplient en dessous. Les états sans solution, incertains
  ou à recalculer restent visibles et retirent la proposition obsolète.
- **Réglages** : adresse API, clé masquée en mémoire, vérification de connexion et état
  du modèle. Les messages d'erreur apparaissent sur la page en cours. Modifier le serveur
  ou la clé invalide la connexion et les données reçues, comme avant le changement visuel.
  La connexion utilise un formulaire validable avec Entrée. **Effacer la clé** retire
  la clé de la session et invalide la connexion sans requête supplémentaire. Les informations
  de session et l'accès au laboratoire se déplient dans deux panneaux secondaires.

Le **Contrôleur local** reste accessible depuis Réglages, avec la même apparence dans
l'extension. La page séparée `controller-lab.html` conserve sa scène de laboratoire.
Le terrain est une disposition illustrative : il ne fournit jamais de coordonnées de clic
au contrôleur. Le moteur SBC et le contrat de perception ne sont pas modifiés par le thème.

Le scénario **Exemple fictif → Maquette A1 · 11 cartes** charge
`data/fixtures/sbc-report-a1.synthetic.json`. Ses coûts de 4 200 + 6 800 = 11 000 sont
cohérents avec les cartes, mais aucun solveur ni contrôle métier n'est exécuté. Il sert
à comparer le rendu au dessin dans le même écran que les autres rapports. Le libellé
de formation est déduit des postes du rapport lorsque les onze cartes le permettent.

Vérifications : typage, formatage et 184 tests frontend, puis build ; parcours manuel en
360 et 440 pixels avec l'API locale authentifiée, analyse du laboratoire et calcul CP-SAT
sur les données fictives. L'overlay de détection garde les dimensions de l'image affichée.
Le modèle entraîné pour la Web App EA reste à raccorder.

## Audit de fidélité A1

La comparaison porte sur la colonne **A1 — Stade** de la planche, avec le scénario
**Maquette A1 · 11 cartes** dans l'application. Le dessin décrit Équipe ; les autres
pages sont jugées sur la cohérence des couleurs, des matières, des caractères, des
commandes et des états. Les données de contrôle sont fictives.

| Écart observé | Correction appliquée |
| --- | --- |
| En-tête trop haut et marque ressemblant à un globe filaire | Hauteur de ligne corrigée ; ballon à panneaux pleins et doubles diagonales conservées. |
| Lien textuel encombrant dans le popup | Icône d'ouverture dans un onglet et fermeture explicite limitée au popup ; aucun bouton d'épinglage factice. |
| Fond et panneaux trop uniformément verts | Fond anthracite en mode luminosité et panneaux plus neutres ; vert conservé pour le terrain et les actions. |
| Sources placées avant la proposition | Terrain dès le haut, puis joueur, coûts, budget et achats ; sources disponibles ensuite, avec l'inventaire API conservé. |
| Cartes trop discrètes et survol confondu avec une sélection | Cartes agrandies, contour de sélection renforcé ; survol par éclaircissement. Taille réduite sur les rangées de cinq cartes. |
| Lignes du terrain mal ajustées à son ratio affiché | SVG adapté à la surface réelle du terrain. |
| Bandeau du joueur rectangulaire et métadonnées intercalées avant les coûts | Bandeau incliné et arrondi ; nom complet, version et valeur disponibles dans les détails de la carte. |
| Total insuffisamment mis en valeur | Cadre citron incliné, budget plus lisible et typographie des montants adaptée à leur longueur. |
| Achats présentés comme une liste de texte générique | Mini-cartes non interactives, versions, quantités, prix par carte et total du rapport. |
| Écrans de départ peu travaillés | Illustration de cartes pour l'inventaire vide et l'import de rapport ; sources fictives encadrées. |
| Coûts absents affichés comme trois cases vides | Pas de bandeau de coûts sans composition ; états sans solution, incertains et à recalculer explicitement distingués. |
| Contours de focus coupés sur les boutons inclinés | Focus intérieur sur les onglets et actions ; cadre extérieur du CTA réservé au clavier. |
| Laboratoire intégré moins cohérent en plein écran | Deux colonnes alignées, champs et actions regroupés ; retour à une colonne sur petit écran. |

Contrôles manuels : 360, 440 et 1 280 pixels, onze cartes et petite équipe de trois
cartes, achats dépliés, import local, nom long, montants dépassant le milliard, états
sans solution et lecture incertaine. Aucun débordement horizontal sur les vues contrôlées.
Le parcours avec l'API locale vérifie aussi le calcul CP-SAT, la conservation du budget
et de l'inventaire après réouverture des sources, et l'alignement image/rectangles après
analyse manuelle. Les captures locales sont dans `artifacts/design/audit-a1/` (ignorées
par Git).

Les commandes d'ouverture et de fermeture du popup sont couvertes par les tests de
l'extension. L'épinglage de l'extension appartient à Chrome. Le dessin au crayon reste
une direction graphique : les textes et les commandes sont des éléments HTML accessibles,
et les cartes utilisent des silhouettes génériques. L'audit visuel ne raccorde pas le
modèle EA ni le placement automatique des joueurs.

## Passe de fidélité : proportions et matières

La deuxième comparaison reprend les proportions de la colonne A1, plutôt que seulement
ses couleurs. À 440 pixels, sur le scénario de onze cartes, le terrain passe d'environ
416 × 396 à **432 × 351 pixels**. L'action principale termine vers **715 pixels** de
hauteur, contre environ 790 auparavant. Le terrain déborde légèrement de la gouttière,
comme dans le croquis, sans sortir du cadre.

Les cartes sont plus larges et plus courtes, avec une pointe et un liseré vectoriels.
Les rangées ont un léger décalage central pour retrouver le relief du dessin ; le gardien
reste séparé des défenseurs. Ce relief est un calcul d'affichage : le rapport et ses
affectations ne sont pas modifiés, et ces positions ne sont jamais des points de clic.

Le symbole du logo occupe davantage de place, les onglets inactifs sont inclinés,
le titre est plus large, et les badges utilisent un dégradé argenté. Les hachures sont
communes au fond et au gazon. Le bandeau du joueur, les coûts et le bouton reprennent
les cadres inclinés ; l'action principale a deux diagonales à gauche, sans flèche ajoutée.
Le catalogue utilise les mêmes cartes et les mêmes proportions que l'application.

Les captures de cette passe sont dans `artifacts/design/fidelity-a1/` (ignorées par Git).
Vérifications : largeurs utiles de 327, 360, 440 et 1 280 pixels, trois et onze cartes,
rangée de cinq cartes, noms longs et grands montants. La largeur minimale héritée de
l'ancien thème a été retirée pour éviter les coupures dans une fenêtre étroite. La
connexion API et l'alignement image/rectangles de l'analyse restent vérifiés.

## Les pièces du rendu

Les assets utilisés et leurs références de travail sont locaux, dans
`frontend/src/design-a1/assets/`.

| Fichier | Rôle | Format |
| --- | --- | --- |
| `charcoal-surface.png` | Texture sombre du cadre et des panneaux | 1 254 × 1 254, opaque |
| `pitch-grass.png` | Matière du terrain, éclaircie au rendu pour retrouver A1 | 1 122 × 1 402, opaque |
| `card-gold-sketch.svg` | Carte affichée : or, hachures et contour en écusson | Vectoriel |
| `card-gold.png` | Ancienne matière dorée, conservée comme référence de travail | 1 093 × 1 439, alpha transparent |
| `card-mask.svg` | Contour net et forme commune à la carte et à sa sélection | Vectoriel |
| `pencil-strokes.svg` | Hachures communes au fond et au terrain | Vectoriel |
| `cost-frame.svg` | Cadre incliné et traits clairs du bandeau des coûts | Vectoriel |
| `action-frame.svg` | Contour clair du bouton principal incliné | Vectoriel |
| `player-silhouette.svg` | Portrait générique de remplacement | Vectoriel |
| `pitch-lines.svg` | Lignes blanches en perspective | Vectoriel |
| `brand-mark.svg` | Marque originale : doubles diagonales et ballon | Vectoriel |
| `fonts/BarlowCondensed-SemiBold.ttf` | Libellés et texte droit | Police locale |
| `fonts/Barlow-ExtraBoldItalic.ttf` | Titres, notes, chiffres et marque | Police locale |

Les trois matières PNG ont été produites avec l'outil intégré `image_gen`, à partir de la
planche comme référence de style. Les requêtes exactes retenues sont conservées dans
[generated-assets.json](prompts/generated-assets.json). Un essai de nettoyage de carte
non retenu n'est pas intégré au dépôt. Les premières requêtes de matières mentionnent
A3 ; ces matières communes ont été conservées, puis l'assemblage a été réalisé pour
**A1**, conformément à la précision de l'utilisateur.

La carte affichée est maintenant reconstruite en SVG à partir du dessin A1 : elle est
plus large et moins haute, avec une pointe, un liseré et des hachures. Les nouveaux SVG
sont des sources vectorielles écrites dans le dépôt. Le PNG doré d'origine n'est plus
utilisé dans le rendu livré.

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
La carte SVG possède un fond transparent ; le masque commun stabilise la sélection.

## Réutiliser le kit

Importer `design-a1/StadiumKit.tsx`, puis placer les composants sous un conteneur
`.stadium-kit`. Le style est limité à cette classe : il n'écrase pas les autres écrans.

- `StadiumBrand` assemble le symbole et le nom en texte.
- `StadiumCard` affiche une carte et sa sélection, avec un nom accessible au clavier.
- `StadiumPitch` reçoit les joueurs, leurs coordonnées en pourcentage et le libellé de
  formation. Il applique le relief graphique du croquis sans décider des affectations
  du solveur ni modifier le rapport.
- `stadium-kit.css` fournit les onglets, panneaux, coûts, bouton principal et états visuels.

Les noms, notes, postes, origines et montants restent des textes HTML. La texture ne
contient aucune information métier. Les lignes du terrain restent vectorielles et la
carte utilise le même masque pour son fond et son contour de sélection. Cela permet de
reproduire le style sans figer toute l'interface dans une capture d'écran.

Palette principale : anthracite `#181b18`, vert citron `#d0ff22`, texte `#f6f5ed` et
or `#f4da87`. Les principales valeurs sont centralisées dans les variables
`--stadium-*`. Les polices sont servies avec le build : aucune requête Google Fonts
n'est nécessaire à l'ouverture de l'extension.

Le croquis sert de référence de direction ; ses lettres dessinées à la main sont
reconstruites avec les polices locales. La validation visuelle porte sur le résultat
réel assemblé, puis sur sa déclinaison dans les écrans fonctionnels.
