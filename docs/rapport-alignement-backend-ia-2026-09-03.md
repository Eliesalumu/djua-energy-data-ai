# Rapport d'alignement Backend -> IA -> Frontend

Date: 2026-09-03
Contrat de reference: `schemas/backend_ai_prediction_scoring_request.v1.schema.json`
Endpoint principal: `POST /v1/customer/evaluate-from-telemetry`

## 1. Contrat d'entree

Le backend metier envoie un snapshot unique compose de:

- `schema_version`, `request_id`, `as_of`
- `identity`: `client_id`, `kit_id`, `device_id`, references installation/contrat/affectation et `resolution_status`
- `customer`: segment, anciennete et contrats actifs
- `contract`: statut et montant periodique
- `records[]`: fenetre de telemetrie brute du meme kit et device
- `payments[]`: paiements bruts rattaches au client et au contrat
- `data_quality`: resolution, champs manquants et avertissements

La version de contrat est `1.0`. L'identite client-kit-device reste resolue par le backend metier. L'API IA ne tente pas de la deviner.

La requete top-level est fermee pour eviter les sections inconnues. Les records telemetry et paiements restent extensibles, conformement au JSON Schema de reference: le backend peut fournir les mesures additionnelles de connectivite, GPS, securite, qualite et diagnostic deja prevues par le contrat.

## 2. Validation

Avant l'inference, FastAPI/Pydantic controle les types, les champs obligatoires, les enumerations, les bornes numeriques et la version `1.0`.

Le validateur inter-sections controle aussi:

- une identite `resolved` contient `client_id`, `kit_id` et `device_id`;
- chaque record porte le meme `kit_id` et `device_id` que l'identite;
- les records sont de type `telemetry` et passent la validation prediction;
- la fenetre n'est pas vide;
- les paiements sont preserves bruts pour audit et recalcul.

Un payload invalide est rejete avant calcul de modele. Une identite non resolue reste representable, mais la decision est bloquee ou orientee vers `resolve_identity` avec confiance nulle.

## 3. Ingestion et fenetre temporelle

Le pipeline prend les records recus, verifie leur contrat telemetry, puis les combine avec l'historique recent du device dans SQLite quand il existe. Le store conserve les mesures brutes dans `telemetry_records` et evite les doublons via `message_id`.

La fenetre finalement utilisee est celle qui est tracee dans la prediction: debut, fin et nombre de records. Les champs d'identite backend sont copies dans les enregistrements persistes pour les recherches client/kit/device.

## 4. Features et inference

Les records sont transformes par les deux pipelines existants:

1. `build_maintenance_features` prepare les tendances tension/temperature, ratio solaire-charge, connectivite et indicateurs batterie.
2. `build_security_features` prepare geofence, distance, mouvement, ouverture du boitier, tamper et silence device.
3. `LocalInferenceEngine` charge les artefacts joblib locaux et leurs metadonnees.
4. Le modele maintenance produit `technical_risk_probability` et une action technique.
5. Le modele security produit `suspicious_activity_score`, les types d'evenements suspects et une action terrain.
6. Les regles de securite et de batterie peuvent relever une probabilite modele lorsqu'un signal critique brut est present.
7. `build_alert_decision` transforme les sorties en priorite et action operationnelle.

Les versions de modeles et les features utilisees sont conservees dans la trace de prediction. Les artefacts actuels sont entraines sur donnees synthetiques et doivent donc etre consideres comme demo/MVP.

## 5. Scoring client et decision

Les paiements bruts sont agreges par `build_payment_features` puis combines avec:

- valeur client;
- risque paiement;
- risque operationnel issu de maintenance/security;
- qualite et resolution de l'identite.

`CustomerDecisionEngine` produit une decision normalisee avec `scores`, `decision`, `reasons`, `confidence`, `data_quality`, `model` et `traceability`. La priorite finale est `low`, `medium`, `high` ou `critical`.

Le scoring client ne remplace pas la sortie des modeles kit: il la compose explicitement et conserve les sorties brutes dans `kit_intelligence` et dans le snapshot auditable.

## 6. Stockage database

`RealtimeTelemetryStore` utilise SQLite local et conserve:

- `telemetry_records`: mesures brutes;
- `prediction_history`: sorties maintenance/security, priorite, score et features;
- `device_state`: dernier etat par device;
- `customers`: dernier rattachement et derniers scores client;
- `customer_decision_history`: snapshot d'entree et resultat complet.

Les identifiants backend ne sont pas recalcules dans la base IA. Ils sont stockes tels que recus pour garantir la correlation et l'audit.

## 7. Retour vers le backend

La reponse de `POST /v1/customer/evaluate-from-telemetry` contient notamment:

- `request_id`, `as_of`, identite et statut identite;
- scores client, paiement, operationnel et priorite;
- decision recommandee et besoin de revue humaine;
- raisons, codes de raisons et confiance;
- qualite data;
- trace des versions de modeles et des predictions source;
- references de persistence (`decision_id`, `prediction_id` et fenetre utilisee).

Le mode pull `/v1/backend-sync/resolved-telemetry-events/run` reutilise exactement le meme processeur et renvoie un ACK technique au backend metier.

## 8. Frontend de demonstration

`apps/api/static/kit_console.html` et `kit_console.js` utilisent le meme endpoint principal et construisent le meme contrat JSON. Le formulaire pre-remplit trois scenarios:

- `normal`: fonctionnement stable, geofence inside, batterie saine;
- `critical`: tension et sante batterie faibles, surcharge et consommation anormale;
- `security`: geofence outside, boitier ouvert et vitesse non nulle.

Le frontend affiche le JSON envoye, le JSON recu, les scores, les facteurs, la decision et le chat contextuel. Le bouton de scoring client renvoie le meme snapshot complet avec les paiements du profil choisi.

Le payload frontend ne genere plus de section top-level `assignment` hors contrat.

## 9. Validation executee

Commandes executees avec un repertoire temporaire local pour contourner les permissions Windows du dossier temporaire global:

- compilation: `python -m py_compile apps/api/main.py` -> OK;
- tests ciblant le flux Backend->IA -> `4 passed`;
- tests precedents du moteur/API -> `31 passed` dans l'etat avant le durcissement;
- les warnings restants concernent une depreciation joblib/numpy, pas le contrat.

## 10. Limites explicites

- Les artefacts maintenance/security sont synthetiques.
- SQLite est le stockage local de demo; une production devra utiliser la base cible et ses migrations.
- La persistance des interventions terrain n'est pas encore branchee.
- Les schemas frontend `frontend.v1`, `fleet.v1`, etc. restent des contrats de presentation distincts du contrat Backend->IA d'entree; ils consomment les sorties tracees mais ne doivent pas etre confondus avec le payload d'inference.
- La validation exacte du JSON Schema externe doit rester active dans la CI pour toute evolution du contrat.
