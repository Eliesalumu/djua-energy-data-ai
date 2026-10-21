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
  `whatsapp_logic_version` doit valoir `conversational-demo-v4` : les reponses WhatsApp
  des comptes authentifies passent par OpenAI, meme sans telemetrie.
  `legacy` signale un ancien module charge.
- Les salutations et questions generales ne chargent pas le parc. Le texte de
  secours n'est pas transmis a OpenAI ; il est affiche uniquement en cas d'echec,
  avec la mention explicite « Reponse de secours » et un code dans les logs.
- Pour la demonstration demandee, si le stockage temps reel est vide, WhatsApp
  lit le CSV synthetique embarque depuis le depot : 50 devices, sans ecriture
  dans SQLite, sans prediction inventee et avec les memes controles de grants.
  Des que des mesures persistent dans le stockage, cette source prend priorite
  et le CSV n'est plus utilise. `DJUA_WHATSAPP_DEMO_DATA=false` desactive la demo.
- Les chemins du dataset et des modeles sont resolus depuis le fichier de l'API
  dans le depot, meme quand le package metier est installe dans un virtualenv.
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
