# Rapport - Integration du copilote IA conversationnel

## Objectif

L'objectif est d'ajouter un chat IA a la plateforme Djua Energy. L'operateur peut poser une question naturelle comme `Parle-moi du device-4`, et le systeme repond a partir des donnees du device et des predictions des modeles deja entraines.

Le LLM ne remplace pas les modeles Random Forest. Les modeles existants prennent les decisions maintenance et securite. Le LLM sert a transformer ces resultats en explication claire, humaine et exploitable.

## Architecture

Le chat suit ce flux :

```text
Question utilisateur
-> extraction du device_id
-> lecture du dataset MVP
-> calcul des indicateurs device
-> inference maintenance et securite
-> construction d'un contexte JSON fiable
-> appel OpenAI si disponible
-> reponse humaine ou fallback local
```

## Fichiers ajoutes

`src/djua_energy/chat/context_builder.py` extrait le device demande, lit `data/generated/mvp_dataset.csv`, calcule les indicateurs importants et prepare le contexte transmis au LLM.

`src/djua_energy/chat/service.py` orchestre le chat. Il construit le contexte, appelle l'API OpenAI via `OPENAI_API_KEY`, et bascule sur une reponse locale si OpenAI est indisponible.

`src/djua_energy/chat/prompts.py` contient les instructions donnees au LLM. Le prompt force le modele a utiliser uniquement le contexte fourni et a ne pas inventer de donnees.

`scripts/chat_device_cli.py` fournit la demonstration CLI conversationnelle.

## API ajoutee

Un endpoint a ete ajoute dans `apps/api/main.py` :

```text
POST /ai/chat
```

Exemple de payload :

```json
{
  "message": "Parle-moi du device-3"
}
```

La reponse contient le texte du chat, le device detecte, les sources utilisees, le contexte et l'information indiquant si OpenAI a ete utilise.

## Demonstration CLI

Commande :

```powershell
.\.venv\Scripts\python.exe scripts\chat_device_cli.py
```

Questions utiles :

```text
Parle-moi du device-3
Quel device est normal ?
Parle-moi du device-50
```

## Configuration OpenAI

Le code lit la cle depuis l'environnement :

```text
OPENAI_API_KEY
```

Le modele peut etre change avec :

```text
OPENAI_MODEL
```

Par defaut, le MVP utilise `gpt-4.1-mini`.

## Robustesse demo

Si l'appel OpenAI echoue, par exemple reseau bloque, quota atteint ou cle invalide, la demo ne s'arrete pas. Le systeme produit une reponse locale a partir du meme contexte device. C'est important pour une soutenance, car la demonstration reste fluide meme si le service externe est indisponible.

## Tests

Les tests ajoutés couvrent l'extraction du device, la construction du contexte, le fallback local et le endpoint `/ai/chat`.

Commande :

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_chat.py tests\unit\test_api.py -q
```

