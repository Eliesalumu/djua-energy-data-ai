# Rapport de travail - Djua Energy Data & AI

## Date
2026-07-16

## Objectif de la journée
Créer un socle professionnel, local-first et cloud-ready pour le projet Djua Energy, puis mettre en place une première tranche verticale fonctionnelle autour de données IoT synthétiques, avec documentation, architecture, pipeline local, API et tests.

## Contexte initial
Le dépôt ne contenait qu’un scaffold minimal et une documentation de base. L’objectif était de transformer ce point de départ en une structure exploitable, compréhensible et extensible, tout en gardant une approche volontairement simple et locale.

## Résultats principaux obtenus

### 1. Structuration professionnelle du dépôt
Mise en place d’une architecture claire et modulaire avec :
- un dossier d’application pour l’API,
- un dossier de code Python organisé par domaine,
- un dossier de documentation,
- un dossier de données,
- un dossier d’infrastructure et de gouvernance,
- un dossier de tests,
- un dossier d’artefacts locaux.

Cette structure permet une évolution progressive sans casser la base existante.

### 2. Documentation en français
Rédaction d’une documentation de référence couvrant :
- la présentation du projet,
- la vision métier,
- la portée du MVP,
- les cas d’usage futurs,
- la roadmap,
- la gouvernance de base,
- la structure du dépôt.

Cette documentation a été enrichie avec une section détaillée sur :
- l’arborescence du projet,
- le rôle de chaque module,
- le rôle de chaque fichier important,
- les dépendances installées et leurs raisons d’être.

### 3. Mise en place d’un premier pipeline Data & IA local
Implémentation d’un vertical slice fonctionnel basé sur des données IoT synthétiques, comprenant :
- génération de données,
- validation des payloads,
- construction de features,
- entraînement de modèles simples,
- sauvegarde des artefacts,
- inférence locale.

### 4. Développement d’une API locale FastAPI
Création d’une API légère et testable avec des endpoints permettant :
- de vérifier l’état du service,
- de générer une démo de données,
- de réaliser une prédiction de maintenance,
- de réaliser une prédiction de sécurité.

### 5. Ajout de tests automatisés
Mise en place de tests unitaires pour valider :
- la validation des payloads,
- la génération de données synthétiques,
- la création des features.

## Détails techniques réalisés

### Modules principaux créés ou complétés

#### Pipeline de données
- [src/djua_energy/pipeline/contracts.py](src/djua_energy/pipeline/contracts.py)
  - Validation des structures de payload IoT.
  - Vérification des champs requis.
  - Contrôle basique des valeurs métier.

- [src/djua_energy/pipeline/synthetic_data.py](src/djua_energy/pipeline/synthetic_data.py)
  - Génération de données synthétiques déterministes.
  - Simulation de scénarios réalistes comme :
    - fonctionnement normal,
    - dégradation progressive de batterie,
    - surchauffe,
    - mouvement suspect,
    - tentative de sabotage,
    - perte de connectivité,
    - ouverture de boîtier,
    - incompatibilité d’identité,
    - etc.

- [src/djua_energy/pipeline/features.py](src/djua_energy/pipeline/features.py)
  - Construction de features de maintenance et de sécurité.
  - Inclusion de variables liées à la tension, à la température, aux erreurs, aux mouvements, à la connectivité, aux événements de sécurité.

- [src/djua_energy/pipeline/train.py](src/djua_energy/pipeline/train.py)
  - Entraînement local de modèles de base.
  - Utilisation de RandomForestClassifier.
  - Sauvegarde des modèles et des features dans le dossier d’artefacts.

- [src/djua_energy/pipeline/inference.py](src/djua_energy/pipeline/inference.py)
  - Chargement des artefacts locaux.
  - Exécution d’inférences conservatrices et explicables.
  - Gestion d’un comportement sûr même lorsque les classes sont peu diversifiées.

#### API locale
- [apps/api/main.py](apps/api/main.py)
  - Exposition d’une API FastAPI locale.
  - Endpoints :
    - /health
    - /maintenance/predict
    - /security/predict
    - /demo/generate

#### Scripts et démonstration
- [scripts/demo_pipeline.py](scripts/demo_pipeline.py)
  - Démonstration complète du pipeline.
  - Génération, entraînement et inférence dans un flux simple.

#### Tests
- [tests/unit/test_pipeline.py](tests/unit/test_pipeline.py)
  - Vérification des composants de base du pipeline.

## Dépendances installées
Les dépendances suivantes ont été installées pour soutenir la première tranche verticale :

- fastapi : pour l’API locale.
- uvicorn : pour servir l’API.
- pandas : pour manipuler les données et créer des features.
- scikit-learn : pour entraîner des modèles de type RandomForest.
- joblib : pour sauvegarder et charger les modèles et features.
- pytest : pour automatiser les tests.

Ces dépendances ont été choisies pour rester simples, locales, pédagogiques et facilement reproductibles.

## Choix de conception retenus

### Local-first
Le projet a été conçu pour fonctionner sans dépendre immédiatement d’un cloud, d’un service externe ou d’un broker IoT.

### Simplicité explicable
Les modèles utilisés sont basés sur des approches simples et compréhensibles, sans réseau profond ni complexité inutile.

### Modularité
Chaque composant a un rôle précis : génération, validation, features, entraînement, inférence, API.

### Confiance humaine
Les prédictions restent conservatrices et demandent une validation humaine, notamment en sécurité.

## Problèmes rencontrés et solutions appliquées

### Problème 1 : insuffisance de diversité de classes pour la sécurité
Au cours de l’implémentation, l’inférence de sécurité a montré un risque lié à un manque de signal positif suffisant dans les données synthétiques.

### Solution
- enrichissement des scénarios synthétiques,
- ajout de signaux plus marqués pour le mouvement, le sabotage et la perte de connectivité,
- mise en place d’un comportement sûr de l’inférence en cas de faible diversité de classes.

### Résultat
La pipeline est désormais stable et les prédictions sont générées de manière propre, même dans un contexte synthétique limité.

## Validation effectuée
Une validation a été réalisée avec :
- la suite de tests unitaires,
- une exécution du script de démonstration,
- une vérification du fonctionnement de l’API locale.

### Résultat vérifié
La commande suivante a été exécutée avec succès :

```bash
pytest -q
```

Résultat observé : 3 tests passés.

## État du projet à la fin de la journée
Le projet est maintenant dans un état solide pour une première livraison technique :
- dépôt structuré,
- documentation en place,
- pipeline local fonctionnel,
- API locale opérationnelle,
- modèles entraînés localement,
- tests validés,
- base prête pour de nouvelles évolutions métier.

## Ce qui est déjà en place
- structure de dépôt professionnelle,
- documentation fonctionnelle et technique,
- pipeline Data & IA local,
- génération de données synthétiques,
- validation de payloads,
- features métier, 
- entraînement de modèles,
- API de démonstration,
- tests automatisés.

## Ce qui reste à faire
Les prochaines étapes possibles sont :
- enrichir la qualité des données synthétiques,
- ajouter des schémas plus formels,
- connecter l’API à des services plus métier,
- préparer une vraie ingestion de données,
- ajouter de la gouvernance autour du modèle,
- préparer une évolution vers des cas d’usage plus réalistes.

## Conclusion
Aujourd’hui, le projet a été transformé d’un simple scaffold en une base de travail concrète, cohérente et démontrable. La première tranche verticale a été implémentée avec succès, avec un accent fort sur la reproductibilité, la clarté du code et la préparation à des évolutions futures.
