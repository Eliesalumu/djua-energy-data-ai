# Assistants OpenAI sur Render

Les assistants parc et Solar Advisor utilisent la meme configuration serveur.
En local, `.env` est relu a chaque appel. Sur Render (ou `DJUA_ENV=production`),
seule la variable `OPENAI_API_KEY` du service est utilisee. Le fichier local
ne part ni dans Git ni dans l'image Docker.

## Deploiement

Deployer les changements du depot, y compris `apps/api/static`, `src` et
`.dockerignore`. Le dataset MVP requis au demarrage est inclus dans Docker.
`render.yaml` fournit un Blueprint Docker pour un nouveau service. Pour un
service existant, conserver sa configuration et ajouter les variables dans
Environment :

- `OPENAI_API_KEY` : la cle fonctionnelle, en secret.
- `DJUA_OPENAI_MODEL` : `gpt-4.1-mini` (valeur commune par defaut).
- `DJUA_ENV` : `production`.

Choisir Save and deploy. Le fichier `.env` local n'est pas synchronise
automatiquement. Ne jamais mettre la cle dans un frontend ou un Blueprint.

## Verification

- `/health` doit repondre. `revision` indique `RENDER_GIT_COMMIT` et
  `whatsapp_logic_version` doit valoir `auth-intent-scope-v2` pour le routage
  identite/aide sans telemetrie. `legacy` signale un ancien module charge.
- En runtime Python natif, `pip install -r requirements.txt` installe aussi
  le projet en editable (`-e .`), afin de charger le code metier de `src`
  depuis le depot courant, sans reutiliser une ancienne copie installee.
- `/demo/solar-advisor` fournit une interface de conversation, un resume du
  devis et un mode Question sur le devis. La source OpenAI ou la cause du
  fallback sont affichees sous chaque reponse.
- `/demo/kit-console` fournit le chat de supervision.
- `POST /solar-advisor/conversation` doit retourner `used_ai: true` ; les routes
  `/recommendations/{id}/ask` et `/recommendations/{id}/explain` aussi.

## Affichage progressif

Les deux pages integrent `/static/progressive-text.js`. L'API JSON reste
compatible : le navigateur recoit la reponse complete puis l'affiche
progressivement. Un indicateur est visible pendant l'attente, les doubles
envois sont bloques et la preference de reduction des animations est respectee.
Ce comportement est une animation d'affichage, pas un flux de tokens OpenAI.
Un frontend separe doit integrer ce script (ou son equivalent) dans son propre
deploiement ; deployer uniquement l'API ne change pas son rendu.

Sources : https://render.com/docs/configure-environment-variables
