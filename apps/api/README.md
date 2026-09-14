# API

API FastAPI locale du MVP DJUA Energy.

Routes principales dans `main.py` :

- `/telemetry/analyze` pour ingestion, prediction maintenance/securite et alerte.
- `/maintenance/predict` et `/security/predict` pour tester directement les modeles.
- `/v1/devices/evaluate-from-telemetry` pour calculer maintenance/securite depuis `records[]`, construire `kit_intelligence` et historiser une prediction technique par device.
- `/v1/predictions` pour lire les predictions techniques par kit ou device.
- `/frontend/*` pour les payloads de demonstration de l'interface.
- `/demo/kit-console` pour ouvrir une interface graphique de demo: saisie manuelle des variables d'un kit, prediction, explication et chat contextuel.

L'API IA/Data ne consomme plus de donnees client, contrat ou paiement. Le payload attendu est centre sur `device_id`, `kit_id` et `records[]`.

Le stockage local conserve trois tables principales: `telemetry_records`, `prediction_history` et `device_state`.
