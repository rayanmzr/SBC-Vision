# Extension Chrome et interface React

Responsable principal : Samy Allali.

Le client retenu est une extension Chrome avec interface React, reliée à l'API Python. Il affichera l'état de l'analyse, l'inventaire, les cartes protégées, les conditions du SBC, les recommandations nominatives et le récapitulatif final. Les modèles et le solveur restent côté Python.

Le socle initial contient le contrat d'API, pas encore l'extension. La carte `SBV-015` couvre son initialisation, la configuration de l'URL d'API et un premier parcours sur données synthétiques clairement identifiées. La carte `SBV-016` couvre la capture et le contrôleur : premier test sur une page locale, puis vérification après chaque action.

Prévoir des états distincts : chargement, lecture incertaine, règle non prise en charge, aucune solution connue, composition vérifiée et confirmation en attente. Un échec réseau ne doit pas afficher une réussite.
