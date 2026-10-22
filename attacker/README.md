# Red Team — déclencheur d'incident depuis le PC Attaquant

Outillage de la **partie attaquante** du démonstrateur RESILIENCE-ALPHA. Il sert à
lancer, **depuis un poste distinct du PC Hôte**, le scénario de déni de service qui
déclenche la boucle de résilience du groupe : détection ML → remédiation Ansible
automatique → preuve de reprise par un nouveau paiement.

> ## ⚠️ Périmètre et autorisation — à lire avant toute exécution
>
> - **Exercice pédagogique en laboratoire fermé** (workshop M2 EPSI 2026-27, groupe 10).
> - La cible est **le seul démonstrateur du groupe** : un SI de paiement **fictif**
>   (AlphaPay / PayPoc), **sans aucune donnée réelle**, cartes de test uniquement.
> - L'attaque ne part **que** du point d'accès Wi-Fi isolé **`RESILIENCE-G10`**
>   (réseau **`192.168.137.0/24`**) et ne vise **que** le point d'entrée de ce SI
>   (le WAF, accessible sur l'adresse du PC Hôte `192.168.137.1`).
> - **Aucune cible n'est codée en dur vers une adresse publique.** La cible est
>   toujours passée en paramètre, et un garde-fou refuse toute adresse hors
>   `192.168.137.0/24` / `localhost` (voir [`flood.sh`](flood.sh)).
> - Usage strictement pédagogique, sur un système dont le groupe est propriétaire,
>   dans le cadre du cours. **Ne jamais pointer cet outillage vers un autre système.**

## Rôle

Le PC Attaquant (le XPS de Pablo, Debian 13) génère une **saturation HTTP** du point
d'entrée du SI. Cette charge anormale est détectée automatiquement, la remédiation
bloque l'IP de l'attaquant, et le service reste disponible pour les vrais clients.
L'objectif n'est **pas** de « casser » quoi que ce soit, mais de **prouver la
reprise autonome** : un nouveau paiement doit passer *pendant que l'attaque continue*.

## Scénario SO7 (EBIOS → démo)

| Élément | Valeur |
|---|---|
| Source de risque / scénario | **SO7** — déni de service par saturation du point d'entrée (risque **R7**) |
| Cible | **Le WAF** (ModSecurity CRS), unique point d'entrée du SI, exposé sur `192.168.137.1` |
| Vecteur | Flood HTTP sur `GET /api/ping` (générateur de charge `hey`) |
| Ce qui est détecté | **Débit hors normale** : le `ml-detector` apprend d'abord la normale, puis signale une anomalie via **Local Outlier Factor** après **3 mesures** consécutives hors profil |
| Ce qui est réparé | La **remédiation Ansible** applique **`block_ip`** sur l'IP de l'attaquant (ajout à la blocklist du frontend), le service reste servi aux clients légitimes |
| Critère de réussite | **Un nouveau paiement approuvé pendant que l'attaque continue** |

La fiche détaillée (hypothèse, commande exacte, effet attendu, observation) est dans
[`fiche-scenario-so7.md`](fiche-scenario-so7.md) (livrable de planning **RA-09**).

## Prérequis

- Être connecté au point d'accès **`RESILIENCE-G10`** (le poste doit avoir une IP
  dans `192.168.137.0/24`).
- Le POC doit tourner sur le PC Hôte et le `ml-detector` doit avoir **appris la
  normale** (`ml_detector_trained = 1`) — sinon la détection ne prouve rien.
- **Podman rootless** (pas de sudo, pas d'installation native) ; repli **Docker** si
  présent. L'image publique `williamyeh/hey` est téléchargée au premier lancement.

## Lancement

Les recettes `just` prennent leurs arguments **positionnellement** (comme `just
restore` ou `just user` ailleurs dans ce dépôt) : `just attack [cible] [durée]
[concurrence]`. Sans argument, la cible par défaut est le point d'accès du lab.

```bash
# 1. Vérifications AVANT (réseau, cible joignable, image hey disponible)
just attack-check http://192.168.137.1
#    équivaut à : bash attacker/preflight.sh http://192.168.137.1

# 2. Lancer le flood (cible, durée, concurrence — défauts : .../ 60s / 90)
just attack http://192.168.137.1 60s 90
#    ou, en s'appuyant sur les défauts : just attack
#    équivaut à : bash attacker/flood.sh http://192.168.137.1 60s 90
```

Variantes utiles :

- WAF sur Podman rootless côté Hôte (port 8080) : `just attack http://192.168.137.1:8080`.
- Durée plus longue pour prouver la reprise *pendant* l'attaque : `just attack http://192.168.137.1 120s 90`.

> `just attack target="..."` **ne fonctionne pas** : après le nom de recette, `just`
> traite `name=value` comme une valeur positionnelle littérale. On passe donc les
> valeurs dans l'ordre, ou on utilise directement `bash attacker/flood.sh`.

## Observation

Pendant et après l'attaque :

- **Grafana**, dashboard **« 07 · Résilience »** (`http://localhost:3000` côté Hôte) :
  pic de débit, drapeau d'anomalie, remédiations déclenchées, IP bloquée.
- Côté Hôte : `just logs ml-detector remediation`.
- Déroulé complet du jour J : [`../docs/demo-jour-j.md`](../docs/demo-jour-j.md).

> **Note IP sous Docker Desktop (WSL2).** Selon la façon dont le WAF voit l'adresse
> source, le PC Attaquant et le PC Hôte peuvent arriver avec la même IP de passerelle.
> La preuve de reprise passe alors par un **achat sur la boutique** (le flux de
> `just demo`), pas par un paiement direct depuis l'attaquant. C'est une limite du
> réseau de démo, pas de cet outillage.

## Contenu du dossier

| Fichier | Rôle |
|---|---|
| [`flood.sh`](flood.sh) | Lanceur shell portable (Podman par défaut, repli Docker), garde-fou de périmètre |
| [`preflight.sh`](preflight.sh) | Vérifications avant lancement (réseau, cible, image) |
| [`fiche-scenario-so7.md`](fiche-scenario-so7.md) | Fiche de scénario d'attaque (RA-09) |
| `../justfile` | Recettes `just attack` et `just attack-check` |
