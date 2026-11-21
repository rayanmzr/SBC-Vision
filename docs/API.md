# API de perception

Le bouton « Envoyer à l’API » de l’extension appelle `POST /api/v1/perception/analyze`.
Le mode `SBC_PERCEPTION_MODE=detector` relie le détecteur de Saber aux régions puis à
l’OCR de Rayan. Les poids restent côté Python. La cible produit est la Web App EA.

## Activation

Installer les options `data,solver,ocr,vision`, Tesseract et un modèle ONNX de la
[release modeles-v1](https://github.com/rayanmzr/SBC-Vision/releases/tag/modeles-v1).
Vérifier son empreinte avant de le placer sous `data/processed/models/`, hors Git.

```bash
SBC_PERCEPTION_MODE=detector \
SBC_DETECTOR=yolo:data/processed/models/yolo26s-easysbc-ft-s0.onnx \
SBC_CARD_LAYOUT=club-list SBC_OCR_MODE=tesseract-regions \
SBC_ENGINE_MODE=local SBC_ENGINE_DATABASE=data/processed/futbin_fc27.sqlite3 \
uvicorn sbc_vision.api.main:app --host 127.0.0.1 --port 8000
```

`SBC_DETECTION_THRESHOLD` vaut 0,61 par défaut ; ce seuil doit encore être évalué sur EA.
`SBC_CARD_LAYOUT=club-list` lit les noms et statistiques à droite des miniatures de la
liste du club. Le profil `card` vise une carte complète. Une disposition inconnue ou
une région hors image reste à relire ; les profils ne s’interchangent pas automatiquement.
Sans OCR activé, le mode détecteur renvoie uniquement ses éléments.

`/health` indique si le modèle est chargé ; `/api/v1/capabilities` annonce les fonctions
activées. Par défaut la perception est désactivée et une analyse valide renvoie
`503 perception_unavailable`. Le mode explicite `lab-colors` sert aux scènes fictives
locales, décrites dans [LAB_PERCEPTION_API.md](LAB_PERCEPTION_API.md).

## Entrée et réponse

Le corps est le fichier binaire PNG/JPEG, avec `Content-Type: image/png` ou `image/jpeg`.
Le type annoncé doit correspondre aux octets réels. `capture_id` est facultatif, non vide,
limité à 128 caractères ; sinon le serveur génère un UUID.

```bash
python scripts/analyze_image.py chemin/capture-ea.png \
  --url http://127.0.0.1:8000 --capture-id ea-screen-001
```

La réponse `200` suit `contracts/perception.schema.json` : capture, dimensions, modèle et
éléments avec type, boîte en pixels d’origine, texte, confiance et actions possibles.
Le champ facultatif `ocr` contient les mots/régions, cartes et versions candidates,
les conditions interprétées et leurs limites. La réponse est revalidée : les identifiants
sont uniques, les boîtes restent dans l’image, et l’OCR se rapporte aux cartes de la même
capture. Un JSON conforme peut néanmoins contenir une erreur visuelle.

L’extension affiche les lectures puis propose une confirmation locale des exemplaires
et le transfert des conditions complètes au solveur. Les routes de l’inventaire, des
protections et du calcul sont décrites dans [SBC_API.md](SBC_API.md). Cette analyse ne
crée aucun exemplaire, n’appelle pas FUTBIN et n’exécute aucun clic sur EA.

## Limites et erreurs

Limites : 5 Mio, 8 192 pixels par côté, 20 millions de pixels, 10 secondes de réception,
15 secondes d’inférence. Le pipeline conserve une copie de l’image pour son worker ;
une annulation HTTP ne libère pas le modèle pendant que ce worker calcule encore.
Un seul calcul de détection/OCR est admis à la fois par pipeline. Le délai ne tue pas
le thread ni Tesseract ; une isolation annulable reste nécessaire avant partage à forte charge.

| Statut | Signification |
| --- | --- |
| 400 / 408 | Image invalide ou réception trop lente |
| 413 | Taille ou dimensions dépassées |
| 415 | Format non pris en charge ou différent du type annoncé |
| 422 | Identifiant de requête invalide |
| 429 | Pipeline occupé ; réessayer après le calcul en cours |
| 502 | Échec de l’inférence ou résultat incohérent |
| 503 | Pipeline absent |
| 504 | Délai d’inférence dépassé |

Les erreurs applicatives contiennent `detail.code` et `detail.message`.
Les images sont traitées en mémoire ; aucune capture ni rapport n’est conservé par la
route. Les outils OCR peuvent employer des fichiers temporaires système. Les logs
n’incluent pas les octets des captures. En mode partagé, les routes métier exigent une
clé Bearer ; voir [DEPLOYMENT.md](DEPLOYMENT.md).

## Contrôles et limites EA

Les tests hors ligne vérifient le transport, les refus, les délais, le verrou et la
chaîne détecteur → régions → OCR avec un moteur fictif explicite. Le raccord séparé
`POST /api/v1/ocr/analyze` accepte aussi des régions fournies, voir [OCR_API.md](OCR_API.md).

Sur le lot privé de développement EA du 20 novembre : une capture du club donne trois
miniatures et trois lectures exploitables, dont une version ambiguë ; une capture de
composition donne seulement quatre des onze emplacements. Les régions des conditions
ne sont pas générées automatiquement. L’OCR global retrouve les onze libellés de poste,
mais cette lecture n’est pas encore reliée à une extraction complète et vérifiée des règles.
Ce lot a servi aux réglages ; ces observations ne mesurent pas la généralisation.

L’extension empaquetée a été chargée dans un Chromium isolé : connexion à l’API locale,
calcul CP-SAT sur données fictives, protection persistante et analyse de la capture EA
ont été exercés. Le scan hybride OCR/HTML est décrit dans [SBC_API.md](SBC_API.md#scan-hybride-du-club-ea).
Les actions de placement et d'échange ne sont pas raccordées ; `controller` et
`live_actions_enabled` restent faux côté serveur. Le client du scan n'autorise que Next.

Essai supplémentaire depuis le popup de l'extension chargée dans Chrome : neuf pages,
163 observations sauvegardées via HTTP ; neuf lectures OCR exploitables dont huit
concordent avec des lignes entièrement visibles. Ce second passage utilise la capture
native de l'onglet et ne remplace pas le premier relevé par capture du bureau. Les deux
comptages OCR restent séparés ; aucun score indépendant de précision n'est annoncé.
