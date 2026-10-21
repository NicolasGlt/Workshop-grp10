# Plan d'implémentation — consigne additionnelle 1 (identification par visage + LED)

Document de travail. Texte de la consigne : [CONSIGNE.md](CONSIGNE.md). Cas à valider : [RECETTE.md](RECETTE.md). Vue d'ensemble : [README.md](README.md).

Légende des sources : **[V]** vérifié en ligne le 2026-10-20 (liens en fin de document), **[T]** connaissance non vérifiée, à confirmer par le test de l'étape concernée.

---

## 1. Principe

Le SI de paiement n'existe pas encore. On construit donc l'identification comme **une seule application Python, lancée directement sous Windows (hors Docker)** : page de login, page d'administration des habilitations, reconnaissance faciale, règles d'échec et de blocage, pilotage de la LED, base SQLite.

- Hors Docker, parce que Docker Desktop ne donne pas accès à une webcam USB : il faudrait usbipd et un noyau WSL2 recompilé avec les pilotes vidéo [V]. La consigne place le back-office dans la solution conteneurisée : la phrase à tenir devant le jury est « la capture vidéo et le modèle tournent sur l'hôte parce que la caméra y est physiquement branchée et que Docker Desktop ne la voit pas ; le reste rejoindra les conteneurs ».
- Une seule application, parce qu'il n'y a encore aucun service d'authentification où se brancher. Le code est découpé en modules (`camera`, `face`, `led`, `auth`) pour pouvoir, plus tard, soit faire rediriger le vrai back-office vers ce login, soit recopier le module `auth` dans le service d'auth de l'équipe. Le choix entre les deux dépendra du langage retenu par l'équipe (non tranché à ce jour).
- Pas de React pour ces pages : du HTML et du JavaScript simples servis par l'application, rien à compiler.

## 2. Choix techniques

| Sujet | Choix | Raison |
|---|---|---|
| Détection du visage | YuNet (`face_detection_yunet_2023mar.onnx`) via `cv2.FaceDetectorYN` | Inclus dans `opencv-python` (OpenCV ≥ 4.5.4), aucune compilation [V] |
| Reconnaissance | SFace (`face_recognition_sface_2021dec.onnx`) via `cv2.FaceRecognizerSF`, similarité cosinus | Petit réseau, tourne sur le processeur, seuil de référence publié : 0,363 sur LFW, plus haut = plus strict [V] |
| Écarté : `face_recognition` | — | Dépend de dlib, qui demande CMake et Visual C++ sous Windows [V] |
| Écarté : LBPH | — | Demande `opencv-contrib`, plus sensible à l'éclairage, score moins lisible |
| Mode de vérification | 1:1 : on compare uniquement aux gabarits de l'identifiant saisi | Plus fiable avec 5 personnes, et c'est ce que dit la consigne (« confirmer l'identité ») |
| Règle de décision | 3 images au-dessus du seuil dans une fenêtre de 5 s | Une image isolée peut donner un faux positif |
| Enrôlement | 5 gabarits par personne, légère rotation de la tête ; on ne stocke que les vecteurs (128 nombres), pas les photos | Robustesse + données biométriques minimisées |
| Caméra | `cv2.VideoCapture(index, cv2.CAP_MSMF)` avec `OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS=0`, ouverture « à blanc » au démarrage de l'application, un thread qui garde la dernière image | Les forums donnent DirectShow plus rapide [V], mais la mesure sur notre webcam (étape 1) donne MSMF plus rapide (0,4 s contre 0,5 s jusqu'à la 1re image, 30 contre 20 img/s) ; la 1re ouverture à froid prend ~4 s, d'où l'ouverture à blanc ; le thread sert à la fois l'aperçu vidéo et la vérification |
| Serveur | FastAPI + uvicorn, sessions par cookie signé (`itsdangerous`), mots de passe en `bcrypt` | Paquets précompilés pour Windows [T] |
| Base | SQLite (fichier local) | Rien à installer ; migrable vers la base de l'équipe |
| ESP8266 | Serveur HTTP sur l'ESP, IP fixe ; l'application lui envoie un mode, l'ESP gère seul durées et clignotements avec `millis()` | L'ESP exécute exactement « 10 clignotements » et « 30 s » ; l'appel ne bloque jamais le login (délai max 500 ms) |

## 2 bis. Matériel et câblage

### Inventaire (photos du 2026-10-20)

| Élément | Identification | Remarque |
|---|---|---|
| PC Hôte | Portable Windows 11, Python 3.11 (`python`) et 3.12 (`py`) | Possède déjà deux caméras intégrées, « FHD Camera » et « FHD IR Camera » (VID 5986) : ce ne sont pas elles qu'il faut utiliser |
| Webcam USB | Webcam 1080p générique (étiquette « Webcam-new », réf. B0BG1YJWFN), câble intégré | Classe vidéo USB standard, sans pilote [T] |
| Carte ESP8266 | NodeMCU LoLin V3 d'AZ-Delivery, module ESP8266MOD 12-F, port micro-USB | PlatformIO : `board = nodemcuv2` [T] ; puce USB probablement CH340, pilote installé par Windows Update ou à la main [T] |
| Câble | USB-A vers micro-USB, tressé | Doit transporter les données, pas seulement la charge : on le saura au branchement |
| Plaque d'essai | Deux mini plaques rouges dans un support, la carte posée à cheval | Chaque colonne de 5 trous entre le bord et la rainure est reliée ; les trous libres dans la colonne d'une broche sont reliés à cette broche |
| LED bicolore | LED 5 mm transparente, rouge/vert | Nombre de pattes à confirmer ; avec deux résistances fournies, probablement 3 pattes (une commune) |
| Résistances | 2, corps bleu | Valeur non lue (bagues de couleur) ; toute valeur entre 100 Ω et 1 kΩ convient en 3,3 V [T] |
| Fils de connexion | Aucun | Montage en pliant les pattes de la LED et des résistances ; 3 fils mâle-mâle simplifieraient le montage |

### Broches retenues

Rangée des broches D (USB à gauche) : `3V G TX RX D8 D7 D6 D5 G 3V D4 D3 D2 D1 D0`. La carte est enfoncée dans la plaque : sous chaque broche D restent 3 trous libres reliés à elle (zone A), puis la rainure, puis 5 rangées libres non reliées (zone B).

Montage retenu le 2026-10-20 (sans fils, LED 3 pattes, patte commune = la plus longue, au milieu) : les pattes extérieures de la LED vont directement sur `D7` (GPIO13) et `D5` (GPIO14) ; la patte commune passe la rainure vers la zone B, et **une seule résistance** la relie à `G`. Une résistance commune suffit parce que les deux couleurs ne s'allument jamais en même temps [T]. D7 et D5 ne gênent pas le démarrage de la carte, contrairement à D3, D4 et D8 [T].

```
D7 ───────────────── patte extérieure 1 ┐
D5 ───────────────── patte extérieure 2 ├─ LED
G  ──[résistance]─── patte commune      ┘
```

Si rien ne s'allume, la LED est à anode commune : l'extrémité de la résistance passe de `G` au `3V` voisin et on inverse la logique dans le firmware. Quelle patte extérieure est rouge : déterminé au premier test.

## 3. Arborescence

```
implementation consigne additionnelle 1/
├── README.md, LANCEMENT.md, CONSIGNE.md, PLAN.md, RECETTE.md
├── requirements.txt
├── .env.example          # seuil, index caméra, IP ESP, jeton LED (le vrai .env n'est pas versionné)
├── app/
│   ├── main.py           # FastAPI : routes, sessions
│   ├── camera.py         # thread de capture, allumage/extinction, flux MJPEG
│   ├── face.py           # YuNet + SFace : enrôlement, vérification
│   ├── auth.py           # machine à états, compteur d'échecs, blocage
│   ├── led.py            # appels à l'ESP, en tâche de fond
│   ├── db.py             # schéma SQLite et accès
│   └── static/           # login.html, admin.html, backoffice.html
├── models/               # les 2 fichiers .onnx
├── scripts/              # test_camera.py, test_face.py, create_admin.py
└── esp8266/              # projet PlatformIO, ouvert dans CLion
```

Point incertain [T] : le chemin du projet contient des espaces et un « ! » (`!projets`). Python n'y voit pas de problème, mais certaines chaînes de compilation PlatformIO supportent mal les espaces. Si la compilation échoue à l'étape 3, on déplace le seul dossier `esp8266/` vers un chemin simple.

## 4. Machine à états (ce que devient chaque phrase de la consigne)

| Consigne | Implémentation |
|---|---|
| LED éteinte par défaut | Mode `off` au démarrage de l'ESP et de l'application |
| Identifiant saisi → caméra activée | `POST /api/identify` allume la caméra ; la page affiche le flux vidéo |
| Reconnu → mot de passe autorisé, vert clignotant | Jeton de connexion à usage unique (valable 30 s), LED `green_blink`, le champ mot de passe s'affiche |
| Mot de passe validé → vert fixe 30 s puis extinction, back-office disponible | LED `green_fixed` (l'ESP s'éteint seul après 30 s), caméra coupée, session ouverte, accès au back-office |
| Mot de passe faux → rouge clignotant ×10, tout recommence | LED `red_blink10`, caméra coupée, identifiant vidé, +1 échec |
| Non reconnu → rouge fixe 30 s, caméra éteinte, ressaisie | LED `red_fixed`, saisie bloquée 30 s (compte à rebours), puis caméra coupée, +1 échec |
| 1 réessai puis blocage 5 min | Au 2e échec : identifiant bloqué 5 min, compte à rebours affiché |

Contrôle de sécurité clé : le serveur refuse tout mot de passe envoyé sans jeton « visage OK » valide, lié à l'identifiant et à usage unique. Sinon l'étape faciale se contourne par un simple appel à l'API.

Un identifiant inconnu suit le même chemin qu'un visage non reconnu (caméra, échec, rouge) : on ne révèle pas quels comptes existent.

Ajout hors consigne : si le mot de passe n'est pas saisi dans les 30 s, la LED s'éteint et la caméra se coupe, sans compter d'échec.

## 5. API et données

### Routes de l'application

| Route | Rôle |
|---|---|
| `GET /` | Page de login |
| `GET /camera/stream` | Aperçu vidéo MJPEG (seulement quand la caméra est allumée) |
| `POST /api/identify` `{username}` | Refuse si bloqué (423) ou en pause de 30 s (429) ; sinon vérification faciale → `{status: "face_ok", login_id}` ou `{status: "face_ko", retry_after, attempts_left}` ou `{status: "locked", until}` |
| `POST /api/password` `{login_id, password}` | `{status: "ok"}` + cookie de session, ou `{status: "pwd_ko"}` / `{status: "locked", until}` |
| `POST /api/logout` | Ferme la session |
| `GET /backoffice` | Page provisoire du back-office (session requise) |
| `GET /admin` | Page des habilitations (rôle admin) |
| `GET /api/admin/users` | Liste : rôle, accès back-office, visage enrôlé, état de blocage |
| `POST /api/admin/users` | Créer un utilisateur |
| `PATCH /api/admin/users/{id}` | Changer rôle, accès back-office, mot de passe |
| `POST /api/admin/users/{id}/face` | Enrôler le visage (capture caméra) |
| `DELETE /api/admin/users/{id}/face` | Supprimer les gabarits |
| `POST /api/admin/users/{id}/unlock` | Débloquer |
| `POST /api/admin/led/test` | Faire défiler les modes de la LED |
| `GET /api/admin/events` | 50 derniers événements d'authentification |
| `GET /api/health` | Caméra, modèles, ESP joignable |

Toutes les routes `/api/admin/*` vérifient le rôle admin côté serveur.

### Schéma SQLite

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'lecteur' CHECK (role IN ('admin','operateur','lecteur')),
  backoffice_enabled INTEGER NOT NULL DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE face_templates (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  embedding BLOB NOT NULL,              -- 128 float32
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  created_by INTEGER REFERENCES users(id));

CREATE TABLE login_lockouts (           -- indexé sur l'identifiant SAISI, marche aussi pour les inconnus
  username TEXT PRIMARY KEY,
  failures INTEGER NOT NULL DEFAULT 0,
  cooldown_until TEXT,                  -- les 30 s de rouge
  locked_until TEXT);                   -- les 5 minutes

CREATE TABLE auth_events (
  id INTEGER PRIMARY KEY,
  ts TEXT DEFAULT CURRENT_TIMESTAMP,
  username TEXT, event TEXT, score REAL, detail TEXT);
```

Le premier admin est créé et enrôlé par `scripts/create_user.py <identifiant> --role admin` : sans lui, personne ne pourrait se connecter pour enrôler les autres.

Les événements sont aussi écrits en JSON sur la sortie standard, pour que Loki puisse les ramasser une fois le SI en place (lien avec le SIEM).

## 6. Hypothèses (à faire valider par l'équipe)

1. **Un seul compteur d'échecs par identifiant** : un visage non reconnu et un mot de passe faux comptent tous les deux ; au 2e échec, blocage de 5 min, qui démarre au moment de l'échec. Un login réussi remet le compteur à zéro. Raison : le texte attache la règle à l'échec facial ; l'étendre au mot de passe empêche de tester des mots de passe sans limite une fois le visage passé.
2. **Accès immédiat au back-office** dès le mot de passe validé, pendant que la LED reste verte 30 s. Réglage `BACKOFFICE_DELAY_S` (0 ou 30) pour basculer.
3. **Caméra allumée** de la saisie de l'identifiant jusqu'à la fin de la phase (mot de passe saisi, ou fin des 30 s de rouge). Pour le cas « non reconnu », ce n'est plus une hypothèse : le texte exact dit que la LED reste rouge 30 s « avant que la caméra ne s'éteigne » (voir [CONSIGNE.md](CONSIGNE.md)).
4. **LED éteinte pendant le blocage de 5 min** (la consigne ne dit rien).
5. **« bloqué 5 minutes, etc. »** : après le blocage, le cycle recommence normalement (2 nouvelles tentatives).

Risque résiduel à annoncer : n'importe qui peut bloquer un compte en tapant son identifiant deux fois (déni de service ciblé), acceptable dans l'exercice.

## 7. Étapes

Chaque étape se termine par un test ; on ne passe à la suivante que si le test est vert. Le matériel se branche au fil des étapes, pas avant.

| # | Étape | À brancher | C'est bon quand… |
|---|---|---|---|
| 0 | Prérequis : environnement virtuel Python 3.12, paquets, modèles ONNX | Rien | `cv2.__version__` ≥ 4.5.4, les deux `.onnx` sont dans `models/` |
| 1 | Caméra USB : `scripts/test_camera.py` essaie les index 0 à 3 en DirectShow, affiche l'image, mesure le temps d'ouverture | La webcam USB | Index de la caméra USB identifié (pas la webcam intégrée), ouverture < 2 s |
| 2 | Reconnaissance seule : `scripts/test_face.py` enrôle un visage puis affiche le score en direct | Rien de plus | Écart net entre la bonne personne et une autre ; premier seuil noté |
| 3a | ESP8266 seul : point d'accès en 2,4 GHz, PlatformIO dans CLion, pilote USB, premier téléversement | La carte en USB, broches vides | La carte apparaît comme port COM, se connecte au point d'accès et répond à `curl` |
| 3b | LED : montage sur la plaque, firmware des 5 modes | Carte débranchée pendant le montage, puis rebranchée | Les 5 modes se comportent exactement comme la consigne (10 clignotements comptés, 30 s chronométrées) |
| 4 | Moteur d'authentification : `db`, `camera`, `face`, `led`, `auth`, routes API, `create_admin.py` | Webcam + carte | Les 6 cas de [RECETTE.md](RECETTE.md) passent avec `curl`, sans interface |
| 5 | Page de login | Webcam + carte | Enchaînement identifiant → caméra → mot de passe, comptes à rebours 30 s et 5 min |
| 6 | Page des habilitations | Webcam + carte | Créer, enrôler, retirer l'accès (→ refusé) ; refusé à un non-admin |
| 6b | CLion (exigé) | Carte | Projet `esp8266/` ouvert, compilé et téléversé depuis CLion |
| 7 | Recette allégée : enrôlement des personnes de la démo dans les conditions du jury, rejouer les cas | Webcam + carte | ~10 essais réussis pour la personne de la démo, refus d'une personne non enrôlée |

## 8. Pièges de la démonstration

1. **Blocage en cascade.** Le dashboard et la chaîne de remédiation ne doivent pas dépendre d'une connexion faciale réussie pendant le chronomètre. Ouvrir la session avant le chrono, garder un 2e onglet connecté en secours, avoir le bouton « Débloquer » sous la main. Si le jury veut tester l'échec : pendant les questions, avec un autre identifiant (le blocage est lié à l'identifiant).
2. **Éclairage.** Enrôler dans des conditions proches de la salle du jury ; visage éclairé de face, pas de fenêtre derrière ; caméra fixée à hauteur de visage, place marquée sur la table.
3. **Caméra.** Index fixé dans `.env` et vérifié par `/api/health` (la webcam intégrée prend souvent l'index 0) ; autoriser l'accès des applications de bureau à la caméra dans les paramètres Windows [T]. Pour la finale sur Teams depuis le PC Hôte : régler Teams sur la webcam intégrée, une webcam étant en général réservée à une application à la fois [T, incertain].
4. **Wi-Fi de l'ESP.** L'ESP8266 ne marche qu'en 2,4 GHz : forcer cette bande dans le point d'accès Windows [V] ; désactiver l'extinction automatique du point d'accès [T] ; alimenter l'ESP sur un port USB du PC Hôte ; tester la LED juste avant le passage. Point incertain [T] : la consigne veut le PC Hôte connecté au Wi-Fi du campus en même temps qu'il diffuse le point d'accès ; avec une seule carte Wi-Fi, Windows peut imposer au point d'accès la bande de la connexion campus. Si le campus est en 5 GHz, l'ESP risque de ne pas voir le réseau : à tester à l'étape 3a, avec un plan B (forcer la connexion campus en 2,4 GHz, ou brancher le campus en Ethernet si possible).
5. **Questions attendues.** Une photo sur un téléphone trompera SFace (pas de détection du vivant) : limite assumée ; en industriel, caméra infrarouge type Windows Hello ou défi-réponse. Les visages des membres sont des données biométriques, sensibles au sens de l'article 9 du RGPD [T] : on ne stocke que des vecteurs, avec le consentement des 5 et une purge après le workshop.

## 9. Périmètre recentré sur la consigne (2026-10-20)

Revue phrase par phrase de [CONSIGNE.md](CONSIGNE.md) après les étapes 0 à 6.

**Exigé et fait :** identifiant → caméra → mot de passe ; échec = identifiant vidé + caméra éteinte, 1 réessai puis 5 min ; caméra et IA sur le PC Hôte ; gestion de la reconnaissance et des habilitations dans le back-office (créer, enrôler, supprimer un visage, retirer l'accès) ; ESP8266 en Wi-Fi avec les 5 comportements de LED.

**Exigé et pas encore fait :**
- **CLion + PlatformIO** (« IDE obligatoire ») : installer CLion, ouvrir `esp8266/`, compiler et téléverser depuis CLion.
- **Intégration au back-office du SI conteneurisé** : le SI n'existe pas encore ; décider en équipe comment son back-office s'appuie sur cette application (qui reste hors Docker à cause de la caméra).

**Non demandé, décisions :**
- Pas de script de déblocage en ligne de commande : le bouton « Débloquer » du back-office suffit ; contre le blocage de l'unique admin, créer un 2e compte admin (aucun code).
- **Pas d'inscription en libre-service** (« créer mon compte ») : une habilitation est accordée par un admin ; un enrôlement libre ouvrirait le back-office à n'importe qui et annulerait le dispositif demandé.
- Rôles opérateur / lecteur : gardés (coût nul, appui de « gestion complète »), mais seule la distinction admin / non-admin a un effet aujourd'hui.
- Délai de 30 s pour le mot de passe : écart au texte (« vert clignotant jusqu'à la saisie du mot de passe ») ; à garder et justifier, ou à supprimer, décision d'équipe.
- Journal et empreinte des identifiants inconnus : gardés (pilier SIEM, correction d'une fuite constatée).
- Page `/monitor` : outil de test, à ne pas montrer au jury.
- Étape 7 allégée : enrôler les personnes de la démo + une dizaine d'essais dans les conditions du jury (la matrice 5 × 5 et le 20/20 étaient un objectif personnel, pas la consigne).

## 10. Scénario de démo « avant / après habilitation » (≈ 1 min 30, plutôt pendant les questions)

1. Le jury tente de se connecter avec `jury` : refusé, LED rouge fixe 30 s.
2. L'admin crée `jury` dans la page des habilitations, clique « Enrôler », le jury regarde la caméra 3 s.
3. Le jury se reconnecte : visage reconnu, LED verte clignotante, mot de passe, vert fixe, back-office ouvert.
4. L'admin montre le journal : refus, création, enrôlement, connexion.

Vigilance : l'étape 1 compte un échec sur `jury` ; un 2e échec à l'étape 3 le bloquerait 5 min → bouton « Débloquer ».

## Sources

- [OpenCV : DNN-based Face Detection and Recognition (4.x)](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html)
- [WSL2 USB CAMERA (noyau UVC personnalisé)](https://github.com/Xuanhoang214/WSL2-USB-CAMERA)
- [Forum Docker : USB/IP sur Docker Desktop WSL2](https://forums.docker.com/t/usb-ip-on-docker-desktop-wsl2-backend/135921)
- [face_recognition : échecs d'installation de dlib sous Windows](https://lightrun.com/answers/ageitgey-face_recognition-unable-to-install-face_recognition)
- [Forum OpenCV : MSMF lent à obtenir la première image](https://forum.opencv.org/t/the-msmf-backend-is-slow-to-acquire-the-initial-frame/24121)
- [Microsoft Q&A : bande du point d'accès mobile](https://learn.microsoft.com/en-us/answers/a/4785449)
