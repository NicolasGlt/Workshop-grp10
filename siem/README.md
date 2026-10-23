# SIEM Wazuh — stack indépendante

SIEM du démonstrateur RESILIENCE-ALPHA, répondant à l'exigence du sujet §3.4 (« un SIEM ou une fonction SOC intégrée à votre dispositif de supervision »). Déploiement **Wazuh 4.14.7 single-node** (manager + indexer + dashboard), repris du dépôt officiel `wazuh/wazuh-docker`.

Volontairement **indépendant** de la stack `poc-resilience/` : projet Docker dédié `wazuh-siem`, réseau et volumes séparés, ports qui n'entrent pas en conflit. On peut le démarrer et l'arrêter sans toucher à la démo qui tourne.

## Prérequis

L'indexer (OpenSearch) a besoin de `vm.max_map_count >= 262144` dans la VM Docker. Sous Docker Desktop (WSL2), le régler une fois :

```
docker run --rm --privileged alpine sysctl -w vm.max_map_count=262144
```

## Démarrer

Depuis la racine du dépôt :

```
just siem-certs
just siem-up
```

`siem-certs` génère les certificats internes (une seule fois ; ils sont ignorés par git). `siem-up` démarre les trois conteneurs.

Dashboard : **https://localhost:8443** (certificat auto-signé, accepter l'avertissement du navigateur).

Pour arrêter : `just siem-down`. Pour l'état : `just siem-ps`.

## Accès

| Interface | Adresse | Identifiants par défaut |
|---|---|---|
| Dashboard Wazuh | https://localhost:8443 | `admin` / `SecretPassword` |
| API Wazuh | https://localhost:55000 | `wazuh-wui` / `MyS3cr37P450r.*-` |
| Indexer | https://localhost:9200 | `admin` / `SecretPassword` |

Ce sont les identifiants **par défaut de Wazuh**. Pour un déploiement réel, les changer (indexer `internal_users.yml`, variables d'environnement du compose) et chiffrer les secrets.

## Ports (aucun conflit avec poc-resilience)

Dashboard **8443** (au lieu de 443 pour éviter tout conflit), manager 1514 / 1515 / 514-udp / 55000, indexer 9200.

## Écarts assumés (version « montée pour l'exercice »)

- **Single-node, non durci** : un seul nœud indexer, mots de passe par défaut, pas de TLS externe.
- **Ressources non optimisées** : heap de l'indexer à 1 Go ; cohabite avec la démo + Ollama sur la même machine.
- **Pas encore d'intégration de logs** : aucun agent déployé, les logs du WAF ModSecurity ne sont pas encore envoyés à Wazuh. Piste directe pour aller plus loin : déployer un agent Wazuh et lui faire lire les logs ModSecurity du conteneur `waf` pour corréler avec la démo.

Le but ici était d'avoir un vrai SIEM **monté et démarrable** pour l'exercice, pas une production.
