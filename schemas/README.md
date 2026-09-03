# Schemas

Les schemas JSON definissent les contrats de donnees entre le backend metier, les boitiers, l'API IA/Data et les interfaces.

## Contrat backend -> IA recommande

- `backend_ai_prediction_scoring_request.v1.schema.json` : payload complet a envoyer a `POST /v1/customer/evaluate-from-telemetry` pour calculer les predictions maintenance/securite et le scoring client multidimensionnel.

Ce contrat regroupe l'identite client-kit-device, le profil client, le contrat, l'installation, le kit, la fenetre de telemetrie brute, les paiements bruts, le contexte operationnel, la qualite des donnees, les consentements et les options d'appel.

## Schemas specialises

- `telemetry.v1.schema.json` : mesure boitier brute.
- `payment.v1.schema.json` : agregats paiement.
- `customer.v1.schema.json` : profil client pour les vues front.
- `contract.v1.schema.json` : contrat client-kit.
- `customer_decision_context.v1.schema.json` : snapshot interne du moteur de decision.
- `customer_decision_result.v1.schema.json` : resultat de scoring/decision.
- `prediction.v1.schema.json` : prediction technique.
- `intervention.v1.schema.json` : intervention terrain.
- `solar_advisor.v1.schema.json` : demande Solar Advisor.
