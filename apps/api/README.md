# API

API FastAPI locale du MVP DJUA Energy.

Les routes principales sont dans `main.py` :

- `/telemetry/analyze` pour ingestion, prediction maintenance/securite et alerte.
- `/maintenance/predict` et `/security/predict` pour tester directement les modeles.
- `/v1/customer/evaluate` pour evaluer un snapshot client-kit deja enrichi avec une identite resolue par le backend.
- `/v1/customer/evaluate-from-telemetry` pour calculer maintenance/securite depuis `records[]`, puis produire la decision client.
- `/v1/customers` et `/v1/customers/{client_id}` pour lire la fiche client locale et ses derniers scores.
- `/v1/customer/decisions` et `/v1/customer/decisions/{decision_id}` pour alimenter le frontend avec l'historique des decisions.
- `/v1/predictions` pour lire les predictions techniques par client, kit ou device.
- `/frontend/*` pour les payloads de demonstration de l'interface.
- `/demo/kit-console` pour ouvrir une interface graphique de demo: saisie manuelle des variables d'un kit,
  prediction, scoring client multidimensionnel, explication et chat contextuel.

La resolution client-kit ne se fait pas dans cette API IA. Le backend metier doit fournir `identity.client_id`,
`identity.kit_id`, `identity.device_id`, les references contrat/affectation disponibles, et
`identity.resolution_status`.
Le backend envoie les paiements bruts dans `payments[]`; les agregats de risque paiement sont calcules cote IA/Data.

Le stockage local IA conserve cinq tables principales: `customers`, `telemetry_records`, `prediction_history`,
`device_state` et `customer_decision_history`. Les relations client-kit restent une responsabilite du backend metier;
l'IA stocke les identifiants recus pour l'historique, le dispatch frontend et l'audit.
