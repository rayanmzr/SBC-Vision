# Vision : données, détecteurs et évaluation

Responsable : Saber. Ce document décrit la partie vision telle qu'elle est construite : d'où
viennent les données, comment elles sont étiquetées et contrôlées, quelles approches sont
comparées et comment elles sont mesurées. Les chiffres sont ajoutés au fur et à mesure des runs.

## Le problème

Entrée : une capture d'écran. Sortie : les éléments actionnables, avec leur classe et leur
boîte, au format du [contrat de perception](../contracts/perception.schema.json). Le détecteur
cherche sept classes (`button`, `input`, `link`, `menu`, `checkbox`, `card`, `slot`) ; l'action
découle de la classe par une table fixe (`perception/ontology.py`) : clic pour bouton, lien, case,
carte et emplacement ; saisie pour un champ ; sélection pour un menu. Le texte isolé n'est pas
une classe du détecteur.

Deux étapes d'apprentissage :

1. **Général, sur des milliers de sites (WebUI)** : ce qu'est un bouton, un champ, un lien, un
   menu, une case. C'est ce qui est mesuré sur des sites jamais vus, comme le demande le sujet 2.
2. **Adaptation à la Web App EA FC 27** : cartes, emplacements du terrain et style propre au jeu,
   sur quelques centaines d'écrans pré-annotés par le code de la page puis corrigés.

## Données génériques : WebUI reconstruit

[WebUI](https://github.com/js0nwu/webui) (CMU, CHI 2023) : pages web capturées en 2022 en six
tailles d'écran (quatre d'ordinateur, une tablette, un téléphone), avec l'arbre d'accessibilité,
la boîte et le style calculé de chaque nœud. Splits d'origine séparés par domaine.

Seules les quatre tailles d'ordinateur (1280 à 1920 px de large) servent : la Web App FC 27 se
pilote sur PC, et le sujet demande de généraliser à des sites jamais vus, pas à d'autres
appareils.

| Split | Pages | Captures |
| --- | --- | --- |
| Entraînement (`webui-7k`) | 5 420 | 29 397 |
| Validation | 5 666 | 30 722 |
| Test | 11 253 | 61 501 |

### Pourquoi les étiquettes sont reconstruites

La version « elements » publiée sur Hugging Face ne garde que les **nœuds feuilles**. Un bouton
qui contient une icône et un texte n'y apparaît que comme du texte : sur une page de connexion
examinée, les trois boutons « Continue with Google / GitHub / Slack » n'étaient pas étiquetés. Un
détecteur appris dessus apprendrait que ces boutons n'en sont pas, et l'évaluation pénaliserait
les bonnes détections.

`perception/datasets/webui.py` repart de l'arbre complet : chaque nœud dont le rôle est
interactif garde son rôle et sa **boîte entière** (`bb`, indexée par l'identifiant DOM).
Correspondance des rôles :

| Rôles d'accessibilité | Classe |
| --- | --- |
| `button`, `menuitem`, `tab` | `button` |
| `link` | `link` |
| `textbox`, `searchbox`, `spinbutton`, `combobox` éditable | `input` |
| `combobox`, `listbox`, `PopUpButton` | `menu` |
| `checkbox`, `radio`, `switch`, `menuitemcheckbox`, `menuitemradio` | `checkbox` |

Règles : élément invisible écarté (lui ou un ancêtre en `display:none`, `visibility:hidden`,
`opacity:0`) ; boîte rognée à l'écran, gardée si au moins la moitié est visible ; côté minimal
4 px CSS, aire minimale 64 px² ; boîte de plus de 60 % de l'écran écartée (conteneur de mise en
page) ; deux nœuds imbriqués couvrant la même zone (IoU ≥ 0,8) donnent un seul élément, le plus
spécifique. Coordonnées converties en pixels de capture par l'échelle lue sur la zone d'affichage
de la page (largeur de la capture ÷ largeur CSS de `RootWebArea`, ×1 sur PC) : une échelle fixe
par appareil est fausse pour les sites sans mise en page mobile, mis en page sur 980 px CSS puis
réduits à l'écran (environ 20 % des captures de téléphone, aucune d'ordinateur).

### Contrôle de cohérence image / étiquettes

Les boîtes viennent du code de la page, la capture d'un autre instant. Une boîte posée sur une
zone uniforme (écart type des gris < 3) est écartée ; une page où elles sont au moins 3 et 30 %
est exclue entière (page pas encore affichée). Sur l'entraînement : 8 144 boîtes écartées et
339 captures exclues.

### Audit manuel des étiquettes (24 pages tirées au hasard, graine 42)

- Environ 18 pages correctement étiquetées.
- 3 pages en partie décalées : carrousel ou grille de produits qui a bougé entre le relevé des
  boîtes et la capture. Ce bruit reste dans l'entraînement ; les jeux de test vérifiés à la main
  ne le contiennent pas.
- 2 défauts mineurs : un menu « hamburger » non déclaré comme bouton par le site, des zones
  cliquables invisibles (flèches de carrousel transparentes).
- **5 pages sur 24 sont le même gabarit de boutique publié sous des domaines différents.**
  La séparation par domaine de WebUI ne suffit donc pas : voir ci-dessous.

### Quasi-doublons entre splits

`perception/datasets/near_duplicates.py` résume chaque page par une empreinte de gradient
(dHash 16 × 9, 144 bits) de sa capture d'ordinateur et cherche, pour chaque page de validation
et de test, la page d'entraînement la plus proche.

Calibrage sur les 5 615 pages de validation : pour la moitié, la page d'entraînement la plus
proche est à 33 bits ou moins (parmi 5 400 pages, une mise en page voisine existe presque
toujours). Des paires tirées à chaque distance montrent de vrais doublons et des domaines
« parkés » jusqu'à 10 bits, des boutiques clonées à 15-17, surtout des sites sans rapport vers
22-26 (avec encore un clone WordPress à 25). **Seuil retenu : 18 bits**, soit 1 211 pages de
validation écartées. L'empreinte ne départage pas tout : les scores sont aussi publiés sans
exclusion, pour mesurer l'effet de la fuite.

### Corpus construits (captures d'ordinateur)

| Split | Pages | Domaines | Captures | Éléments | Liens | Boutons | Champs | Menus | Cases |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Entraînement | 5 364 | 4 738 | 19 817 | 294 515 | 263 622 | 17 757 | 9 774 | 2 196 | 1 166 |
| Validation | 5 615 | 1 763 | 20 669 | 297 163 | 266 645 | 17 421 | 9 473 | 2 079 | 1 545 |
| Test | 11 150 | 3 607 | 41 463 | 612 352 | 549 259 | 37 997 | 18 995 | 4 168 | 1 933 |

Les liens dominent (neuf éléments sur dix) : les scores par classe et la matrice de confusion
sont donc publiés à côté des moyennes.

## Évaluation commune

`perception/evaluation/` : la même mesure pour toutes les approches, sur des sous-ensembles figés
(une seule résolution par page, graine fixe).

- **mAP@0,5 et mAP@0,5:0,95** à la manière de COCO, identiques à `pycocotools` (test à 10⁻⁹
  près), jusqu'à 300 détections par classe et par image.
- **Trois niveaux** : classe ; action (`click`, `fill`, `select`), car un lien dessiné comme un
  bouton reste un clic ; interactif ou non, pour comparer un détecteur sans classes (OmniParser).
- **Point de fonctionnement** : précision, rappel et F1 au seuil de score qui maximise le F1 sur
  la validation, réutilisé tel quel sur les tests.
- **Intervalles de confiance à 95 %** par rééchantillonnage de sites entiers (bootstrap ; de
  pages pour un test tiré d'un seul site, `--bootstrap-by group`), et écarts appariés entre
  deux approches (`compare`).
- **Matrice de confusion** avec une ligne et une colonne « fond » : confusions entre classes,
  éléments manqués, fausses détections.
- **Rappel par taille** (seuils de COCO : 32², 96² pixels) et **latence** (médiane, 95ᵉ centile).

## Approches comparées

| | Approche | État |
| --- | --- | --- |
| A | Propositions OpenCV + classifieur classique (gradient boosting) | évaluée (validation, test) |
| B | YOLO26 affiné (Ultralytics), 1280 px, export ONNX | évaluée (validation, test) |
| C | RF-DETR affiné | à faire |
| D | OmniParser v2 sans adaptation | à faire |

### A : OpenCV et classifieur classique

1. Propositions sans apprentissage : contours de Canny à deux sensibilités (blocs, cadres,
   boutons peu contrastés) et regroupement morphologique des lettres en mots et en groupes de
   mots, élargis de marges fixes car la zone cliquable d'un lien déborde de son texte.
2. 19 caractéristiques lisibles par proposition, en temps constant grâce aux images intégrales :
   géométrie, gris moyen et écart type, densité de contours et de texte, saturation, cadre
   intérieur, contraste du remplissage avec l'entourage, emboîtement.
3. Gradient boosting : fond ou l'une des classes. Suppression des non-maxima par classe.

Rappel des propositions seules (IoU ≥ 0,5, 113 captures d'essai) : 77 % (champs 93 %, menus
79 %, liens 77 %, boutons 75 %, cases 42 %), en 51 ms par capture. Ce rappel borne celui de
l'approche ; les cases à cocher redessinées en CSS par-dessus une case native invisible sont la
principale limite.

Classifieur : 1 500 captures d'entraînement (une par page), 303 256 propositions étiquetées,
400 itérations, 69 s. Validation (500 sites, un par domaine, quasi-doublons retirés,
8 118 éléments, seuil 0,81 choisi au meilleur F1) :

| Niveau | mAP@0,5 [IC 95 %] | mAP@0,5:0,95 | F1 |
| --- | --- | --- | --- |
| Classe | 0,322 [0,281 – 0,367] | 0,155 | 0,39 |
| Action | 0,330 [0,305 – 0,371] | 0,179 | 0,41 |
| Interactif | 0,336 [0,310 – 0,363] | 0,134 | 0,42 |

AP@0,5 par classe : champs 0,64, cases 0,48 (28 seulement), liens 0,31, boutons 0,15,
menus 0,03. 58 % des liens sont manqués et 93 % des fausses détections sont des « liens » : les
caractéristiques ne séparent pas un lien d'un texte ordinaire. Rappel des petits éléments
(< 32² px) : 27 %. Latence : 231 ms en médiane, 732 ms au 95ᵉ centile (serveur partagé).

Test (1 000 sites, un par domaine, quasi-doublons retirés soit 2 415 pages écartées,
15 605 éléments, seuil de la validation réutilisé tel quel) :

| Niveau | mAP@0,5 [IC 95 %] | mAP@0,5:0,95 | F1 |
| --- | --- | --- | --- |
| Classe | 0,283 [0,231 – 0,337] | 0,140 | 0,38 |
| Action | 0,299 [0,276 – 0,325] | 0,153 | 0,40 |
| Interactif | 0,335 [0,313 – 0,356] | 0,129 | 0,41 |

Le test confirme la validation (intervalles qui se recouvrent, F1 au seuil 0,38 contre 0,39) ;
la baisse vient surtout des champs (0,64 → 0,56) et des cases (0,48 → 0,37, sur 77 cases).

Sensibilité : avec le même modèle et le même seuil sur 500 sites tirés sans exclure les
quasi-doublons, le mAP@0,5 par classe passe à 0,390 [0,311 – 0,471], et chaque classe monte
(boutons 0,23, cases 0,60, champs 0,69, liens 0,37, menus 0,06). Ces pages, déjà vues ou plus
faciles (domaines parkés), surestimeraient la généralisation.

### B : YOLO26 affiné

`yolo26s.pt` (poids COCO) affiné sur les 19 817 captures PC de l'entraînement (les quatre tailles
d'écran de chaque page), 1280 px, lots de 16, sans miroir horizontal, graine 0, sur un GPU L40S
de Modal (`scripts/modal_train_yolo.py`, run MLflow `yolo26s-webui-1280-s0`). Arrêt automatique
à l'époque 46 faute de progrès depuis l'époque 26, dont les poids sont gardés : 3 h 51 de GPU,
environ 11 $. Au-delà d'une quinzaine d'époques, l'erreur de classification remonte sur la
validation alors qu'elle continue de baisser sur l'entraînement : le modèle apprend les pages
d'entraînement plus qu'il ne progresse sur des sites nouveaux.

Évaluation commune, modèle exporté en ONNX et exécuté par ONNX Runtime sur processeur (4 fils,
serveur partagé), seuil choisi sur la validation (0,30) :

| Niveau | Validation, 500 sites [IC 95 %] | Test, 1 000 sites [IC 95 %] |
| --- | --- | --- |
| Classe | 0,605 [0,544 – 0,664] | 0,539 [0,486 – 0,600] |
| Action | 0,631 [0,578 – 0,698] | 0,620 [0,575 – 0,664] |
| Interactif | 0,682 [0,640 – 0,716] | 0,660 [0,634 – 0,687] |

mAP@0,5:0,95 (classe) : 0,501 en validation, 0,450 en test ; F1 au seuil : 0,66 et 0,64.
AP@0,5 par classe sur le test : champs 0,87, liens 0,63, cases 0,46, boutons 0,39, menus 0,35.
Rappel des petits éléments (< 32² px) : 54 %. Latence : 374 ms en médiane sur la validation,
430 ms sur le test. Les captures de 1920 px, réduites à 1280 px, sont les moins bien traitées
(test, niveau interactif : 0,61 contre 0,72 en 1280 px). Sans retirer les quasi-doublons, le
mAP@0,5 de validation passe à 0,643 (+0,04, contre +0,07 pour la baseline).

Écart apparié B − A (même tirage de sites pour les deux, 500 rééchantillonnages, commande
`compare`) :

| Niveau | Validation | Test |
| --- | --- | --- |
| Classe | +0,28 [0,21 – 0,34] | +0,26 [0,22 – 0,30] |
| Action | +0,30 [0,25 – 0,36] | +0,32 [0,28 – 0,36] |
| Interactif | +0,35 [0,31 – 0,38] | +0,33 [0,31 – 0,35] |

Aucun rééchantillonnage ne donne l'avantage à la baseline. Les erreurs restantes : 24 % des
boutons pris pour des liens et 36 % manqués, et 91 % des fausses détections sont des « liens »,
souvent du texte cliquable que le site n'a pas déclaré comme lien.

## Test vérifié à la main

Les étiquettes de WebUI viennent du code des pages et gardent du bruit ; ce test-ci est revu
capture par capture selon le [guide d'annotation](ANNOTATION.md). Cinq sites absents de WebUI (y
compris sous un autre domaine), capturés le 19/11/2026 (`data/manifests/ood-sites.json`) :
ldlc.com et natureetdecouvertes.com (boutiques), airbnb.fr (réservation), play.grafana.org
(tableau de bord), service-public.gouv.fr (administration). Pour chacun, l'accueil avec son
bandeau de cookies, puis neuf pages de rubriques différentes (graine 0), les quatre tailles
d'écran PC en alternance. Les sites qui refusaient l'accès (Back Market après trois pages,
Boulanger, Maisons du Monde, Decathlon, Cultura dès l'accueil) ont été écartés, sans
contournement. Deux pages encore vides au moment de la capture sont écartées par le contrôle
automatique : 48 captures.

`perception/datasets/capture_web.py` enregistre la capture, l'arbre d'accessibilité et les
boîtes de la page au format WebUI ; `build_webui` en tire la pré-annotation. Les corrections de
la revue sont versionnées (`data/manifests/ood-corrections.json`) et appliquées par
`perception/datasets/corrections.py` ; une boîte ajoutée est recalée sur l'élément de la page qui
la recouvre le mieux.

| | Éléments |
| --- | --- |
| Pré-annotation | 1 269 |
| Gardés / reclassés / retirés | 1 191 / 25 / 53 |
| Ajoutés | 77 |
| Test final | 1 293 |

La pré-annotation trouvait donc 94 % des éléments du test. Elle compte à tort des éléments cachés
(bandeau de cookies, calendrier ouvert, fenêtre modale, liste repliée) et rate ceux que les sites
codent comme de simples blocs cliquables (menus maison, flèches de carrousel, filtres) ou
déclarent mal (un bouton de bandeau en `role="listitem"`).

Résultats, mêmes détecteurs et seuils de validation, toutes les captures, intervalles par
rééchantillonnage des sites (cinq, d'où leur largeur) :

| mAP@0,5 | A | B | Écart B − A apparié |
| --- | --- | --- | --- |
| Classe | 0,148 [0,079 – 0,252] | 0,340 [0,146 – 0,493] | +0,19 [−0,02 – 0,38] |
| Action | 0,201 [0,082 – 0,395] | 0,313 [0,154 – 0,549] | +0,14 [0,03 – 0,29] |
| Interactif | 0,239 [0,174 – 0,372] | 0,455 [0,255 – 0,646] | +0,22 [0,02 – 0,39] |

Par site (classe), YOLO fait 0,52 sur Grafana, 0,51 sur LDLC, 0,44 sur Nature & Découvertes,
0,42 sur Service Public et 0,08 sur Airbnb, où huit pages montrent le calendrier de dates
ouvert : 240 jours-boutons (41 % des boutons du test), dont 12 trouvés. Un widget absent de
l'entraînement suffit à faire tomber un site ; les petits éléments (chevrons de 16 px) restent
l'autre faiblesse (9 % trouvés).

## Adaptation aux cartes et emplacements : EasySBC

La Web App EA FC 27 demande un compte possédant un club FC 27. En attendant des captures
réelles, l'adaptation aux classes `card` et `slot` est préparée sur EasySBC (easysbc.io), un
outil de SBC pour FC 27 qui affiche un terrain à onze emplacements, des cartes de joueurs, des
filtres et des menus. FUTBIN, FUT.GG et FUTWIZ refusent l'accès automatisé : écartés, sans
contournement.

51 pages listées (`data/manifests/near-sites.json` : listes, créateur d'équipe, solutions de
défis obtenues en cliquant « Créer les solutions », fiches joueurs, évolutions), capturées le
20/11/2026 ; 48 passent le contrôle automatique. Le code de la page ne connaît ni carte ni
emplacement : ils sont proposés depuis les images aux proportions d'une carte (une image qui
remplit un bouton du terrain fait de ce bouton un emplacement, `propose_cards`), puis toutes
les pages sont revues (`data/manifests/near-corrections.json`, règles dans le
[guide d'annotation](ANNOTATION.md)) : 1 102 éléments, dont 92 emplacements et 50 cartes.
Découpage par type de page, un tiers en test (`data/manifests/near-split.json`,
`perception/datasets/split_corpus.py`) : 25 pages d'entraînement, 7 de validation, 16 de test.

Affinage du YOLO26s web sur 3 000 captures WebUI (une par site) et les 25 pages
d'entraînement répétées 30 fois (`export_yolo --add`), AdamW, lr 0,0005, 30 époques : 40 min
sur L40S, environ 2 $ (run MLflow `yolo26s-easysbc-ft-s0`). Seuils choisis sur la validation de
chaque corpus, intervalles par rééchantillonnage des pages (`--bootstrap-by group`) pour le test
d'un seul site :

| mAP@0,5 | Avant | Après | Écart apparié |
| --- | --- | --- | --- |
| EasySBC, 16 pages, classe | 0,084 [0,04 – 0,25] | 0,959 [0,92 – 1,00] | +0,85 [0,70 – 0,94] |
| EasySBC, action | 0,157 | 0,958 | +0,75 [0,47 – 0,90] |
| WebUI test, 1 000 sites, classe | 0,539 | 0,529 | −0,01 [−0,03 – +0,01] |
| WebUI test, action | 0,620 | 0,598 | −0,02 [−0,04 – −0,01] |
| Test vérifié, 5 sites, classe | 0,340 | 0,323 | −0,03 [−0,10 – +0,01] |

Les 33 emplacements et 21 cartes du test EasySBC sont tous trouvés (AP 1,00). La mesure est
optimiste : entraînement et test viennent du même site, aux gabarits répétés. Elle montre que
quelques dizaines de pages suffisent à apprendre ces classes, au prix d'un à deux points sur le
web générique ; elle ne mesure pas la reconnaissance sur la vraie Web App, dont le style diffère.

## Organisation du code et sortie pour l'API

`src/sbc_vision/perception/` :

| Module | Rôle |
| --- | --- |
| `ontology.py` | Classes du détecteur (ordre fixe) et action de chaque classe |
| `boxes.py` | Aire, rognage, IoU, suppression des non-maxima : données, détecteurs, mesure |
| `detector.py` | Interface commune (une image RGB → `(classe, boîte, score)`) et chargement d'un détecteur |
| `elements.py` | Détections → `DetectedElement` du contrat, au seuil lu dans le rapport de validation |
| `datasets/` | Format des corpus (`records.py`, seule lecture et écriture), WebUI, captures de sites, contrôles, quasi-doublons, propositions de cartes, corrections, découpages, export YOLO |
| `baselines/` | Approche A (propositions OpenCV, gradient boosting) et son entraînement |
| `detectors/` | Approche B à l'inférence : YOLO exporté en ONNX, sur processeur |
| `evaluation/` | Mesure commune (`evaluate`), métriques COCO, comparaison appariée (`compare`) |

Pour l'API : `load_detector("yolo:<modèle.onnx>")` charge le détecteur, qui rend toutes ses
détections ; `to_elements` garde celles dont le score atteint le seuil du rapport de validation
(`read_threshold`, 0,30 pour le YOLO26s web), les classe par score et les met au format du
contrat (boîte en pixels entiers, action). Le
texte de chaque élément reste vide : l'OCR le remplit. L'assemblage avec l'OCR et le
raccordement à la route `/api/v1/perception/analyze` relèvent du pipeline commun (#14).

## Reproduire

```bash
python -m pip install -c requirements.lock -e '.[dev,vision]'

# Corpus (captures d'ordinateur) : idem pour val_split_webui → val et test_split_webui → test.
python -m sbc_vision.perception.datasets.build_webui --pages <extrait>/train_split_web7k \
    --data-root <extrait> --split train --source webui --out <corpus>
# Quasi-doublons de la validation et du test par rapport à l'entraînement.
python -m sbc_vision.perception.datasets.near_duplicates --corpus <corpus> --data-root <extrait> \
    --reference train --check val test

# A : entraîner, choisir le seuil sur la validation, mesurer sur le test.
python -m sbc_vision.perception.baselines.train_opencv --corpus <corpus> --data-root <extrait> \
    --images 1500 --out models/opencv-gbdt.pkl
python -m sbc_vision.perception.evaluation.evaluate --corpus <corpus> --split val --count 500 \
    --near-duplicate-max 18 --data-root <extrait> \
    --detector opencv:models/opencv-gbdt.pkl --out reports/opencv/val
python -m sbc_vision.perception.evaluation.evaluate --corpus <corpus> --split test --count 1000 \
    --near-duplicate-max 18 --threshold-from reports/opencv/val/report.json \
    --data-root <extrait> --detector opencv:models/opencv-gbdt.pkl --out reports/opencv/test

# B : exporter au format YOLO (dossier neuf), l'archiver dans le volume Modal et entraîner
# (scripts/modal_train_yolo.py, client `modal`), puis évaluer le modèle ONNX avec les mêmes
# commandes et `--detector yolo:<best.onnx>`.
python -m sbc_vision.perception.datasets.export_yolo --corpus <corpus> --data-root <extrait> \
    --out <exports>/webui-desktop --train train:all --val val:500 --near-duplicate-max 18

# Écart apparié entre deux approches évaluées sur les mêmes captures.
python -m sbc_vision.perception.evaluation.compare --corpus <corpus> --split test \
    --a reports/yolo/test --b reports/opencv/test --out reports/compare/yolo-vs-opencv-test.json
```

Test vérifié à la main et adaptation EasySBC (outils de capture : `pip install -e '.[capture]'`,
puis `playwright install chromium`) :

```bash
# Capture, pré-annotation, corrections de la revue, évaluation de toutes les captures.
python -m sbc_vision.perception.datasets.capture_web --sites data/manifests/ood-sites.json \
    --out <captures-ood>
python -m sbc_vision.perception.datasets.build_webui --pages <captures-ood> \
    --data-root <captures-ood> --split ood-auto --source capture --out <corpus-ood>
python -m sbc_vision.perception.datasets.corrections --corpus <corpus-ood> --split ood-auto \
    --out-split ood --data-root <captures-ood> --corrections data/manifests/ood-corrections.json
python -m sbc_vision.perception.evaluation.evaluate --corpus <corpus-ood> --split ood \
    --one-per group --data-root <captures-ood> --threshold-from reports/yolo/val/report.json \
    --detector yolo:<best.onnx> --out reports/yolo/ood

# EasySBC : même capture et pré-annotation (near-sites.json, split near-auto), cartes et
# emplacements proposés (à revoir), corrections, découpage, export d'adaptation.
python -m sbc_vision.perception.datasets.propose_cards --corpus <corpus-near> --split near-auto \
    --data-root <captures-near> --out <propositions.json>
python -m sbc_vision.perception.datasets.corrections --corpus <corpus-near> --split near-auto \
    --out-split near --data-root <captures-near> --corrections data/manifests/near-corrections.json
python -m sbc_vision.perception.datasets.split_corpus --corpus <corpus-near> --split near \
    --assignment data/manifests/near-split.json
python -m sbc_vision.perception.datasets.export_yolo --corpus <corpus> --data-root <extrait> \
    --out <exports>/webui-easysbc --train train:3000 --val val:500 --near-duplicate-max 18 \
    --add train <corpus-near> <captures-near> near-train 30 \
    --add val <corpus-near> <captures-near> near-val 20
# Mesure sur un seul site : une capture par page, rééchantillonnage des pages.
python -m sbc_vision.perception.evaluation.evaluate --corpus <corpus-near> --split near-test \
    --one-per group --bootstrap-by group --data-root <captures-near> \
    --threshold-from reports/yolo-easysbc/near-val/report.json \
    --detector yolo:<best.onnx> --out reports/yolo-easysbc/near-test
```

Les corrections désignent les boîtes pré-annotées par leur rang : elles valent pour les captures
des 19 et 20/11/2026, gardées hors de Git avec le reste des données (une nouvelle capture
demande une nouvelle revue).

Ni les captures, ni les corpus, ni les modèles ne sont versionnés dans Git : les sous-ensembles
d'évaluation se retrouvent à l'identique depuis le corpus (graine 0), et chaque entraînement est
tracé dans MLflow (commit, sources, données, paramètres, métriques, poids).
