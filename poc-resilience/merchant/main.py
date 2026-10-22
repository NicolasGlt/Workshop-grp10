"""Brûlerie du Comptoir — boutique de café fictive qui encaisse via PayPoc.

- sert la boutique (SPA : catalogue, panier, checkout avec saisie carte) ;
- GET  /api/products  : le catalogue (prix maîtrisés côté serveur) ;
- POST /api/checkout  : recalcule le total, transmet la carte à PayPoc (/charge),
  renvoie le résultat. La boutique NE stocke ni ne journalise la carte.
"""

import os
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import jwt
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from prometheus_fastapi_instrumentator import Instrumentator
from psycopg import errors
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, Field

PAYPOC_API_BASE = os.getenv("PAYPOC_API_BASE", "http://waf:8080/api")
MERCHANT_API_KEY = os.environ["MERCHANT_API_KEY"]   # du .env, jamais en dur
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
JWT_TTL_MIN = int(os.getenv("JWT_TTL_MIN", "120"))
HERE = os.path.dirname(__file__)

# Catalogue — prix en euros pour 250 g (source de vérité côté serveur).
WEIGHTS = {"250g": Decimal("1"), "1kg": Decimal("3.6")}
PRODUCTS = [
    {"id": "eth-yirga", "name": "Yirgacheffe", "origin": "Éthiopie", "region": "Gedeo",
     "process": "Lavé", "altitude": "1 900–2 100 m", "roast": 2, "price": 11.50, "category": "single-origin",
     "notes": ["jasmin", "bergamote", "thé noir"], "stock": True,
     "desc": "Un café floral et vif, emblématique des hauts plateaux éthiopiens. "
             "En tasse, une acidité délicate d'agrume et un final thé noir tout en finesse."},
    {"id": "col-huila", "name": "Huila", "origin": "Colombie", "region": "Pitalito",
     "process": "Lavé", "altitude": "1 600–1 850 m", "roast": 3, "price": 10.90, "category": "single-origin",
     "notes": ["caramel", "pomme rouge", "noisette"], "stock": True,
     "desc": "Rond et équilibré, le classique colombien. Douceur caramélisée, "
             "corps moyen et une pointe fruitée qui le rend très polyvalent."},
    {"id": "bra-cerrado", "name": "Cerrado", "origin": "Brésil", "region": "Minas Gerais",
     "process": "Naturel", "altitude": "1 100–1 300 m", "roast": 4, "price": 9.80, "category": "single-origin",
     "notes": ["chocolat noir", "noix", "praliné"], "stock": True,
     "desc": "Gourmand et peu acide, parfait en espresso. Dominante cacao, "
             "texture épaisse et une belle persistance pralinée."},
    {"id": "ken-nyeri", "name": "Nyeri AA", "origin": "Kenya", "region": "Nyeri",
     "process": "Lavé", "altitude": "1 700–1 900 m", "roast": 2, "price": 13.20, "category": "single-origin",
     "notes": ["cassis", "pamplemousse", "tomate séchée"], "stock": True,
     "desc": "Puissant et juteux, un Kenya de caractère. Acidité éclatante de cassis "
             "et une structure qui remplit la bouche."},
    {"id": "esp-comptoir", "name": "Assemblage Comptoir", "origin": "Assemblage", "region": "Amérique du Sud",
     "process": "Mixte", "altitude": "—", "roast": 4, "price": 10.20, "category": "assemblage",
     "notes": ["cacao", "fruits secs", "sucre roux"], "stock": True,
     "desc": "Notre espresso signature : rond, chocolaté, crema dense. "
             "Pensé pour le lait comme pour la dégustation serrée."},
    {"id": "dec-swiss", "name": "Décaféiné Sucre de Canne", "origin": "Pérou", "region": "Cajamarca",
     "process": "Sugar Cane (EA)", "altitude": "1 500–1 800 m", "roast": 3, "price": 11.90, "category": "decafeine",
     "notes": ["chocolat au lait", "amande", "vanille"], "stock": True,
     "desc": "Décaféiné sans solvant, au sucre de canne. Tout le plaisir, "
             "sans la caféine : doux, enveloppant, légèrement vanillé."},
    {"id": "eth-guji", "name": "Guji Naturel", "origin": "Éthiopie", "region": "Guji",
     "process": "Naturel", "altitude": "1 950–2 200 m", "roast": 1, "price": 13.90, "category": "single-origin",
     "notes": ["myrtille", "fraise", "cacao au lait"], "stock": False,
     "desc": "Édition limitée : une bombe fruitée façon confiture de baies. "
             "Torréfaction claire pour préserver l'explosion aromatique."},
    {"id": "mat-v60", "name": "Kit Filtre V60", "origin": "Matériel", "region": "—",
     "process": "—", "altitude": "—", "roast": 0, "price": 29.00, "category": "materiel",
     "notes": ["dripper", "100 filtres", "guide"], "stock": True, "no_weight": True, "no_grind": True,
     "desc": "Le nécessaire pour la méthode douce : dripper céramique, "
             "100 filtres et notre guide d'extraction maison."},

    # ---- Machines à café ----
    {"id": "mac-uno", "name": "Comptoir Uno", "origin": "Machine", "region": "À capsules",
     "process": "—", "altitude": "—", "roast": 0, "price": 99.00, "category": "machine",
     "notes": ["compacte", "chauffe 25 s", "19 bars"], "stock": True, "no_weight": True, "no_grind": True,
     "desc": "Notre machine à capsules compacte : prête en 25 secondes, pression 19 bars, "
             "idéale pour un expresso serré sans encombrer le plan de travail."},
    {"id": "mac-milk", "name": "Comptoir Milk", "origin": "Machine", "region": "À capsules",
     "process": "—", "altitude": "—", "roast": 0, "price": 149.00, "category": "machine",
     "notes": ["mousseur lait", "2 tasses", "19 bars"], "stock": True, "no_weight": True, "no_grind": True,
     "desc": "La capsule avec mousseur à lait intégré : cappuccino et latte d'une seule touche, "
             "réservoir double pour enchaîner deux tasses."},
    {"id": "mac-barista", "name": "Comptoir Barista", "origin": "Machine", "region": "Porte-filtre",
     "process": "—", "altitude": "—", "roast": 0, "price": 349.00, "category": "machine",
     "notes": ["porte-filtre", "buse vapeur", "inox"], "stock": True, "no_weight": True, "no_grind": True,
     "desc": "L'expresso à l'ancienne : porte-filtre pression, buse vapeur pro pour la microfoam, "
             "corps inox. Pour qui veut maîtriser son extraction."},
    {"id": "mac-auto", "name": "Comptoir Automatic", "origin": "Machine", "region": "Avec broyeur",
     "process": "—", "altitude": "—", "roast": 0, "price": 699.00, "category": "machine",
     "notes": ["broyeur grains", "écran tactile", "12 recettes"], "stock": True, "no_weight": True, "no_grind": True,
     "desc": "Machine automatique avec broyeur à grains intégré : du grain à la tasse, "
             "écran tactile et 12 recettes mémorisées. Le confort absolu au quotidien."},
    {"id": "mac-travel", "name": "Comptoir Nomade", "origin": "Machine", "region": "Portable",
     "process": "—", "altitude": "—", "roast": 0, "price": 79.00, "category": "machine",
     "notes": ["portable", "rechargeable", "manuel"], "stock": False, "no_weight": True, "no_grind": True,
     "desc": "Expresso partout : pompe manuelle, batterie rechargeable, format sac à dos. "
             "Édition limitée pour les amateurs en vadrouille."},
]
BY_ID = {p["id"]: p for p in PRODUCTS}

pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=10, open=False, kwargs={"row_factory": dict_row})


@asynccontextmanager
async def lifespan(_app):
    pool.open(wait=True, timeout=30)
    yield
    pool.close()


app = FastAPI(title="Brûlerie du Comptoir", version="1.1.0", lifespan=lifespan)
Instrumentator(excluded_handlers=["/metrics", "/health"]).instrument(app).expose(app, include_in_schema=False)


# ------------------------- comptes clients (JWT) -------------------------
def make_token(id_compte: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": str(id_compte), "name": name, "iat": now,
                       "exp": now + timedelta(minutes=JWT_TTL_MIN)}, JWT_SECRET, algorithm="HS256")


def optional_user(authorization: str = Header(default="")) -> dict | None:
    """Identité du client si connecté, sinon None (checkout invité toléré)."""
    if not authorization.lower().startswith("bearer "):
        return None
    try:
        p = jwt.decode(authorization[7:], JWT_SECRET, algorithms=["HS256"])
        return {"id_compte": p["sub"], "name": p.get("name", "")}
    except jwt.PyJWTError:
        return None


def require_user(authorization: str = Header(default="")) -> dict:
    u = optional_user(authorization)
    if not u:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return u


def wallet_of(conn, id_compte: str) -> str:
    """Compte bancaire du client (pour rattacher les cartes) ; créé si absent."""
    row = conn.execute(
        "SELECT id_compte_bancaire FROM comptes_bancaires WHERE id_compte = %s ORDER BY creation_compte_bancaire LIMIT 1",
        (id_compte,),
    ).fetchone()
    if row:
        return row["id_compte_bancaire"]
    row = conn.execute(
        "SELECT ajouter_compte_bancaire(%s, %s, 0, 'EUR') AS id",
        (id_compte, "SHOP-" + secrets.token_hex(5).upper()),
    ).fetchone()
    return row["id"]


class RegisterIn(BaseModel):
    prenom: str = Field(min_length=1, max_length=100)
    nom: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=10, max_length=128)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)


@app.get("/health", include_in_schema=False)
def health():
    with pool.connection() as conn:
        conn.execute("SELECT 1")
    return {"status": "ok"}


@app.post("/api/register", status_code=201)
def register(body: RegisterIn):
    try:
        with pool.connection() as conn:
            row = conn.execute(
                "SELECT creer_compte(%s, %s, %s, %s, NULL, NULL) AS id",
                (body.prenom, body.nom, body.email, body.password),
            ).fetchone()
            wallet_of(conn, row["id"])  # prépare le porte-cartes
    except errors.UniqueViolation:
        raise HTTPException(status_code=409, detail="Un compte existe déjà avec cet email")
    except errors.RaiseException as exc:
        raise HTTPException(status_code=400, detail=str(exc).split("CONTEXT:")[0].strip())
    name = f"{body.prenom} {body.nom}"
    return {"token": make_token(row["id"], name), "name": name}


@app.post("/api/login")
def login(body: LoginIn):
    with pool.connection() as conn:
        row = conn.execute(
            """SELECT c.id_compte, u.prenom, u.nom,
                      verify_password(%s, c.password_hash) AS ok, c.statut
                 FROM comptes c JOIN utilisateurs u ON u.id_user = c.id_user
                WHERE lower(c.email) = lower(%s)""",
            (body.password, body.email),
        ).fetchone()
    if not row or not row["ok"]:
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    if row["statut"] != "ACTIVE":
        raise HTTPException(status_code=403, detail="Compte non actif")
    name = f"{row['prenom']} {row['nom']}"
    return {"token": make_token(row["id_compte"], name), "name": name}


@app.get("/api/account")
def account(user: dict = Depends(require_user)):
    me = user["id_compte"]
    with pool.connection() as conn:
        profil = conn.execute(
            "SELECT u.prenom, u.nom, c.email FROM comptes c JOIN utilisateurs u ON u.id_user = c.id_user WHERE c.id_compte = %s",
            (me,),
        ).fetchone()
        if not profil:
            raise HTTPException(status_code=404, detail="Compte introuvable")
        commandes = conn.execute(
            """SELECT reference, montant, devise, statut, ville, created_at
                 FROM commandes WHERE id_compte = %s ORDER BY created_at DESC LIMIT 50""",
            (me,),
        ).fetchall()
        cartes = conn.execute(
            """SELECT ca.card_last4, ca.actif, ca.creation_carte
                 FROM cartes ca JOIN comptes_bancaires cb ON cb.id_compte_bancaire = ca.id_compte_bancaire
                WHERE cb.id_compte = %s ORDER BY ca.creation_carte DESC""",
            (me,),
        ).fetchall()
    return jsonable_encoder({"profil": profil, "commandes": commandes, "cartes": cartes})


@app.get("/")
def home():
    return FileResponse(os.path.join(HERE, "static", "index.html"))


@app.get("/api/products")
def products():
    return {"products": PRODUCTS, "weights": {k: str(v) for k, v in WEIGHTS.items()}}


@app.post("/api/checkout")
async def checkout(request: Request, user: dict | None = Depends(optional_user)):
    body = await request.json()
    items = body.get("items", [])
    customer = body.get("customer", {})
    card = body.get("card", {})
    save_card = bool(body.get("save_card"))

    # Recalcul du total côté serveur (on ne fait jamais confiance au client)
    total = Decimal("0")
    summary = []
    for it in items:
        p = BY_ID.get(it.get("id"))
        if not p:
            return JSONResponse({"status": "error", "message": "Produit inconnu"}, status_code=400)
        qty = max(1, min(20, int(it.get("qty", 1))))
        weight = it.get("weight", "250g") if not p.get("no_weight") else "250g"
        mult = WEIGHTS.get(weight, Decimal("1"))
        line = (Decimal(str(p["price"])) * mult * qty).quantize(Decimal("0.01"))
        total += line
        summary.append(f'{p["name"]} x{qty} ({weight})')
    if total <= 0:
        return JSONResponse({"status": "error", "message": "Panier vide"}, status_code=400)

    order_ref = "CMD-" + os.urandom(3).hex().upper()
    payload = {
        "amount": str(total), "currency": "EUR", "order_ref": order_ref,
        "customer_name": str(customer.get("name", ""))[:140],
        "customer_email": str(customer.get("email", ""))[:255],
        "adresse": str(customer.get("address", ""))[:400],
        "code_postal": str(customer.get("zip", ""))[:20],
        "ville": str(customer.get("city", ""))[:140],
        "id_compte": user["id_compte"] if user else None,
        "card": {
            "number": str(card.get("number", "")),
            "exp_month": int(card.get("exp_month", 0) or 0),
            "exp_year": int(card.get("exp_year", 0) or 0),
            "cvv": str(card.get("cvv", "")),
            "holder": str(card.get("holder", ""))[:140],
        },
    }
    # Transmission à PayPoc (via le WAF). La boutique ne conserve rien de la carte.
    try:
        with httpx.Client(base_url=PAYPOC_API_BASE, timeout=10.0) as c:
            r = c.post("/charge", headers={"X-Api-Key": MERCHANT_API_KEY}, json=payload)
        data = r.json()
    except (httpx.HTTPError, ValueError):
        return JSONResponse({"status": "error", "message": "Paiement indisponible (PayPoc injoignable)"}, status_code=502)

    if r.status_code == 422:
        return JSONResponse({"status": "invalid", "reason": data.get("detail", "carte invalide")}, status_code=422)
    if r.status_code >= 500:
        return JSONResponse({"status": "error", "message": "Banque injoignable, réessayez"}, status_code=502)

    # Enregistrement de la carte sur le compte client (si connecté, demandé et paiement accepté).
    # On ne stocke jamais le PAN en clair ni le CVV : ajouter_carte hache le numéro et ne garde que last4 + token.
    data["card_saved"] = False
    if user and save_card and data.get("status") == "approved":
        number = re.sub(r"\s+", "", str(card.get("number", "")))
        last4 = number[-4:]
        mm = int(card.get("exp_month", 0) or 0)
        yy = int(card.get("exp_year", 0) or 0) % 100
        if re.fullmatch(r"[0-9]{12,19}", number) and 1 <= mm <= 12:
            try:
                with pool.connection() as conn:
                    wallet = wallet_of(conn, user["id_compte"])
                    exists = conn.execute(
                        "SELECT 1 FROM cartes WHERE id_compte_bancaire = %s AND card_last4 = %s",
                        (wallet, last4),
                    ).fetchone()
                    if not exists:
                        conn.execute(
                            "SELECT ajouter_carte(%s, %s, %s, %s, %s)",
                            (wallet, "tok_" + secrets.token_hex(8), number,
                             str(card.get("holder", ""))[:150] or "CARTE", f"{mm:02d}/{yy:02d}"),
                        )
                    data["card_saved"] = True
            except Exception:
                data["card_saved"] = False

    data["order_ref"] = order_ref
    data["total"] = str(total)
    data["summary"] = summary
    data["logged_in"] = bool(user)
    return JSONResponse(data, status_code=200)


@app.get("/api/order/{payment_id}")
def order_status(payment_id: str):
    """Statut d'un paiement (utilisé par la boutique pour suivre une validation 3DS en attente)."""
    try:
        with httpx.Client(base_url=PAYPOC_API_BASE, timeout=8.0) as c:
            r = c.get(f"/payments/{payment_id}", headers={"X-Api-Key": MERCHANT_API_KEY})
        if r.status_code != 200:
            return JSONResponse({"statut": "unknown"}, status_code=r.status_code)
        d = r.json()
        return {"statut": d.get("statut"), "reference_banque": d.get("reference_banque")}
    except (httpx.HTTPError, ValueError):
        return JSONResponse({"statut": "error"}, status_code=502)
