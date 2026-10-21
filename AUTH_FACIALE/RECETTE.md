# Recette — consigne additionnelle 1

À rejouer à l'étape 4 (avec `curl`), puis aux étapes 5 et 7 (avec l'interface). Cocher et noter la date.

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
