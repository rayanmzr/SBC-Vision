# Données et signalement de sécurité

Ne pas ouvrir une issue publique contenant un token, cookie, identifiant de connexion, capture de compte ou inventaire réel. Contacter le propriétaire du dépôt pour convenir d'un canal privé.

- La connexion EA est effectuée par l'utilisateur dans son navigateur ; l'application n'a pas à collecter son mot de passe.
- Les captures et inventaires réels restent dans des répertoires ignorés par Git.
- Les journaux ne doivent pas enregistrer images, cookies ou en-têtes d'authentification.
- Le contrôleur est désactivé dans le socle initial. Les étapes d'observation, de simulation et d'exécution doivent être distinguées avant son implémentation.
- Une nouvelle capture et une confirmation explicite sont nécessaires avant toute soumission de cartes.
- Un test réseau ne doit pas contourner un refus d'accès ou une protection du fournisseur.

Les données synthétiques de `data/fixtures/` sont destinées aux tests et peuvent être publiées.
