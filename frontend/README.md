# Application React

Responsable principal : Samy Allali.

Le frontend sera un client de l'API. Il affichera l'état de l'analyse, l'inventaire, les cartes protégées, les conditions du SBC, les recommandations nominatives et le récapitulatif final. Il ne doit pas charger les poids du modèle.

Le socle initial contient le contrat d'API, pas encore l'application React. La carte `SBV-015` couvre son initialisation, la configuration de l'URL d'API et un premier parcours sur données synthétiques clairement identifiées.

Prévoir des états distincts : chargement, lecture incertaine, règle non prise en charge, aucune solution connue, composition vérifiée et confirmation en attente. Un échec réseau ne doit pas afficher une réussite.
