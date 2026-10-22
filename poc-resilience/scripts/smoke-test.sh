#!/usr/bin/env bash
# =====================================================================
# Smoke test du POC PayPoc (boutique café + saisie carte).
# Vérifie la boutique, le flux de paiement par carte, le WAF et l'observabilité.
# Usage : ./scripts/smoke-test.sh
#         BASE=http://192.168.1.50 MERCHANT=http://192.168.1.50:8082 ./scripts/smoke-test.sh
# =====================================================================
set -uo pipefail

BASE="${BASE:-http://localhost}"
MERCHANT="${MERCHANT:-http://localhost:8082}"
PROM="${PROM:-http://localhost:9090}"
GRAFANA="${GRAFANA:-http://localhost:3000}"
API_KEY="${MERCHANT_API_KEY:-$(sed -n 's/^MERCHANT_API_KEY=//p' "$(dirname "$0")/../.env" 2>/dev/null)}"
# Sous Windows, python3 peut n'être que le raccourci du Microsoft Store, qui ne lance rien
PY=python3; "$PY" -c '' 2>/dev/null || PY=python

pass=0; fail=0
ok(){ echo "  [OK]   $1"; pass=$((pass+1)); }
ko(){ echo "  [FAIL] $1"; fail=$((fail+1)); }
check(){ [[ "$3" == "$2" ]] && ok "$1 ($3)" || ko "$1 (attendu $2, obtenu $3)"; }
code(){ curl -s -o /dev/null -w "%{http_code}" "$@"; }
field(){ "$PY" -c"import sys,json;print(json.load(sys.stdin).get('$1',''))"; }

charge(){ # $1=numéro carte  -> body JSON de /charge
  cat <<JSON
{"amount":"12.50","currency":"EUR","order_ref":"SMOKE",
 "customer_name":"Smoke","customer_email":"s@poc.local",
 "card":{"number":"$1","exp_month":12,"exp_year":30,"cvv":"123","holder":"SMOKE TEST"}}
JSON
}

echo "== Chaîne applicative"
check "WAF healthz"              200 "$(code "$BASE/healthz")"
check "Façade PayPoc"            200 "$(code "$BASE/")"
check "Boutique café"            200 "$(code "$MERCHANT/")"
check "Catalogue produits"       200 "$(code "$MERCHANT/api/products")"
check "Clé API absente refusée"  401 "$(code -X POST "$BASE/api/charge" -H 'Content-Type: application/json' -d "$(charge 4242424242424242)")"

echo "== Paiement par carte (via WAF)"
# 5555..4444 : carte de test non enrôlée -> autorisation directe.
# 4242..4242 : carte d'Alice, enrôlée -> validation 3DS dans NovaPay (pending_auth).
APPROVED=$(curl -s -X POST "$BASE/api/charge" -H "X-Api-Key: $API_KEY" -H 'Content-Type: application/json' -d "$(charge 5555555555554444)" | field status)
check "Carte 5555 -> approved"   approved "$APPROVED"
PENDING=$(curl -s -X POST "$BASE/api/charge" -H "X-Api-Key: $API_KEY" -H 'Content-Type: application/json' -d "$(charge 4242424242424242)" | field status)
check "Carte 4242 (Alice) -> 3DS" pending_auth "$PENDING"
DECLINED=$(curl -s -X POST "$BASE/api/charge" -H "X-Api-Key: $API_KEY" -H 'Content-Type: application/json' -d "$(charge 4000000000000002)" | field status)
check "Carte 4000..0002 -> declined" declined "$DECLINED"
check "Carte invalide (Luhn) -> 422" 422 "$(code -X POST "$BASE/api/charge" -H "X-Api-Key: $API_KEY" -H 'Content-Type: application/json' -d "$(charge 1234567812345678)")"
check "Checkout boutique (5555)"  200 "$(code -X POST "$MERCHANT/api/checkout" -H 'Content-Type: application/json' -d '{"items":[{"id":"bra-cerrado","qty":1,"weight":"250g"}],"customer":{"name":"S","email":"s@p.l","address":"a","zip":"75001","city":"Paris"},"card":{"number":"5555555555554444","exp_month":12,"exp_year":30,"cvv":"123","holder":"S T"}}')"

echo "== Sécurité WAF"
check "WAF actif (SQLi -> 403)"  403 "$(code "$BASE/api/ping?id=1%27%20OR%20%271%27=%271")"

echo "== Observabilité"
targets=$(curl -s "$PROM/api/v1/targets?state=active")
for job in prometheus payment-api bank merchant ml-detector remediation blackbox-http postgres; do
  health=$(printf '%s' "$targets" | "$PY" -c "
import sys,json
d=json.load(sys.stdin)
h=[t['health'] for t in d['data']['activeTargets'] if t['labels'].get('job')=='$job']
print(h[0] if h else 'absent')" 2>/dev/null || echo injoignable)
  [[ "$health" == "up" ]] && ok "Prometheus '$job' up" || ko "Prometheus '$job' : $health"
done
check "Grafana" 200 "$(code "$GRAFANA/api/health")"

echo
echo "Résultat : $pass OK / $fail FAIL"
exit $(( fail > 0 ))
