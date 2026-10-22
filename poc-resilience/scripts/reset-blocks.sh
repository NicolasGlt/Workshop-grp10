#!/usr/bin/env bash
# Débloque toutes les IP actuellement bloquées par la remédiation, pour rejouer la
# démo (flood -> détection -> blocage) sans attendre le TTL de 5 min.
#
# Passe par l'API de la remédiation (action unblock_ip), exactement comme le ferait
# le ml-detector : chaque IP est retirée de la blocklist nginx, le frontend est
# rechargé, et l'état TTL en mémoire du moteur est vidé. La remédiation n'étant pas
# exposée (réseau interne remnet), on l'appelle depuis l'intérieur du conteneur via
# `compose exec` ; le jeton est déjà présent dans son environnement.
set -euo pipefail
COMPOSE="${COMPOSE:-docker compose}"

$COMPOSE exec -T remediation python - <<'PY'
import json, os, urllib.request

TOKEN = os.environ["REMEDIATION_TOKEN"]


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        "http://127.0.0.1:8000" + path, data=data, method=method,
        headers={"Content-Type": "application/json", "X-Remediation-Token": TOKEN})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


ips = call("GET", "/status").get("blocks_active", [])
if not ips:
    print("Aucune IP bloquée : rien à faire.")
else:
    for ip in ips:
        res = call("POST", "/remediate",
                   {"action": "unblock_ip", "ip": ip, "reason": "reset démo"})
        print(f"débloqué {ip} -> {res.get('status')}")
    print(f"RESET : {len(ips)} IP débloquée(s).")
PY
