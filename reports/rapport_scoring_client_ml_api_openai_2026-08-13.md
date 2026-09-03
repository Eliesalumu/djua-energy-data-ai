# Rapport pedagogique - Scoring client ML branche sur API externe et OpenAI

Date: 2026-08-13

## 1. Objectif

L'objectif est de transformer l'API externe DJUA ENERGY en source de donnees pour un vrai scoring client base sur le machine learning.

Le systeme construit fait quatre choses:

1. Generer un historique coherent de 500 clients.
2. Entrainer un modele ML sur cet historique.
3. Appeler l'API externe deja en ligne pour scorer un client reel par son numero Orange Money.
4. Ajouter une explication lisible, locale par defaut ou enrichie par OpenAI si la cle API est disponible.

## 2. Donnees historiques creees

Le dataset genere se trouve ici:

`data/generated/customer_scoring_history.csv`

Il contient:

- 500 clients uniques.
- 12 mois d'historique par client.
- 6 000 lignes au total.
- Une cible ML: `default_next_90d`.

Chaque ligne represente l'etat d'un client a un mois donne. Le modele apprend donc a repondre a la question suivante:

> A partir du profil actuel et du comportement de paiement observe, ce client risque-t-il un defaut ou une suspension dans les 90 prochains jours ?

## 3. Variables utilisees par le modele

Le modele utilise 14 variables:

- `estimated_income_usd`: revenu estime.
- `orange_money_account_age_months`: anciennete Orange Money.
- `historical_risk_score`: risque historique fourni par l'API.
- `paid_months_count`: nombre de mois deja payes.
- `kit_is_suspended`: statut suspendu ou non.
- `payment_success_rate`: taux de paiements reussis.
- `failed_payment_count_12m`: paiements echoues.
- `late_payment_count_12m`: paiements en retard.
- `missed_payment_count_12m`: paiements manques.
- `days_since_last_payment`: anciennete du dernier paiement.
- `avg_payment_amount_usd`: montant moyen paye.
- `payment_amount_volatility`: variabilite des paiements.
- `income_to_fee_ratio`: rapport revenu / abonnement.
- `profession_risk_score`: risque moyen associe au type de profession.

Ces variables sont construites depuis la reponse:

`GET /api/external/scoring-data/:phone`

## 4. Modele entraine

Le modele choisi est un `RandomForestClassifier`.

Pourquoi ce choix:

- Il fonctionne bien comme baseline.
- Il accepte des relations non lineaires.
- Il est robuste pour un dataset synthetique.
- Il donne une probabilite de risque facilement convertible en score.

Artefacts produits:

- `artifacts/customer_scoring_model.joblib`
- `artifacts/customer_scoring_features.joblib`
- `artifacts/customer_scoring_metadata.json`

Resultats du dernier entrainement:

- Clients: 500
- Lignes historiques: 6 000
- Lignes d'entrainement: 4 800
- Lignes de test: 1 200
- Taux de defaut synthetique: 8,97%
- Accuracy: 0,7742
- Precision: 0,2148
- Recall: 0,6337
- F1: 0,3208
- ROC AUC: 0,7734

Lecture pedagogique:

- L'AUC de 0,77 indique que le modele sait raisonnablement separer les clients plus risques des clients moins risques.
- La precision est basse car les defauts sont rares dans le dataset. C'est normal dans un probleme de risque.
- Le recall est plus eleve, ce qui est utile pour ne pas manquer trop de clients a risque.

## 5. Comment le score est calcule

Le modele predit:

`default_probability_90d`

Cette probabilite est convertie en score:

`score = 100 - probabilite_de_defaut * 100`

Exemple:

- Probabilite de defaut: 0,18
- Score client: 82 / 100
- Niveau: faible risque

Seuils:

- `low`: probabilite inferieure a 0,35
- `medium`: probabilite entre 0,35 et 0,65
- `high`: probabilite superieure ou egale a 0,65

## 6. Garde-fous metier

Le ML ne decide pas seul. Des garde-fous explicites sont appliques apres prediction.

Exemples:

- Si le kit est suspendu, le risque ne peut pas rester artificiellement faible.
- Si le taux de paiement reussi est inferieur a 50%, le risque minimal est renforce.
- Si le compte Orange Money est tres recent, la confiance doit etre interpretee avec prudence.

Cette approche hybride est importante: le modele donne la prediction, les regles empechent des sorties incoherentes.

## 7. Endpoint interne ajoute

Nouvelle route:

`GET /scoring/customers/{phone}`

Parametre optionnel:

`explain_with_llm=true`

Exemple:

`GET /scoring/customers/0848451555?explain_with_llm=true`

Fonctionnement:

1. Le backend appelle l'API externe:
   `GET /api/external/scoring-data/{phone}`
2. Il transforme la reponse en features ML.
3. Il charge le modele local.
4. Il calcule le score.
5. Il applique les garde-fous metier.
6. Il retourne le score avec explication.

## 8. Reponse attendue

Exemple de reponse:

```json
{
  "phone": "0848451555",
  "account_number": "ACC-2026-0001",
  "client_name": "Jean-Luc Kabila",
  "score": 82,
  "risk_level": "low",
  "default_probability_90d": 0.18,
  "decision": "eligible",
  "main_factors": [
    "Historique de paiement et profil client globalement favorables."
  ],
  "model": {
    "name": "customer_scoring",
    "version": "customer-scoring-synthetic-v1",
    "trained_on_synthetic_data": true
  }
}
```

## 9. Integration OpenAI

L'explication LLM est optionnelle.

Variables a configurer:

```env
OPENAI_API_KEY=...
DJUA_OPENAI_MODEL=gpt-5-mini
```

Si `OPENAI_API_KEY` est absente, le systeme retourne automatiquement une explication locale. Cela evite de bloquer le scoring en demo ou en environnement hors ligne.

L'appel OpenAI est limite a l'explication. Le LLM ne remplace pas le modele ML et ne change pas le score.

## 10. Commandes utiles

Generer uniquement le dataset:

```bash
python scripts/generate_customer_scoring_dataset.py
```

Entrainer le modele:

```bash
python scripts/train_scoring.py
```

Lancer les tests:

```bash
python -m pytest tests/unit
```

Dans cet environnement, les tests ont ete lances avec:

```bash
.\.venv\Scripts\python.exe -m pytest tests\unit
```

Resultat:

`37 passed`

## 10.1 Demo CLI PowerShell

Une demo PowerShell a ete ajoutee:

`scripts/demo_customer_scoring.ps1`

Elle permet de montrer le scoring client sans interface graphique.

Scenario bon client:

```powershell
.\scripts\demo_customer_scoring.ps1 -Scenario bon
```

Scenario client moyen:

```powershell
.\scripts\demo_customer_scoring.ps1 -Scenario moyen
```

Scenario client a risque:

```powershell
.\scripts\demo_customer_scoring.ps1 -Scenario risque
```

Sortie JSON:

```powershell
.\scripts\demo_customer_scoring.ps1 -Scenario risque -Json
```

Avec l'API externe reelle:

```powershell
.\scripts\demo_customer_scoring.ps1 -ExternalApiBaseUrl "https://ton-api-djua.example.com" -Phone "0848451555"
```

Avec un serveur FastAPI local ou deploye:

```powershell
.\scripts\demo_customer_scoring.ps1 -ApiUrl "http://127.0.0.1:8000" -Phone "0848451555"
```

Avec explication OpenAI:

```powershell
$env:OPENAI_API_KEY="..."
.\scripts\demo_customer_scoring.ps1 -Scenario moyen -ExplainWithLlm
```

## 10.2 Chat IA conversationnel

Une deuxieme demo CLI permet de poser une question naturelle a l'IA:

`scripts/demo_customer_scoring_chat.ps1`

Exemple local:

```powershell
.\scripts\demo_customer_scoring_chat.ps1 -Scenario risque -Question "IA, que penses-tu de ce client ? Donne-moi une analyse tres detaillee."
```

Mode interactif:

```powershell
.\scripts\demo_customer_scoring_chat.ps1 -Scenario moyen
```

Exemple de questions:

```text
IA, que penses-tu de ce client ?
Pourquoi son score est-il moyen ?
Est-ce qu'on peut lui faire confiance ?
Quelle action recommandes-tu ?
Quels sont les points rassurants et les points dangereux ?
```

Avec l'API externe reelle:

```powershell
.\scripts\demo_customer_scoring_chat.ps1 -ExternalApiBaseUrl "https://ton-api-djua.example.com" -Phone "0848451555" -Question "IA, que penses-tu du client ?"
```

Avec OpenAI:

```powershell
$env:OPENAI_API_KEY="..."
.\scripts\demo_customer_scoring_chat.ps1 -Scenario risque -UseOpenAI -Question "IA, que penses-tu de ce client ?"
```

Important: meme sans `OPENAI_API_KEY`, la demo repond avec une explication conversationnelle locale. Avec OpenAI, la reponse devient plus naturelle et plus riche, mais le score reste calcule par le modele ML.

## 10.3 Chat IA surveillance du parc

Une demo conversationnelle existe aussi pour interroger le parc de kits solaires:

`scripts/demo_fleet_chat.ps1`

Exemple en mode interactif:

```powershell
.\scripts\demo_fleet_chat.ps1
```

Questions utiles:

```text
Resume-moi l'etat du parc
Quels devices sont critiques ?
Parle-moi du device-3
Que dois-je traiter en priorite aujourd'hui ?
Quel device est normal ?
```

Question directe:

```powershell
.\scripts\demo_fleet_chat.ps1 -Question "Resume-moi l'etat du parc et dis-moi quoi traiter en priorite aujourd'hui"
```

Forcer le mode local sans OpenAI:

```powershell
.\scripts\demo_fleet_chat.ps1 -NoOpenAI -Question "Parle-moi du device-3"
```

Forcer OpenAI strict:

```powershell
.\scripts\demo_fleet_chat.ps1 -RequireOpenAI -Question "Quels devices sont critiques ?"
```

La demo s'appuie sur:

- `data/generated/mvp_dataset.csv`
- `artifacts/maintenance_model.joblib`
- `artifacts/security_model.joblib`
- `src/djua_energy/chat/service.py`
- `POST /ai/chat`

## 11. Limites importantes

Le modele est utile pour une demonstration ML credible, mais il reste entraine sur des donnees synthetiques.

Avant une mise en production, il faudra:

- Remplacer progressivement le dataset synthetique par des historiques reels.
- Definir officiellement ce qu'est un defaut: retard 30 jours, suspension, non-paiement 90 jours, perte definitive, etc.
- Auditer les biais potentiels, notamment autour de la profession et du revenu.
- Ajouter un suivi de derive des donnees.
- Enregistrer les predictions et comparer avec le comportement reel a 30/60/90 jours.
- Garder une revue humaine pour les decisions sensibles.

## 12. Conclusion

La solution est maintenant alignee avec une approche ML:

- donnees historiques coherentes,
- modele entraine,
- scoring par API,
- explication metier,
- couche LLM optionnelle,
- tests automatises.

Le prochain vrai saut de qualite viendra de l'integration d'historiques reels de paiement Orange Money et de statuts reels de suspension/reprise des kits.
