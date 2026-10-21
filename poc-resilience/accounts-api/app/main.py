# API Comptes/Cartes — travail BDD du groupe (schéma de référence du projet).
# Intégrée telle quelle à Resilience-Alpha : expose creer_compte / ajouter_compte_bancaire
# / ajouter_carte / verify_password du modèle bancaire commun. Connexion via POSTGRES_* (rôle app_user).
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, status
from psycopg import errors
from psycopg.rows import dict_row
from .database import open_pool, close_pool, get_connection
from .schemas import AccountCreate, PasswordCheck, BankAccountCreate, CardCreate

@asynccontextmanager
async def lifespan(app: FastAPI):
    open_pool()
    yield
    close_pool()

app = FastAPI(
    title="Payment Security API",
    version="1.0.0",
    description="API du prototype de paiement : comptes, verification et cartes tokenisees.",
    lifespan=lifespan,
)

@app.get("/health", tags=["system"])
def health():
    try:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return {"status": "ok", "database": "connected"}
    except Exception as exc:
        raise HTTPException(503, "Base de donnees indisponible") from exc

@app.post("/accounts", status_code=status.HTTP_201_CREATED, tags=["accounts"])
def create_account(payload: AccountCreate):
    try:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT creer_compte(
                    %(prenom)s, %(nom)s, %(email)s, %(password)s,
                    %(numero_tel)s, %(adresse)s
                ) AS id_compte""",
                payload.model_dump(mode="json"),
            )
            row = cur.fetchone()
            conn.commit()
        return {
            "id_compte": row["id_compte"],
            "email": payload.email,
            "message": "Compte cree, mot de passe stocke sous forme de hash bcrypt."
        }
    except errors.UniqueViolation as exc:
        raise HTTPException(409, "Cet email existe deja") from exc
    except errors.RaiseException as exc:
        raise HTTPException(400, str(exc).split("CONTEXT:")[0].strip()) from exc

@app.post("/auth/verify-password", tags=["authentication"])
def verify(payload: PasswordCheck):
    with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """SELECT verify_password(%s, password_hash) AS valid
               FROM comptes WHERE lower(email) = lower(%s)""",
            (payload.password, str(payload.email)),
        )
        row = cur.fetchone()
    return {"valid": bool(row and row["valid"])}

@app.post("/bank-accounts", status_code=201, tags=["bank accounts"])
def create_bank_account(payload: BankAccountCreate):
    try:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT ajouter_compte_bancaire(
                    %(id_compte)s, %(iban_reference)s, %(solde)s, %(devise)s
                ) AS id_compte_bancaire""",
                payload.model_dump(mode="json"),
            )
            row = cur.fetchone()
            conn.commit()
        return {"id_compte_bancaire": row["id_compte_bancaire"]}
    except errors.ForeignKeyViolation as exc:
        raise HTTPException(404, "Compte utilisateur introuvable") from exc
    except errors.UniqueViolation as exc:
        raise HTTPException(409, "Cette reference bancaire existe deja") from exc

@app.post("/cards", status_code=201, tags=["cards"])
def create_card(payload: CardCreate):
    try:
        with get_connection() as conn, conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT ajouter_carte(
                    %(id_compte_bancaire)s, %(card_token)s,
                    %(numero_carte)s, %(nom_carte)s, %(expiration)s
                ) AS id_carte""",
                payload.model_dump(mode="json"),
            )
            row = cur.fetchone()
            conn.commit()
        return {
            "id_carte": row["id_carte"],
            "card_last4": payload.numero_carte[-4:],
            "message": "Carte ajoutee. Aucun CVV n'est accepte ni conserve."
        }
    except errors.ForeignKeyViolation as exc:
        raise HTTPException(404, "Compte bancaire introuvable") from exc
    except errors.UniqueViolation as exc:
        raise HTTPException(409, "Ce token existe deja") from exc
    except errors.RaiseException as exc:
        raise HTTPException(400, str(exc).split("CONTEXT:")[0].strip()) from exc
