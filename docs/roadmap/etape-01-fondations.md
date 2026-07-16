# Étape 1 — Fondations locales et contrat de télémétrie v1

## Pourquoi cette étape vient en premier

Cette étape est la plus sûre pour établir un socle local stable avant d’introduire des couches métier plus complexes. Elle permet d’aligner l’équipe autour du contrat de données et du lancement technique minimal.

## Ce que cette étape prouvera

- la structure Python locale peut être préparée ;
- le contrat de télémetrie v1 peut être défini ;
- un payload valide peut être validé sans dépendance MySQL ni MQTT ;
- l’équipe dispose d’un point de départ commun.

## Fichiers qui seront modifiés

- pyproject.toml
- .env.example
- apps/api/main.py
- schemas/telemetry.v1.schema.json
- docs/contrats/contrat-telemetrie.md

## Décisions nécessaires

- choisir le format du payload télémétrique v1 ;
- définir l’identifiant de dispositif et les champs de base ;
- décider de l’endroit où seront conservés les schémas.

## Données attendues de l’Embedded Systems Engineer

- identifiant du dispositif ;
- horodatage ;
- état de batterie ;
- température ;
- statut binaire ou message d’état.

## Critères d’acceptation

- un environnement local peut être créé ;
- un payload valide passe la validation de schéma ;
- un endpoint de santé minimal peut être exposé ;
- aucun stockage MySQL ni MQTT n’est nécessaire à cette étape.

## Commandes prévues

- python -m venv .venv
- pip install -r requirements.txt (à venir)
- python -m uvicorn apps.api.main:app --reload

## Risques

- format de télémétrie non stabilisé ;
- ambiguïté sur les champs obligatoires ;
- dépendances techniques non encore clarifiées.

## Hors périmètre volontaire

- MySQL ;
- Alembic ;
- MQTT ;
- modèles ML ;
- règles de scoring.

## Résultat démontrable attendu

Un exemple de payload télémétrique valide pourra être observé et validé localement, sans dépendance métier supplémentaire.

Validez-vous le lancement de l’étape 1 : initialisation technique locale et contrat de télémétrie v1 ?
