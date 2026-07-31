# Contrat GUI - Data - IA DJUA Energy

Ce document explique ce que le boitier ou simulateur doit envoyer, comment le backend stocke les donnees, comment les modeles IA travaillent, et ce que le GUI doit appeler pour afficher les 8 interfaces de demonstration.

## 1. Flux complet

```text
Device ou simulateur
-> POST /telemetry/analyze
-> validation du contrat telemetry.v1
-> table telemetry_records
-> recuperation historique recent du meme device
-> feature engineering
-> maintenance_model.joblib + security_model.joblib
-> alert decision engine
-> table prediction_history
-> table device_state
-> GET /frontend/live/ui
-> GUI DJUA Energy
```

## 2. Ce que le device doit envoyer

Toutes les 5 minutes, chaque device envoie un payload complet. Il ne faut pas envoyer la batterie a 10h00 puis le GPS a 10h05. A chaque tick, on envoie toutes les variables importantes mises a jour.

Endpoint :

```http
POST /telemetry/analyze
Content-Type: application/json
```

Body :

```json
{
  "records": [
    {
      "message_id": "fleet-1800000000-device-001-0001",
      "schema_version": "1.0",
      "message_type": "telemetry",
      "device_id": "device-001",
      "kit_id": "kit-001",
      "serial_number": "DJUA-SN-00001",
      "event_time": "1800000000",
      "sequence_number": 1,
      "battery_voltage_v": 13.18,
      "battery_current_a": 3.24,
      "battery_power_w": 42.7,
      "battery_temperature_c": 33.04,
      "state_of_charge_pct": 87.8,
      "state_of_health_pct": 97.7
    }
  ]
}
```

Champs minimum obligatoires :

```text
message_id
schema_version
message_type
device_id
kit_id
serial_number
event_time
sequence_number
battery_voltage_v
battery_current_a
battery_power_w
battery_temperature_c
state_of_charge_pct
state_of_health_pct
```

Champs fortement recommandes pour que le GUI et l'IA soient complets :

```text
region
season
day_period
ambient_temperature_c
humidity_pct
solar_irradiance_w_m2
network_quality
installation_type
battery_age_months
usage_profile
security_risk_zone
solar_voltage_v
solar_current_a
solar_power_w
energy_generated_wh
panel_temperature_c
solar_error_code
load_voltage_v
load_current_a
load_power_w
energy_consumed_wh
overload_detected
short_circuit_detected
latitude
longitude
gps_accuracy_m
distance_from_installation_m
geofence_status
speed_mps
movement_detected
movement_duration_seconds
movement_event_count
tamper_detected
enclosure_opened
impact_detected
identity_mismatch_detected
connectivity_type
connection_status
connectivity_gap_seconds
network_operator
device_temperature_c
reset_count
missing_measurement_count
sensor_failure_detected
abnormal_consumption_detected
battery_error_code
device_error_code
```

## 3. Comment le backend stocke

Base SQLite actuelle :

```text
data/runtime/djua_realtime.sqlite
```

### telemetry_records

Historique brut de tout ce que les devices envoient.

Colonnes principales :

```text
message_id PRIMARY KEY
device_id
kit_id
event_time
sequence_number
scenario
payload_json
inserted_at
```

Le backend garde le payload complet dans `payload_json`. Cela permet d'ajouter des champs sans casser la base.

### prediction_history

Historique des sorties IA.

Colonnes principales :

```text
prediction_id
device_id
kit_id
predicted_at
window_started_at
window_ended_at
records_used
maintenance_probability
security_probability
risk_score
risk_level
alert_priority
recommended_action
maintenance_prediction_json
security_prediction_json
alert_json
feature_snapshot_json
```

### device_state

Dernier etat connu de chaque device, pret pour le dashboard.

Colonnes principales :

```text
device_id PRIMARY KEY
kit_id
last_event_time
last_prediction_at
status
risk_level
risk_score
alert_priority
recommended_action
latest_payload_json
latest_prediction_json
updated_at
```

## 4. Comment les modeles captent les donnees

Le modele ne lit pas directement la base. Le service d'ingestion fait ceci :

```text
1. nouvelle mesure recue
2. insertion dans telemetry_records
3. lecture des dernieres mesures du meme device
4. calcul des features
5. appel maintenance_model.joblib
6. appel security_model.joblib
7. sauvegarde prediction_history
8. mise a jour device_state
```

Features maintenance :

```text
battery_voltage_trend
battery_voltage_volatility
soc_drop
battery_temp_trend
max_battery_temp
charge_duration_seconds
discharge_duration_seconds
solar_load_ratio
health_delta
error_count
reset_frequency
sensor_availability
connectivity_gap
device_temp_internal
solar_controller_instability
overload_signal
short_circuit_signal
electrical_stability
ambient_temperature
humidity_pct
solar_irradiance
battery_age_months
night_operation
usage_intensity
network_quality_score
season_rainy
```

Features securite :

```text
distance_to_installation
geofence_exit
movement_speed
movement_duration
movement_events
enclosure_opened
tamper_events
impact_or_tilt
movement_then_gap
gap_after_opening
device_silence_duration
identity_mismatch
sim_or_operator_change
post_security_reset
security_sensor_missing
abnormal_usage
repeated_suspicious_events
security_risk_zone_score
network_quality_score
mobile_installation
night_operation
```

## 5. Endpoint API pour brancher le GUI

Endpoint live consolide :

```http
GET /frontend/live/ui
```

Ce endpoint lit la vraie base temps reel et renvoie les sections necessaires aux 8 ecrans :

```text
command_center
decision_detail
digital_twin
fleet_monitoring
create_intervention
customer_profile
performance
administration
```

## 6. Mapping avec les 8 interfaces du PowerPoint

### 1. Executive AI Command Center

Source API :

```text
GET /frontend/live/ui -> command_center
```

Affiche :

```text
devices supervises
alertes a traiter
devices hors ligne
sante batterie moyenne
energie generee
alertes prioritaires
activite recente
etat systeme
```

### 2. Decision Detail

Source API :

```text
GET /frontend/live/ui -> decision_detail
```

Affiche :

```text
prediction_id
device_id
records_used
maintenance_probability
security_probability
risk_score
risk_level
recommended_action
feature_snapshot
maintenance_prediction
security_prediction
alert
```

### 3. Smart Kit Digital Twin

Source API :

```text
GET /frontend/live/ui -> digital_twin
```

Affiche :

```text
kit_id
device_id
battery voltage/temp/SOC/SOH/age
solar power
load power
device temperature
connectivity status
GPS
geofence
latest AI prediction
```

### 4. Fleet Monitoring

Source API :

```text
GET /frontend/live/ui -> fleet_monitoring
```

Affiche :

```text
map points
latitude
longitude
region
risk_level
risk_score
status
connectivity_status
geofence_status
filters
```

### 5. Create Intervention

Source API :

```text
GET /frontend/live/ui -> create_intervention
```

Affiche :

```text
recommended_queue
device_id
kit_id
priority
reason
recommended_action
form_options
```

### 6. Customer Profile

Source API actuelle :

```text
GET /frontend/live/ui -> customer_profile
```

Etat actuel :

```text
Les donnees client/paiement ne sont pas encore branchees.
Le GUI peut afficher le contexte risque kit.
Prochaine table a ajouter : customers, payments, customer_interactions.
```

### 7. Performance & Outcomes

Source API :

```text
GET /frontend/live/ui -> performance
```

Affiche :

```text
model_runs
alerts_by_level
energy_generated_kwh
average_battery_health_pct
```

### 8. Administration

Source API :

```text
GET /frontend/live/ui -> administration
```

Affiche :

```text
metadata modeles
tables disponibles
contrat ingestion
etat API/database/modeles
```

## 7. Ce que le developpeur frontend doit faire

1. Lancer le serveur :

```powershell
python -m uvicorn apps.api.main:app --reload
```

2. Alimenter la DB :

```powershell
python scripts\simulate_fleet_realtime.py
```

3. Brancher le GUI sur :

```http
GET http://127.0.0.1:8000/frontend/live/ui
```

4. Lire les sections JSON selon l'ecran :

```text
Command Center      -> response.command_center
Decision Detail     -> response.decision_detail
Digital Twin        -> response.digital_twin
Fleet Monitoring    -> response.fleet_monitoring
Create Intervention -> response.create_intervention
Customer Profile    -> response.customer_profile
Performance         -> response.performance
Administration      -> response.administration
```

