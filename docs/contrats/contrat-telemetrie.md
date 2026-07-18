# Contrat Telemetrie v1

Ce contrat decrit les donnees brutes attendues depuis le boitier ou un backend passerelle. Le boitier n'envoie pas les features IA. Il envoie des mesures terrain ; le pipeline calcule ensuite les variables de prediction.

## Flux Cible

```text
Boitier
-> backend ou passerelle IoT
-> POST /telemetry/analyze
-> validation
-> IA maintenance + securite
-> priorisation alerte
```

## Frequence Recommandee

- Telemetrie normale : toutes les 5 a 15 minutes.
- Minimum acceptable MVP : toutes les 30 minutes.
- Evenement securite : envoi immediat.
- Perte reseau : stockage local puis envoi au retour de connectivite.

## Champs Obligatoires MVP Et Contexte Attendu

Les champs techniques de base restent obligatoires pour accepter un message. Les champs de contexte sont attendus pour exploiter completement le modele v2 avec regions, saisons, meteo, usage et risque securite.

| Champ | Type | Unite | Description |
|---|---|---:|---|
| `message_id` | string | - | Identifiant unique du message |
| `schema_version` | string | - | Version du contrat, ex: `1.0` |
| `message_type` | string | - | `telemetry` |
| `device_id` | string | - | Identifiant boitier |
| `kit_id` | string | - | Identifiant kit solaire |
| `serial_number` | string | - | Numero de serie fabricant |
| `event_time` | string | timestamp | Date/heure de mesure |
| `sequence_number` | integer | - | Numero croissant du message |
| `battery_voltage_v` | number | V | Tension batterie |
| `battery_current_a` | number | A | Courant batterie |
| `battery_power_w` | number | W | Puissance batterie |
| `battery_temperature_c` | number | C | Temperature batterie |
| `state_of_charge_pct` | number | % | Niveau de charge |
| `state_of_health_pct` | number | % | Sante batterie estimee |
| `region` | string | - | Region ou zone geographique |
| `season` | string | - | `dry`, `rainy`, `harmattan`, `transition` |
| `day_period` | string | - | `day` ou `night` |
| `ambient_temperature_c` | number | C | Temperature exterieure |
| `humidity_pct` | number | % | Humidite relative |
| `solar_irradiance_w_m2` | number | W/m2 | Ensoleillement |
| `network_quality` | string | - | `good`, `medium`, `weak` |
| `installation_type` | string | - | Type d'installation |
| `battery_age_months` | integer | mois | Age batterie |
| `usage_profile` | string | - | `low`, `normal`, `intensive` |
| `security_risk_zone` | string | - | `low`, `medium`, `high` |

## Champs Recommandes Pour Maintenance

| Champ | Type | Unite | Utilisation IA |
|---|---|---:|---|
| `charge_duration_seconds` | number | s | Analyse charge |
| `discharge_duration_seconds` | number | s | Analyse decharge |
| `solar_power_w` | number | W | Ratio production / consommation |
| `load_power_w` | number | W | Consommation du kit |
| `battery_error_code` | string | - | Erreur BMS |
| `solar_error_code` | string | - | Erreur controleur solaire |
| `reset_count` | integer | - | Instabilite boitier |
| `missing_measurement_count` | integer | - | Qualite capteurs |
| `connectivity_gap_seconds` | integer | s | Silence reseau |
| `device_temperature_c` | number | C | Temperature interne boitier |
| `overload_detected` | boolean | - | Surcharge electrique |
| `short_circuit_detected` | boolean | - | Court-circuit |

## Champs Recommandes Pour Securite

| Champ | Type | Unite | Utilisation IA |
|---|---|---:|---|
| `movement_detected` | boolean | - | Deplacement detecte |
| `movement_duration_seconds` | number | s | Duree mouvement |
| `movement_event_count` | number | - | Nombre d'evenements |
| `tamper_detected` | boolean | - | Manipulation suspecte |
| `enclosure_opened` | boolean | - | Boitier ouvert |
| `impact_detected` | boolean | - | Choc detecte |
| `latitude` | number | degres | Position GPS |
| `longitude` | number | degres | Position GPS |
| `gps_accuracy_m` | number | m | Precision GPS |
| `distance_from_installation_m` | number | m | Distance a la position autorisee |
| `geofence_status` | string | - | `inside` ou `outside` |
| `speed_mps` | number | m/s | Vitesse de deplacement |
| `identity_mismatch_detected` | boolean | - | Incoherence identite/SIM |
| `network_operator` | string | - | Operateur reseau |
| `sensor_failure_detected` | boolean | - | Capteur securite indisponible |
| `abnormal_consumption_detected` | boolean | - | Usage anormal |

## Exemple Minimal

```json
{
  "message_id": "msg-001",
  "schema_version": "1.0",
  "message_type": "telemetry",
  "device_id": "device-1",
  "kit_id": "kit-1",
  "serial_number": "SN-001",
  "event_time": "1700000000",
  "sequence_number": 1,
  "battery_voltage_v": 12.4,
  "battery_current_a": 2.1,
  "battery_power_w": 26.0,
  "battery_temperature_c": 47.0,
  "state_of_charge_pct": 55.0,
  "state_of_health_pct": 90.0,
  "region": "sahel_north",
  "season": "dry",
  "day_period": "day",
  "ambient_temperature_c": 39.5,
  "humidity_pct": 28.0,
  "solar_irradiance_w_m2": 890.0,
  "network_quality": "medium",
  "installation_type": "household_rooftop",
  "battery_age_months": 18,
  "usage_profile": "normal",
  "security_risk_zone": "medium"
}
```

## Exemple Recommande

```json
{
  "message_id": "msg-001",
  "schema_version": "1.0",
  "message_type": "telemetry",
  "device_id": "device-1",
  "kit_id": "kit-1",
  "serial_number": "SN-001",
  "event_time": "1700000000",
  "sequence_number": 1,
  "battery_voltage_v": 12.4,
  "battery_current_a": 2.1,
  "battery_power_w": 26.0,
  "battery_temperature_c": 47.0,
  "state_of_charge_pct": 55.0,
  "state_of_health_pct": 90.0,
  "region": "sahel_north",
  "season": "dry",
  "day_period": "day",
  "ambient_temperature_c": 39.5,
  "humidity_pct": 28.0,
  "solar_irradiance_w_m2": 890.0,
  "network_quality": "medium",
  "installation_type": "household_rooftop",
  "battery_age_months": 18,
  "usage_profile": "normal",
  "security_risk_zone": "medium",
  "solar_power_w": 70.0,
  "load_power_w": 55.0,
  "movement_detected": false,
  "tamper_detected": false,
  "enclosure_opened": false,
  "connectivity_gap_seconds": 0,
  "device_temperature_c": 39.0
}
```
