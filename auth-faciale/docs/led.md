# Comportement de la LED — référence

Ce document fait foi sur **ce que la LED doit afficher à chaque étape du parcours** et vérifie que le
code l'applique. Il consolide ce qui était jusqu'ici réparti entre [consigne.md](consigne.md)
(texte du sujet), [plan.md](plan.md) (section 4) et le [README](../README.md) (sections 6.3 et 6.5).

Principe posé par le sujet et tenu par le code : **la LED est un témoin, pas un contrôle d'accès.**
Si l'ESP ne répond pas, la connexion se poursuit et l'incident est journalisé (`led_unreachable`,
voir [app/led.py](../app/led.py)).

## 1. Les 5 modes du firmware

Le sujet définit cinq comportements de LED ; le firmware
[esp8266/src/main.cpp](../esp8266/src/main.cpp) expose exactement cinq modes. L'application envoie un
nom de mode (`POST /led?mode=<mode>&k=<jeton>`), l'ESP gère seul durées et clignotements avec
`millis()` (il ne bloque jamais l'application).

| Mode | Couleur / rythme | Durée | Qui met fin |
|---|---|---|---|
| `off` | éteinte | — | — |
| `green_blink` | vert, clignote 2 fois/s | indéfinie | le mode suivant (ne s'éteint pas seul) |
| `green_fixed` | vert fixe | 30 s | le firmware (auto-extinction) |
| `red_blink10` | rouge, 10 allumages | ~5 s | le firmware (auto-extinction) |
| `red_fixed` | rouge fixe | 30 s | le firmware (auto-extinction) |

Durées côté firmware : `BLINK_MS = 250`, `FIXED_MS = 30000`. Câblage : vert sur D7 (GPIO13), rouge
sur D5 (GPIO14), LED bicolore à cathode commune, une seule résistance (les deux couleurs ne sont
jamais allumées en même temps).

## 2. Comportement attendu par étape du parcours

Chaque ligne cite la phrase du sujet qui l'impose, le mode envoyé, et l'endroit du code qui l'envoie.
Le parcours suit la machine à états de [app/auth.py](../app/auth.py).

| Étape du parcours | État interne | Ce que dit le sujet | Mode envoyé | Code |
|---|---|---|---|---|
| **Repos** | `idle` | « Par défaut la LED devra être éteinte » | `off` | [main.py](../app/main.py) au démarrage (`lifespan`) |
| **Demande de visage** (scan caméra) | `verifying` | *(le sujet n'allume le vert qu'une fois reconnu — voir §3)* | *(aucun : reste `off`)* | — |
| **Visage reconnu** | `wait_password` | « reconnue […] la LED passe au vert clignotant jusqu'à ce que le mot de passe soit saisi » | `green_blink` | [auth.py](../app/auth.py) `identify`, cas `ok` |
| **Accès accordé** (mot de passe correct) | → `idle` | « mot de passe validé → vert fixe pendant 30 secondes puis s'éteint et la page du Back est disponible » | `green_fixed` | [auth.py](../app/auth.py) `password`, cas succès |
| **Échec visage** (non reconnu) | `cooldown` | « non reconnue → rouge fixe pendant 30 secondes avant que la caméra ne s'éteigne » | `red_fixed` | [auth.py](../app/auth.py) `identify`, cas `ko` |
| **Échec mot de passe** | → `idle` | « mot de passe pas bon → clignote en rouge 10 fois puis s'éteint et on recommence » | `red_blink10` | [auth.py](../app/auth.py) `password`, cas échec |

**Revue de code (2026-10-22) : les six transitions prescrites par le sujet sont correctement
câblées.** Chaque mode envoyé correspond à l'état, et le démarrage force bien `off`. Aucun écart
« mauvais mode envoyé » constaté.

## 3. Ce que le sujet ne prescrit pas

Trois situations du parcours n'ont pas de comportement de LED dans le texte du sujet. Le code y laisse
la LED **éteinte**. Ces points sont des décisions, pas des exigences : à confirmer en équipe.

| Situation | État | Comportement actuel | Fondement |
|---|---|---|---|
| Pendant le scan du visage | `verifying` | LED éteinte | Le sujet n'allume le vert qu'« une fois reconnue ». Avant reconnaissance, rien n'est prescrit : on reste à l'état par défaut (éteint). |
| Tentative sur un identifiant bloqué 5 min | `locked` (HTTP 423) | LED éteinte (aucun `led.send`) | Le sujet ne dit rien de l'état de la LED pendant le blocage. Hypothèse 4 de [plan.md](plan.md) : « LED éteinte pendant le blocage ». |
| Délai de 30 s pour saisir le mot de passe écoulé | `wait_password` → `idle` | `off` | **Ajout hors sujet** de l'équipe (`PASSWORD_TTL_S`). Le sujet dit « vert clignotant jusqu'à ce que le mot de passe soit saisi », sans borne de temps. Le délai évite que la LED clignote indéfiniment. |

Si l'équipe décide plus tard de signaler physiquement un refus sur identifiant bloqué, le mode
disponible le plus proche serait une brève salve `red_blink10` (événement court, puis extinction) ;
il faudrait alors l'ajouter dans `identify`, au point où le code renvoie `423`. Ce n'est pas demandé
par le sujet et ce n'est pas fait.

## 4. Points de vigilance

- **Couplage des 30 s.** À la fin du `cooldown`, le code ne renvoie pas `off` : il compte sur
  l'auto-extinction du firmware après `FIXED_MS` (30 s), qui coïncide avec `COOLDOWN_S` (30 s). Les
  deux valeurs doivent rester égales ; changer l'une sans l'autre désynchroniserait la LED et l'état.
- **`green_blink` ne s'éteint pas seul.** Il n'est arrêté que par le mode suivant. Tous les chemins de
  sortie de `wait_password` envoient bien un autre mode (`green_fixed`, `red_blink10`, ou `off` au
  délai dépassé), et l'application envoie `off` à son démarrage : une LED restée au vert après un
  arrêt brutal de l'application est donc remise à zéro au redémarrage.
- **ESP injoignable.** Les ordres passent par une file à un seul thread (ordre garanti, 0,5 s de délai
  maximal). Un échec n'interrompt pas la connexion ; il est seulement journalisé.

## 5. Vérification physique devant l'ESP

Hotspot RESILIENCE-G10 allumé, ESP alimenté (192.168.137.200). L'ESP répondait au moment de la revue
(`GET /health` → `{"mode":"off","rssi":-58}`). La revue de code est faite ; **la confirmation visuelle
de chaque transition reste à cocher** (couleur et nombre de clignotements, qu'un contrôle logiciel ne
peut pas voir).

| # | Transition à provoquer | Attendu à l'œil | Fait |
|---|---|---|---|
| 1 | Application démarrée, au repos | LED éteinte | [ ] |
| 2 | Identifiant reconnu | vert clignotant (≈ 2/s) jusqu'à la saisie | [ ] |
| 3 | Mot de passe correct | vert fixe, extinction après 30 s | [ ] |
| 4 | Mot de passe faux | rouge, **10 clignotements** comptés, puis extinction | [ ] |
| 5 | Visage non reconnu | rouge fixe, extinction après 30 s | [ ] |
| 6 | Vert / rouge non inversés | vert = D7, rouge = D5 ; sinon LED à anode commune (voir [plan.md](plan.md) §2 bis) | [ ] |

Les modes se testent isolément sans l'application via la page d'administration (bouton « tester la
LED », `POST /api/admin/led/test`) ou directement :

```bash
curl -s -X POST "http://192.168.137.200/led?mode=red_blink10&k=<LED_TOKEN>"
```
