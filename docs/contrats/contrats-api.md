# Contrats API

Ce document centralise les contrats entre le pole Data & AI et l'interface DJUA ENERGY.

Etat au 2026-07-20 : le MVP local expose deja le flux principal `POST /telemetry/analyze`.
La presente mise a jour ajoute une surface de demonstration orientee frontend sous `/frontend/*`.
Elle permet a une equipe React ou Next.js de construire les ecrans sans inventer de logique metier critique.

Toutes les reponses de demonstration indiquent :

- `meta.schema_version` : version stable du payload.
- `meta.generated_at` : date de generation.
- `meta.data_mode` : `synthetic_demo` quand les donnees sont simulees.
- `meta.ai_traceability` quand la route melange modele, telemetrie et calculs metier.
- des identifiants coherents entre kits, clients, decisions, alertes et interventions.
- des libelles, statuts, unites, timestamps et messages lisibles.

## Regle de verite IA

Les routes `/frontend/*` appellent maintenant les modeles locaux via `LocalInferenceEngine`.
Pour chaque kit de demonstration, l'API construit une fenetre de telemetrie puis execute :

- `engine.infer_maintenance(records)` pour la probabilite de risque technique.
- `engine.infer_security(records)` pour le score d'activite suspecte.
- `build_alert_decision(...)` pour transformer les deux sorties modele en priorite d'alerte.

Les payloads exposent la provenance avec les valeurs suivantes :

- `model_output` : valeur sortie directement du modele ou de ses metadonnees.
- `model_derived` : valeur calculee a partir des sorties modele, par exemple score consolide, criticite, alerte ou recommandation.
- `model_feature` : feature calculee depuis la telemetrie et entree dans le modele.
- `telemetry` : mesure brute envoyee par le boitier ou par le generateur synthetique.
- `telemetry_derived` : aggregation simple de telemetrie, par exemple energie totale ou disponibilite.
- `artifact_metadata` : information lue depuis `artifacts/metadata.json`.
- `not_available` : information que les modeles actuels ne savent pas produire.

Les modeles actuels ne produisent pas encore :

- score paiement client ;
- ROI financier ;
- MTTR reel ;
- taux de confirmation ou faux positifs bases sur feedback humain ;
- derive MLOps ;
- cout reel d'intervention ;
- duree reelle d'intervention ;
- explication SHAP ou contribution mathematique exacte par feature.

Quand une route doit afficher ces notions, elle retourne `null` ou `not_available` avec une explication au lieu d'inventer un resultat.

## Routes existantes MVP

| Methode | Route | Usage |
| --- | --- | --- |
| `GET` | `/health` | Verifier que l'API locale repond. |
| `POST` | `/telemetry/analyze` | Flux principal : validation, idempotence, inference IA, alerte, audit, metriques. |
| `GET` | `/telemetry/metrics` | Lire les metriques en memoire. |
| `GET` | `/telemetry/quarantine` | Lire les records invalides mis en quarantaine. |
| `GET` | `/telemetry/audit` | Lire le journal d'audit local. |
| `POST` | `/maintenance/predict` | Tester directement le modele maintenance. |
| `POST` | `/security/predict` | Tester directement le modele securite. |
| `POST` | `/demo/generate` | Generer quelques records de demo. |

## Routes frontend ajoutees

| Methode | Route | Ecran alimente |
| --- | --- | --- |
| `GET` | `/frontend/command-center` | Executive AI Command Center. |
| `GET` | `/frontend/decisions/{decision_id}` | Decision Investigation Workspace. |
| `GET` | `/frontend/kits/{kit_id}/digital-twin` | Smart Kit Digital Twin. |
| `GET` | `/frontend/fleet` | Fleet Monitoring. |
| `GET` | `/frontend/customers/{client_id}/risk-profile` | Customer Risk Profile. |
| `GET` | `/frontend/performance` | Performance & Outcomes. |
| `GET` | `/frontend/admin/data-ai` | Administration technique Data & AI. |
| `GET` | `/frontend/realtime/events` | Evenements quasi temps reel pour animation frontend. |

## Continuite metier garantie dans la demo

Les donnees de demonstration utilisent des identifiants stables :

- `kit-0` est relie a `device-0`, `client-001`, `decision-001`, `alert-001` et `intervention-001`.
- `kit-1` est relie a `device-1`, `client-002`, `decision-002`, `alert-002` et `intervention-002`.
- `kit-2` est relie a `device-2`, `client-003` et `decision-003`.

Cette continuite permet au frontend de naviguer depuis une alerte vers une decision, puis vers le kit, le client et l'intervention recommandee sans perdre le contexte.

## Executive AI Command Center

`GET /frontend/command-center` retourne :

- `summary` : indicateurs prets a afficher avec valeur, unite, periode, valeur precedente, variation, tendance, etat, fraicheur et sparkline.
- `priority_alerts` : alertes IA avec criticite, kit, client, localisation, statut de revue et action recommandee.
- `fleet_map` : points GPS, clusters, heatmap et filtres disponibles.
- `decision_engine` : volumes de decisions, severites, statuts, taux de confirmation, faux positifs et temps moyen de revue.
- `system_status` : ingestion, IA et connectivite IoT avec statut, message, disponibilite et impact.
- `recent_activity` : flux d'evenements recents avec acteur, entite liee, criticite et statut.

Les compteurs de decisions, kits a risque et alertes sont `model_derived`.
L'energie, la disponibilite et la position viennent de la telemetrie.
Les taux de confirmation, faux positifs et temps de revue sont `not_available` tant que le feedback humain n'est pas persiste.

Exemple d'appel :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/frontend/command-center
```

## Decision Investigation Workspace

`GET /frontend/decisions/decision-001` retourne :

- `decision` : resume complet de la decision IA.
- `natural_language_explanation` : texte lisible par un responsable operationnel.
- `risk_factors` : facteurs avec valeur observee, valeur attendue, unite, contribution, source et date.
- `score_history` : serie temporelle exploitable dans un graphique.
- `evidence` : preuves avec fiabilite, pertinence et explication.
- `timeline` : etapes depuis la telemetrie jusqu'a la decision.
- `recommendations` : proposition d'intervention.
- `feedback_options` : valeurs acceptables pour un futur retour humain.

Le score de decision est `model_output`.
L'historique de score est recalcule point par point en appelant les modeles sur les prefixes de la fenetre.
Les facteurs affiches sont les sorties modele et les features d'entree. Ils expliquent les signaux disponibles, mais ne sont pas encore des contributions SHAP.

## Smart Kit Digital Twin

`GET /frontend/kits/kit-0/digital-twin` retourne :

- `identity` : identite kit, device, client, firmware, region et statut.
- `health` : score global, tendance, confiance, horizon et recommandation.
- `battery`, `solar`, `load`, `connectivity`, `physical_security`, `location`.
- `components` : batterie et module IoT avec statut, score, unite et recommandation.
- `telemetry` : serie temporelle graphique.
- `events` : evenements lies au kit.
- `maintenance_prediction` : probabilite de panne, horizon, composant, priorite et action suggeree.

La prediction de maintenance vient de `infer_maintenance`.
Les mesures batterie, solaire, charge, connectivite, securite physique et localisation viennent de la derniere telemetrie analysee.

## Fleet Monitoring

`GET /frontend/fleet` retourne :

- `summary` : total, online, offline, a risque, en intervention, anomalies.
- `kits` : liste paginee des kits avec score, risque, connectivite, alerte et intervention active.
- `pagination` : page, taille, total, tri et filtres appliques.
- `map` : points et couches disponibles.
- `location_history` : trajectoires simplifiees.

Le risque par kit vient des sorties modele.
La localisation et le statut reseau viennent de la telemetrie.

## Customer Risk Profile

`GET /frontend/customers/client-001/risk-profile` retourne :

- `customer` : score, niveau, tendance, version modele, confiance et facteurs.
- `payment_risk` : risque paiement avec contexte.
- `consumption` : profil d'usage et comparaison.
- `kit_risk` : signaux kit lie au client.
- `recommendations` : actions proposees avec justification.

Il n'existe pas encore de modele client dedie dans le MVP.
Le score client est donc `model_derived` depuis le risque IA du kit rattache.
Le risque paiement est `not_available`.

## Performance & Outcomes

`GET /frontend/performance` retourne :

- `operational_kpis` : KPI avec variations et unites.
- `energy_impact` : energie generee, energie sauvee, CO2 evite et methode.
- `financial_impact` : economies, pertes evitees, ROI, methodologie et incertitude.
- `models` : precision, recall, F1, faux positifs, periode et sante modele.
- `drift` : derive data/features/predictions et recommandation.

Les performances modeles viennent de `artifacts/metadata.json`.
Les champs non presents dans les artefacts, comme precision, recall, F1 et taux de faux positifs, sont retournes a `null`.
Les chiffres financiers, la derive et le MTTR sont `not_available` tant que les donnees necessaires ne sont pas branchees.

## Administration Data & AI

`GET /frontend/admin/data-ai` retourne :

- `models` : modeles charges, versions, environnement, date d'entrainement et schema.
- `pipelines` : ingestion et feature pipeline avec statut, duree, volumes valides/rejetes et doublons.
- `data_quality` : completude, retards, erreurs de validation et message lisible.

Cette route lit l'etat des modeles depuis le moteur charge et `artifacts/metadata.json`.
La qualite globale est `not_available`; les rejets runtime restent consultables via `/telemetry/quarantine`.

## Temps reel

`GET /frontend/realtime/events` simule un flux quasi temps reel.

Chaque evenement contient :

- `event_id`, `type`, `version`, `timestamp`.
- `entity` concernee.
- `old_values` et `new_values`.
- `severity`, `source`, `correlation_id`.
- `message` lisible et `suggested_action`.

Transport actuel : polling demo. Chemin cible : SSE ou WebSocket lorsque l'application passera en temps reel complet.
Les evenements sont derives des decisions modele courantes, mais le transport temps reel n'est pas encore persistant.

## Erreurs

Les routes de detail retournent une erreur structuree si l'entite est absente :

```json
{
  "error": {
    "code": "DECISION_NOT_FOUND",
    "message": "decision introuvable",
    "field": "decision_id",
    "suggestion": "Verifier l'identifiant fourni.",
    "request_id": "req-decision-999",
    "severity": "warning",
    "temporary": false
  }
}
```

## Test CLI

Demarrer l'API :

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload
```

Tester le flux telemetry existant :

```powershell
.\.venv\Scripts\python.exe scripts\demo_telemetry_api.py
```

Tester le contrat frontend ajoute :

```powershell
.\.venv\Scripts\python.exe scripts\demo_telemetry_api.py --frontend-contract
```

Le CLI appelle les routes principales `/frontend/*`, affiche le schema retourne, le mode de donnees et les cles principales. Il sort en erreur si une route ne repond pas.

## Limites actuelles

- Les endpoints frontend utilisent des donnees synthetiques coherentes, pas encore une base persistante.
- Les scores, decisions, alertes, risques kit et predictions maintenance/securite viennent bien des modeles locaux.
- Les donnees non couvertes par les modeles sont marquees `not_available` ou `demo_assumption_not_model_output`.
- Le temps reel est simule par polling.
- Le feedback humain est expose comme options de contrat mais n'est pas encore persiste.
- Les filtres, tris et pages sont documentes dans les payloads, mais le filtrage serveur complet reste a implementer.
- L'authentification, les roles et le controle d'acces restent a ajouter avant usage production.
