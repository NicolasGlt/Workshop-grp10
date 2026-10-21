"""NovaPay — espace client (néobanque de démo) — POC Resilience-Alpha.

Application de consultation EN LECTURE SEULE branchée sur le modèle bancaire du
groupe : un utilisateur (Alice, Bob…) se connecte avec son email + mot de passe
(vérifiés par la fonction SQL verify_password), puis visualise :
  - le solde de ses comptes bancaires (comptes_bancaires.solde) ;
  - ses cartes (cartes : card_last4 uniquement, jamais le PAN ni le CVV) ;
  - l'historique de ses transactions (transactions).

Aucune écriture en base. Rôle PostgreSQL : app_user (privilèges minimaux).
"""

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_TTL_MIN = int(os.getenv("JWT_TTL_MIN", "60"))
STATIC_DIR = Path(__file__).parent / "static"

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row})


@asynccontextmanager
async def lifespan(_app):
    pool.open(wait=True, timeout=30)
    yield
    pool.close()


app = FastAPI(title="NovaPay — espace client", version="1.0.0", lifespan=lifespan)
Instrumentator(should_group_status_codes=False, excluded_handlers=["/metrics", "/health"]) \
    .instrument(app).expose(app, include_in_schema=False)


# ------------------------- auth -------------------------
class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


def make_token(id_compte: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(id_compte), "name": name, "iat": now, "exp": now + timedelta(minutes=JWT_TTL_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Non authentifié")
    try:
        payload = jwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Session expirée")
    return {"id_compte": payload["sub"], "name": payload.get("name", "")}


def user_bank_account_ids(conn, id_compte: str) -> list[str]:
    rows = conn.execute(
        "SELECT id_compte_bancaire FROM comptes_bancaires WHERE id_compte = %s",
        (id_compte,),
    ).fetchall()
    return [r["id_compte_bancaire"] for r in rows]


# ------------------------- endpoints -------------------------
@app.get("/health", include_in_schema=False)
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/login")
def login(body: LoginIn):
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT c.id_compte, u.prenom, u.nom,
                      verify_password(%s, c.password_hash) AS ok, c.statut
                 FROM comptes c
                 JOIN utilisateurs u ON u.id_user = c.id_user
                WHERE lower(c.email) = lower(%s)""",
            (body.password, body.email),
        ).fetchone()
    if not row or not row["ok"]:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if row["statut"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Compte non actif")
    name = f"{row['prenom']} {row['nom']}"
    return {"token": make_token(row["id_compte"], name), "name": name}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT u.prenom, u.nom, c.email, c.numero_tel, c.adresse
                 FROM comptes c JOIN utilisateurs u ON u.id_user = c.id_user
                WHERE c.id_compte = %s""",
            (user["id_compte"],),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return jsonable_encoder(row)


@app.get("/api/accounts")
def accounts(user: dict = Depends(current_user)):
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT id_compte_bancaire, iban_reference, solde, devise, actif
                 FROM comptes_bancaires
                WHERE id_compte = %s
                ORDER BY creation_compte_bancaire""",
            (user["id_compte"],),
        ).fetchall()
    return jsonable_encoder(rows)


@app.get("/api/cards")
def cards(user: dict = Depends(current_user)):
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT ca.card_last4, ca.actif, ca.creation_carte,
                      cb.iban_reference, cb.devise
                 FROM cartes ca
                 JOIN comptes_bancaires cb ON cb.id_compte_bancaire = ca.id_compte_bancaire
                WHERE cb.id_compte = %s
                ORDER BY ca.creation_carte""",
            (user["id_compte"],),
        ).fetchall()
    return jsonable_encoder(rows)


@app.get("/api/transactions")
def transactions(user: dict = Depends(current_user)):
    with pool.connection() as conn:
        ids = user_bank_account_ids(conn, user["id_compte"])
        if not ids:
            return []
        rows = conn.execute(
            """SELECT t.montant, t.devise, t.statut, t.description, t.reference_banque,
                      t.date_transaction,
                      (t.id_compte_emetteur = ANY(%s)) AS est_emetteur
                 FROM transactions t
                WHERE t.id_compte_emetteur = ANY(%s) OR t.id_compte_recepteur = ANY(%s)
                ORDER BY t.date_transaction DESC
                LIMIT 50""",
            (ids, ids, ids),
        ).fetchall()
    for r in rows:
        r["sens"] = "debit" if r.pop("est_emetteur") else "credit"
    return jsonable_encoder(rows)


# ------------------------- validation bancaire (3DS) -------------------------
@app.get("/api/authorizations")
def authorizations(user: dict = Depends(current_user)):
    """Demandes de paiement EN ATTENTE sur les cartes du porteur connecté."""
    with pool.connection() as conn:
        rows = conn.execute(
            """SELECT t.id_transaction, t.montant, t.devise, t.description, t.date_transaction,
                      ca.card_last4, m.name AS marchand
                 FROM transactions t
                 JOIN cartes ca ON ca.id_carte = t.id_carte
                 JOIN comptes_bancaires cb ON cb.id_compte_bancaire = ca.id_compte_bancaire
                 LEFT JOIN merchants m ON m.id_compte_bancaire = t.id_compte_recepteur
                WHERE cb.id_compte = %s AND t.statut = 'PENDING'
                ORDER BY t.date_transaction DESC""",
            (user["id_compte"],),
        ).fetchall()
    return jsonable_encoder(rows)


def _owned_pending(conn, payment_id: str, id_compte: str):
    return """ id_transaction = %s AND statut = 'PENDING'
               AND id_carte IN (SELECT ca.id_carte FROM cartes ca
                                JOIN comptes_bancaires cb ON cb.id_compte_bancaire = ca.id_compte_bancaire
                                WHERE cb.id_compte = %s) """


@app.post("/api/authorizations/{payment_id}/approve")
def approve(payment_id: str, user: dict = Depends(current_user)):
    ref = "BNK-" + secrets.token_hex(6).upper()
    insufficient = False
    with pool.connection() as conn, conn.transaction():
        # Verrouille la demande en attente appartenant au porteur connecté.
        row = conn.execute(
            "SELECT id_compte_emetteur, id_compte_recepteur, montant FROM transactions WHERE "
            + _owned_pending(conn, payment_id, user["id_compte"]) + " FOR UPDATE",
            (payment_id, user["id_compte"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Demande introuvable ou déjà traitée")
        # Débit du porteur (compte émetteur) avec contrôle de solde (CHECK solde >= 0).
        debited = conn.execute(
            "UPDATE comptes_bancaires SET solde = solde - %s "
            "WHERE id_compte_bancaire = %s AND solde >= %s RETURNING id_compte_bancaire",
            (row["montant"], row["id_compte_emetteur"], row["montant"]),
        ).fetchone()
        if not debited:
            # Fonds insuffisants -> on refuse (ces écritures sont bien validées, pas de rollback).
            insufficient = True
            conn.execute("UPDATE transactions SET statut='REJECTED' WHERE id_transaction = %s", (payment_id,))
            conn.execute("UPDATE commandes SET statut='DECLINED' WHERE id_transaction = %s", (payment_id,))
            conn.execute(
                "INSERT INTO logs (id_transaction, type_event, niveau, description) VALUES (%s, %s, %s, %s)",
                (payment_id, "payment_refused_3ds", "WARNING", "solde insuffisant"),
            )
        else:
            # Crédit du marchand + finalisation.
            conn.execute("UPDATE comptes_bancaires SET solde = solde + %s WHERE id_compte_bancaire = %s",
                         (row["montant"], row["id_compte_recepteur"]))
            conn.execute("UPDATE transactions SET statut='COMPLETED', reference_banque=%s WHERE id_transaction = %s",
                         (ref, payment_id))
            conn.execute("UPDATE commandes SET statut='PAID' WHERE id_transaction = %s", (payment_id,))
            conn.execute(
                "INSERT INTO logs (id_transaction, type_event, niveau, description) VALUES (%s, %s, %s, %s)",
                (payment_id, "payment_approved_3ds", "INFO", f"validé par le porteur, ref={ref}"),
            )
    if insufficient:
        raise HTTPException(status_code=402, detail="Solde insuffisant pour valider ce paiement")
    return {"status": "approved", "bank_reference": ref}


@app.post("/api/authorizations/{payment_id}/refuse")
def refuse(payment_id: str, user: dict = Depends(current_user)):
    with pool.connection() as conn, conn.transaction():
        row = conn.execute(
            "UPDATE transactions SET statut='REJECTED' WHERE "
            + _owned_pending(conn, payment_id, user["id_compte"])
            + " RETURNING id_transaction",
            (payment_id, user["id_compte"]),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Demande introuvable ou déjà traitée")
        conn.execute("UPDATE commandes SET statut='DECLINED' WHERE id_transaction = %s", (payment_id,))
        conn.execute(
            "INSERT INTO logs (id_transaction, type_event, niveau, description) VALUES (%s, %s, %s, %s)",
            (payment_id, "payment_refused_3ds", "WARNING", "refusé par le porteur"),
        )
    return {"status": "refused"}


# ------------------------- SPA -------------------------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=STATIC_DIR), name="static")
