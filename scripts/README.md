# Scripts

Scripts utiles pour generer des donnees, lancer des demonstrations et simuler les integrations.

## Simulation backend complete

```powershell
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 8 --sleep-seconds 0.2
```

Ce script simule le backend metier. Il appelle `POST /v1/customer/evaluate-from-telemetry` avec:

```text
identity resolue
customer
contract
payments[] bruts
records[] telemetry
context
data_quality
```

Puis il relit:

```text
GET /v1/customers/{client_id}
GET /v1/predictions?client_id=...
GET /v1/customer/decisions?client_id=...
GET /realtime/devices/{device_id}/state
```

Runbook detaille:

```text
docs/runbooks/simulation-backend-temps-reel.md
```

## Synchronisation depuis un backend metier

```powershell
.\.venv\Scripts\python.exe scripts\sync_backend_resolved_events.py --backend-url http://127.0.0.1:9000 --limit 100
```

Ce script demande a l'API IA/Data locale de consommer:

```text
GET /v1/ai/resolved-telemetry-events
POST /v1/ai/resolved-telemetry-events/{request_id}/ack
```

Le traitement interne reutilise le meme pipeline que `POST /v1/customer/evaluate-from-telemetry`.
