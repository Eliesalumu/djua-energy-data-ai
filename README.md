# Djua Energy Data & AI

Plateforme locale Data, IA et IoT pour la supervision de kits solaires Pay-As-You-Go.

Le projet est aujourd'hui un MVP demonstrable : il simule des donnees de boitier, construit des features, execute des modeles locaux de maintenance/securite, priorise les alertes et expose une API FastAPI locale.

## Etat Actuel

Les briques suivantes sont operationnelles en local :

- dataset MVP synthetique coherent dans `data/generated/mvp_dataset.csv` ;
- generation de donnees IoT dans `src/djua_energy/pipeline/synthetic_data.py` ;
- contrat minimal de validation dans `src/djua_energy/pipeline/contracts.py` ;
- calcul de features maintenance et securite dans `src/djua_energy/pipeline/features.py` ;
- entrainement local dans `src/djua_energy/pipeline/train.py` ;
- artefacts modeles dans `artifacts/` ;
- inference locale dans `src/djua_energy/pipeline/inference.py` ;
- CLI de demonstration jury dans `scripts/predict_device_cli.py` ;
- API FastAPI locale dans `apps/api/main.py` ;
- ingestion MVP avec validation, anti-doublon, quarantaine, audit, metriques et alerte ;
- module DJUA AI Solar Advisor pour recommander un kit solaire avant installation ;
- tests unitaires couvrant le pipeline, l'ingestion et les handlers API.

## Flux MVP

```text
Boitier ou simulateur
-> POST /telemetry/analyze
-> validation
-> quarantaine si invalide
-> anti-doublon
-> inference IA maintenance + securite
-> priorisation alerte
-> audit + metriques
-> reponse API
```

Le CLI de demonstration utilise le dataset existant :

```text
data/generated/mvp_dataset.csv
-> conversion en payloads telemetry
-> inference IA
-> presentation par scenario
-> synthese finale par niveau d'alerte
```

## API Locale

Lancer l'API :

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload
```

Endpoints principaux :

```text
GET  /health
POST /telemetry/analyze
GET  /telemetry/metrics
GET  /telemetry/quarantine
GET  /telemetry/audit
POST /maintenance/predict
POST /security/predict
POST /v1/customer/evaluate
POST /v1/customer/evaluate-from-telemetry
GET  /v1/customers
GET  /v1/customers/{client_id}
GET  /v1/customer/decisions
GET  /v1/customer/decisions/{decision_id}
GET  /v1/predictions
POST /demo/generate
```

Les endpoints `/maintenance/predict` et `/security/predict` sont des endpoints directs de test modele. Le flux principal MVP est `/telemetry/analyze`.

Pour la decision client multidimensionnelle, le backend metier doit envoyer une identite client-kit deja resolue
dans `identity`, avec `resolution_status`. `/v1/customer/evaluate` consomme un snapshot deja enrichi avec
`kit_intelligence`. Si le backend appelant dispose de la telemetrie brute, utiliser
`/v1/customer/evaluate-from-telemetry` : l'API calcule alors uniquement maintenance/securite localement avant
d'appeler le moteur de decision client. L'API IA ne resout pas les affectations client-kit.
Le backend envoie l'historique brut dans `payments[]`; l'API IA/Data calcule les features paiement (`payment_success_rate`,
retards, echecs, jours depuis dernier paiement, solde ouvert) avant le scoring.

Les mesures recues par `/telemetry/analyze` et `/v1/customer/evaluate-from-telemetry` sont stockees dans
`telemetry_records`, puis les predictions utilisent la fenetre historique recente du device pour capter les tendances.
Le stockage IA/Data repose sur cinq tables principales: `customers`, `telemetry_records`, `prediction_history`,
`device_state` et `customer_decision_history`. Les decisions client sont historisees dans
`customer_decision_history`; les profils clients et derniers scores sont relisibles via `/v1/customers`, et les
predictions techniques filtrees par client/kit/device via `/v1/predictions`.

## Demonstrations

Demo CLI par device :

```powershell
.\.venv\Scripts\python.exe scripts\predict_device_cli.py
```

Demo API vers `/telemetry/analyze` :

```powershell
.\.venv\Scripts\python.exe scripts\demo_telemetry_api.py
```

Demo flotte temps reel multi-devices :

```powershell
.\.venv\Scripts\python.exe scripts\simulate_fleet_realtime.py
```

La commande ci-dessus tourne en continu jusqu'a `Ctrl+C`. Pour une demo courte :

```powershell
.\.venv\Scripts\python.exe scripts\simulate_fleet_realtime.py --cycles 18
```

Demo jury internationale temps reel :

```powershell
.\scripts\demo_jury_realtime_fleet.ps1
```

Demo conseil energetique et recommandation de kit :

```powershell
.\.venv\Scripts\python.exe scripts\demo_solar_advisor.py
```

Generer le dataset synthetique Solar Advisor de 100 000 lignes :

```powershell
.\.venv\Scripts\python.exe scripts\generate_solar_advisor_dataset.py --rows 100000
```

Endpoints Solar Advisor :

```text
GET  /solar-advisor/catalogs
POST /solar-advisor/recommend
POST /solar-advisor/conversation
GET  /solar-advisor/recommendations
GET  /solar-advisor/recommendations/{recommendation_id}
POST /solar-advisor/recommendations/{recommendation_id}/contact
POST /solar-advisor/recommendations/{recommendation_id}/explain
```

Pour activer l'explication IA apres devis, configurer une nouvelle cle OpenAI en variable d'environnement, jamais dans le code :

```powershell
$env:OPENAI_API_KEY="votre_nouvelle_cle"
```

## Donnees Boitier Attendues

Le boitier envoie des mesures brutes. Le pipeline calcule ensuite les features IA.

Champs obligatoires acceptes par le validateur :

- `message_id`
- `schema_version`
- `message_type`
- `device_id`
- `kit_id`
- `serial_number`
- `event_time`
- `sequence_number`
- `battery_voltage_v`
- `battery_current_a`
- `battery_power_w`
- `battery_temperature_c`
- `state_of_charge_pct`
- `state_of_health_pct`

Champs de contexte attendus pour la prediction v2 :

- `region`
- `season`
- `day_period`
- `ambient_temperature_c`
- `humidity_pct`
- `solar_irradiance_w_m2`
- `network_quality`
- `installation_type`
- `battery_age_months`
- `usage_profile`
- `security_risk_zone`

Champs fortement recommandes pour prediction complete :

- solaire : `solar_voltage_v`, `solar_current_a`, `solar_power_w`, `energy_generated_wh`
- consommation : `load_voltage_v`, `load_current_a`, `load_power_w`, `energy_consumed_wh`
- securite : `movement_detected`, `tamper_detected`, `enclosure_opened`, `impact_detected`
- localisation : `latitude`, `longitude`, `gps_accuracy_m`, `distance_from_installation_m`, `geofence_status`, `speed_mps`
- connectivite : `connection_status`, `connectivity_type`, `connectivity_gap_seconds`, `network_operator`
- sante boitier : `device_temperature_c`, `reset_count`, `sensor_failure_detected`, `missing_measurement_count`

## Structure

```text
apps/       API locale, simulateur et worker futurs
artifacts/  modeles et metadonnees locales
data/       donnees generees, brutes, features et synthetiques
docs/       documentation architecture, contrats, donnees, roadmap
schemas/    schemas JSON des contrats
scripts/    scripts de demonstration et outillage
src/        code Python modulaire
tests/      tests unitaires et futurs tests integration
```

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Ce Qui Reste A Faire

- aligner progressivement tous les documents avec le code MVP actuel ;
- enrichir les tests API et integration ;
- ajouter une persistance reelle pour audit, metriques, quarantaine et alertes ;
- implementer le simulateur IoT actif ;
- preparer les modules database, worker, feedback technicien et MLOps ;
- renforcer securite API : authentification, gestion clients, droits, rate limiting ;
- exposer une documentation OpenAPI exportee et partageable.

## Prochaine Priorite

La prochaine priorite est de stabiliser le contrat de telemetrie et les tests API autour du flux complet :

```text
/telemetry/analyze -> validation -> IA -> alerte -> audit -> metriques
```

Cela rend le MVP transmissible au backend, au fabricant du boitier et au jury.
