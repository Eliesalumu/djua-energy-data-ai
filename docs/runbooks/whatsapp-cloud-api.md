# WhatsApp DJUA — mise en service

## Alignement Meta — 19 octobre 2026

Le canal utilise exactement `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_API_VERSION`,
`WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN` et `WHATSAPP_APP_SECRET`.
Le Phone Number ID public cible est `1386186767909577`, avec `v25.0` :

```text
https://graph.facebook.com/v25.0/1386186767909577/messages
```

Le WABA ID et le numero de telephone ne sont jamais substitues a ce Phone
Number ID dans l'URL. Les valeurs restent lues depuis Render; le code ne les
modifie pas. Aucun secret reel n'est fourni dans le depot. Si un App Secret a
ete partage dans une conversation, le regenerer dans la meme application Meta
puis remplacer `WHATSAPP_APP_SECRET` dans Render et redeployer. Sa valeur seule
ne permet pas de confirmer qu'il correspond a l'application du webhook.

Au demarrage, les parametres absents, les placeholders et les formats invalides
du Phone Number ID / de la version sont signales par **nom de variable seulement**.
Une configuration WhatsApp incomplete ne bloque pas `/health`. En production,
le POST refuse toujours une configuration invalide du secret ou du Phone Number
ID; le worker laisse les messages deja recus en `pending` jusqu'a une
configuration valide. Les notifications `statuses` signees sont ignorees avec
HTTP 200 et ne declenchent aucune reponse.

Les logs `djua.whatsapp.*` exposent les etapes signature, selection, permissions,
presence des donnees, appels Graph et transitions du worker. Les references de
messages et de devices sont hachees; les telephones, textes, tokens et secrets
ne sont pas journalises. Les erreurs Graph n'exposent que le code HTTP.

La base du canal, du worker et de `manage_whatsapp.py` reste celle de
`RealtimeTelemetryStore`, issue de `DJUA_DATABASE_URL`. Aucun deplacement de
la base ni de la strategie de stockage n'est effectue par cet alignement.
Les tables existantes specifiques au Solar Advisor ne sont pas deplacees.

Fichiers concernes : `apps/api/routers/whatsapp.py`,
`src/djua_energy/channels/whatsapp/config.py` (nouveau), `client.py`, `service.py`,
`tests/unit/test_whatsapp.py`, `tests/unit/test_deployment.py` et ce guide.
L'utilitaire ASGI des tests de deploiement a ete corrige pour joindre
`Content-Type: application/json` aux corps JSON; aucun assouplissement de la
validation de l'API n'a ete necessaire.

Verification utilisee :

```powershell
.\.venv\Scripts\python.exe -m pytest tests --basetemp data/runtime/whatsapp-meta-final -p no:cacheprovider -q
.\.venv\Scripts\python.exe -m compileall -q apps/api/routers/whatsapp.py src/djua_energy/channels/whatsapp scripts/manage_whatsapp.py
.\.venv\Scripts\python.exe scripts/manage_whatsapp.py --help
```

Les tests ciblent aussi la version `v25.0`, l'URL ci-dessus, les en-tetes Bearer
et JSON, le corps brut signe avec Unicode, un mauvais Phone Number ID, la
deduplication de bout en bout, les permissions et l'absence de telemetrie. Un
test lance reellement Uvicorn sur localhost avec une base temporaire et des
secrets de fixture, puis controle `/health` et le challenge du webhook. Aucun
message n'est envoye a Meta durant ces tests. Les comptes et mesures de fixture
restent isoles de la base d'exploitation.

Resultat de l'alignement : **105 tests reussis en 226,29 s**, avec 1010
avertissements de depreciation NumPy/joblib. Compilation Python, verification
des espaces Git et aide CLI : OK. Le test de demarrage reel confirme HTTP 200
JSON pour `/health` et HTTP 200 texte avec le challenge exact pour le webhook.
Les permissions et le worker sont conserves. L'acceptation reelle des credentials
par Meta et la correspondance de l'App Secret doivent etre verifiees apres
redeploiement; les tests locaux utilisent un client Graph factice.

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
| `WHATSAPP_GLOBAL_ROLES` | Variable historique ignoree pour les permissions : seul admin est global |
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

Sans acces au Shell Render, ajouter `WHATSAPP_BOOTSTRAP_PHONE` dans
**Environment**, avec le numero international a enregistrer, puis choisir
**Save and deploy**. Au demarrage, le repository existant cree ou met a jour
ce seul compte avec `role=admin`, `display_name=Admin test`, `active=true`, dans
la base configuree par `DJUA_DATABASE_URL`. Les associations et le customer_id
eventuels sont conserves. Les autres utilisateurs ne sont pas modifies.
Le log de confirmation est `WhatsApp admin bootstrap completed`, sans numero.
Une erreur est journalisee sans bloquer `/health`. Une variable absente ou vide
ne provoque aucune operation. Les redemarrages ne creent pas de doublons.
Apres confirmation, la variable peut etre retiree de Render : le compte reste
enregistre sur le disque persistant. Aucun numero personnel ne doit etre ajoute
au depot.

Verification du bootstrap le 21 octobre 2026 : **114 tests reussis en 205,59 s**
avec la commande `python -m pytest tests --basetemp data/runtime/whatsapp-bootstrap-tests -p no:cacheprovider -q`.
Les tests couvrent creation, mises a jour idempotentes, reactivation, conservation
des associations, absence de modification des autres roles, variable vide,
numero invalide et erreur de stockage sans echec du demarrage. Un vrai processus
Uvicorn confirme aussi la creation automatique de l'admin dans la meme base et
la reponse HTTP 200 de `/health`. Le numero utilise dans ces tests est fictif.

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

Seul admin dispose d'un acces global, independamment de `WHATSAPP_GLOBAL_ROLES`.
Customer, support et technician restent limites aux associations explicites. Un numero
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
