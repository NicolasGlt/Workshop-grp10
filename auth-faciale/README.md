# auth-faciale : authentification du back-office par visage et LED connectée

Brique de sécurité du projet **PROJECT RESILIENCE-ALPHA** (workshop M2 EPSI 2026-27, groupe 10), en réponse à la **consigne additionnelle 1** : entre l'identifiant et le mot de passe, le back-office vérifie le visage de l'utilisateur avec une webcam USB branchée sur le PC Hôte, et un ESP8266 relié en Wi-Fi affiche chaque étape sur une LED bicolore.

> Prototype de workshop : fonctionnel et testé sur le matériel du groupe, pas un produit industriel. Les limites connues sont listées dans la section [Sécurité](#9-sécurité).

## Sommaire

1. [Fonctionnalités](#1-fonctionnalités)
2. [Démarrage rapide](#2-démarrage-rapide)
3. [Utilisation](#3-utilisation)
4. [Configuration](#4-configuration)
5. [Architecture](#5-architecture)
6. [Fonctionnement détaillé](#6-fonctionnement-détaillé)
7. [Référence de l'API](#7-référence-de-lapi)
8. [Modèle de données](#8-modèle-de-données)
9. [Sécurité](#9-sécurité)
10. [Tests](#10-tests)
11. [Dépannage](#11-dépannage)
12. [Choix et écarts par rapport à la consigne](#12-choix-et-écarts-par-rapport-à-la-consigne)
13. [Documents associés et sources](#13-documents-associés-et-sources)

---

## 1. Fonctionnalités

- **Connexion en trois temps** : identifiant → reconnaissance du visage par la webcam USB → mot de passe. Le mot de passe n'est accepté qu'après un visage reconnu.
- **Règle d'échec de la consigne** : identifiant vidé et caméra éteinte après un échec ; un réessai, puis identifiant bloqué 5 minutes.
- **IA légère sur le PC Hôte** : détection YuNet et reconnaissance SFace (OpenCV), sur le processeur, sans compilation.
- **Gestion des habilitations dans le back-office** : comptes, rôles, enrôlement et suppression du visage, accès au back-office, mot de passe, déblocage, journal.
- **Installation web du premier admin** (`/setup`) et **enrôlement guidé sur 5 angles** (face, gauche, droite, haut, bas), aperçu de la caméra et consigne affichés avant toute capture.
- **LED bicolore pilotée en Wi-Fi par un ESP8266**, avec les 5 comportements exigés : éteinte, vert clignotant, vert fixe 30 s, rouge ×10, rouge fixe 30 s.
- **Journal d'authentification** en base et en JSON sur la sortie standard (prêt pour Loki / SIEM).

## 2. Démarrage rapide

### Prérequis

| Élément | Version / modèle utilisé |
|---|---|
| Windows 10/11 (PC Hôte) | Windows 11 |
| Python | 3.12 |
| Webcam USB (classe vidéo standard) | webcam 1080p générique |
| Carte ESP8266 + LED bicolore à cathode commune + 1 résistance (100 Ω à 1 kΩ) | NodeMCU LoLin V3 (ESP-12F) |
| CLion + PlatformIO Core (IDE imposé par la consigne) | CLion 2026.2, PlatformIO Core 6.2 |
| Point d'accès Windows du groupe | `RESILIENCE-G<n>`, bande **2,4 GHz**, PC en 192.168.137.1 |

### Installation

Depuis la racine du dépôt (pas à pas complet : [GUIDE-WINDOWS.md](../GUIDE-WINDOWS.md#11-back-office-à-reconnaissance-faciale)) :

```powershell
just env                 # crée auth-faciale\.env, BACKOFFICE_DB_PASSWORD identique à poc-resilience\.env
just backoffice-install  # .venv et dépendances
notepad auth-faciale\.env   # CAM_INDEX=0 si le PC n'a qu'une webcam
```

La base est celle du SI : la stack `poc-resilience` doit tourner (PostgreSQL publié sur `127.0.0.1:5432` seulement). Une ancienne base SQLite se reprend sans réenrôler : `.venv\Scripts\python scripts\migrate_sqlite.py auth.db`.

Les deux modèles ONNX sont fournis dans `models/` (origine et empreintes en [section 13](#13-documents-associés-et-sources)).

### Firmware de l'ESP8266

1. Copier `esp8266/include/secrets.h.example` en `esp8266/include/secrets.h`, puis renseigner le nom et le mot de passe du point d'accès, et un jeton aléatoire `LED_TOKEN` (ce fichier n'est jamais versionné).
2. Brancher la carte en USB. Si Windows ne la reconnaît pas, installer le pilote de la puce CH340 (`CH341SER`, éditeur WCH).
3. Ajuster `upload_port` dans `esp8266/platformio.ini` (par exemple `COM3`).
4. Dans CLion : ouvrir le dossier `esp8266/`, puis lancer la configuration « PlatformIO » (▶), qui compile et téléverse. En ligne de commande : `pio run -t upload`.
5. Câblage (carte débranchée) : patte verte → D7, patte rouge → D5, patte commune (la plus longue) → résistance → G.

### Premier administrateur

Tant qu'aucun compte n'existe, http://127.0.0.1:8000 redirige vers la page d'installation `/setup` : identifiant, mot de passe (8 caractères minimum, avec confirmation), puis enrôlement guidé du visage sur 5 angles. Le compte n'est créé qu'une fois les 5 angles capturés. La page n'accepte que le poste lui-même (client en boucle locale, sinon 403) et se ferme définitivement dès qu'un compte existe (redirection vers `/`, API en 404).

En secours, application arrêtée (la webcam ne sert qu'à un programme à la fois), le même parcours existe en ligne de commande, consignes dans la console :

```powershell
.venv\Scripts\python scripts\create_user.py <identifiant> --role admin
```

### Lancement

1. Activer le point d'accès Windows ; l'ESP s'y connecte seul (`curl.exe http://192.168.137.200/health` doit répondre).
2. Démarrer l'application :

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

3. Ouvrir http://127.0.0.1:8000 (au premier lancement : page d'installation, voir ci-dessus).

Procédure complète du jour de la démo et contrôles avant passage : [docs/lancement.md](docs/lancement.md).

## 3. Utilisation

### Se connecter

1. Saisir l'identifiant : la webcam s'allume et son image s'affiche.
2. Visage reconnu : LED **vert clignotant**, le champ mot de passe apparaît (30 s pour le saisir).
3. Mot de passe correct : LED **vert fixe 30 s**, caméra éteinte, ouverture du back-office.
4. Mot de passe faux : LED **rouge ×10**, caméra éteinte, retour à l'identifiant.
5. Visage non reconnu : LED **rouge fixe 30 s**, caméra allumée pendant ces 30 s puis éteinte, nouvelle saisie possible ensuite.
6. Deux échecs de suite sur le même identifiant : blocage **5 minutes**.

### Gérer les habilitations (rôle admin)

Back-office → **Gestion des habilitations** : créer un compte, **Enrôler** son visage (parcours guidé, voir ci-dessous), changer son rôle, retirer ou rendre l'accès, changer le mot de passe, débloquer, supprimer (confirmation en deux clics), tester la LED, consulter le journal.

Il n'y a volontairement pas d'inscription en libre-service : une habilitation est accordée par un admin.

### Enrôler un visage (installation et bouton « Enrôler »)

1. L'aperçu de la caméra s'affiche (en miroir) avant toute capture, avec la liste des 5 angles.
2. Pour chaque angle (de face, tête tournée à gauche, à droite, levée, baissée), la page affiche la consigne, une flèche, le temps restant et trois témoins : visage détecté, un seul visage, angle atteint. Un message corrige la pose (« Tournez encore la tête vers votre gauche », « Rapprochez-vous »…).
3. L'angle est capturé dès qu'il est tenu quelques images de suite ; on passe seul au suivant.
4. Angle non atteint en 20 s, ou bouton **Annuler** : rien n'est enregistré, bouton **Recommencer**. Les anciens gabarits restent en place jusqu'à un enrôlement complet.

## 4. Configuration

Réglages dans `app/config.py`, chacun surchargeable par une variable d'environnement du même nom ou par le fichier `.env` (non versionné, modèle `.env.example`).

| Variable | Défaut | Rôle |
|---|---|---|
| `BACKOFFICE_DB_PASSWORD` | aucun | mot de passe du rôle `backoffice` de la base du SI |
| `DATABASE_URL` | construit depuis `DB_HOST`, `DB_PORT`, `DB_NAME` | connexion PostgreSQL complète, prioritaire |
| `CAM_INDEX` | `1` | index de la webcam USB (`0` est souvent la webcam intégrée ; `scripts/test_camera.py` aide à le trouver). Backend MSMF sous Windows, V4L2 sous Linux |
| `GRAFANA_URL`, `PGADMIN_URL`, `SHOP_URL` | `localhost` | liens du back-office vers les outils du SI |
| `FACE_THRESHOLD` | `0.363` | seuil de similarité cosinus SFace |
| `FACE_HITS` | `3` | images au-dessus du seuil nécessaires |
| `FACE_TIMEOUT_S` | `5` | durée maximale de la vérification |
| `PASSWORD_TTL_S` | `30` | délai de saisie du mot de passe (ajout hors consigne) |
| `BACKOFFICE_DELAY_S` | `0` | attente avant l'ouverture du back-office (`0` ou `30`, selon la lecture retenue) |
| `LED_URL` | `http://192.168.137.200` | adresse de l'ESP |
| `LED_TOKEN` | lu dans `esp8266/include/secrets.h` | jeton partagé avec l'ESP |
| `SESSION_SECRET` | aléatoire à chaque démarrage | clé de signature des sessions |
| `ENROLL_ANGLE_TIMEOUT_S` | `20` | temps maximal pour tenir chaque angle de l'enrôlement |
| `ENROLL_HOLD_FRAMES` | `4` | images consécutives à la bonne orientation avant capture |
| `ENROLL_FRONT_MAX` | `0.08` | lacet maximal accepté « de face » |
| `ENROLL_YAW_MIN` | `0.15` | lacet minimal à gauche et à droite, par rapport à la pose de face |
| `ENROLL_PITCH_MIN` | `0.08` | tangage minimal en haut et en bas, par rapport à la pose de face |
| `ENROLL_MIN_FACE_PX` | `80` | largeur minimale du visage dans l'image |
| `ENROLL_YAW_SIGN` | `1` | `-1` si la caméra livre une image déjà retournée (gauche et droite inversées) |

Valeurs fixées par la consigne : 30 s de rouge (`COOLDOWN_S`), 5 min de blocage (`LOCK_S`), 2 échecs (`MAX_FAILURES`).

## 5. Architecture

```
                         PC Hôte (Windows)
 ┌─────────────────────────────────────────────────────────────┐
 │  Navigateur ──HTTP──> Application FastAPI (127.0.0.1:8000)    │
 │                          │           │            │          │
 │                     webcam USB  PostgreSQL   ordres LED      │
 │                     (OpenCV)   du SI :5432  (HTTP, file)     │
 │                                                   │          │
 │  Point d'accès Windows RESILIENCE-G<n> (192.168.137.1)        │
 └───────────────────────────────────────────────────│─────────┘
                                                     │ Wi-Fi 2,4 GHz
                                      ESP8266 (192.168.137.200)
                                      LED bicolore rouge / vert
```

Une seule application Python porte les pages web, la reconnaissance faciale, les règles d'échec, la base et le pilotage de la LED.

- **Hors Docker** : Docker Desktop sous Windows ne donne pas accès à une webcam USB (il faudrait usbipd et un noyau WSL2 recompilé). La consigne impose la caméra sur le PC Hôte, donc la partie qui la lit tourne sur l'hôte. Le rattachement au back-office conteneurisé du SI reste à décider en équipe.
- **Écoute sur 127.0.0.1** : l'application n'est pas joignable depuis le point d'accès, donc pas depuis le PC Attaquant.

### Arborescence

```
auth-faciale/
├── README.md               ce document
├── .env.example            modèle du .env (mot de passe de la base, webcam, LED)
├── docs/
│   ├── lancement.md        procédure du jour de la démo
│   ├── consigne.md         texte exact de la consigne et sa lecture
│   ├── plan.md             plan, choix techniques, hypothèses, pièges de démo
│   └── recette.md          cas de test et résultats
├── requirements.txt        dépendances Python (versions figées)
├── .gitignore
├── models/                 modèles ONNX (YuNet, SFace)
├── app/
│   ├── main.py             routes HTTP, sessions, contrôle des droits
│   ├── auth.py             machine à états du poste, règles d'échec
│   ├── face.py             détection, reconnaissance, mesure de l'angle de la tête
│   ├── enroll.py           enrôlement guidé sur 5 angles (thread + état interrogeable)
│   ├── camera.py           allumage/extinction de la webcam, flux MJPEG
│   ├── led.py              ordres à l'ESP, non bloquants
│   ├── db.py               schéma backoffice (PostgreSQL du SI), journal, lecture du métier
│   ├── config.py           réglages
│   └── static/             login.html, setup.html, backoffice.html, admin.html, enroll.js, monitor.html
├── scripts/
│   ├── create_user.py      secours de /setup : compte + enrôlement en ligne de commande
│   ├── migrate_sqlite.py   reprise d'une ancienne base SQLite (comptes et visages)
│   ├── test_camera.py      repérage de la webcam, temps d'ouverture
│   └── test_face.py        enrôlement et score en direct (calibration)
├── tests/                  tests unitaires (pytest), sans caméra ni base
└── esp8266/                projet PlatformIO (CLion)
    ├── platformio.ini
    ├── src/main.cpp        firmware de la LED
    └── include/secrets.h.example
```

Générés localement et jamais versionnés : `.venv/`, `.env`, `esp8266/include/secrets.h`, `esp8266/.pio/`.

## 6. Fonctionnement détaillé

### 6.1 Reconnaissance faciale (`app/face.py`)

- **YuNet** trouve les visages ; on garde le plus grand. **SFace** transforme le visage redressé en un vecteur de 128 nombres ; deux images de la même personne donnent des vecteurs proches (similarité cosinus).
- **Vérification 1:1** : le visage filmé n'est comparé qu'aux gabarits de l'identifiant saisi.
- **Décision** : 3 images au-dessus du seuil de 0,363 (valeur de référence publiée par OpenCV pour SFace) en moins de 5 s.
- **Enrôlement guidé** (`app/enroll.py`) : un vecteur par angle, 5 angles (face, gauche, droite, haut, bas), seulement quand un seul visage est visible. Les profils améliorent la reconnaissance quand la personne ne regarde pas parfaitement la caméra. Aucune photo n'est conservée.
- **Mesure de l'angle** (`face.pose`) : à partir des 5 points de repère que YuNet renvoie déjà (yeux, bout du nez, coins de la bouche), sans modèle supplémentaire. Lacet = décalage horizontal du nez par rapport au milieu des yeux, divisé par l'écart entre les yeux. Tangage = position verticale du nez entre la ligne des yeux (0) et celle de la bouche (1). Ce sont des rapports entre points du visage, donc indépendants de la distance à la caméra ; gauche, droite, haut et bas se jugent par rapport à la pose de face capturée en premier, ce qui absorbe les différences de morphologie.
- **Mesures du 20/10/2026** : utilisateur légitime à 0,49 au pire (0,88 en moyenne) ; une autre personne présentée sur ce compte, 0,18.
- **Écartés** : `face_recognition` (dépend de dlib, compilation C++ sous Windows) et LBPH (sensible à l'éclairage, demande `opencv-contrib`).

### 6.2 Caméra (`app/camera.py`)

La webcam est réellement ouverte et fermée, comme l'exige la consigne. Un thread lit les images tant qu'elle est allumée ; la vérification et l'aperçu dans la page lisent la dernière image. La première ouverture à froid prend environ 4 s, les suivantes moins de 0,5 s : l'application fait une ouverture « à blanc » au démarrage. Pilote retenu : MSMF avec `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`, mesuré plus rapide que DirectShow sur notre webcam.

### 6.3 Machine à états du poste (`app/auth.py`)

| État | Caméra | LED | Transition |
|---|---|---|---|
| `idle` | éteinte | éteinte | identifiant saisi → `verifying` |
| `verifying` | allumée | inchangée | reconnu → `wait_password` ; sinon → `cooldown` |
| `wait_password` | allumée | vert clignotant | mot de passe reçu ou 30 s écoulées → `idle` |
| `cooldown` | allumée | rouge fixe | 30 s écoulées : caméra coupée → `idle` |
| `enrolling` | allumée | inchangée | 5 angles capturés, échec, annulation → `idle` |

Un seul poste et une seule caméra : l'état est global, et toute saisie hors de `idle` reçoit « poste occupé ». Le mot de passe n'est accepté qu'avec le jeton `login_id` délivré après reconnaissance : aléatoire, à usage unique, lié à l'utilisateur, valable 30 s.

### 6.4 Échecs et blocage

- Un compteur par identifiant ; un visage non reconnu et un mot de passe faux comptent chacun (hypothèse : le texte lie la règle au visage, l'étendre au mot de passe évite de tester des mots de passe sans limite une fois le visage passé).
- 2e échec : blocage de 5 minutes à partir de cet échec. Une connexion réussie remet le compteur à zéro.
- Un identifiant inconnu se comporte comme un visage non reconnu (même réponse, même durée) : on ne peut pas deviner quels comptes existent. Il n'est jamais stocké en clair, seulement sous forme d'empreinte HMAC (`inconnu-xxxxxxxxxxxx`), car un mot de passe tapé dans le mauvais champ finirait sinon dans le journal.
- Un compte dont l'accès est retiré est traité comme inconnu.

### 6.5 LED et ESP8266 (`app/led.py`, `esp8266/src/main.cpp`)

Comportement attendu de la LED à chaque étape du parcours, confronté au code : [docs/led.md](docs/led.md).

L'ESP est un petit serveur HTTP à l'adresse fixe 192.168.137.200. L'application lui envoie un mode ; l'ESP gère seul durées et clignotements avec `millis()`, sans bloquer.

| Requête | Effet |
|---|---|
| `POST /led?mode=off&k=<jeton>` | éteinte |
| `POST /led?mode=green_blink&k=<jeton>` | vert clignotant (2 fois par seconde) jusqu'à l'ordre suivant |
| `POST /led?mode=green_fixed&k=<jeton>` | vert fixe 30 s, puis extinction |
| `POST /led?mode=red_blink10&k=<jeton>` | rouge clignotant exactement 10 fois, puis extinction |
| `POST /led?mode=red_fixed&k=<jeton>` | rouge fixe 30 s, puis extinction |
| `GET /health` | mode courant et force du signal |

Sans le bon jeton : 403 ; mode inconnu : 400. Les ordres passent par une file traitée par un seul thread (ordre garanti, 0,5 s de délai maximal). **Si l'ESP ne répond pas, la connexion continue** et l'incident est journalisé (`led_unreachable`) : la LED est un témoin, pas un contrôle d'accès. La consigne ne tranche pas ce cas ; c'est un choix à valider en équipe.

Câblage sans fils de connexion : pattes extérieures directement sur D7 (vert, GPIO13) et D5 (rouge, GPIO14), patte commune vers G à travers une seule résistance, suffisante parce que les deux couleurs ne s'allument jamais ensemble.

### 6.6 Habilitations

Rôles `admin`, `operateur`, `lecteur`. Seule la distinction admin / non-admin a un effet aujourd'hui (accès à la gestion des habilitations) ; les deux autres rôles sont prêts pour le back-office du SI. Un admin ne peut ni se retirer ses propres droits ni se supprimer.

### 6.7 Journal

Événements écrits en base et en une ligne JSON sur la sortie standard : `face_ok` (avec score), `face_ko`, `login_ok`, `password_ko`, `password_timeout`, `locked_attempt`, `camera_error`, `user_created`, `user_updated`, `user_deleted`, `face_enrolled` (avec le nombre d'angles), `face_enroll_failed` (avec la raison), `face_deleted`, `user_unlocked`, `setup_admin_created` (premier admin créé par `/setup`), `led_unreachable`.

## 7. Référence de l'API

| Méthode et route | Accès | Rôle |
|---|---|---|
| `GET /` | public | page de connexion ; redirige vers `/setup` tant qu'aucun compte n'existe |
| `GET /setup` | boucle locale, aucun compte | installation du premier admin ; 403 hors boucle locale, redirection vers `/` dès qu'un compte existe |
| `POST /api/setup/start` `{username, password, confirm}` | boucle locale, aucun compte | lance l'enrôlement (202) ; le compte admin est créé à la fin ; 400 saisie invalide, 403 hors boucle locale, 404 installation faite, 409 poste occupé |
| `GET /api/enroll/state` | page qui a lancé l'enrôlement | angle en cours, consigne, témoins, temps restant, statut (`running`, `done`, `failed`, `cancelled`) |
| `POST /api/enroll/cancel` | page qui a lancé l'enrôlement | annulation |
| `GET /backoffice` | connecté | back-office (page provisoire) |
| `GET /admin` | admin | gestion des habilitations |
| `GET /monitor` | local | outil de test : état du poste et caméra |
| `GET /camera/stream` | local | flux MJPEG, caméra allumée uniquement |
| `POST /api/identify` `{username}` | public | `face_ok` + `login_id` ; `face_ko` + `retry_after` ; `locked` (423) ; `busy` (409) ; `camera_error` (503) |
| `POST /api/password` `{login_id, password}` | public | `ok` + cookie de session ; `pwd_ko` ; `invalid` (400) |
| `POST /api/logout` | connecté | fermeture de session |
| `GET /api/me` | connecté | identifiant et rôle |
| `GET /api/state` | public | état du poste, temps restant, caméra |
| `GET /api/health` | public | caméra, ESP, état du poste |
| `GET /api/admin/users` | admin | comptes, visage, blocage |
| `POST /api/admin/users` | admin | création |
| `PATCH /api/admin/users/{id}` | admin | rôle, accès, mot de passe |
| `DELETE /api/admin/users/{id}` | admin | suppression |
| `POST /api/admin/users/{id}/face` | admin | lance l'enrôlement guidé (202), suivi par `/api/enroll/state` ; 409 poste occupé |
| `DELETE /api/admin/users/{id}/face` | admin | suppression du visage |
| `POST /api/admin/users/{id}/unlock` | admin | déblocage |
| `POST /api/admin/led/test` | admin | séquence de test de la LED |
| `GET /api/admin/events` | admin | 50 derniers événements |

« Public » et « local » : sans session, mais l'application n'écoute que sur 127.0.0.1.

## 8. Modèle de données

Schéma `backoffice` de la base PostgreSQL du SI, tables créées au premier lancement (`app/db.py`). Le rôle `backoffice` (`poc-resilience/db/init/05-backoffice.sh`) en est propriétaire et ne fait que **lire** le métier : transactions, commandes, journal, marchands sans la colonne `api_key`. Il ne voit ni les cartes ni les clés API, et ne peut rien écrire hors de son schéma (vérifié le 21/10).

| Table | Contenu |
|---|---|
| `users` | identifiant, empreinte bcrypt du mot de passe, rôle, accès, date de création |
| `face_templates` | 5 vecteurs SFace par utilisateur, date, auteur ; supprimés avec l'utilisateur |
| `login_lockouts` | compteur d'échecs et fin de blocage, par identifiant (empreinte pour les inconnus) |
| `auth_events` | journal horodaté |

Dates en horodatage Unix (secondes).

## 9. Sécurité

**Mesures en place**

- Mots de passe stockés en empreinte bcrypt salée, jamais en clair, jamais journalisés.
- Mot de passe accepté uniquement avec le jeton « visage reconnu », à usage unique et court.
- 2 échecs → 5 minutes de blocage ; comparaisons de jetons en temps constant.
- Session par cookie signé, `SameSite=Strict`, 8 h maximum ; secret renouvelé à chaque démarrage.
- Droits d'administration vérifiés côté serveur sur chaque route `/api/admin/*`.
- Application limitée à 127.0.0.1 ; ESP protégé par jeton ; identifiants inconnus jamais stockés en clair.
- Installation `/setup` : client en boucle locale exigé en plus de l'écoute sur 127.0.0.1, fermée dès qu'un compte existe ; le premier admin et ses gabarits sont créés en une transaction qui verrouille la table et revérifie qu'elle est vide (deux installations simultanées ne créent qu'un compte).
- L'état d'un enrôlement n'est lisible que par la session de navigateur qui l'a lancé.
- Biométrie minimisée : vecteurs uniquement, aucune photo.
- Secrets hors du dépôt (`secrets.h`, `.env` dans `.gitignore`).
- Base du SI publiée sur 127.0.0.1 seulement, rôle dédié en moindre privilège.

**Limites connues**

- Pas de détection du vivant : une photo du visage sur un téléphone peut tromper SFace. Parade industrielle : caméra infrarouge (type Windows Hello) ou défi-réponse.
- Trafic vers l'ESP en HTTP clair sur le point d'accès : un appareil connecté qui capterait le jeton pourrait piloter la LED, sans effet sur l'authentification.
- Gabarits stockés en clair dans la base (en production : chiffrement applicatif des gabarits, secrets dans Vault).
- Politique de mot de passe minimale (8 caractères).
- Données biométriques (article 9 du RGPD) : consentement des personnes enrôlées, purge du schéma `backoffice` après le workshop.
- N'importe qui peut bloquer un compte 5 minutes en échouant deux fois sur son identifiant.
- Si l'unique admin est bloqué, personne ne peut débloquer : prévoir deux admins.

## 10. Tests

- [docs/recette.md](docs/recette.md) : les 6 cas de la consigne, les cas de sécurité et ceux de l'installation et de l'enrôlement, avec leurs résultats.
- `tests/` : tests unitaires sans caméra ni base (points de repère synthétiques, caméra et base simulées) : mesure d'angle, parcours des 5 angles, échecs et reprise, installation fermée et refusée hors boucle locale. Lancement depuis `auth-faciale/` : `.venv\Scripts\python -m pip install pytest` puis `.venv\Scripts\python -m pytest tests`, ou sous Linux `uv run --python 3.13 --no-project --with-requirements requirements.txt --with pytest pytest tests`.
- `scripts/test_camera.py <dossier>` : sonde les index 0 à 3, enregistre une image par caméra et mesure l'ouverture ; `--show <index>` pour un aperçu.
- `scripts/test_face.py <fichier.npy> [index] [étiquette]` : enrôle un visage, affiche le score en direct et un bilan par étiquette (« moi » / « autre ») pour régler le seuil.
- Page `/monitor` : état du poste et image de la caméra en temps réel.

## 11. Dépannage

| Symptôme | Cause probable | Action |
|---|---|---|
| La LED ne réagit plus | point d'accès coupé | le réactiver, attendre 10 s |
| L'ESP ne voit pas le réseau | point d'accès en 5 GHz | forcer la bande 2,4 GHz |
| La carte n'apparaît pas en port COM | câble de charge seule, ou pilote CH340 absent | autre câble, pilote `CH341SER` |
| « Caméra indisponible » | webcam débranchée ou prise par une autre application | rebrancher, fermer l'autre application |
| Mauvaise caméra utilisée | index 0 = webcam intégrée | régler `CAM_INDEX` |
| « Poste occupé » | 30 s de rouge ou saisie du mot de passe en cours | attendre la fin du compte à rebours |
| Enrôlement : un angle n'est jamais « atteint » | seuil trop exigeant pour la personne, ou lumière de côté | lire lacet et tangage affichés sous les témoins, ajuster `ENROLL_YAW_MIN` / `ENROLL_PITCH_MIN` |
| Enrôlement : « gauche » demande de tourner à droite | image déjà retournée par la caméra | `ENROLL_YAW_SIGN=-1` |
| `/setup` répond 403 | page ouverte depuis une autre machine | l'ouvrir sur le PC Hôte, en `127.0.0.1` |
| Compte bloqué | 2 échecs sur l'identifiant | bouton « Débloquer » (autre admin) ou attendre 5 min |
| Port 8000 occupé | ancienne instance lancée | fermer l'autre terminal |

## 12. Choix et écarts par rapport à la consigne

Détail dans [docs/plan.md](docs/plan.md), sections 6 et 9.

- **Délai de 30 s pour le mot de passe** : ajouté pour que la LED ne clignote pas indéfiniment, alors que le texte dit « jusqu'à la saisie du mot de passe ». À valider en équipe.
- **Échec du mot de passe compté** dans la règle « 1 réessai puis 5 minutes » : hypothèse.
- **Back-office accessible dès le mot de passe validé**, la LED restant verte 30 s : hypothèse, réglable (`BACKOFFICE_DELAY_S`).
- **ESP hors ligne** : la connexion continue (choix de résilience) ; la consigne ne dit rien.
- **Hors Docker** à cause de la webcam ; intégration au back-office du SI à décider.

## 13. Documents associés et sources

**Documents**

- [docs/lancement.md](docs/lancement.md) : mise en route et contrôles avant la démo.
- [docs/consigne.md](docs/consigne.md) : texte exact de la consigne et ce qu'il impose.
- [docs/plan.md](docs/plan.md) : plan d'implémentation, choix techniques, pièges de démo, scénario « avant / après habilitation ».
- [docs/recette.md](docs/recette.md) : cas de test et résultats.

**Modèles** (dépôt GitHub `opencv/opencv_zoo`, licences dans ce dépôt)

| Fichier | Taille | SHA-256 |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | 232 589 octets | `8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4` |
| `face_recognition_sface_2021dec.onnx` | 38 696 353 octets | `0BA9FBFA01B5270C96627C4EF784DA859931E02F04419C829E83484087C34E79` |

**Sources**

- [OpenCV : DNN-based Face Detection and Recognition](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)
- [JetBrains : PlatformIO dans CLion](https://www.jetbrains.com/help/clion/platformio.html)
- [Forum OpenCV : lenteur d'ouverture MSMF](https://forum.opencv.org/t/the-msmf-backend-is-slow-to-acquire-the-initial-frame/24121)
- [Forum Docker : USB sur Docker Desktop WSL2](https://forums.docker.com/t/usb-ip-on-docker-desktop-wsl2-backend/135921)
