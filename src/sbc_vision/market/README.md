# Catalogue et prix

Responsable principal : Rayan. L'import fournit au futur solveur les caractéristiques des versions et des prix datés.

## Les trois fichiers

| Fichier | Rôle |
| --- | --- |
| `futbin.py` | Lit les listes, récupère le JSON par lots et garde les champs utiles. |
| `database.py` | Crée SQLite et enregistre les pages, cartes et prix. |
| `__main__.py` | Lit les options, utilise le cache et coordonne l'import. |

## Utilisation depuis la racine

```bash
source .venv/bin/activate
python -m pip install -c requirements.lock -e '.[dev,data]'

# Commencer par deux pages, soit 60 versions lors du premier essai.
python -m sbc_vision.market --pages 2

# Relancer : les cartes de moins de 24 heures sont réutilisées.
python -m sbc_vision.market --pages 2

# Rafraîchir les prix d'une carte précise, sans reparcourir les listes.
python -m sbc_vision.market --ids 107 --refresh
```

`--db` change le fichier SQLite ; `--max-age` change la durée du cache en heures. Pour parcourir tout le catalogue, donner une limite supérieure à la dernière page, par exemple `--pages 1000` ; l'import s'arrête à la dernière page annoncée par le site. Ce parcours complet n'a pas encore été exécuté. Les pages en cache ne découvrent pas les ajouts à elles seules : utiliser `--refresh` pour relire l'index.

## Ce qui est conservé

- `pages` : numéros, identifiants et dernière page connue, pour la reprise.
- `cards` : identifiant de version, nom, note et JSON des attributs, positions et prix.
- `prices` : historique des relevés, séparés selon les clés `ps` et `pc` de FUTBIN.

Les dates sont en UTC et correspondent à notre collecte, pas à l'heure de mise à jour du fournisseur. Un prix absent reste `NULL` ; il n'est jamais remplacé par zéro ni par celui d'une autre série. Avant une résolution réelle, rafraîchir les candidats utiles.

Le fichier `data/processed/futbin_fc27.sqlite3` est local et ignoré par Git. Pour consulter les premières cartes avec SQLite :

```bash
sqlite3 data/processed/futbin_fc27.sqlite3 'SELECT id, name, rating FROM cards LIMIT 5;'
```

Chaque lot est enregistré dans une transaction. En cas d'erreur ou d'interruption, les lots précédents restent disponibles ; relancer la commande reprend les éléments manquants. Les réponses incomplètes sont rejetées et les refus HTTP arrêtent l'import.

Lire [DATA.md](../../../docs/DATA.md) pour la provenance et les conditions d'utilisation. Données de prix : [FUTBIN](https://www.futbin.com/).
