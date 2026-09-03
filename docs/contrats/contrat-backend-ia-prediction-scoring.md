# Contrat Backend -> IA/Data : prediction et scoring

Ce document donne le format exact attendu par l'API IA/Data pour calculer :

- les predictions maintenance et securite du kit ;
- le scoring client multidimensionnel ;
- la decision d'intervention ou de suivi commercial.

Le schema JSON canonique est :

```text
schemas/backend_ai_prediction_scoring_request.v1.schema.json
```

## Endpoint recommande

```http
POST /v1/customer/evaluate-from-telemetry
Content-Type: application/json
```

Le backend doit envoyer un snapshot complet et coherent. Le backend reste responsable de la resolution `client_id` + `kit_id` + `device_id` + `contract_id` + `assignment_id`. L'API IA/Data ne devine pas l'identite client-kit.

## Payload attendu

```json
{
  "schema_version": "1.0",
  "request_id": "req-backend-ai-20260828-0001",
  "as_of": "2026-08-28T14:30:00+02:00",
  "identity": {},
  "customer": {},
  "contract": {},
  "records": [],
  "payments": [],
  "data_quality": {}
}
```

Champs racine obligatoires :

- `schema_version` : toujours `"1.0"`.
- `request_id` : identifiant unique de correlation/idempotence.
- `as_of` : date du snapshot, ISO 8601 ou timestamp Unix.
- `identity` : rattachement client-kit-device resolu par le backend.
- `customer` : profil client et valeur client.
- `contract` : contrat commercial actif ou connu.
- `records` : fenetre de telemetrie brute du kit/device.
- `payments` : historique brut des paiements.
- `data_quality` : statut de resolution, fraicheur, champs manquants et warnings.

Champs racine optionnels mais recommandes :

- `source` : provenance backend.
- `subscription` : alias/compatibilite avec donnees d'abonnement.
- `installation` : position, geofence et type d'installation.
- `kit` : caracteristiques materiel/firmware.
- `context` : region, saison, meteo et zone de risque.
- `payment` : agregats paiement deja calcules, si disponibles.
- `kit_intelligence` : prediction kit deja calculee, seulement si le backend en possede une fiable.
- `consents` : consentements d'usage des donnees.
- `options` : options d'appel.

## Points non negociables

- `identity.resolution_status` doit etre `resolved` pour une decision client fiable.
- `identity.client_id`, `identity.contract_id` et `identity.assignment_id` doivent etre presents pour eviter une confiance reduite.
- `records[]` doit contenir au moins une mesure, idealement 3 a 100 mesures recentes, triees par `event_time`.
- Chaque mesure `records[]` doit avoir `message_type: "telemetry"` et les champs batterie obligatoires.
- `payments[]` doit contenir les paiements bruts, idealement 6 a 12 mois.
- Les statuts paiement attendus sont `paid`, `completed`, `success`, `successful`, `settled`, `late`, `missed`, `pending`, `overdue`, `unpaid`, `failed`, `rejected`, `cancelled`, `canceled`, `unknown`.
- Les champs inconnus sont acceptes dans les sous-objets metier, mais les champs du contrat canonique doivent garder les noms exacts.

## Exemple complet backend

```json
{
  "schema_version": "1.0",
  "request_id": "req-backend-ai-20260903-0001",
  "as_of": "2026-09-03T13:30:00+02:00",
  "identity": {
    "client_id": "client-923",
    "kit_id": "kit-034",
    "device_id": "device-001",
    "installation_id": "installation-674",
    "contract_id": "contract-884",
    "assignment_id": "assignment-889",
    "resolution_status": "resolved"
  },
  "customer": {
    "customer_segment": "residential",
    "tenure_months": 18,
    "active_contracts": 1
  },
  "contract": {
    "contract_id": "contract-884",
    "status": "active",
    "periodic_amount_usd": 20
  },
  "records": [
    {
      "message_id": "msg-device-001-0001",
      "schema_version": "1.0",
      "message_type": "telemetry",
      "device_id": "device-001",
      "kit_id": "kit-034",
      "serial_number": "SN-KIT-034",
      "event_time": "1788434940",
      "sequence_number": 1,
      "battery_voltage_v": 12.6,
      "battery_current_a": 1.1,
      "battery_power_w": 13.9,
      "state_of_charge_pct": 67,
      "state_of_health_pct": 86,
      "battery_error_code": "NONE",
      "solar_power_w": 63,
      "solar_error_code": "NONE",
      "load_power_w": 44,
      "overload_detected": false,
      "abnormal_consumption_detected": false,
      "geofence_status": "outside",
      "speed_mps": 1.6,
      "enclosure_opened": true,
      "region": "kinshasa",
      "season": "dry",
      "day_period": "night",
      "ambient_temperature_c": 29,
      "humidity_pct": 52,
      "device_temperature_c": 38.2,
      "missing_measurement_count": 0
    }
  ],
  "payments": [
    {
      "payment_id": "pay-001",
      "client_id": "client-923",
      "contract_id": "contract-884",
      "due_date": "2026-08-01T00:00:00+02:00",
      "paid_at": "2026-08-01T12:00:00+02:00",
      "amount_due": 20,
      "amount_paid": 20,
      "days_late": 0,
      "status": "paid",
      "method": "orange_money"
    }
  ],
  "data_quality": {
    "identity_resolved": true,
    "missing_features": [],
    "warnings": []
  }
}
```

## Validation

Avant d'envoyer au backend IA/Data, valider le JSON contre :

```powershell
.\.venv\Scripts\python.exe -m json.tool schemas\backend_ai_prediction_scoring_request.v1.schema.json
```

Le schema contient un exemple complet directement dans `examples`.
