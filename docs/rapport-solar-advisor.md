# Rapport pedagogique - DJUA AI Solar Advisor

## 1. Ce qui existait au depart

Le projet DJUA ENERGY contenait deja un MVP local pour superviser des kits solaires:

- ingestion de telemetrie IoT via `POST /telemetry/analyze`;
- validation, quarantaine et dedoublonnage des messages;
- modeles locaux `joblib` pour maintenance predictive et securite;
- stockage SQLite de l'etat temps reel dans `data/runtime/djua_realtime.sqlite`;
- endpoints FastAPI pour le command center, la flotte, les decisions IA et le jumeau numerique;
- scripts de simulation temps reel.

La base de donnees generale n'etait pas encore implementee. Le depot utilise donc surtout des services Python simples et un stockage SQLite local-first.

## 2. Ce qui a ete ajoute

Nouveau module: **DJUA AI Solar Advisor**.

Fichiers principaux:

| Fichier | Role simple |
|---|---|
| `src/djua_energy/solar_advisor/catalog.py` | Lit les catalogues CSV d'appareils et de composants solaires. |
| `src/djua_energy/solar_advisor/consumption_engine.py` | Calcule la consommation quotidienne des appareils. |
| `src/djua_energy/solar_advisor/sizing_engine.py` | Calcule panneaux, batteries, onduleur et regulateur. |
| `src/djua_energy/solar_advisor/recommendation_engine.py` | Non separe: la logique de recommandation est orchestree dans `service.py` pour rester simple au MVP. |
| `src/djua_energy/solar_advisor/conversation_engine.py` | Extrait quelques besoins depuis une phrase simple. |
| `src/djua_energy/solar_advisor/explanation_engine.py` | Produit une explication lisible. |
| `src/djua_energy/solar_advisor/quote_service.py` | Genere une proposition/devis de demonstration. |
| `src/djua_energy/solar_advisor/repository.py` | Sauvegarde recommandations et demandes de contact dans SQLite. |
| `src/djua_energy/solar_advisor/service.py` | Assemble tout le flux. |
| `data/catalogs/appliances.csv` | Catalogue synthetique d'appareils adaptes au contexte africain. |
| `data/catalogs/solar_components.csv` | Catalogue synthetique de panneaux, batteries, onduleurs et regulateurs. |
| `scripts/generate_solar_advisor_dataset.py` | Genere `data/generated/solar_recommendation_dataset.csv`. |
| `scripts/demo_solar_advisor.py` | Demo locale interactive: assistant guide ou configurateur manuel. |
| `tests/unit/test_solar_advisor.py` | Tests du nouveau module. |
| `schemas/solar_advisor.v1.schema.json` | Contrat JSON de demande de recommandation. |

## 3. Fonctionnement du module

L'utilisateur donne ses appareils: par exemple television, congelateur, ampoules, ventilateurs et ordinateur.

Le systeme cherche chaque appareil dans le catalogue. Si la puissance exacte n'est pas donnee, il utilise une puissance typique et signale l'hypothese.

La consommation est calculee avec:

```text
energie quotidienne = quantite x puissance x heures par jour x cycle d'utilisation
```

Puis le moteur ajoute une marge de securite pour couvrir les incertitudes et une future evolution.

Ensuite il dimensionne:

- les panneaux solaires selon la consommation et les heures de soleil utiles;
- les batteries selon l'autonomie demandee;
- l'onduleur selon la puissance simultanee et les pics de demarrage;
- le regulateur selon le courant venant des panneaux.

Le resultat est explique avec des phrases simples et sauvegarde.

## 4. Pourquoi le calcul est separe du chatbot

Un chatbot peut mal comprendre ou inventer. Pour une installation solaire, inventer le nombre de panneaux ou la capacite batterie serait dangereux.

Le chatbot sert donc seulement a aider l'utilisateur a formuler son besoin. Le calcul technique reste dans un moteur deterministe, c'est-a-dire un code qui donne le meme resultat si on lui donne les memes entrees.

## 5. Dataset synthetique

Le script `scripts/generate_solar_advisor_dataset.py` peut generer 100 000 lignes.

Commande:

```powershell
.\.venv\Scripts\python.exe scripts\generate_solar_advisor_dataset.py --rows 100000
```

Le dataset couvre plusieurs scenarios:

- petit menage;
- menage urbain;
- boutique avec froid;
- salon de coiffure;
- centre de sante.

Chaque ligne contient la consommation, la configuration recommandee, le prix de demonstration et un indicateur de budget insuffisant.

## 6. Machine Learning

Aucun nouveau modele ML n'a ete ajoute pour ce module MVP.

Raison: le dimensionnement solaire doit d'abord etre fonde sur des formules physiques et des regles metier. Un modele ML futur pourrait apprendre a ajuster les marges a partir de donnees reelles: consommation mesuree, satisfaction, incidents, autonomie reelle, modifications apres installation.

## 7. API

### `GET /solar-advisor/catalogs`

Retourne les catalogues de demonstration.

### `POST /solar-advisor/recommend`

Entree: liste d'appareils, ville, autonomie, budget, preference.

Sortie: consommation, dimensionnement, composants, explication, devis et limites.

### `POST /solar-advisor/conversation`

Entree: message en langage naturel.

Sortie: demande structuree, questions restantes et recommandation si les informations sont suffisantes.

### `GET /solar-advisor/recommendations`

Liste les recommandations sauvegardees.

### `GET /solar-advisor/recommendations/{recommendation_id}`

Retourne une recommandation precise.

### `POST /solar-advisor/recommendations/{recommendation_id}/contact`

Cree une demande de contact Orange Energy.

### `POST /solar-advisor/recommendations/{recommendation_id}/explain`

Retourne une explication apres devis. Si `OPENAI_API_KEY` est configuree, l'explication est reformulee par OpenAI. Sinon le module retourne une explication locale.

## 8. Base de donnees

Base locale: `data/runtime/solar_advisor.sqlite`.

Tables:

| Table | Role |
|---|---|
| `advisor_recommendations` | Sauvegarde la demande, la consommation, le dimensionnement et la recommandation complete. |
| `advisor_contact_requests` | Sauvegarde une demande de rappel ou de contact commercial. |

## 9. Tests

Tests ajoutes:

- recommandation complete;
- appareil inconnu;
- extraction conversationnelle;
- sauvegarde de contact;
- endpoints API;
- exposition des catalogues.

Tests a lancer:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 10. Guide de lancement

Activer l'environnement:

```powershell
.\.venv\Scripts\Activate.ps1
```

Lancer l'API:

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8001
```

Generer le dataset:

```powershell
.\.venv\Scripts\python.exe scripts\generate_solar_advisor_dataset.py --rows 100000
```

Lancer la demo:

```powershell
.\.venv\Scripts\python.exe scripts\demo_solar_advisor.py
```

Configurer l'explication IA, uniquement avec une nouvelle cle non exposee:

```powershell
$env:OPENAI_API_KEY="votre_nouvelle_cle"
```

## 11. Guide de demonstration jury

1. Lancer l'API.
2. Montrer `GET /solar-advisor/catalogs`.
3. Lancer `scripts\demo_solar_advisor.py`.
4. Choisir `1` pour assistant conversationnel ou `2` pour configurateur manuel.
5. Saisir les appareils du client devant le jury.
6. Montrer la consommation calculee appareil par appareil.
7. Montrer panneaux, batteries, onduleur et autonomie.
8. Demander l'explication IA apres devis.
9. Montrer la demande de contact creee.
10. Recuperer le resultat par `GET /solar-advisor/recommendations/{id}`.

Phrase simple a dire:

>DJUA ENERGY ne supervise pas seulement les kits installes. La plateforme aide aussi Orange Energy avant l'installation, en recommandant le bon kit selon les besoins du client.

## 12. Statut reel

| Fonctionnalite | Statut | Preuve | Fichier | Limite |
|---|---|---|---|---|
| Calcul consommation | IMPLEMENTE | Tests unitaires | `consumption_engine.py` | Puissances typiques a valider terrain |
| Dimensionnement solaire | IMPLEMENTE | Tests unitaires | `sizing_engine.py` | Regles simplifiees MVP |
| Catalogue appareils | IMPLEMENTE | CSV | `data/catalogs/appliances.csv` | Donnees synthetiques |
| Catalogue composants | SIMULE POUR LE MVP | CSV avec `is_synthetic` | `data/catalogs/solar_components.csv` | Remplacer par catalogue officiel |
| Conversation | PARTIELLEMENT IMPLEMENTE | Extraction locale + CLI guide | `conversation_engine.py` | LLM utilise seulement pour reformuler si cle configuree |
| Explication IA apres devis | PARTIELLEMENT IMPLEMENTE | Endpoint `/explain` | `ai_assistant.py` | Depend de `OPENAI_API_KEY`; fallback local disponible |
| Devis | SIMULE POUR LE MVP | `quote_service.py` | Prix fictifs |
| Persistance | IMPLEMENTE | SQLite | `repository.py` | Pas encore de migrations production |
| Contact Orange Energy | PARTIELLEMENT IMPLEMENTE | Table locale | `repository.py` | Pas de CRM connecte |
| Dataset 100 000 lignes | IMPLEMENTE PAR SCRIPT | Script | `generate_solar_advisor_dataset.py` | A generer localement |

## 13. Responsabilites

| Tache | Data/IA | Developpement | IoT | Orange Energy |
|---|---|---|---|---|
| Regles de dimensionnement | Responsable | Support API | Validation terrain | Validation metier |
| Interface chatbot | Support extraction | Responsable | - | Ton et parcours commercial |
| Catalogue officiel | Support schema | Integration | Compatibilite materielle | Responsable donnees |
| Association kit installe | Baseline attendue | Backend | Responsable device | Process attribution |
| Suivi apres installation | Analyse ecarts | API/dashboard | Telemetrie reelle | Validation pilote |

## 14. Prochaines etapes

Avant la prochaine demonstration:

- ajouter une page frontend dediee;
- enrichir les scenarios de demo;
- verifier les prix avec Orange Energy.

Avant le jury:

- preparer captures d'ecran;
- generer le dataset 100 000 lignes;
- repeter la demo API + script.

Apres le concours:

- connecter un CRM;
- ajouter comptes utilisateurs;
- relier recommandation et kit installe.

Pour un pilote reel:

- remplacer les catalogues synthetiques;
- valider les formules avec des techniciens;
- mesurer les ecarts entre estimation et consommation reelle.
