"""traffic — clients simulés à faible débit.

Une plateforme de paiement n'est jamais muette : ce service produit une activité
normale et variable (consultation, paiements par carte non enrôlée, quelques refus),
pour que les dashboards vivent et que ml-detector apprenne une normale réaliste.
Passe par le WAF comme un vrai marchand. Aucune donnée réelle : cartes de test.
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone

import httpx

BASE = os.getenv("TARGET_URL", "http://waf:8080")
API_KEY = os.environ["MERCHANT_API_KEY"]
MIN_RPS = float(os.getenv("MIN_RPS", "1"))
MAX_RPS = float(os.getenv("MAX_RPS", "6"))

# Cartes de test non enrôlées (pas de 3DS) : approuvée, puis refus fonds insuffisants.
CARDS = ["5555555555554444"] * 9 + ["4000000000000002"]

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("traffic")
logging.getLogger("httpx").setLevel(logging.WARNING)   # pas une ligne par requête dans Loki


def audit(event, **f):
    log.info(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **f}))


def charge(client: httpx.Client) -> int:
    body = {
        "amount": f"{random.uniform(3, 60):.2f}", "currency": "EUR", "order_ref": "SIM",
        "customer_name": "Client simulé", "customer_email": "sim@poc.local",
        "card": {"number": random.choice(CARDS), "exp_month": 12, "exp_year": 30,
                 "cvv": "123", "holder": "CLIENT SIMULE"},
    }
    return client.post(f"{BASE}/api/charge", json=body, headers={"X-Api-Key": API_KEY}).status_code


def main():
    audit("startup", target=BASE, min_rps=MIN_RPS, max_rps=MAX_RPS)
    with httpx.Client(timeout=5.0, headers={"User-Agent": "poc-traffic/1.0"}) as client:
        rps, sent, errors = MIN_RPS, 0, 0
        while True:
            # Débit qui dérive lentement entre MIN_RPS et MAX_RPS, comme une journée calme.
            rps = min(MAX_RPS, max(MIN_RPS, rps + random.uniform(-0.5, 0.5)))
            try:
                if random.random() < 0.15:
                    charge(client)
                else:
                    client.get(f"{BASE}/api/ping")
                sent += 1
            except httpx.HTTPError:
                errors += 1
            if sent % 500 == 0:
                audit("progress", sent=sent, errors=errors, rps=round(rps, 2))
            time.sleep(random.expovariate(rps))


if __name__ == "__main__":
    main()
