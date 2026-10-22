# Recette — consigne additionnelle 1

À rejouer à l'étape 4 (avec `curl`), puis aux étapes 5 et 7 (avec l'interface). Cocher et noter la date. Premier compte : page `/setup` (cas E1 à E6), `scripts/create_user.py` en secours.

## Cas de la consigne

| # | Scénario | Attendu | API (étape 4) | Interface (étapes 5-7) |
|---|---|---|---|---|
| 1 | Au repos | LED éteinte | [x] 2026-10-20 | [ ] |
| 2 | Identifiant saisi, personne reconnue | Caméra allumée, LED verte clignotante jusqu'au mot de passe, champ mot de passe affiché | [x] 2026-10-20 (reconnu en 1,6 s, score 0,948) | [ ] |
| 3 | Puis mot de passe correct | LED verte fixe 30 s puis éteinte, caméra coupée, back-office accessible | [x] 2026-10-20 (session ouverte, `/api/me` 200) | [ ] |
| 4 | Reconnu, mais mot de passe faux | LED rouge clignotante 10 fois puis éteinte, identifiant vidé, caméra coupée, retour au début | [x] 2026-10-20 | [ ] |
| 5 | Identifiant saisi, personne non reconnue | LED rouge fixe 30 s, saisie impossible pendant 30 s, puis caméra coupée et ressaisie possible | [x] 2026-10-20 (caméra allumée pendant les 30 s, 409 pendant le rouge) | [ ] |
| 6 | Deux échecs de suite sur le même identifiant | Identifiant bloqué 5 minutes, compte à rebours affiché, puis déblocage automatique | [x] 2026-10-20 (423, `retry_after` 260 s) ; déblocage automatique non attendu jusqu'au bout | [ ] |

## Cas de sécurité

| # | Scénario | Attendu | Résultat |
|---|---|---|---|
| S1 | `POST /api/password` sans `login_id` ou avec un `login_id` inventé | Refusé | [x] 400 |
| S2 | Réutiliser un `login_id` déjà consommé | Refusé | [x] 400 |
| S3 | `login_id` de l'utilisateur A avec le mot de passe de B | Refusé | [ ] par construction (le jeton porte l'utilisateur), pas testé avec deux comptes |
| S4 | Identifiant inexistant | Même comportement qu'un visage non reconnu (cas 5) | [x] même réponse et même durée (6,0 s contre 6,1 s) |
| S5 | Routes `/api/admin/*` avec un compte non admin, puis sans session | Refusé (403 / 401) | [x] 403 / 401 |
| S6 | ESP débranché pendant un login | Le login fonctionne quand même, un avertissement est journalisé | [x] 2026-10-20, involontairement : point d'accès coupé, logins OK, `led_unreachable` journalisé ; ESP reconnecté seul en ~3 s après réactivation |
| S7 | Mot de passe non saisi pendant 30 s | LED éteinte, caméra coupée, aucun échec compté | [x] validé avec 120 s, puis revérifié à 15 s dans la page (2026-10-20) |

## Installation et enrôlement guidé

Tests unitaires : `tests/` (45 tests, caméra, détection et base simulées). Ils prouvent la logique, pas le comportement devant la webcam ni la création en PostgreSQL : colonne « Caméra » à remplir par l'équipe.

| # | Scénario | Attendu | Tests unitaires | Caméra et base réelles |
|---|---|---|---|---|
| E1 | Aucun compte, ouvrir http://127.0.0.1:8000 | Redirection vers `/setup` | [x] 2026-10-21 | [ ] |
| E2 | `/setup` ouvert depuis une autre machine (ou `POST /api/setup/start` d'un client hors boucle locale) | 403, rien n'est créé | [x] 2026-10-21 (192.168.137.12, 10.0.0.5 refusés ; 127.0.0.2 et ::1 acceptés) | [ ] |
| E3 | Mot de passe < 8 caractères, confirmation différente, identifiant vide | 400, message clair, enrôlement non lancé | [x] 2026-10-21 | [ ] |
| E4 | Installation complète | Aperçu caméra affiché avant la 1re capture, 5 angles dans l'ordre, compte `admin` créé avec 5 gabarits, `setup_admin_created` au journal | [x] 2026-10-21 | [ ] |
| E5 | Après le 1er compte : `/setup`, puis `POST /api/setup/start` | Redirection vers `/`, puis 404 ; `/` affiche la connexion | [x] 2026-10-21 | [ ] |
| E6 | Compte créé par ailleurs pendant l'enrôlement de `/setup` | Échec « installation fermée », aucun second admin | [x] 2026-10-21 (logique ; verrou PostgreSQL non testé) | [ ] |
| E7 | Angle non tenu pendant 20 s | Échec nommant l'angle, rien d'enregistré, « Recommencer » relance tout | [x] 2026-10-21 | [ ] |
| E8 | Deux visages devant la caméra | Aucune capture, témoin « un seul visage » en rouge | [x] 2026-10-21 | [ ] |
| E9 | « Annuler » pendant l'enrôlement | Caméra coupée, poste libéré, rien d'enregistré | [x] 2026-10-21 | [ ] |
| E10 | Saisie d'un identifiant sur `/` pendant un enrôlement | 409 « poste occupé » | [x] 2026-10-21 | [ ] |
| E11 | « Enrôler » depuis `admin.html` | Même parcours, 5 gabarits remplacent les anciens, `face_enrolled` au journal | [x] 2026-10-21 | [ ] |
| E12 | « Tête tournée à gauche » : la personne tourne vers SA gauche | Angle atteint ; si c'est l'inverse, `ENROLL_YAW_SIGN=-1` | n/a | [ ] |
| E13 | Après enrôlement 5 angles, connexion de face puis tête légèrement tournée | Reconnu (cas 2), score noté | n/a | [ ] |
| E14 | `/api/enroll/state` depuis un autre navigateur | 404 | [x] 2026-10-21 | [ ] |

## Calibration du seuil (étape 7)

Score cosinus SFace de chaque personne filmée contre les gabarits de chaque compte. Le seuil se place entre le plus haut score d'imposteur (hors diagonale) et le plus bas score légitime (diagonale).

| Filmé \ Gabarit | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|
| P1 | | | | | |
| P2 | | | | | |
| P3 | | | | | |
| P4 | | | | | |
| P5 | | | | | |

Seuil retenu : ____ (départ : 0,363). Conditions d'éclairage : ____.

## Critères finaux

- [ ] 20 connexions réussies sur 20 pour la personne de la démo, dans les conditions de la démo.
- [ ] 0 acceptation sur 10 essais d'une personne non enrôlée.
- [ ] Temps entre la saisie de l'identifiant et l'affichage du champ mot de passe : ____ s (objectif < 5 s).
