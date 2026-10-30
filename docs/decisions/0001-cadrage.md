# ADR 0001 - Périmètre et architecture initiale

Statut : proposé au superviseur, décisions d'équipe confirmées le 30 octobre 2026.

- Application : Web App EA FC 27, sujet 2.
- Contribution centrale : perception d'interface et JSON d'actions, avec généralisation hors domaine.
- Agent initial : contrôleur scripté ; pas d'API LLM payante obligatoire.
- API Python FastAPI, modèle côté serveur, client React, Docker et cloud.
- Optimisation : OR-Tools et contraintes documentées, candidats et prix datés.
- Source métier exploratoire : FUTBIN, index et JSON par lots avec cache ; pas de garantie d'API publique.
- Démonstrateur local minimal de secours, attribué à Samy, sous réserve de validation pédagogique.

Toute modification importante de ce périmètre fait l'objet d'une nouvelle décision liée à une issue. La licence du code et le choix du cloud restent ouverts.
