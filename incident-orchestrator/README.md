# Orchestrateur d'incident

Composant **de confiance** (côté PC Hôte, comme le `ml-detector` est de confiance côté cluster)
qui met le LLM au service de la résilience **sans jamais lui donner la main sur le système**.
Il relie trois briques déjà en place — l'observabilité (Prometheus, santé Docker), l'assistant
RAG (le LLM) et le moteur de remédiation (catalogue d'actions fermé) — et publie une **timeline
live** de l'incident sur http://127.0.0.1:8002.

## Deux usages du LLM, automatiques, sans intervention humaine

### 1. Attaque (flood) — le LLM est **informatif**
La boucle déterministe reste **inchangée et instantanée** : `ml-detector → remediation (block_ip)`.
Le LLM **n'est pas dans le chemin critique**. En parallèle, l'orchestrateur **observe** qu'un
blocage a eu lieu (via `/status` de la remédiation) et demande au LLM d'**expliquer** la décision
à partir du corpus (RAG) : incident, action, pourquoi, procédure citée. Le LLM ne décide ni
n'exécute rien.

### 2. Chaos (service tombé) — le LLM est **décideur du service**
L'orchestrateur **détecte** la dégradation (santé des conteneurs Docker), envoie au LLM le
**symptôme + l'état de santé** et lui demande **quel** service relancer. Le LLM, via le RAG sur
l'architecture (`api → bank → db`), répond en **JSON contraint** (`{"action","service","reason"}`).
Là où la règle déterministe du `ml-detector` redémarrerait `api` **en dur** (le symptôme), le LLM
remonte à la **cause** (`bank` tombé) grâce aux dépendances documentées.

> Le LLM **propose**, l'orchestrateur **dispose** : la réponse est **validée contre un catalogue
> fermé** (action `restart_service` uniquement, service dans une whitelist **et** réellement
> dégradé) avant tout appel. Si la réponse du LLM est invalide, un **repli déterministe** redémarre
> le service observé dégradé → la **reprise reste garantie sans humain** (sujet §3.3).

Le LLM **ne touche jamais le système** : il ne voit que le contexte qu'on lui passe et répond du
texte/JSON. Seul l'orchestrateur détient le jeton et appelle l'API de remédiation.

## Chemins réseau (choix assumé)

L'assistant RAG et Ollama tournent sur l'**hôte** (loopback), la remédiation est **dans le cluster**.
L'orchestrateur tourne **sur l'hôte** pour parler au LLM en loopback (l'assistant reste donc
**non exposé**, mesure M11). Pour atteindre l'API de remédiation, celle-ci est publiée **sur
`127.0.0.1` uniquement** (comme la base de données), donc **invisible depuis le point d'accès**, et
reste protégée par **jeton + catalogue fermé**. Sur un hôte Docker Linux natif, on ferait tourner
l'orchestrateur en conteneur sur le réseau `monitoring` et ce port loopback serait inutile.

## Lancer

Pré-requis : la stack `poc-resilience` tourne, l'assistant RAG tourne sur `:8001`
(`just assistant`), le jeton `REMEDIATION_TOKEN` est dans `poc-resilience/.env`.

```bash
just orchestrator-install   # une fois
just orchestrator           # http://127.0.0.1:8002
```

Démos :

```bash
just chaos            # arrête bank -> l'orchestrateur détecte, le LLM décide bank, reprise
just chaos api        # autre service
# flood (cf. attacker/) : la timeline montre le blocage déterministe + l'explication du LLM
```

## Réglages (`incident-orchestrator/app/config.py`, surchargeables par variables d'env)

| variable | rôle | défaut |
|---|---|---|
| `ASSISTANT_URL` | assistant RAG (le LLM) | `http://127.0.0.1:8001` |
| `REMEDIATION_URL` | API de remédiation (port loopback) | `http://127.0.0.1:8099` |
| `PROM_URL` | Prometheus | `http://127.0.0.1:9090` |
| `MONITORED_SERVICES` | services suivis / whitelist de redémarrage | `api,bank,merchant,frontend,waf,accounts-api,clientapp` |
| `CHAOS_COOLDOWN` | délai anti-rejeu entre deux reprises (s) | `90` |

La base `db` est **hors** du périmètre de redémarrage automatique (décision humaine).
