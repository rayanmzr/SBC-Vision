# Samy Allali - Application et intégration

Compte : [SamyALlali](https://github.com/SamyALlali).

## But

Relier les briques dans une application reproductible, avec une API, un contrôleur et une interface de suivi.

## Responsabilités

- Construire le frontend React et l'API FastAPI avec gestion claire des erreurs.
- Implémenter la capture locale et le contrôleur scripté à partir du JSON de perception.
- Séparer observation, simulation et exécution ; vérifier l'écran après chaque action.
- Afficher inventaire, protections, contraintes, achats, coût et confirmation finale.
- Préparer Docker, CI, déploiement cloud, limites des requêtes et mesure de latence.
- Réaliser un démonstrateur local minimal si le repli est validé par le superviseur et nécessaire.

## Interfaces avec l'équipe

Le client envoie des images à l'API, sans embarquer le modèle. Saber et Rayan fournissent perception/OCR et résolution. Le contrôleur n'invente pas de coordonnées lorsque la lecture est incertaine ; il signale l'échec ou demande une nouvelle observation.

## Livrables attendus

Client et API, contrat de transport, journal d'étapes sans données sensibles, tests d'intégration, conteneur, URL de démonstration et guide de lancement. La démo distingue clairement service réel et environnement de secours.

## Premières tâches

Voir `SBV-014` à `SBV-019`. Commencer par l'API et les contrats ; le frontend et le contrôleur peuvent ensuite avancer avec des fixtures synthétiques explicitement indiquées.
