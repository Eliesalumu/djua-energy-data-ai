# Simulation backend temps reel vers API IA/Data

Ce runbook montre le flux complet sans vrai backend metier. Le script joue le role du backend: il envoie une identite client-kit resolue, un client, un contrat, des paiements bruts `payments[]` et une mesure telemetry a chaque cycle.

## 1. Demarrer l'API

Dans un premier PowerShell:

```powershell
cd C:\Users\PC\djua-energy-data-ai
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

## 2. Lancer le backend simule

Dans un deuxieme PowerShell:

```powershell
cd C:\Users\PC\djua-energy-data-ai
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 8 --sleep-seconds 0.2
```

Par defaut, le script cree un client/device unique a chaque lancement. Cela evite que l'historique d'une ancienne demo rende la colonne `historique_utilise` difficile a comprendre.

Pour reutiliser toujours `client-sim-001` et `device-sim-001`:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 8 --fixed-demo-ids
```

Pour montrer un client bon payeur afin que la decision soit surtout portee par le risque technique:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 8 --payment-profile good
```

Pour montrer un client avec retards de paiement:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 8 --payment-profile late
```

Pour afficher le premier JSON envoye:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 3 --show-first-payload
```

## 3. Consommer un backend metier reel

Si le backend metier expose lui-meme les snapshots resolus, l'API IA/Data peut maintenant les consommer en mode pull.

Le backend metier doit exposer:

```text
GET  /v1/ai/resolved-telemetry-events?cursor=...&limit=...
POST /v1/ai/resolved-telemetry-events/{request_id}/ack
```

L'API IA/Data expose le declencheur:

```text
POST /v1/backend-sync/resolved-telemetry-events/run
```

Depuis PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\sync_backend_resolved_events.py --backend-url http://127.0.0.1:9000 --limit 100
```

Ce script demande a l'API IA/Data de:

```text
1. appeler le backend metier
2. lire items[]
3. valider chaque snapshot
4. calculer predictions et scoring
5. stocker les resultats localement
6. envoyer un ACK technique au backend
```

## 4. Ce que le script push envoie

Chaque appel cible:

```text
POST /v1/customer/evaluate-from-telemetry
```

Le payload contient:

```text
identity      -> client_id, kit_id, device_id, contract_id, assignment_id, resolution_status
customer      -> segment, anciennete, nombre de contrats actifs
contract      -> statut et montant periodique
payments[]    -> paiements bruts Orange/backend
records[]     -> telemetry brute du kit
context       -> region, saison, temperature, periode
data_quality  -> etat qualite declare par le backend
```

Le backend simule n'envoie pas `payment_success_rate` ou `late_payments_last_6_months`. Ces features sont calculees par l'API IA/Data depuis `payments[]`.

## 5. Ce qui se passe dans l'API

Ordre du flux:

```text
1. L'API recoit le JSON backend.
2. Elle valide records[].
3. Elle calcule les features paiement depuis payments[].
4. Elle stocke les mesures dans telemetry_records avec client_id/kit_id/device_id.
5. Elle recharge l'historique du device.
6. Elle calcule les trends techniques.
7. Elle produit maintenance/security.
8. Elle stocke prediction_history.
9. Elle met a jour device_state.
10. Elle construit kit_intelligence.
11. Elle calcule le scoring client.
12. Elle stocke customer_decision_history.
13. Elle met a jour customers.
14. Elle retourne la decision.
```

Dans PowerShell, chaque cycle affiche des blocs JSON lisibles:

```text
MESURE 1/8
JSON recu du backend
-> identite client/kit/device, contrat, assignment, client, paiements bruts et mesure du kit

Interpretation IA
-> phrase courte pour expliquer le scenario de demo

JSON produit par l'API IA/Data
-> historique utilise, scores calcules, decision et tables alimentees
```

Important: le JSON de mesure est groupe par famille de signaux:

```text
identification_mesure
batterie
solaire
consommation
securite_et_position
connectivite_et_boitier
contexte
```

Cela montre que la prediction ne se base pas seulement sur temperature/sante/tension, mais sur un ensemble de signaux techniques et sur l'historique deja stocke.

Pour afficher aussi les noms techniques des tables et IDs:

```powershell
.\.venv\Scripts\python.exe scripts\simulate_backend_full_flow.py --ticks 8 --technical
```

## 6. Lecture frontend apres simulation

Le script relit automatiquement:

```text
GET /v1/customers/{client_id}
GET /v1/predictions?client_id=...
GET /v1/customer/decisions?client_id=...
GET /realtime/devices/{device_id}/state
```

Pour un dashboard complet alimente par les donnees reelles stockees cote IA/Data:

```text
GET /frontend/live/ui
```

Ce payload agrege `device_state`, `prediction_history`, `telemetry_records`, `customers` et `customer_decision_history`.

Commandes manuelles:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/v1/customers/client-sim-001
Invoke-RestMethod "http://127.0.0.1:8000/v1/predictions?client_id=client-sim-001&limit=5"
Invoke-RestMethod "http://127.0.0.1:8000/v1/customer/decisions?client_id=client-sim-001&limit=5"
Invoke-RestMethod http://127.0.0.1:8000/realtime/devices/device-sim-001/state
```

## 7. Tables alimentees

```text
customers
telemetry_records
prediction_history
device_state
customer_decision_history
```

Cette simulation permet de verifier que les donnees arrivent comme attendu du backend, que l'IA calcule les features/trends, que les scores sont produits, puis que le frontend peut relire les resultats.
