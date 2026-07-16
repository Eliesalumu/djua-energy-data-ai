# Matrice fichier-réponsabilité

| Élément | Responsable | Fournisseur d’entrée | Consommateur | Étape | Statut |
| --- | --- | --- | --- | --- | --- |
| apps/api/main.py | Backend Developer | Data & AI Engineer | Utilisateurs et services | Étape 1 | Créé, non implémenté |
| apps/simulator/main.py | Embedded Systems Engineer | Data & AI Engineer | Ingestion | Étape 2 | Créé, non implémenté |
| schemas/telemetry.v1.schema.json | Data & AI Engineer | Embedded Systems Engineer | Ingestion et validation | Étape 1 | Créé, non implémenté |
| src/djua_energy/ingestion | Data & AI Engineer | Simulateur / boîtier | Qualité et features | Étape 2 | Créé, non implémenté |
