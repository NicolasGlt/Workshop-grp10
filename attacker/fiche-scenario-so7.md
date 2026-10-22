# Fiche de scénario d'attaque — SO7 (livrable RA-09)

Relie le scénario opérationnel **SO7** de l'analyse EBIOS du groupe à la démo de
reprise autonome. Exercice pédagogique, laboratoire fermé, SI **fictif** du groupe.

## Identification

| Champ | Valeur |
|---|---|
| Référence EBIOS | **SO7** — déni de service par saturation du point d'entrée |
| Risque associé | **R7** |
| Livrable planning | **RA-09** |
| Périmètre | Point d'accès isolé `RESILIENCE-G10`, réseau `192.168.137.0/24` |
| Autorisation | SI de démonstration du groupe, données fictives, usage de cours uniquement |

## Hypothèse

Un attaquant présent sur le même réseau que le SI de paiement cherche à rendre le
service indisponible en **saturant le point d'entrée HTTP** (le WAF) de requêtes,
sans identifiants ni exploitation applicative — une simple montée en charge au-delà
de la normale apprise.

## Cible

Le **WAF** (ModSecurity CRS), unique point d'entrée du SI, exposé sur l'adresse du
PC Hôte **`192.168.137.1`** (port 80 par défaut ; 8080 si WAF lancé via Podman
rootless côté Hôte). Endpoint sollicité : **`GET /api/ping`**.

## Outil

Générateur de charge HTTP public **`hey`** (image conteneur `williamyeh/hey`),
exécuté depuis le PC Attaquant par **Podman rootless** (repli Docker). Aucun
installation native, pas de sudo. Même outil que la démo locale du groupe
(`poc-resilience/scripts/demo-incident.*`), déporté sur le PC Attaquant.

## Commande exacte

Depuis le XPS Debian, connecté à `RESILIENCE-G10` :

```bash
just attack-check http://192.168.137.1     # vérifs AVANT
just attack http://192.168.137.1 60s 90    # cible, durée, concurrence (positionnels)
```

> Les arguments `just` sont **positionnels** : `just attack target="..."` ne marche
> pas (`just` collerait `target=` dans la valeur). Voir `attacker/README.md`.

Équivalent sans `just` :

```bash
bash attacker/preflight.sh http://192.168.137.1
bash attacker/flood.sh http://192.168.137.1 60s 90
```

Ce que lance `just attack` sous le capot (Podman rootless) :

```bash
podman run --rm docker.io/williamyeh/hey \
  -z 60s -c 90 -T application/json \
  -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" \
  http://192.168.137.1/api/ping
```

## Effet attendu

- Montée brutale du **débit de requêtes** sur le WAF, bien au-dessus de la normale.
- Le `ml-detector` sort du profil appris et lève une anomalie.
- La remédiation Ansible s'exécute **sans intervention humaine**.

## Ce qu'on observe (Grafana « 07 · Résilience » + logs)

| Signal | Où |
|---|---|
| **Débit** (requêtes/s) au-dessus de la normale | Grafana 07 · Résilience |
| **Drapeau d'anomalie** levé par **Local Outlier Factor** après **3 mesures** | Grafana 07, logs `ml-detector` |
| **Remédiations déclenchées** (`ml_detector_remediations_total`) | Grafana 07, logs `remediation` |
| **IP de l'attaquant bloquée** (`block_ip`, ajout blocklist frontend) | Grafana 07, logs `remediation` |

## Critère de réussite

> **Un nouveau paiement est approuvé pendant que l'attaque continue.**

La reprise est prouvée si, le flood toujours en cours, un achat passe sur la boutique
(flux `just demo`) et ressort **`approved`** : le service reste disponible aux clients
légitimes alors que l'IP attaquante est bloquée.

## Limites connues

- Sous Docker Desktop (WSL2), le WAF peut voir l'attaquant et l'Hôte avec la même IP
  de passerelle ; la preuve de paiement passe alors par la boutique, pas par un
  paiement direct depuis l'attaquant.
- Le scénario n'a **pas** pu être joué de bout en bout avant le gel du code : le PC
  Hôte Windows et le POC n'étaient pas disponibles. Seuls la syntaxe, le garde-fou de
  périmètre et le téléchargement de l'image ont été vérifiés sur le XPS.
