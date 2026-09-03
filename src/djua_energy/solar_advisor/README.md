# DJUA AI Solar Advisor

Ce module recommande un kit solaire a partir des besoins declares par un client.

Il est volontairement separe du chatbot. Le chatbot peut aider a comprendre une phrase, mais le nombre de panneaux, de batteries et la puissance de l'onduleur viennent d'un moteur deterministe. Cela rend le resultat testable, explicable et reproductible.

## Flux

```text
Utilisateur
-> appareils et usages
-> catalogue appareils
-> calcul de consommation
-> dimensionnement panneaux/batteries/onduleur/regulateur
-> choix de composants de demonstration
-> explication
-> devis synthetique
-> sauvegarde SQLite
```

## Limites MVP

- Les composants et les prix sont synthetiques.
- Les formules sont prudentes mais doivent etre validees par un expert solaire avant installation reelle.
- Aucun LLM externe n'est requis.
- La persistance est locale dans `data/runtime/solar_advisor.sqlite`.

## Endpoints

- `GET /solar-advisor/catalogs`
- `POST /solar-advisor/recommend`
- `POST /solar-advisor/conversation`
- `GET /solar-advisor/recommendations`
- `GET /solar-advisor/recommendations/{recommendation_id}`
- `POST /solar-advisor/recommendations/{recommendation_id}/contact`
- `POST /solar-advisor/recommendations/{recommendation_id}/explain`

## Explication IA optionnelle

Le moteur fonctionne sans OpenAI. Pour activer la reformulation IA apres devis, definir une variable d'environnement:

```powershell
$env:OPENAI_API_KEY="votre_nouvelle_cle"
```

Ne jamais mettre la cle dans le code, dans un CSV ou dans Git.
