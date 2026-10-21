"""Banque fictive — PayPoc POC.

POST /authorize : la passerelle envoie le numéro de carte (test) + le montant,
la banque décide approve/decline selon des CARTES DE TEST déterministes
(à la manière de Stripe). Aucune donnée réelle, aucun stockage, aucun PAN dans les logs.
"""

import json
import logging
import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import FastAPI
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

# Cartes de test -> décision (numéro sans espaces). Tout autre numéro valide = approuvé.
TEST_CARDS = {
    "4242424242424242": "approved",
    "4000000000000002": "insufficient_funds",
    "4000000000009995": "insufficient_funds",
    "4000000000000069": "expired_card",
    "4000000000000127": "incorrect_cvc",
    "4100000000000019": "card_blocked",
}


class JsonFormatter(logging.Formatter):
    def format(self, r):
        p = {"ts": datetime.now(timezone.utc).isoformat(), "level": r.levelname, "event": r.getMessage()}
        p.update(getattr(r, "fields", {}))
        return json.dumps(p, default=str, ensure_ascii=False)

_h = logging.StreamHandler(); _h.setFormatter(JsonFormatter())
log = logging.getLogger("bank"); log.addHandler(_h); log.setLevel(logging.INFO); log.propagate = False
def audit(event, **f): log.info(event, extra={"fields": f})

AUTHORIZATIONS = Counter("bank_authorizations_total", "Autorisations traitées", ["decision", "reason"])

app = FastAPI(title="Banque fictive", version="2.0.0")
Instrumentator(should_group_status_codes=False, excluded_handlers=["/metrics", "/health"]) \
    .instrument(app).expose(app, include_in_schema=False)


class AuthorizeIn(BaseModel):
    card_number: str = Field(min_length=12, max_length=19)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    merchant: str = Field(default="", max_length=140)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.post("/authorize")
def authorize(body: AuthorizeIn):
    number = "".join(c for c in body.card_number if c.isdigit())
    last4 = number[-4:]
    decision = TEST_CARDS.get(number, "approved")   # défaut : accepté

    if decision != "approved":
        AUTHORIZATIONS.labels("declined", decision).inc()
        audit("authorization_declined", last4=last4, amount=str(body.amount), reason=decision)
        return {"decision": "declined", "reason": decision, "auth_code": None, "bank_reference": None}

    auth_code = secrets.token_hex(4).upper()
    bank_reference = "BNK-" + secrets.token_hex(6).upper()
    AUTHORIZATIONS.labels("approved", "ok").inc()
    audit("authorization_approved", last4=last4, amount=str(body.amount),
          auth_code=auth_code, bank_reference=bank_reference)
    return {"decision": "approved", "reason": None, "auth_code": auth_code, "bank_reference": bank_reference}
