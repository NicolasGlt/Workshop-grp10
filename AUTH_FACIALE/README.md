# Authentification renforcée du back-office (consigne additionnelle 1)

Workshop M2 EPSI 2026-27, PROJECT RESILIENCE-ALPHA, groupe 10.

Ce dossier contient la réponse à la consigne additionnelle 1 : ajouter au back-office une vérification du visage par caméra USB entre l'identifiant et le mot de passe, gérer les habilitations dans le back-office, et signaler chaque étape par une LED bicolore pilotée en Wi-Fi par un ESP8266. Le texte exact de la consigne est dans [CONSIGNE.md](CONSIGNE.md).

Documents associés :

- [LANCEMENT.md](LANCEMENT.md) : démarrer la solution en deux minutes ;
- [PLAN.md](PLAN.md) : plan d'implémentation, choix techniques, hypothèses, pièges de démo ;
- [RECETTE.md](RECETTE.md) : cas de test et résultats ;
- [progress.md](progress.md) : journal d'avancement et décisions.

---

## 1. Ce que voit l'utilisateur

1. Il saisit son identifiant sur la page de connexion.
2. La webcam USB du PC Hôte s'allume et l'image s'affiche dans la page.
3. Si son visage correspond à celui enregistré pour cet identifiant, la LED passe au vert clignotant et le champ mot de passe apparaît.
4. Mot de passe correct : LED verte fixe 30 s puis éteinte, caméra coupée, le back-office s'ouvre.
5. Mot de passe faux : LED rouge qui clignote 10 fois puis s'éteint, caméra coupée, l'identifiant est vidé et tout recommence.
6. Visage non reconnu : LED rouge fixe 30 s, la caméra reste allumée pendant ces 30 s puis s'éteint, l'identifiant est vidé et peut être ressaisi.
7. Deux échecs de suite sur le même identifiant (visage ou mot de passe) : identifiant bloqué 5 minutes.

Un administrateur gère depuis le back-office les comptes, leurs rôles, leur accès, l'enregistrement de leur visage et le déblocage.

## 2. Architecture

```
                 PC Hôte (Windows)
 ┌──────────────────────────────────────────────────────────┐
 │  Navigateur ──HTTP──> Application FastAPI (127.0.0.1:8000) │
 │                          │        │          │            │
 │                     webcam USB  SQLite    file d'ordres   │
 │                     (OpenCV)   auth.db     LED (HTTP)      │
 │                                                │          │
 │  Point d'accès Windows RESILIENCE-G10 (192.168.137.1)      │
 └────────────────────────────────────────────────│─────────┘
                                                  │ Wi-Fi 2,4 GHz
                                   ESP8266 (192.168.137.200)
                                   LED bicolore rouge / vert
```

Une seule application Python, lancée directement sous Windows, porte tout : pages web, reconnaissance faciale, règles d'échec, base de données, pilotage de la LED.

**Pourquoi hors Docker**, alors que le reste du SI est conteneurisé : Docker Desktop sous Windows ne donne pas accès à une webcam USB (il faudrait usbipd et un noyau WSL2 recompilé avec les pilotes vidéo). La consigne impose que la caméra soit branchée sur le PC Hôte ; la partie qui la lit tourne donc sur l'hôte. Le code est découpé en modules pour que la partie authentification puisse ensuite être rattachée au back-office du SI.

**Pourquoi 127.0.0.1** : l'application n'écoute que sur la machine elle-même. Elle n'est pas joignable depuis le point d'accès, donc pas depuis le PC Attaquant.

## 3. Arborescence

```
implementation consigne additionnelle 1/
├── README.md, LANCEMENT.md, CONSIGNE.md, PLAN.md, RECETTE.md, progress.md
├── requirements.txt          dépendances Python, versions figées
├── auth.db                   base SQLite (créée au premier lancement, NE PAS rendre)
├── models/                   modèles ONNX de détection et de reconnaissance
├── app/
│   ├── main.py               routes HTTP, sessions, contrôle des droits
│   ├── auth.py               machine à états du poste de connexion, règles d'échec
│   ├── face.py               détection (YuNet) et reconnaissance (SFace)
│   ├── camera.py             allumage/extinction réels de la webcam, flux vidéo
│   ├── led.py                envoi des ordres à l'ESP8266, sans bloquer
│   ├── db.py                 schéma et accès SQLite, journal
│   ├── config.py             réglages (surchargeables par variables d'environnement)
│   └── static/
│       ├── login.html        page de connexion en deux temps
│       ├── backoffice.html   page provisoire du back-office
│       ├── admin.html        gestion des habilitations
│       └── monitor.html      outil de test (état du poste + caméra), à ne pas montrer au jury
├── scripts/
│   ├── create_user.py        création d'un compte + enrôlement en ligne de commande (premier admin)
│   ├── test_camera.py        repérage de l'index de la webcam et mesure du temps d'ouverture
│   └── test_face.py          enrôlement et affichage du score en direct (calibration)
└── esp8266/                  projet PlatformIO (s'ouvre dans CLion)
    ├── platformio.ini
    ├── src/main.cpp          firmware de la LED
    └── include/
        ├── secrets.h.example modèle
        └── secrets.h         Wi-Fi + jeton LED (NE PAS versionner ni rendre)
```

## 4. Fonctionnement détaillé

### 4.1 Reconnaissance faciale (`app/face.py`)

Deux petits réseaux de neurones fournis par OpenCV, qui tournent sur le processeur :

- **YuNet** (`face_detection_yunet_2023mar.onnx`) trouve les visages dans l'image ; on garde le plus grand.
- **SFace** (`face_recognition_sface_2021dec.onnx`) transforme le visage, une fois redressé, en un vecteur de 128 nombres. Deux photos de la même personne donnent des vecteurs proches.

La proximité se mesure par similarité cosinus. On a écarté `face_recognition` (dépend de dlib, qui demande CMake et un compilateur C++ sous Windows) et LBPH (plus sensible à l'éclairage, demande `opencv-contrib`).

Règles retenues :

- **Vérification 1:1** : on ne compare le visage filmé qu'aux gabarits de l'identifiant saisi, pas à toute la base.
- **Seuil 0,363** : valeur de référence publiée par OpenCV pour SFace. Mesures du 2026-10-20 : Jérémy reconnu avec un score minimal de 0,49 (moyenne 0,88) ; un collègue présenté sur le compte de Jérémy obtient 0,18, refusé.
- **3 images au-dessus du seuil en moins de 5 s** : une image isolée ne suffit pas, ce qui limite les faux positifs.
- **Enrôlement** : 5 vecteurs pris à 0,5 s d'intervalle, seulement quand un seul visage est visible. On ne stocke jamais de photo.
- **Identifiant inconnu** : la vérification dure quand même ses 5 s ; la réponse est identique à un visage non reconnu, ce qui empêche de deviner quels comptes existent.

### 4.2 Caméra (`app/camera.py`)

La webcam est réellement ouverte et fermée (`cv2.VideoCapture` / `release`), comme le demande la consigne (« la caméra s'éteint »). Un thread lit les images en continu tant qu'elle est allumée ; la vérification et l'aperçu MJPEG de la page lisent la dernière image.

Mesures sur notre webcam : la toute première ouverture prend environ 4 s, les suivantes moins de 0,5 s. L'application fait donc une ouverture « à blanc » au démarrage. Le pilote MSMF de Windows s'est montré plus rapide que DirectShow sur cette webcam (contrairement à ce qu'indiquent les forums), d'où le choix de MSMF avec `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`.

### 4.3 Machine à états du poste (`app/auth.py`)

Un seul poste, une seule caméra : l'état est global.

| État | Entrée | Caméra | LED | Sortie |
|---|---|---|---|---|
| `idle` | démarrage, fin de phase | éteinte | éteinte | saisie d'un identifiant → `verifying` |
| `verifying` | identifiant saisi | allumée | inchangée | reconnu → `wait_password` ; sinon → `cooldown` |
| `wait_password` | visage reconnu | allumée | `green_blink` | mot de passe reçu ou délai de 30 s dépassé → `idle` |
| `cooldown` | visage non reconnu | allumée | `red_fixed` | après 30 s : caméra coupée → `idle` |
| `enrolling` | enrôlement lancé par un admin | allumée | inchangée | fin de capture → `idle` |

Pendant tout état autre que `idle`, une nouvelle saisie est refusée (« poste occupé »). Les minuteries (30 s de rouge, délai du mot de passe) portent un numéro de génération : une minuterie devenue périmée ne fait rien.

Le mot de passe n'est accepté qu'avec le **jeton « visage reconnu »** (`login_id`) : aléatoire, à usage unique, lié à l'utilisateur et valable 30 s. Appeler directement l'API du mot de passe sans être passé par la caméra est refusé.

### 4.4 Échecs et blocage (`app/db.py`, table `login_lockouts`)

- Un compteur par identifiant saisi. Un visage non reconnu et un mot de passe faux comptent chacun pour un échec (hypothèse à valider par l'équipe : le texte attache la règle au visage ; l'étendre au mot de passe empêche de tester des mots de passe sans limite une fois le visage passé).
- Au 2e échec : blocage 5 minutes à partir de l'échec, compteur remis à zéro. Une connexion réussie remet aussi le compteur à zéro.
- **Identifiants inconnus** : ils ne sont jamais stockés en clair, ni dans le compteur ni dans le journal, mais sous forme d'empreinte `inconnu-xxxxxxxxxxxx` (HMAC-SHA256). Raison : un mot de passe tapé par erreur dans le champ identifiant finissait en clair dans le journal (incident constaté le 2026-10-20, corrigé). L'empreinte utilise le secret de session, qui change à chaque démarrage : les compteurs des identifiants inconnus repartent alors à zéro.
- Risque résiduel assumé : n'importe qui peut bloquer un compte 5 minutes en échouant deux fois sur son identifiant.

### 4.5 LED et ESP8266 (`app/led.py`, `esp8266/src/main.cpp`)

L'ESP8266 (NodeMCU LoLin V3) est un petit serveur web à l'adresse fixe 192.168.137.200 sur le point d'accès. L'application lui envoie un mode, l'ESP gère seul les durées et le clignotement avec `millis()`, sans jamais bloquer.

| Requête | Effet |
|---|---|
| `POST /led?mode=off&k=<jeton>` | éteinte |
| `POST /led?mode=green_blink&k=<jeton>` | vert clignotant (2 fois par seconde) jusqu'à l'ordre suivant |
| `POST /led?mode=green_fixed&k=<jeton>` | vert fixe 30 s puis extinction |
| `POST /led?mode=red_blink10&k=<jeton>` | rouge clignotant exactement 10 fois puis extinction |
| `POST /led?mode=red_fixed&k=<jeton>` | rouge fixe 30 s puis extinction |
| `GET /health` | mode courant et force du signal Wi-Fi |

Sans le bon jeton : 403. Mode inconnu : 400. Le jeton est le même des deux côtés : l'application le lit dans `esp8266/include/secrets.h`.

Côté application, les ordres passent par une file traitée par un seul thread : ils partent dans l'ordre, avec 0,5 s de délai maximal. **Si l'ESP ne répond pas, la connexion continue** et l'incident est journalisé (`led_unreachable`) : la LED est un signal, pas un contrôle d'accès. Ce cas a été vérifié en conditions réelles (point d'accès coupé).

Câblage, sans fils de connexion : pattes extérieures de la LED directement sur D7 (vert, GPIO13) et D5 (rouge, GPIO14), patte commune (cathode, la plus longue) reliée à G par une seule résistance. Une résistance commune suffit parce que les deux couleurs ne s'allument jamais en même temps. Schéma et photos : [PLAN.md](PLAN.md) section 2 bis.

Le projet se compile et se téléverse depuis **CLion** (IDE imposé), configuration « PlatformIO » → ▶, ou en ligne de commande avec `pio run -t upload`.

### 4.6 Habilitations (`app/main.py`, `app/static/admin.html`)

Trois rôles : `admin`, `operateur`, `lecteur`. Aujourd'hui seule la distinction admin / non-admin a un effet : seul un admin accède à la gestion des habilitations. Les deux autres rôles sont prêts pour le vrai back-office du SI.

Depuis la page « Gestion des habilitations », un admin peut : créer un compte, enregistrer (« Enrôler ») ou supprimer le visage, changer le rôle, retirer ou rendre l'accès au back-office, changer le mot de passe, débloquer, supprimer un compte, tester la LED, lire le journal. Un admin ne peut ni se retirer ses propres droits ni se supprimer lui-même. Un compte dont l'accès est retiré est traité comme un identifiant inconnu à la connexion.

Il n'y a volontairement **pas d'inscription en libre-service** : une habilitation est accordée par un admin, sinon n'importe qui pourrait s'enrôler et entrer.

Le tout premier admin se crée en ligne de commande (`scripts/create_user.py`), puisqu'il faut un admin connecté pour en créer d'autres.

### 4.7 Journal (table `auth_events`)

Chaque événement est écrit en base et en une ligne JSON sur la sortie standard, pour qu'un collecteur comme Loki puisse le ramasser une fois le SI en place : `face_ok` (avec le score), `face_ko`, `login_ok`, `password_ko`, `password_timeout`, `locked_attempt`, `camera_error`, `user_created`, `user_updated`, `user_deleted`, `face_enrolled`, `face_deleted`, `user_unlocked`, et `led_unreachable` (sortie standard seulement).

## 5. Référence de l'API

| Méthode et route | Accès | Rôle |
|---|---|---|
| `GET /` | public | page de connexion |
| `GET /backoffice` | connecté | page du back-office (provisoire) |
| `GET /admin` | admin | gestion des habilitations |
| `GET /monitor` | public (local) | outil de test |
| `GET /camera/stream` | public (local) | flux MJPEG, seulement caméra allumée |
| `POST /api/identify` `{username}` | public | `face_ok` + `login_id`, `face_ko` + `retry_after`, `locked` (423), `busy` (409), `camera_error` (503) |
| `POST /api/password` `{login_id, password}` | public | `ok` + cookie de session, `pwd_ko`, `invalid` (400) |
| `POST /api/logout` | connecté | ferme la session |
| `GET /api/me` | connecté | identifiant et rôle |
| `GET /api/state` | public | état du poste, temps restant, caméra |
| `GET /api/health` | public | caméra, index, état de l'ESP, état du poste |
| `GET /api/admin/users` | admin | liste des comptes avec visage et blocage |
| `POST /api/admin/users` | admin | créer un compte |
| `PATCH /api/admin/users/{id}` | admin | rôle, accès, mot de passe |
| `DELETE /api/admin/users/{id}` | admin | supprimer un compte |
| `POST /api/admin/users/{id}/face` | admin | enrôler le visage (caméra) |
| `DELETE /api/admin/users/{id}/face` | admin | supprimer le visage |
| `POST /api/admin/users/{id}/unlock` | admin | débloquer |
| `POST /api/admin/led/test` | admin | séquence de test de la LED |
| `GET /api/admin/events` | admin | 50 derniers événements |

« Public (local) » : sans session, mais l'application n'écoute que sur 127.0.0.1.

## 6. Données (`app/db.py`)

| Table | Contenu |
|---|---|
| `users` | identifiant, empreinte bcrypt du mot de passe, rôle, accès au back-office, date de création |
| `face_templates` | 5 vecteurs SFace par utilisateur (128 nombres flottants), date, auteur de l'enrôlement ; supprimés avec l'utilisateur |
| `login_lockouts` | compteur d'échecs et fin de blocage, par identifiant (empreinte pour les inconnus) |
| `auth_events` | journal horodaté |

Les dates sont des horodatages Unix (secondes).

## 7. Sécurité

Ce qui est en place :

- mots de passe stockés en empreinte **bcrypt** salée, jamais en clair, jamais journalisés ;
- mot de passe accepté uniquement avec le jeton « visage reconnu », à usage unique et de courte durée ;
- 2 échecs → 5 minutes de blocage ;
- comparaisons de jetons en temps constant (`hmac.compare_digest`) ;
- session par cookie signé, `SameSite=Strict`, 8 heures maximum ; le secret change à chaque démarrage, ce qui déconnecte tout le monde ;
- droits d'administration vérifiés côté serveur sur chaque route `/api/admin/*` ;
- application limitée à 127.0.0.1, ESP protégé par jeton, aucun identifiant inconnu stocké en clair ;
- biométrie minimisée : seulement des vecteurs, aucune photo.

Limites connues, à dire au jury plutôt qu'à cacher :

- **Pas de détection du vivant** : une photo du visage sur un téléphone peut tromper SFace. En contexte industriel : caméra infrarouge (type Windows Hello) ou défi-réponse.
- Le trafic vers l'ESP est en HTTP clair sur le point d'accès ; un appareil connecté au réseau qui capterait le jeton pourrait piloter la LED (sans effet sur l'authentification).
- `auth.db` n'est pas chiffrée sur le disque ; en production, chiffrement du disque et secrets dans Vault.
- Politique de mot de passe minimale (8 caractères).
- Les visages des membres sont des données biométriques, sensibles au sens de l'article 9 du RGPD : consentement des personnes enrôlées, purge de `auth.db` après le workshop.
- Déblocage impossible si le seul admin est lui-même bloqué : prévoir deux admins.

## 8. Configuration (`app/config.py`)

Chaque valeur peut être surchargée par une variable d'environnement du même nom.

| Variable | Défaut | Rôle |
|---|---|---|
| `CAM_INDEX` | 1 | index de la webcam USB (0 = webcam intégrée sur ce PC) |
| `FACE_THRESHOLD` | 0,363 | seuil de similarité cosinus |
| `FACE_HITS` | 3 | images au-dessus du seuil pour reconnaître |
| `FACE_TIMEOUT_S` | 5 | durée maximale de la vérification |
| `PASSWORD_TTL_S` | 30 | délai pour saisir le mot de passe (ajout hors consigne) |
| `BACKOFFICE_DELAY_S` | 0 | attente avant l'ouverture du back-office (0 ou 30 selon la lecture retenue) |
| `LED_URL` | `http://192.168.137.200` | adresse de l'ESP |
| `LED_TOKEN` | lu dans `secrets.h` | jeton partagé avec l'ESP |
| `SESSION_SECRET` | aléatoire au démarrage | clé de signature des sessions |

Constantes fixées par la consigne : 30 s de rouge (`COOLDOWN_S`), 5 min de blocage (`LOCK_S`), 2 échecs (`MAX_FAILURES`).

## 9. Installation depuis zéro

Prérequis : Windows, Python 3.12 (`py -3.12`), la webcam et la carte branchées.

```powershell
cd "<dossier du projet>"
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Modèles, à placer dans `models/` (dépôt GitHub `opencv/opencv_zoo`) :

| Fichier | Taille | SHA-256 |
|---|---|---|
| `face_detection_yunet_2023mar.onnx` | 232 589 octets | `8F2383E4DD3CFBB4553EA8718107FC0423210DC964F9F4280604804ED2552FA4` |
| `face_recognition_sface_2021dec.onnx` | 38 696 353 octets | `0BA9FBFA01B5270C96627C4EF784DA859931E02F04419C829E83484087C34E79` |

ESP8266 :

1. Pilote USB de la puce CH340 (`CH341SER`, éditeur WCH) si Windows ne le trouve pas seul.
2. PlatformIO Core (installé ici dans `%USERPROFILE%\.platformio\penv`) et CLion.
3. Copier `esp8266/include/secrets.h.example` en `secrets.h` et renseigner le Wi-Fi et un jeton aléatoire.
4. Si besoin, adapter `upload_port` dans `platformio.ini` (COM3 sur le PC Hôte).
5. Téléverser depuis CLion (▶) ou avec `pio run -t upload`.

Premier admin :

```powershell
.venv\Scripts\python scripts\create_user.py <identifiant> --role admin
```

Le mot de passe est demandé au clavier ; l'enrôlement du visage suit (rester seul face à la webcam).

Lancement : voir [LANCEMENT.md](LANCEMENT.md).

## 10. Tests

- `scripts/test_camera.py <dossier>` : sonde les index 0 à 3, enregistre une image par caméra et mesure le temps d'ouverture (en DirectShow, outil de diagnostic) ; `--show <index>` pour un aperçu.
- `scripts/test_face.py <fichier.npy> [index] [étiquette]` : enrôle un visage et affiche le score en direct ; bilan par étiquette en quittant (« moi » / « autre »), utile pour régler le seuil.
- Page `/monitor` : état du poste et image de la caméra en temps réel.
- [RECETTE.md](RECETTE.md) : les 6 cas de la consigne et 7 cas de sécurité, avec les résultats obtenus le 2026-10-20.

## 11. Écarts et décisions par rapport à la consigne

Détail dans [PLAN.md](PLAN.md) sections 6 et 9. En résumé :

- délai de 30 s pour le mot de passe : ajouté (sinon la LED clignoterait en vert sans fin si la personne s'en va), alors que le texte dit « jusqu'à la saisie du mot de passe » ; à confirmer en équipe ;
- échec du mot de passe compté dans la règle « 1 réessai puis 5 minutes » : hypothèse ;
- back-office accessible dès le mot de passe validé, la LED restant verte 30 s : hypothèse, réglable ;
- application hors Docker à cause de la caméra ; intégration au back-office du SI à décider quand il existera.

## 12. À ne jamais versionner ni rendre

`.venv/`, `esp8266/.pio/`, `esp8266/include/secrets.h`, `auth.db` (empreintes de mots de passe et données biométriques).

## Sources

- [OpenCV : DNN-based Face Detection and Recognition](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)
- [JetBrains : PlatformIO dans CLion](https://www.jetbrains.com/help/clion/platformio.html)
- [Forum OpenCV : lenteur d'ouverture MSMF](https://forum.opencv.org/t/the-msmf-backend-is-slow-to-acquire-the-initial-frame/24121)
- [Forum Docker : USB sur Docker Desktop WSL2](https://forums.docker.com/t/usb-ip-on-docker-desktop-wsl2-backend/135921)
