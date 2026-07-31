# Rapport - Passage du dataset statique au systeme temps reel

## Idee generale

Au depart, le projet utilisait un fichier CSV statique. Ce fichier contient beaucoup de lignes, mais il ne bouge pas. C'est utile pour entrainer et tester les modeles, mais ce n'est pas suffisant pour suivre des vrais devices sur le terrain.

Le nouveau fonctionnement ajoute une logique plus proche de la realite
:

```text
device
-> nouvelle mesure toutes les 5 minutes
-> API
-> base de donnees
-> fenetre recente du device
-> modele IA
-> prediction
-> etat courant du device
-> historique consultable
```
Une ligne n'est donc plus seulement une ligne dans un fichier. Elle devient un evenement qui arrive dans le systeme.

## Ce qui a ete ajoute

### 1. Ingestion continue

Le endpoint existant `POST /telemetry/analyze` accepte deja des mesures de telemetrie.

Maintenant, quand une nouvelle mesure arrive :

- elle est validee ;
- les mesures invalides partent en quarantaine ;
- les doublons sont ignores ;
- les mesures valides sont enregistrees;
- le modele est appele ;
- le resultat est stocke.

Cela permet d'envoyer une seule mesure toutes les 5 minutes, comme le ferait un vrai boitier.

### 2. Vraie base de donnees locale

Une base SQLite locale a ete ajoutee par defaut :

```text
data/runtime/djua_realtime.sqlite
```

Elle contient trois tables principales :

```text
telemetry_records
prediction_history
device_state
```

`telemetry_records` garde les mesures brutes recues.

`prediction_history` garde chaque decision du modele dans le temps.

`device_state` garde seulement le dernier etat connu de chaque device.

En clair :

```text
telemetry_records = tout ce que le device a envoye
prediction_history = tout ce que l'IA a predit
device_state = l'etat actuel du parc
```

### 3. Fenetre glissante par device

Le modele ne juge pas seulement la derniere mesure.

Quand une nouvelle mesure arrive pour `device-0`, le systeme va chercher les dernieres mesures du meme device, par defaut les 24 plus recentes.

Exemple :

```text
11h00 -> mesure normale
11h05 -> mesure normale
11h10 -> temperature batterie un peu plus haute
11h15 -> voltage en baisse
11h20 -> connexion degradee
```

Le modele voit cette evolution. C'est ce qui lui permet de dire :

```text
11h00 : tout va bien
13h30 : risque eleve
```

### 4. Historique des predictions

A chaque passage du modele, on stocke :

- le device concerne ;
- l'heure de prediction ;
- le nombre de mesures utilisees ;
- le score maintenance ;
- le score securite;
- le score global;
- le niveau de risque;
- la recommandation;
- les features importantes.

Cela permet d'expliquer l'evolution d'un device dans le temps.

### 5. Mise a jour automatique de l'etat du parc

Apres chaque prediction, la table `device_state` est mise a jour.

Elle donne la derniere image connue du parc :

```text
device-0 -> risque high, score 81, derniere mesure 13h30
device-1 -> risque low, score 12, derniere mesure 13h25
device-2 -> offline, score 74, derniere mesure 13h20
```

Cette table est celle qu'un dashboard peut lire pour afficher l'etat actuel.

## Endpoints ajoutes

Voir l'etat courant de tout le parc :

```text
GET /realtime/fleet-state
```

Voir l'etat courant d'un device :

```text
GET /realtime/devices/{device_id}/state
```

Voir l'historique IA d'un device :

```text
GET /realtime/devices/{device_id}/predictions
```

## Simulation temps reel

Un script a ete ajoute :

```text
scripts/simulate_realtime_stream.py
```

Il simule un device qui envoie des mesures successives. Le scenario commence normal, puis devient progressivement plus risque.

Commande rapide :

```powershell
.\.venv\Scripts\python.exe scripts\simulate_realtime_stream.py --cycles 18 --sleep-seconds 0
```

Commande plus proche du reel :

```powershell
.\.venv\Scripts\python.exe scripts\simulate_realtime_stream.py
--cycles 18 --interval-seconds 300 --sleep-seconds 300
```

La deuxieme commande attend vraiment 5 minutes entre deux mesures.

## Comment lancer

Lancer l'API :

```powershell
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --reload
```

Dans un autre PowerShell, lancer la simulation :

```powershell
.\.venv\Scripts\python.exe scripts\simulate_realtime_stream.py --cycles 18 --sleep-seconds 0
```

Consulter l'etat du device :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/realtime/devices/device-0/state
```

Consulter son historique IA :

```powershell
Invoke-RestMethod http://127.0.0.1:8000/realtime/devices/device-0/predictions
```
## Limite actuelle

Le systeme est maintenant pret pour un flux continu local.

Mais il reste deux etapes pour une production complete :

- brancher un vrai transport terrain comme MQTT, HTTP embarque ou passerelle IoT;
- remplacer SQLite par MySQL/PostgreSQL si plusieurs services ecrivent en meme temps ou si le volume devient important.

Le plus important est acquis : le projet n'est plus limite a un CSV statique. Il peut recevoir des donnees nouvelles, recalculer le risque, garder l'historique et mettre a jour l'etat courant du parc.
