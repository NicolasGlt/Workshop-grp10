"""PayPoc — passerelle de paiement — POC Resilience-Alpha.

Branchée sur le modèle bancaire du collègue (BDD de référence) :
  - le marchand est identifié par sa clé API (table `merchants` -> compte bancaire) ;
  - chaque paiement par carte est enregistré comme une `transactions` (du compte
    "EXTERNAL-GATEWAY" vers le compte du marchand), statut COMPLETED ou REJECTED ;
  - les événements vont dans la table `logs`.

SÉCURITÉ : le numéro de carte et le CVV ne sont JAMAIS stockés ni journalisés.
Validation (Luhn, CVV, date) côté passerelle avant tout appel banque.
"""

import json
import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from prometheus_client import Counter
from prometheus_fastapi_instrumentator import Instrumentator
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]
BANK_URL = os.getenv("BANK_URL", "http://bank:8000")


class JsonFormatter(logging.Formatter):
    def format(self, r):
        p = {"ts": datetime.now(timezone.utc).isoformat(), "level": r.levelname, "event": r.getMessage()}
        p.update(getattr(r, "fields", {}))
        return json.dumps(p, default=str, ensure_ascii=False)

_h = logging.StreamHandler(); _h.setFormatter(JsonFormatter())
log = logging.getLogger("payment-api"); log.addHandler(_h); log.setLevel(logging.INFO); log.propagate = False


def db_log(conn, event, ip=None, description="", level="INFO", id_transaction=None):
    """Journalise sur stdout (JSON -> Loki) et dans la table `logs` du modèle bancaire."""
    log.info(event, extra={"fields": {"ip": ip, "description": description}})
    try:
        conn.execute(
            "INSERT INTO logs (id_transaction, type_event, niveau, adresse_ip, description) "
            "VALUES (%s, %s, %s, %s, %s)",
            (id_transaction, event, level, ip, description),
        )
    except Exception:
        log.warning("log_insert_failed", extra={"fields": {"event": event}})


PAYMENTS = Counter("payment_payments_total", "Paiements par statut", ["status"])
PAYMENT_AMOUNT = Counter("payment_amount_euros_total", "Montant cumulé des paiements approuvés")
BANK_CALLS = Counter("payment_bank_calls_total", "Appels à la banque", ["outcome"])
CARD_VALIDATION = Counter("payment_card_validation_total", "Validation carte côté passerelle", ["result"])

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row})
bank_client: httpx.Client | None = None


@asynccontextmanager
async def lifespan(_app):
    global bank_client
    pool.open(wait=True, timeout=30)
    bank_client = httpx.Client(base_url=BANK_URL, timeout=5.0)
    log.info("startup", extra={"fields": {"db": "connected", "bank": BANK_URL}})
    yield
    bank_client.close(); pool.close()


app = FastAPI(title="PayPoc Payment Gateway", version="3.0.0", lifespan=lifespan)
Instrumentator(should_group_status_codes=False, excluded_handlers=["/metrics", "/health"]) \
    .instrument(app).expose(app, include_in_schema=False)


# ------------------------- helpers carte -------------------------
def luhn_ok(number: str) -> bool:
    checksum = 0
    for i, d in enumerate(reversed([int(x) for x in number])):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def card_brand(number: str) -> str:
    if number.startswith("4"):
        return "visa"
    if number[:2] in ("34", "37"):
        return "amex"
    if (51 <= int(number[:2]) <= 55) or (2221 <= int(number[:4]) <= 2720):
        return "mastercard"
    return "card"


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    return xff.split(",")[0].strip() if xff else (request.client.host if request.client else "unknown")


def current_merchant(x_api_key: str = Header(default="")) -> dict:
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Clé API manquante")
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id_merchant, name, id_compte_bancaire FROM merchants WHERE api_key = %s",
            (x_api_key,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Clé API invalide")
    return row


# ------------------------- schémas -------------------------
class Card(BaseModel):
    number: str = Field(min_length=12, max_length=23)
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=0, le=2100)
    cvv: str = Field(min_length=3, max_length=4)
    holder: str = Field(min_length=2, max_length=140)


class ChargeIn(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    order_ref: str = Field(default="", max_length=140)
    customer_name: str = Field(default="", max_length=140)
    customer_email: str = Field(default="", max_length=255)
    id_compte: str | None = Field(default=None)   # compte client si connecté (sinon invité)
    adresse: str = Field(default="", max_length=400)
    code_postal: str = Field(default="", max_length=20)
    ville: str = Field(default="", max_length=140)
    card: Card


# ------------------------- endpoints -------------------------
@app.get("/health", include_in_schema=False)
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.get("/ping", include_in_schema=False)
def ping():
    return {"pong": True}


def validate_card(card: Card) -> str | None:
    number = re.sub(r"\s+", "", card.number)
    if not number.isdigit() or not luhn_ok(number):
        return "invalid_card_number"
    if not card.cvv.isdigit():
        return "invalid_cvv"
    year = card.exp_year + 2000 if card.exp_year < 100 else card.exp_year
    now = datetime.now(timezone.utc)
    if (year, card.exp_month) < (now.year, now.month):
        return "card_expired"
    return None


@app.post("/charge", status_code=201)
def charge(body: ChargeIn, request: Request, merchant: dict = Depends(current_merchant)):
    ip = client_ip(request)
    number = re.sub(r"\s+", "", body.card.number)

    # 1) Validation côté passerelle (avant tout appel banque)
    err = validate_card(body.card)
    if err:
        CARD_VALIDATION.labels("invalid").inc()
        with pool.connection() as conn:
            db_log(conn, "card_validation_failed", ip, f"reason={err}", level="WARNING")
        raise HTTPException(status_code=422, detail=err)
    CARD_VALIDATION.labels("valid").inc()

    last4 = number[-4:]
    brand = card_brand(number)

    # 2) Carte ENRÔLÉE (connue d'un compte client) -> validation bancaire 3DS.
    #    On met le paiement EN ATTENTE ; le porteur l'approuvera depuis son app banque (NovaPay).
    with pool.connection() as conn:
        enrolled = conn.execute(
            """SELECT ca.id_carte, ca.id_compte_bancaire FROM cartes ca
                WHERE ca.card_last4 = %s AND ca.actif
                  AND ca.numero_carte_hash = crypt(%s, ca.numero_carte_hash)
                LIMIT 1""",
            (last4, number),
        ).fetchone()

    # Une carte enrôlée est rattachée à un compte client : le paiement est un virement
    # du compte du PORTEUR vers le marchand. On ne peut pas payer son propre compte marchand.
    if enrolled and enrolled["id_compte_bancaire"] != merchant["id_compte_bancaire"]:
        desc = f"Commande {body.order_ref} · {brand.upper()} ••{last4} · validation bancaire en attente"
        with pool.connection() as conn, conn.transaction():
            tx = conn.execute(
                """INSERT INTO transactions
                     (id_compte_emetteur, id_compte_recepteur, id_carte, montant, devise, statut,
                      reference_banque, description)
                   VALUES (%s, %s, %s, %s, %s, 'PENDING', NULL, %s)
                   RETURNING id_transaction""",
                (enrolled["id_compte_bancaire"], merchant["id_compte_bancaire"], enrolled["id_carte"],
                 body.amount, body.currency.upper(), desc),
            ).fetchone()
            txid = tx["id_transaction"]
            conn.execute(
                """INSERT INTO commandes
                     (reference, id_merchant, id_transaction, id_compte, client_nom, client_email,
                      adresse, code_postal, ville, montant, devise, statut)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')""",
                (body.order_ref or "CMD", merchant["id_merchant"], txid, body.id_compte or None,
                 body.customer_name or None, body.customer_email or None,
                 body.adresse or None, body.code_postal or None, body.ville or None,
                 body.amount, body.currency.upper()),
            )
            db_log(conn, "payment_pending_3ds", ip, f"montant={body.amount} last4={last4}",
                   level="INFO", id_transaction=txid)
        PAYMENTS.labels("pending").inc()
        return jsonable_encoder({"payment_id": txid, "last4": last4, "brand": brand, "status": "pending_auth"})

    # 3) Carte non enrôlée -> autorisation banque classique (instantanée)
    # 2) Autorisation banque (seule la banque voit le numéro)
    try:
        resp = bank_client.post("/authorize", json={
            "card_number": number, "amount": str(body.amount),
            "currency": body.currency.upper(), "merchant": merchant["name"],
        })
        resp.raise_for_status()
        decision = resp.json()
    except (httpx.HTTPError, ValueError):
        BANK_CALLS.labels("error").inc()
        PAYMENTS.labels("failed").inc()
        log.warning("payment_bank_unreachable", extra={"fields": {"ip": ip, "merchant": merchant["name"]}})
        raise HTTPException(status_code=502, detail="Banque injoignable, réessayez")

    BANK_CALLS.labels("ok").inc()
    approved = decision["decision"] == "approved"
    statut = "COMPLETED" if approved else "REJECTED"
    reason = None if approved else decision.get("reason", "declined")
    desc = (f"Commande {body.order_ref} · {brand.upper()} ••{last4}"
            + ("" if approved else f" · refus:{reason}"))

    with pool.connection() as conn, conn.transaction():
        tx = conn.execute(
            """INSERT INTO transactions
                 (id_compte_emetteur, id_compte_recepteur, id_carte, montant, devise, statut,
                  reference_banque, description)
               VALUES (
                 (SELECT id_compte_bancaire FROM comptes_bancaires WHERE iban_reference = 'EXTERNAL-GATEWAY'),
                 %s, NULL, %s, %s, %s, %s, %s)
               RETURNING id_transaction, date_transaction""",
            (merchant["id_compte_bancaire"], body.amount, body.currency.upper(), statut,
             decision.get("bank_reference"), desc),
        ).fetchone()
        txid = tx["id_transaction"]

        if approved:
            conn.execute(
                "UPDATE comptes_bancaires SET solde = solde + %s WHERE id_compte_bancaire = %s",
                (body.amount, merchant["id_compte_bancaire"]),
            )
            db_log(conn, "payment_approved", ip,
                   f"montant={body.amount} last4={last4} ref={decision.get('bank_reference')}",
                   level="INFO", id_transaction=txid)
            PAYMENTS.labels("approved").inc(); PAYMENT_AMOUNT.inc(float(body.amount))
            result = {"status": "approved", "auth_code": decision.get("auth_code"),
                      "bank_reference": decision.get("bank_reference")}
        else:
            db_log(conn, "payment_declined", ip, f"reason={reason} last4={last4}",
                   level="WARNING", id_transaction=txid)
            PAYMENTS.labels("declined").inc()
            result = {"status": "declined", "reason": reason}

        # Commande boutique (achat invité) liée au marchand et à la transaction.
        # Les coordonnées de livraison sont conservées ici, jamais de donnée carte.
        conn.execute(
            """INSERT INTO commandes
                 (reference, id_merchant, id_transaction, id_compte, client_nom, client_email,
                  adresse, code_postal, ville, montant, devise, statut)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (body.order_ref or "CMD", merchant["id_merchant"], txid, body.id_compte or None,
             body.customer_name or None, body.customer_email or None,
             body.adresse or None, body.code_postal or None, body.ville or None,
             body.amount, body.currency.upper(), "PAID" if approved else "DECLINED"),
        )

    return jsonable_encoder({"payment_id": txid, "last4": last4, "brand": brand, **result})


@app.get("/payments/{payment_id}")
def get_payment(payment_id: str, merchant: dict = Depends(current_merchant)):
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT id_transaction, montant, devise, statut, reference_banque,
                      description, date_transaction
                 FROM transactions
                WHERE id_transaction = %s AND id_compte_recepteur = %s""",
            (payment_id, merchant["id_compte_bancaire"]),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Paiement introuvable")
    return jsonable_encoder(row)
