# Guide de reproduction sous Windows

Ce guide s'adresse aux examinateurs. Il reproduit le démonstrateur RESILIENCE-ALPHA du groupe 10 sur **un seul PC Windows**, commande par commande, du poste vierge à la preuve de reprise autonome. Toutes les commandes se tapent dans **PowerShell**, sauf mention contraire.

Ce que vous allez voir : un SI de paiement fictif subit une attaque par saturation, un modèle de ML détecte l'anomalie, un moteur Ansible bloque l'attaquant **sans intervention humaine**, et un nouveau paiement est approuvé. Aucune donnée réelle : cartes de test uniquement.

## Sommaire

| Étape | Contenu | Durée | Obligatoire |
|---|---|---|---|
| [1](#1-vérifier-le-poste) | Vérifier le poste | 2 min | oui |
| [2](#2-installer-les-outils) | Installer les outils | 15 min | oui |
| [3](#3-récupérer-le-code) | Récupérer le code | 2 min | oui |
| [4](#4-générer-la-configuration) | Générer la configuration et les secrets | 1 min | oui |
| [5](#5-démarrer-le-si) | Démarrer le SI | 5 à 10 min | oui |
| [6](#6-vérifier-que-tout-fonctionne) | Vérifier que tout fonctionne | 1 min | oui |
| [7](#7-faire-un-achat-comme-un-client) | Faire un achat comme un client | 5 min | oui |
| [8](#8-la-preuve--attaque-détection-reprise-autonome) | **La preuve : attaque, détection, reprise autonome** | 3 min | oui |
| [9](#9-sauvegarde-et-restauration-de-la-base) | Sauvegarde et restauration de la base | 2 min | conseillé |
| [10](#10-panne-de-service-et-assistant-ia) | Panne de service et assistant IA (Ollama) | 15 min | facultatif |
| [11](#11-back-office-à-reconnaissance-faciale) | Back-office à reconnaissance faciale (webcam) | 5 min | facultatif |
| [12](#12-attaque-depuis-un-second-pc) | Attaque depuis un second PC | 10 min | facultatif |
| [13](#13-tests-automatisés) | Tests automatisés | 5 min | facultatif |
| [14](#14-arrêter-et-nettoyer) | Arrêter et nettoyer | 1 min | |
| [Dépannage](#dépannage) | Symptômes et solutions | | |

Les étapes 1 à 8 suffisent à constater la boucle complète. Les suivantes montrent les autres piliers.

## 1. Vérifier le poste

| Élément | Minimum | Vérification |
|---|---|---|
| Windows | 10 (22H2) ou 11, 64 bits | `winver` |
| Mémoire | 16 Go (32 Go conseillés avec Ollama) | Gestionnaire des tâches, onglet Performances |
| Disque libre | 20 Go | Explorateur |
| Virtualisation | activée dans le BIOS | Gestionnaire des tâches, Performances, Processeur : « Virtualisation : Activé » |
| Droits | administrateur, pour l'installation seulement | |

Ports utilisés sur le PC : 80, 3000, 5050, 8081, 8082, 8083, et en boucle locale seulement 5432, 8000, 8001, 8002, 8099, 9090. Fermer tout logiciel qui occupe le port 80 (IIS, Skype ancien, autre serveur web).

## 2. Installer les outils

Ouvrir **PowerShell en administrateur** (clic droit sur le menu Démarrer, « Terminal (administrateur) »).

**2.1 Sous-système Linux (WSL2)**, requis par Docker Desktop :

```powershell
wsl --status
```

Si la commande répond que WSL n'est pas installé :

```powershell
wsl --install --no-distribution
```

puis **redémarrer le PC**.

**2.2 Les quatre outils**, avec le gestionnaire de paquets intégré à Windows :

```powershell
winget install -e --id Docker.DockerDesktop
```

```powershell
winget install -e --id Git.Git
```

```powershell
winget install -e --id Casey.Just
```

```powershell
winget install -e --id Python.Python.3.12
```

| Outil | Rôle dans le projet |
|---|---|
| Docker Desktop | fait tourner les 20 conteneurs du SI |
| Git for Windows | récupère le code, et fournit le `bash` dont se servent quelques scripts (installé dans `C:\Program Files\Git`, emplacement attendu) |
| just | lanceur de commandes : chaque étape du projet est une recette `just` |
| Python 3.12 | génère la configuration, et fait tourner le back-office et l'assistant IA hors conteneur |

**2.3 Démarrer Docker Desktop** depuis le menu Démarrer. Accepter les conditions, ignorer la connexion à un compte Docker. Attendre en bas à gauche de la fenêtre l'indicateur **« Engine running »**.

**2.4 Fermer le terminal, puis en ouvrir un nouveau, sans les droits administrateur.** Un nouveau terminal est nécessaire pour que Windows trouve les outils fraîchement installés. Vérifier :

```powershell
docker version
```

```powershell
docker compose version
```

```powershell
git --version
```

```powershell
just --version
```

```powershell
py -3.12 --version
```

Chaque commande doit afficher un numéro de version. `docker version` doit montrer une section **Server** : sinon Docker Desktop n'est pas encore démarré.

## 3. Récupérer le code

Placer le projet dans un chemin court, sans espace ni accent, hors OneDrive :

```powershell
cd C:\
```

```powershell
git clone https://github.com/NicolasGlt/Workshop-grp10.git
```

```powershell
cd C:\Workshop-grp10
```

**Toutes les commandes suivantes se lancent depuis `C:\Workshop-grp10`**, la racine du dépôt. `just` seul affiche la liste des recettes disponibles.

> Depuis l'archive `Workshop2026-M2-G10-Code.zip` plutôt que GitHub : `Expand-Archive Workshop2026-M2-G10-Code.zip -DestinationPath C:\`, puis `cd` dans le dossier extrait.

## 4. Générer la configuration

```powershell
just env
```

La commande crée les fichiers de configuration `poc-resilience\.env`, `auth-faciale\.env` et `rag-assistant\.env` depuis leurs modèles, et **génère un secret aléatoire** pour chaque mot de passe, clé et jeton. Résultat attendu :

```text
poc-resilience/.env créé : 9 secret(s) généré(s) POSTGRES_PASSWORD, APP_DB_PASSWORD, ...
auth-faciale/.env créé : 1 secret(s) généré(s) BACKOFFICE_DB_PASSWORD
rag-assistant/.env créé : 0 secret(s) généré(s)

Comptes d'administration (valeurs lues dans poc-resilience/.env) :
  Grafana  http://localhost:3000  admin / 9ef2cf95...
  pgAdmin  http://localhost:5050  admin@example.com / 098337df...
```

**Noter le mot de passe Grafana**, utile à l'étape 7. Pour le retrouver plus tard :

```powershell
Select-String GRAFANA_ADMIN_PASSWORD poc-resilience\.env
```

Les `.env` ne sont jamais versionnés. Le dépôt contient aussi une version **chiffrée** des secrets de l'équipe (`secrets/*.enc.env`, SOPS + age), lisible par les seuls membres : vous n'en avez pas besoin, vos secrets générés localement la remplacent.

## 5. Démarrer le SI

```powershell
just demo-prep
```

La commande construit les images, démarre les 20 conteneurs, attend qu'ils soient tous sains, puis attend que le détecteur ML ait **appris la normale du trafic** (environ 2 minutes). Le premier lancement télécharge et construit les images : compter 5 à 10 minutes selon la connexion. Fin attendue :

```text
Conteneurs : 20/20 sains
  ml-detector en apprentissage de la normale (~2 min)...
Detecteur entraine : pret pour just demo
Boutique          http://localhost:8082
...
```

Pendant l'apprentissage, ne lancez pas de charge sur le SI : le modèle apprendrait une normale faussée. L'état des conteneurs à tout moment :

```powershell
just ps
```

## 6. Vérifier que tout fonctionne

```powershell
just smoke
```

Le test parcourt la chaîne applicative, fait un paiement par carte à travers le WAF, vérifie qu'une injection SQL est bloquée, puis interroge Prometheus et Grafana. Chaque ligne doit être `[OK]`, et la dernière :

```text
Résultat : N OK / 0 FAIL
```

## 7. Faire un achat comme un client

| Interface | Adresse | Identifiants |
|---|---|---|
| Boutique (Brûlerie du Comptoir) | http://localhost:8082 | achat sans compte |
| NovaPay, espace client de la banque | http://localhost:8083 | `alice@example.com` / `Alice_Test_2026!` |
| Grafana, supervision | http://localhost:3000 | `admin` / mot de passe de l'étape 4 |
| API Comptes, documentation Swagger | http://localhost:8081/docs | aucun |
| pgAdmin, console de la base | http://localhost:5050 | identifiants affichés à l'étape 4 |
| Prometheus | http://localhost:9090 | aucun |

**7.1 Paiement direct.** Sur la boutique, ajouter un café au panier, « Passer au paiement », remplir les coordonnées, puis la carte `5555 5555 5555 4444`, date future, CVV `123`. Résultat : commande confirmée avec sa référence bancaire.

**7.2 Paiement avec validation forte (3DS).** Même parcours avec la carte d'Alice `4242 4242 4242 4242`. Le paiement passe en attente : se connecter à NovaPay avec le compte d'Alice et valider l'opération. La boutique affiche alors la confirmation.

**7.3 Carte refusée.** La carte `4000 0000 0000 0002` est refusée pour fonds insuffisants.

**7.4 Supervision.** Dans Grafana, menu Dashboards, dossier **Resilience-Alpha** : le dashboard **01 · Paiements** montre vos transactions. Les paiements du trafic simulé (préfixe `[SIM]`) sont masqués par défaut, la variable **Origine des paiements** les affiche.

## 8. La preuve : attaque, détection, reprise autonome

C'est le cœur du sujet. Ouvrir d'abord dans Grafana le dashboard **07 · Résilience** et vérifier que le panneau **Modèle entraîné** vaut **1**.

**8.1 Suivre les décisions en direct** (facultatif). Dans un second terminal PowerShell, depuis `C:\Workshop-grp10` :

```powershell
just logs ml-detector remediation
```

`Ctrl+C` arrête l'affichage, pas les services.

**8.2 Lancer la démonstration**, dans le premier terminal :

```powershell
just demo
```

Le script déroule quatre temps, sans aucune intervention :

| Temps | Ce qui se passe | Sortie attendue |
|---|---|---|
| 1. Avant | un achat sur la boutique | `Paiement de contrôle : approved` |
| 2. Incident | 60 s de saturation HTTP du WAF (`hey`, 90 connexions) | statistiques de `hey`, dont de nombreuses réponses `[403]` |
| 3. Reprise | le détecteur (Local Outlier Factor) voit le débit sortir de la normale apprise, la remédiation Ansible bloque l'émetteur | `Remédiations déclenchées : 1` |
| 4. Après | un nouvel achat sur la boutique | `Nouveau paiement : approved` |

Dans Grafana 07, au même moment : le débit monte, le score d'anomalie passe le drapeau, une remédiation est comptée, une IP apparaît dans **IP bloquées actuellement**, et la disponibilité de l'API reste à 1.

L'IP bloquée affichée est celle de la passerelle du réseau Docker (`172.x.0.1`) : sous Docker Desktop, le relais réseau de Windows réécrit l'adresse source. Le blocage coupe bien l'attaquant. Sur un hôte Linux, l'adresse réelle apparaîtrait.

**8.3 Rejouer.** Un blocage dure 5 minutes. Pour rejouer sans attendre :

```powershell
just attack-reset
```

puis attendre **une minute** que le débit retombe, et relancer `just demo`.

## 9. Sauvegarde et restauration de la base

Pilier continuité d'activité (PRA). Les commandes passent par le conteneur de la base, aucun client PostgreSQL n'est requis.

```powershell
just backup
```

Crée un dump horodaté dans `poc-resilience\backup\dumps\`, avec son empreinte SHA-256 et le nombre de lignes de chaque table.

```powershell
just restore-check
```

Restaure ce dump dans une base de test séparée, compare chaque table au dump, puis supprime la base de test : la base en service n'est pas touchée. Toutes les tables doivent être identiques.

`just restore` remplace réellement la base de service (confirmation demandée) et affiche le **RTO mesuré**.

## 10. Panne de service et assistant IA

Cette étape demande **Ollama**, qui fait tourner un modèle de langage en local. Elle montre deux choses : un assistant qui répond aux opérateurs à partir de la documentation de l'équipe (RAG), et un orchestrateur qui, quand un service tombe, demande au modèle **quel** service relancer, valide sa réponse contre une liste fermée, puis lance la reprise.

**10.1 Installer Ollama et les modèles** (PowerShell administrateur pour la première commande) :

```powershell
winget install -e --id Ollama.Ollama
```

Puis dans un terminal normal :

```powershell
ollama pull qwen2.5:7b
```

```powershell
ollama pull nomic-embed-text
```

Le premier est le modèle de réponse (7 milliards de paramètres, environ 5 Go), le second sert à indexer la documentation. Sur un PC sans carte graphique dédiée, `qwen2.5:3b` répond plus vite.

**10.2 Installer l'assistant**, depuis `C:\Workshop-grp10` :

```powershell
just assistant-install
```

```powershell
notepad rag-assistant\.env
```

Dans le Bloc-notes, compléter la ligne `RAG_MODEL=` avec le nom exact du modèle, par exemple `RAG_MODEL=qwen2.5:7b`, puis enregistrer et fermer.

```powershell
just assistant-index
```

```powershell
just assistant-check
```

Le diagnostic vérifie Ollama, les modèles et l'index, puis pose une question test. Toutes les lignes doivent être au vert.

**10.3 Lancer l'assistant** dans un **deuxième terminal**, à laisser ouvert :

```powershell
cd C:\Workshop-grp10
```

```powershell
just assistant
```

Ouvrir http://127.0.0.1:8001 et poser par exemple « Que faire si la démo ne détecte pas le flood ? ». La réponse cite ses sources dans la documentation.

**10.4 Lancer l'orchestrateur** dans un **troisième terminal**, à laisser ouvert :

```powershell
cd C:\Workshop-grp10
```

```powershell
just orchestrator-install
```

```powershell
just orchestrator
```

Ouvrir la timeline de l'incident : http://127.0.0.1:8002

**10.5 Provoquer une panne**, dans le premier terminal :

```powershell
just chaos
```

La commande arrête le service `bank`. Sur la timeline : dégradation détectée, question au modèle, décision (`restart_service bank`, avec la raison), redémarrage, service rétabli. Autre service :

```powershell
just chaos api
```

Si la réponse du modèle est invalide, un repli déterministe relance le service observé en panne : la reprise ne dépend jamais du modèle. La base `db` est volontairement exclue des redémarrages automatiques.

## 11. Back-office à reconnaissance faciale

Demande une **webcam**. Le back-office tourne hors conteneur pour accéder à la caméra, et s'appuie sur la base du SI, qui doit tourner.

**11.1 Installer** :

```powershell
just backoffice-install
```

**11.2 Choisir la caméra.** Ouvrir `auth-faciale\.env` :

```powershell
notepad auth-faciale\.env
```

Mettre `CAM_INDEX=0` si le PC n'a qu'une webcam (intégrée ou USB), laisser `1` pour une webcam USB à côté d'une webcam intégrée. Enregistrer.

**11.3 Lancer**, dans un terminal à laisser ouvert :

```powershell
just backoffice
```

**11.4 Créer le premier administrateur.** Ouvrir http://127.0.0.1:8000 : à la première visite, la page d'installation demande un identifiant, un mot de passe (8 caractères minimum), puis enregistre le visage sous 5 angles en suivant les consignes à l'écran.

**11.5 Se connecter.** Saisir l'identifiant : la caméra s'allume et vérifie le visage, puis le mot de passe est demandé. Deux échecs bloquent le compte 5 minutes. La gestion des habilitations est dans le back-office, pour un administrateur.

La LED connectée (carte ESP8266) est facultative : sans la carte, le back-office fonctionne et ignore la LED. Montage et firmware : [auth-faciale/README.md](auth-faciale/README.md#firmware-de-lesp8266).

## 12. Attaque depuis un second PC

Le sujet prévoit une attaque venue d'un **PC Attaquant** relié au point d'accès du groupe. L'étape 8 lance la même attaque depuis un conteneur du PC Hôte, ce qui suffit à prouver la boucle. Cette variante utilise deux PC Windows.

**Sur le PC Hôte** (celui des étapes 1 à 8) :

1. Paramètres Windows, Réseau et Internet, **Point d'accès sans fil mobile** : activé, nom `RESILIENCE-G10`, bande 2,4 GHz. Le PC Hôte prend l'adresse `192.168.137.1`.
2. Ouvrir le port du WAF au seul réseau du point d'accès, dans PowerShell administrateur :

```powershell
New-NetFirewallRule -DisplayName "RESILIENCE-ALPHA WAF" -Direction Inbound -Protocol TCP -LocalPort 80 -RemoteAddress 192.168.137.0/24 -Action Allow
```

**Sur le PC Attaquant** : refaire les étapes 2 et 3 (Docker Desktop, Git, just suffisent), se connecter au Wi-Fi `RESILIENCE-G10`, puis depuis `C:\Workshop-grp10` :

```powershell
just attack-check
```

Les trois contrôles doivent passer : adresse en `192.168.137.x`, WAF joignable, image `hey` disponible ou téléchargeable.

```powershell
just attack http://192.168.137.1 120s 90
```

Pendant les 120 s d'attaque, faire un achat sur la boutique du PC Hôte : il doit être approuvé. Le dashboard 07 montre la détection et le blocage. Un garde-fou refuse toute cible hors de `192.168.137.0/24` et de `localhost`.

## 13. Tests automatisés

**Back-office** (sans caméra ni base) :

```powershell
auth-faciale\.venv\Scripts\python -m pip install pytest
```

```powershell
auth-faciale\.venv\Scripts\python -m pytest auth-faciale\tests
```

**Laboratoire ML** (données simulées, indépendant du SI) :

```powershell
cd ml-lab
```

```powershell
py -3.12 -m venv .venv
```

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

```powershell
.venv\Scripts\python -m pytest
```

```powershell
cd ..
```

## 14. Arrêter et nettoyer

| Besoin | Commande |
|---|---|
| Arrêter un service lancé dans un terminal (assistant, orchestrateur, back-office) | `Ctrl+C` dans ce terminal |
| Arrêter le SI, données conservées | `just down` |
| Redémarrer le SI | `just demo-prep` |
| Tout effacer : base, métriques, logs (confirmation demandée) | `just reset` |

## Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| `just` ou `py` : « n'est pas reconnu » | terminal ouvert avant l'installation | fermer et rouvrir le terminal |
| `docker version` sans section Server | Docker Desktop arrêté | le lancer, attendre « Engine running » |
| `just demo-prep` : port 80 déjà utilisé | IIS ou un autre serveur web | `Get-NetTCPConnection -LocalPort 80` pour trouver le processus, l'arrêter |
| `just demo-prep` bloque sur les conteneurs | un conteneur redémarre en boucle | `just ps`, puis `just logs <service>` |
| `db` en boucle, erreur `\r` ou `not found` | fichiers convertis en fins de ligne Windows (copie hors Git) | recloner avec `git clone` (le dépôt impose les bonnes fins de ligne), puis `just reset` et `just demo-prep` |
| `just demo-prep` bloque sur l'apprentissage | pas de trafic, ou Prometheus injoignable | `just logs ml-detector traffic` |
| `just demo` : « détecteur non entraîné » | SI redémarré il y a moins de 2 minutes | relancer `just demo-prep` |
| `Remédiations déclenchées : 0` | attaquant encore bloqué par la démo précédente | normal, les 403 le montrent. Pour rejouer à neuf : `just attack-reset` |
| Pas de remédiation pendant l'attaque | normale apprise pendant une charge inhabituelle | `just down`, puis `just demo-prep` sans rien lancer pendant l'apprentissage |
| Grafana vide | Prometheus ou Loki pas encore prêts | attendre une minute, recharger |
| `just smoke`, `just backup` : `bash.exe` introuvable | Git for Windows installé ailleurs | réinstaller Git dans `C:\Program Files\Git` |
| `just assistant-check` : Ollama injoignable | Ollama non lancé | le lancer depuis le menu Démarrer |
| Back-office : « Caméra indisponible » | mauvais index, ou caméra prise par Teams | régler `CAM_INDEX`, fermer l'autre application |
| Back-office : `"database": false` sur http://127.0.0.1:8000/api/health | SI arrêté | `just demo-prep` |

## Pour aller plus loin

| Document | Contenu |
|---|---|
| [README.md](README.md) | présentation du projet et arborescence |
| [poc-resilience/README.md](poc-resilience/README.md) | services, API, observabilité, boucle de résilience |
| [poc-resilience/docs/architecture.md](poc-resilience/docs/architecture.md) | architecture détaillée et réseaux |
| [docs/demo-jour-j.md](docs/demo-jour-j.md) | déroulé de la démo devant le jury |
| [attacker/README.md](attacker/README.md) | périmètre et scénario de l'attaque |
| [rag-assistant/README.md](rag-assistant/README.md), [incident-orchestrator/README.md](incident-orchestrator/README.md) | assistant IA et orchestrateur |
| [auth-faciale/README.md](auth-faciale/README.md) | back-office biométrique |
| [poc-resilience/secrets/README.md](poc-resilience/secrets/README.md) | gestion des secrets de l'équipe |
