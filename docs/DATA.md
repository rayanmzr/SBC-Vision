# Données

## Deux corpus distincts

1. **Corpus vision** : captures et annotations des éléments d'interface, pour entraîner et évaluer la perception.
2. **Données métier** : inventaire, règles SBC, caractéristiques et prix de cartes, pour la résolution.

Les données métier ne constituent pas un dataset d'entraînement du détecteur.

## Corpus vision

Cible initiale de 300 à 500 captures annotées, incluant la vraie Web App collectée manuellement et un sous-ensemble de [WebUI](https://github.com/js0nwu/webui). Classes harmonisées, provenance et domaine conservés. Les informations personnelles sont masquées avant partage.

Au moins 50 captures de 5 domaines distincts sont réservées au test hors domaine : boutiques, réservations et tableaux de bord. Les domaines complets sont exclus de l'entraînement et de la validation. Les sessions de capture EA FC sont séparées afin de limiter les quasi-doublons. Voir [EVALUATION.md](EVALUATION.md).

Chaque échantillon doit avoir : ID, origine, domaine, session, taille, split, chemin local de l'image et annotations. Les données originales et les exports lourds ne sont pas committés. Publier un manifeste, des instructions d'accès et des empreintes de version.

## Catalogue et prix FUTBIN

Les tests exploratoires effectués avant l'initialisation du dépôt ont validé :

- Les listes publiques FC 27, leurs filtres et la pagination.
- Un échantillon de 60 cartes, sans compte ni abonnement.
- Le JSON par lots du Squad Builder : 60 IDs connus reçus dans une requête ; postes complets, note, rareté, attributs et prix.
- Une mesure ponctuelle d'environ 0,5 seconde avec compression gzip. Ce n'est pas un engagement de performance.

**L'importeur est disponible** : `python -m sbc_vision.sbc_engine import --pages 2`. Il découvre les identifiants dans les listes, puis complète les cartes par lots via `/siteapi/27/get-squad`. Les paramètres `playerCardIds` sont répétés pour chaque carte demandée. L'index, les données normalisées et les relevés de prix restent dans SQLite. Le point d'accès est interne au site, sans contrat public de stabilité.

L'import réutilise les pages déjà indexées et les cartes collectées depuis moins de 24 heures. Chaque page et chaque lot sont sauvegardés ; la même commande reprend après une interruption. `--refresh` relit les pages et les cartes du périmètre demandé ; `--ids` cible les cartes utiles. Les requêtes sont espacées d'au moins deux secondes. Une erreur HTTP arrête l'import, sans nouvelle tentative automatique ni contournement. Voir le [guide](../src/sbc_vision/sbc_engine/README.md).

Sources : [catalogue](https://www.futbin.com/27/players), [Squad Builder](https://www.futbin.com/27/squad-builder), [conditions](https://www.futbin.com/tos).

La section 13 prévoit une exception pour l'utilisation des **prix** par les étudiants avec attribution. Ne pas en déduire un droit de redistribution générale du catalogue, des images ou de tous les contenus du site.

Attribution à conserver : « Données de prix : FUTBIN — https://www.futbin.com/ ».

## Identité et prix

- Distinguer identifiant du joueur de base, identifiant de version et exemplaire du club.
- Conserver les quantités et les versions ; ne pas dédupliquer simplement par nom.
- Un relevé contient source, marché tel que fourni, valeur en crédits et date de collecte. L'âge affiché par la source est distinct de notre heure de lecture.
- Le JSON normalisé conserve l'identifiant de base FUTBIN ; ce n'est pas un identifiant EA garanti. Le statut `untradeable` vient du catalogue et ne décrit pas l'exemplaire détenu dans le club.
- Le fournisseur expose différentes séries de prix : les conserver sans supposer qu'elles sont interchangeables.
- `null` signifie inconnu, jamais gratuit. Une carte sans prix connu ne devient pas un achat à coût nul.
- Vérifier l'identité et les positions complètes des candidats retenus avant le calcul final.
- Une estimation n'est pas une offre d'achat garantie.

## Inventaire local

La table `club_items` référence la version du catalogue pour chaque exemplaire confirmé. La protection et le statut échangeable appartiennent à l'exemplaire ; ils sont conservés lors d'une nouvelle observation. Les quantités sont comptées à partir des identifiants stables d'exemplaires, jamais à partir du nombre de captures.

Le rapprochement des lectures OCR propose des versions, sans les valider automatiquement. Le suivi des exemplaires entre écrans et le scan du compte restent à raccorder. Le [guide](../src/sbc_vision/sbc_engine/README.md) fournit les formats et une démo entièrement fictive dans une base séparée.

## Emplacements

- `data/fixtures/` : petits exemples synthétiques versionnés pour les tests hors ligne.
- `data/raw/` : captures originales locales, ignorées par Git.
- `data/processed/` : recadrages, annotations préparées et bases SQLite locales, ignorés par Git.

`perception.synthetic.json` teste le contrat avec une sortie écrite à la main. `club.synthetic.json` contient trois versions et trois exemplaires inventés, dont deux copies d'une même version avec des protections différentes. `solver.synthetic.json` ajoute trois cartes et un défi à trois postes pour comparer les méthodes. Les noms, prix et confirmations de ces démos sont fictifs ; aucune de ces fixtures ne définit un SBC EA validé.

Les manifestes et guides d'accès sont versionnés ; les captures privées, inventaires réels, cookies et poids lourds restent hors de Git. Les journaux ne doivent pas enregistrer images ni en-têtes d'authentification. Ne pas publier de données sensibles dans une issue. Les licences, coûts et disponibilités des sources doivent être vérifiés avant diffusion.

## Vérification du 6 novembre

Un appel public au JSON FUTBIN a répondu HTTP 403 depuis l’environnement local. Aucun contournement n’a été tenté. Le cache est conservé et un import de fichier normalisé est disponible pour les exports obtenus par un accès autorisé ; la provenance, les prix inconnus et les dates de collecte sont préservés.

## Essais du 12 novembre

L'actualisation ciblée d'une version puis l'import de deux pages ont fonctionné, sans modification du mécanisme d'accès : 60 versions actualisées et 62 versions en base locale. Le refus précédent n'est donc plus reproductible sur ce périmètre limité. Le catalogue complet et les correspondances des cartes évoluées restent à vérifier.

Trois captures réelles de Chrome ont été conservées uniquement en local dans `data/raw/ea_2026-11-12/` : club, fiche joueur et écran de SBC. Les régions et textes attendus ont été annotés manuellement pour un essai OCR de développement. Les lectures et mesures restent dans `data/processed/ea_2026-11-12/`, sans ajout automatique d'exemplaires ni partage des captures sur GitHub. Aucun achat, placement ou échange n'a été effectué.

L'écran d'un SBC à sept conditions a aussi été collecté, dont une vue en plein écran utilisée pour les annotations. Les sept conditions et les onze postes sont lus. L'import limité de deux pages a apporté uniquement 62 versions or ; il ne couvre pas les cinq cartes argent requises par ce défi. Ce manque de couverture reste distinct de la validité des contraintes et de la disponibilité du point d'accès FUTBIN.

L'import a ensuite été étendu aux filtres publics `version=silver` et `version=bronze`, sur cinq pages chacun : la base contient 362 versions (62 or, 150 argent, 150 bronze). Les requêtes restent espacées et les pages déjà indexées sont réutilisées dans leur propre filtre. Aucun catalogue complet ni couverture exhaustive des versions n'est annoncé. Les données, historiques de prix et propositions nominatives restent dans la base et les rapports locaux ignorés par Git.
