# WhatsApp DJUA — mise en service

## Integration dans le projet

L'API reste `apps/api/main.py`. Elle monte le routeur
`apps/api/routers/whatsapp.py`. Le module `channels/whatsapp` contient les schemas
Meta, le repository SQLite, les permissions, la reception persistante et le
client Graph API. `chat/realtime_context.py` interroge `RealtimeTelemetryStore`.
`DjuaChatService.answer_from_context` reutilise le client IA et fournit un
fallback local sur le contexte deja autorise. Le chat historique conserve son
comportement. WhatsApp n'utilise jamais le CSV de demonstration.

Trois tables sont initialisees automatiquement, de facon additive, dans la meme
base que les mesures : `whatsapp_users`, `whatsapp_device_access`,
`whatsapp_inbox`. Aucune suppression ni migration manuelle n'est necessaire.
Les devices sans prediction mais avec des mesures sont inclus dans le parc.
Les statistiques sont calculees en Python; donnees absentes, dates des dernieres
observations et provenance de simulation sont explicites. L'origine physique
d'une mesure stockee n'est pas consideree comme verifiee automatiquement.

## Render

Dans le service existant, ajouter les variables d'environnement suivantes puis
deployer le code :

| Variable | Valeur a fournir |
| --- | --- |
| `WHATSAPP_VERIFY_TOKEN` | Secret aleatoire choisi par vous, identique au champ Meta |
| `WHATSAPP_ACCESS_TOKEN` | Access token Meta autorise a envoyer des messages |
| `WHATSAPP_PHONE_NUMBER_ID` | Identifiant du numero professionnel Meta, pas son numero de telephone |
| `WHATSAPP_API_VERSION` | Version Graph API active choisie dans votre application, au format `vXX.0` |
| `WHATSAPP_APP_SECRET` | App Secret Meta pour verifier `X-Hub-Signature-256` |
| `OPENAI_API_KEY` | Cle fonctionnelle du projet OpenAI; facultative pour le fallback |
| `DJUA_OPENAI_MODEL` | `gpt-4.1-mini`, ou modele compatible Responses configure |
| `DJUA_ENV` | `production` |
| `WHATSAPP_GLOBAL_ROLES` | Vide par defaut; elevation facultative explicite `support` et/ou `technician`, separes par une virgule |
| `DJUA_DATABASE_URL` | `sqlite:////app/data/runtime/djua_realtime.sqlite` pour le Docker fourni |

Ne jamais mettre les vrais secrets dans Git, le Dockerfile ou le frontend.
Les variables WhatsApp viennent de l'environnement du processus; copier
`.env.example` ne les charge pas automatiquement. En local, les definir dans
le terminal qui lance uvicorn. La signature est facultative uniquement en
developpement si `WHATSAPP_APP_SECRET` est absent. En production, signature et
phone number ID sont obligatoires et le webhook refuse de traiter sinon.

Le Blueprint `render.yaml` prepare une instance Starter avec disque persistant
de 1 Go monte sur `/app/data/runtime`. Ce plan et le disque sont **payants** et
ne sont pas provisionnes par ces changements locaux. Pour votre service
existant, ajouter le disque dans Render avant d'enregistrer des utilisateurs.
Sans disque, les acces, mesures et messages de deduplication sont perdus aux
redeploiements. Si une base existe deja sur le disque ephemere, la sauvegarder
avec l'API de backup SQLite avant de changer le montage, puis la restaurer sur
le disque persistant. Utiliser une seule instance pour ce MVP SQLite.

Sources : [variables Render](https://render.com/docs/configure-environment-variables),
[disques Render](https://render.com/docs/disks).

## Configuration Meta

URL de rappel exacte :

```text
https://djua-energy-data-ai.onrender.com/webhooks/whatsapp
```

Dans **Verifier le token**, saisir exactement la valeur de
`WHATSAPP_VERIFY_TOKEN`, pas l'access token. Abonner l'application au champ
`messages` du compte WhatsApp Business et utiliser le meme phone number ID que
dans Render. Le GET renvoie le challenge brut. Le POST valide la signature,
valide le JSON, ignore statuts et medias, deduplique les textes en SQLite et
renvoie HTTP 200 sans attendre OpenAI ou Meta.

Le worker demarre avec l'application FastAPI et reprend les messages `pending`.
Les envois repondent uniquement a un message entrant. Ce MVP n'envoie pas de
campagnes, de templates ni de messages proactifs hors fenetre de conversation.
La configuration du compte Business, les droits d'application, les destinataires
de test autorises et la disponibilite du numero restent a effectuer dans Meta.

Reference de la plateforme :
[collection officielle Meta](https://www.postman.com/meta/whatsapp-business-platform/overview).

## Enregistrer le premier ADMIN

Dans le **Shell du service Render** (les commandes doivent viser la base du
service deploye, et non votre base locale) :

```sh
read -r -p 'Numero WhatsApp international : ' WHATSAPP_BOOTSTRAP_PHONE
export WHATSAPP_BOOTSTRAP_PHONE
python scripts/manage_whatsapp.py user --role admin --name 'Admin test'
unset WHATSAPP_BOOTSTRAP_PHONE
```

Le numero doit contenir l'indicatif pays; le script normalise le `+`, les
espaces et les separateurs. Aucun numero personnel n'est fourni dans le code.
Le repository est aussi utilisable directement depuis un script d'exploitation.
Il n'existe aucun endpoint public d'attribution de privileges.

## Associer un client a ses devices

Toujours dans le Shell Render, remplacer les identifiants par ceux des devices
effectivement ingeres :

```sh
read -r -p 'Numero WhatsApp client : ' CLIENT_PHONE
python scripts/manage_whatsapp.py user --phone "$CLIENT_PHONE" --role customer --customer-id client-demo --name 'Client demo'
python scripts/manage_whatsapp.py grant --phone "$CLIENT_PHONE" --device DEVICE_123 --kit KIT_123 --primary
# Autre kit du meme client, si necessaire :
python scripts/manage_whatsapp.py grant --phone "$CLIENT_PHONE" --device DEVICE_124 --kit KIT_124
# Retirer un acces :
python scripts/manage_whatsapp.py revoke --phone "$CLIENT_PHONE" --device DEVICE_124
# Desactiver un compte :
python scripts/manage_whatsapp.py user --phone "$CLIENT_PHONE" --role customer --customer-id client-demo --inactive
unset CLIENT_PHONE
```

`user` cree ou met a jour les attributs du compte; `grant` est idempotent.
Le script accepte aussi `--database CHEMIN` avant la sous-commande. La mise a
jour d'un compte conserve ses associations; une revocation est explicite.

## Permissions

| Role | Perimetre par defaut |
| --- | --- |
| customer | Devices explicitement associes, jamais tout le parc |
| technician | Devices explicitement associes |
| support | Devices explicitement associes |
| admin | Tous les devices stockes et recherche des clients enregistres |

La configuration peut elever support/technician, jamais customer. Un numero
inconnu ou inactif ne recoit aucune mesure. Une demande explicite visant un
device etranger est refusee avant l'appel IA. Plusieurs kits sans selection
explicite entrainent une question de clarification, meme si un kit est marque
principal. Une demande sur « mes kits » utilise uniquement le perimetre autorise.
Les coordonnees telephoniques ne sont pas transmises a OpenAI.

## Tester depuis WhatsApp

Avec un client associe a un seul device :

- « Comment va mon kit ? »
- « Pourquoi ma production baisse ? »
- « Quel est le niveau de ma batterie ? »
- « Historique recent de DEVICE_123 »
- « Comment va DEVICE_DUN_AUTRE_CLIENT ? » doit etre refuse.

Avec l'admin :

- « Comment va le parc ? »
- « Combien de kits sont critiques ? »
- « Quels sont les 10 kits les plus preoccupants ? »
- « Quels kits ont un probleme de batterie ? »
- « Quelle est la situation du client client-demo ? »
- « Comment vont DEVICE_123 et DEVICE_124 ? »

Si aucun historique n'existe, le bot l'indique. Une baisse de puissance seule
ne permet pas d'affirmer une cause. Le fallback respecte les memes permissions.

## Exploitation et limites MVP

```sh
python scripts/manage_whatsapp.py status --message-id IDENTIFIANT_WAMID
```

Etats : `pending`, `processing`, `sending`, `sent`, `failed`, `uncertain`.
`sent` signifie accepte par l'API Meta, pas confirme livre au destinataire.
Les notifications de livraison sont ignorees, sans declencher de reponse.
Les erreurs enregistrent uniquement un code neutre (`meta_http_401`, etc.),
jamais les en-tetes ou les corps contenant des secrets. Le journal d'acces
uvicorn masque la query string du webhook de verification.

L'unicite du message entrant et la reservation transactionnelle empechent les
traitements concurrents. Aucun renvoi automatique apres un envoi incertain :
cela evite un doublon si Meta a accepte le message avant une coupure reseau.
Un arret brutal pendant `processing` ou `sending` necessite une verification
operateur; ces etats ne sont pas rejoues automatiquement. Le MVP ne garantit
pas un envoi « exactement une fois » a travers une API distante.

Les textes et numeros sont stockes dans la base privee pour le traitement.
Ne pas versionner cette base. Les fichiers runtime deja suivis par Git avant
cette integration restent a exclure de tout commit contenant des donnees privees.
Sauvegardes et politique de retention restent a organiser par l'exploitant;
ne pas purger les identifiants de deduplication dans la fenetre de retry Meta.
Les tests locaux utilisent un client Meta factice : aucun message reel envoye.

Commande de verification :

```powershell
.\.venv\Scripts\python.exe -m pytest tests --basetemp data/runtime/whatsapp-full-tests -p no:cacheprovider -q
```

Verification finale du 10 octobre 2026 : **74 tests reussis en 72,96 s**
(suite existante et nouveaux tests WhatsApp), avec 1010 avertissements de
depreciation NumPy/joblib provenant du chargement des modeles. Compilation
Python des nouveaux modules et verification des espaces Git : OK.
Les tests couvrent le webhook ASGI, les signatures, l'isolation des clients,
les roles, les agregations, le fallback, le worker, les reservations concurrentes,
la deduplication, les erreurs Meta et le format des messages sortants.
