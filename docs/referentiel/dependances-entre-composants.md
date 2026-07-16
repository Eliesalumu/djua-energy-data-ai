# Dépendances entre composants

Le futur flux de travail suit la chaîne suivante :

simulateur ou boîtier → ingestion → validation → stockage brut → qualité → features → règles ou modèles → prédiction → alerte → backend → intervention → feedback → dataset d’entraînement.

Chaque transition devra être documentée avec son format, ses producteurs et ses consommateurs, ainsi que son plan B pour le MVP local.
