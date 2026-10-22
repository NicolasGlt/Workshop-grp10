#!/usr/bin/env bash
# Démo de reprise autonome, équivalent Linux de demo-incident.ps1 (Podman ou Docker)
#   1. service AVANT (paiement OK)  2. flood HTTP  3. ml-detector -> remediation  4. service APRÈS
# Usage : ./scripts/demo-incident.sh   (BASE, PROM, ENGINE surchargeables, FLOOD_ACTION=block_ip recommandé)
set -uo pipefail
cd "$(dirname "$0")/.."
BASE="${BASE:-http://localhost}"   # Podman rootless (WAF sur 8080) : BASE=http://localhost:8080
PROM="${PROM:-http://localhost:9090}"
MERCHANT="${MERCHANT:-http://localhost:8082}"
ENGINE="${ENGINE:-$(command -v docker || command -v podman)}"

# Paiement comme un vrai client : achat sur la boutique, qui appelle PayPoc via le WAF.
# Ne dépend pas de l'IP vue par le WAF (sous Docker Desktop, l'hôte et le PC Attaquant
# peuvent arriver avec la même IP de passerelle : un paiement direct serait bloqué aussi).
pay(){
  curl -s -X POST "$MERCHANT/api/checkout" -H 'Content-Type: application/json' \
    -d '{"items":[{"id":"bra-cerrado","qty":1,"weight":"250g"}],"customer":{"name":"Demo","email":"demo@poc.local","address":"1 rue du Test","zip":"75001","city":"Paris"},"card":{"number":"5555555555554444","exp_month":12,"exp_year":30,"cvv":"123","holder":"DEMO USER"}}' \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "erreur"
}
prom(){ curl -s "$PROM/api/v1/query?query=$1" | python3 -c "import sys,json;r=json.load(sys.stdin)['data']['result'];print(' '.join(x['value'][1] for x in r) or 'aucune')"; }

echo "=== 1. AVANT incident"
# Le détecteur doit avoir appris la normale (~2 min après son démarrage), sinon la démo ne prouve rien.
for _ in $(seq 1 30); do [ "$(prom ml_detector_trained)" = 1 ] && break; echo "  détecteur en apprentissage..."; sleep 10; done
[ "$(prom ml_detector_trained)" = 1 ] || { echo "ÉCHEC : détecteur non entraîné, démo annulée"; exit 1; }
echo "Détecteur entraîné : oui"
echo "Paiement de contrôle : $(pay)"

echo "=== 2. Incident : flood HTTP (Grafana, dashboard 07 Résilience)"
"$ENGINE" run --rm --network resilience-alpha_edge docker.io/williamyeh/hey -z 60s -c 90 -T application/json \
  -H "User-Agent: Mozilla/5.0" -H "Accept: application/json" http://waf:8080/api/ping \
  | grep -E "Requests/sec|\[[0-9]{3}\]"

echo "=== 3. Reprise autonome en cours"
sleep 20
echo "Remédiations déclenchées : $(prom ml_detector_remediations_total)"

echo "=== 4. APRÈS remédiation"
sleep 10
echo "Nouveau paiement : $(pay)"
