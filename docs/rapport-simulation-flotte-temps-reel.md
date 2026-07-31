# Rapport - Simulation flotte temps reel

## Objectif

La simulation temps reel represente une flotte de devices Djua Energy deja installes sur le terrain. Les modeles IA sont deja entraines dans `artifacts/`; ils ne reapprennent pas pendant la simulation. A chaque tick, chaque device envoie une mesure complete a l'API, l'API sauvegarde la telemetrie, calcule les features, execute les modeles et sauvegarde la prediction.

## Flux implemente

```text
simulate_fleet_realtime.py
-> genere un payload complet par device
-> POST /telemetry/analyze, un device a la fois
-> validation du contrat telemetry
-> insertion dans data/runtime/djua_realtime.sqlite
-> recuperation de la fenetre recente du device
-> inference maintenance + securite
-> decision d'alerte
-> sauvegarde prediction_history
-> mise a jour device_state
```

Un POST par device est volontaire. L'endpoint actuel calcule la prediction pour le dernier device de la fenetre recue. En envoyant un device par appel, chaque device garde son historique et sa prediction temps reel sans incoherence de melange entre devices.

## Variables envoyees

Chaque payload contient les champs obligatoires du contrat :

```text
message_id, schema_version, message_type, device_id, kit_id, serial_number,
event_time, sequence_number, battery_voltage_v, battery_current_a,
battery_power_w, battery_temperature_c, state_of_charge_pct,
state_of_health_pct
```

Le simulateur envoie aussi les variables necessaires aux features IA :

```text
region, season, day_period, ambient_temperature_c, humidity_pct,
solar_irradiance_w_m2, network_quality, installation_type,
battery_age_months, usage_profile, security_risk_zone,
solar_power_w, load_power_w, charge_duration_seconds,
discharge_duration_seconds, battery_error_code, solar_error_code,
overload_detected, short_circuit_detected, connectivity_gap_seconds,
device_temperature_c, reset_count, missing_measurement_count,
sensor_failure_detected, abnormal_consumption_detected,
latitude, longitude, gps_accuracy_m, distance_from_installation_m,
geofence_status, speed_mps, movement_detected, movement_duration_seconds,
movement_event_count, tamper_detected, enclosure_opened, impact_detected,
identity_mismatch_detected, network_operator
```

## Coherence temporelle

Par defaut, la simulation tourne en continu :

```text
--cycles 0
--interval-seconds 300
--sleep-seconds 0
```

Cela signifie : continuer a envoyer des mesures jusqu'a l'arret manuel avec `Ctrl+C`.

Pour une demonstration courte finie :

```powershell
.\.venv\Scripts\python.exe scripts\simulate_fleet_realtime.py --cycles 18
```

Cela signifie 18 mesures par device, espacees de 5 minutes dans le temps simule. Le test est rapide parce que `sleep-seconds` vaut 0.

L'age batterie est incremente selon le temps ecoule :

```text
battery_age_months = age_initial + elapsed_seconds / 30 jours
```

La batterie evolue avec un bilan energetique simple :

```text
energie solaire generee - energie consommee
-> variation du state_of_charge_pct
```

La temperature ambiante change selon :

```text
region + saison + heure de jour + variation meteo
```

La production solaire change selon :

```text
irradiance + saison + jour/nuit + type d'installation + nuages
```

La position GPS reste stable pour les devices normaux. Dans le scenario `security_movement`, la position derive progressivement, la distance depasse le rayon autorise et le geofence passe a `outside`.

## Scenarios de flotte

Le simulateur cree par defaut 6 devices :

```text
device-001 : normal
device-002 : battery_degradation
device-003 : overheating
device-004 : low_solar_input
device-005 : security_movement
device-006 : connectivity_loss
```

## Commandes jury

PowerShell 1 :

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn apps.api.main:app --reload
```

PowerShell 2 :

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\simulate_fleet_realtime.py
```

Arreter la simulation :

```text
Ctrl+C
```

Commande de demonstration internationale :

```powershell
.\scripts\demo_jury_realtime_fleet.ps1
```

Verification de la base temps reel :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/realtime/fleet-state
Invoke-RestMethod http://127.0.0.1:8000/realtime/devices/device-001/predictions
```

## Lecture simple pour presentation

```text
Les boitiers envoient leurs variables toutes les 5 minutes.
L'API valide et memorise chaque mesure.
La base garde l'historique par device.
L'IA analyse la fenetre recente du device.
La prediction et l'etat courant sont sauvegardes.
Le dashboard ou le jury peut lire l'etat de la flotte en temps reel.
```
