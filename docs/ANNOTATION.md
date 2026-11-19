# Guide d'annotation des éléments d'interface

Responsable : Saber. Ce guide dit ce qu'on boîte et avec quelle classe. Il vaut pour la
vérification des pré-annotations (pages web capturées, Web App EA FC 27) et pour toute
annotation à la main. Les classes sont celles du [contrat de perception](../contracts/perception.schema.json).

## Ce qu'on boîte

Tout élément **visible** sur lequel un utilisateur peut **agir** : cliquer, saisir, choisir. Le
texte seul, les images décoratives et les titres ne sont pas boîtés (le texte vient de l'OCR).

| Classe | Ce qu'on y met | Exemples |
| --- | --- | --- |
| `button` | Déclenche une action ou ouvre un panneau | bouton, onglet, groupe de boutons dont un seul est actif (vue, type de graphique), icône cliquable (panier, compte, fermer), flèche de carrousel, bouton qui ouvre une liste d'actions (« Ajouter ▾ »), élément d'un menu ouvert |
| `link` | Mène à une autre page | texte de lien, logo vers l'accueil, vignette ou carte de produit cliquable entière |
| `input` | Zone de saisie | champ de texte, recherche, nombre, date à taper |
| `menu` | Montre une valeur et permet d'en choisir une autre dans une liste | liste déroulante, sélecteur de tri ou de filtre, choix de la période (« Last 1 hour ▾ »), choix de la source de données |
| `checkbox` | Coche ou choix exclusif | case à cocher, bouton radio, interrupteur |
| `card` | EA FC 27 : carte de joueur | carte dans le club, le marché, un SBC |
| `slot` | EA FC 27 : emplacement d'une équipe | poste vide ou occupé sur le terrain d'un SBC |

## Règles

1. **Toute la zone cliquable** : fond et marges intérieures compris, pas seulement le texte.
2. **Visible** : au moins la moitié de l'élément est dans la capture et n'est pas recouverte
   (bandeau, menu ouvert, fenêtre). Derrière une fenêtre modale qui assombrit la page, rien
   n'est boîté : on ne peut pas y cliquer.
3. **Imbrication** : un lien qui enveloppe un bouton de même taille donne un seul élément, le
   bouton. Une carte cliquable qui contient ses propres boutons donne la carte et chacun des
   boutons.
4. **Lien ou bouton** : la fonction décide (changer de page ou agir sur la page), pas l'aspect.
   L'erreur coûte peu : les deux donnent l'action « clic ».
5. **Pas de zone invisible** : une zone cliquable sans aucun repère visuel n'est pas boîtée,
   même si le code la déclare ; un lien large dont seul le logo se voit est boîté sur le logo.
6. **Élément désactivé** (grisé) : boîté quand même, c'est un contrôle ; son état se lit à part.
7. **Curseur** (choix d'un prix ou d'un volume en glissant) : non boîté, l'ontologie n'a pas de
   classe pour lui.

## Pré-annotation et vérification

1. `capture_web` enregistre la capture avec l'arbre d'accessibilité et les boîtes de la page ;
   `build_webui` en tire une pré-annotation, avec les règles de reconstruction de WebUI
   (voir [VISION.md](VISION.md)).
2. Chaque capture est revue avec ses boîtes numérotées. Les corrections sont écrites dans un
   fichier JSON par page : boîtes à retirer ou à reclasser, boîtes à ajouter (voir
   `perception/datasets/corrections.py`).
3. Une boîte ajoutée est recalée sur l'élément de la page qui la recouvre le mieux : la
   précision ne dépend pas du tracé à la main.

Ce que la pré-annotation manque le plus souvent : les éléments que le site code comme de
simples blocs cliquables (menus déroulants maison, flèches de carrousel, filtres), sans rôle
déclaré, ou qu'il déclare mal (un bouton de bandeau de cookies déclaré comme élément de liste).
Ce qu'elle ajoute à tort : des éléments recouverts par un bandeau, un calendrier ouvert ou une
fenêtre modale, et des listes repliées dont les liens existent mais ne se voient pas.
