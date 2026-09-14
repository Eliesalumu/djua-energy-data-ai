# Contrats API

## Endpoints actifs

| Methode | Endpoint | Usage |
| --- | --- | --- |
| GET | `/health` | Verifier l'API. |
| POST | `/telemetry/analyze` | Ingerer des records de telemetrie et produire alerte + prediction. |
| POST | `/maintenance/predict` | Tester directement le modele maintenance. |
| POST | `/security/predict` | Tester directement le modele securite. |
| POST | `/v1/devices/evaluate-from-telemetry` | Flux complet device-only: records -> predictions -> kit_intelligence -> historique. |
| GET | `/v1/predictions` | Lire les predictions techniques par kit ou device. |
| GET | `/demo/kit-console` | Console locale de demonstration. |

Le payload de prediction ne contient plus de donnees client, contrat ou paiement. Les champs d'entree attendus sont `device_id`, `kit_id` et `records[]`.
