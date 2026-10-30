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

**L'importeur reproductible n'est pas encore implémenté dans ce dépôt.** L'index des identifiants est à constituer, puis les cartes peuvent être complétées par lots, stockées localement et actualisées de façon ciblée. Le point d'accès est interne au site, sans contrat public de stabilité ; prévoir cache, reprise, temporisation et erreurs explicites. Ne pas contourner un refus d'accès.

Sources : [catalogue](https://www.futbin.com/27/players), [Squad Builder](https://www.futbin.com/27/squad-builder), [conditions](https://www.futbin.com/tos).

La section 13 prévoit une exception pour l'utilisation des **prix** par les étudiants avec attribution. Ne pas en déduire un droit de redistribution générale du catalogue, des images ou de tous les contenus du site.

Attribution à conserver : « Données de prix : FUTBIN — https://www.futbin.com/ ».

## Identité et prix

- Distinguer identifiant du joueur de base, identifiant de version et exemplaire du club.
- Conserver les quantités et les versions ; ne pas dédupliquer simplement par nom.
- Un relevé contient source, marché tel que fourni, valeur en crédits et date de collecte. L'âge affiché par la source est distinct de notre heure de lecture.
- Le fournisseur expose différentes séries de prix : les conserver sans supposer qu'elles sont interchangeables.
- `null` signifie inconnu, jamais gratuit. Une carte sans prix connu ne devient pas un achat à coût nul.
- Vérifier l'identité et les positions complètes des candidats retenus avant le calcul final.
- Une estimation n'est pas une offre d'achat garantie.

## Emplacements

`data/fixtures/` contient uniquement des données synthétiques. `data/raw/`, `data/processed/`, `artifacts/` et les bases locales sont ignorés par Git. Les licences, coûts et disponibilités des sources doivent être vérifiés avant diffusion.
