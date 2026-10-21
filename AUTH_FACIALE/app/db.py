"""Base du back-office : schéma `backoffice` du PostgreSQL du SI (POC).

Utilisateurs, gabarits de visage, compteurs d'échecs et journal vivent dans le schéma
`backoffice`, propriété du rôle `backoffice` (créé par poc-resilience/db/init/05-backoffice.sh).
Ce rôle ne fait que LIRE le métier (transactions, commandes, marchands sans clé API).
"""
import json
import threading
import time

import psycopg
from psycopg.rows import dict_row

from . import config, face

SCHEMA = """
CREATE TABLE IF NOT EXISTS backoffice.users (
  id BIGSERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'lecteur' CHECK (role IN ('admin','operateur','lecteur')),
  backoffice_enabled INTEGER NOT NULL DEFAULT 1,
  created_at DOUBLE PRECISION NOT NULL);
CREATE TABLE IF NOT EXISTS backoffice.face_templates (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT NOT NULL REFERENCES backoffice.users(id) ON DELETE CASCADE,
  embedding BYTEA NOT NULL,
  created_at DOUBLE PRECISION NOT NULL,
  created_by BIGINT REFERENCES backoffice.users(id) ON DELETE SET NULL);
CREATE TABLE IF NOT EXISTS backoffice.login_lockouts (
  username TEXT PRIMARY KEY,          -- identifiant SAISI : marche aussi pour les inconnus
  failures INTEGER NOT NULL DEFAULT 0,
  locked_until DOUBLE PRECISION);
CREATE TABLE IF NOT EXISTS backoffice.auth_events (
  id BIGSERIAL PRIMARY KEY,
  ts DOUBLE PRECISION NOT NULL,
  username TEXT, event TEXT, score DOUBLE PRECISION, detail TEXT);
"""

_lock = threading.Lock()
_con = None


def _connect():
    con = psycopg.connect(config.DATABASE_URL, autocommit=True, row_factory=dict_row,
                          options="-c search_path=backoffice")
    con.execute(SCHEMA)
    return con


def _run(fn):
    """Exécute fn(connexion) ; reconnecte une fois si la base a redémarré."""
    global _con
    with _lock:
        for attempt in (1, 2):
            try:
                if _con is None or _con.closed:
                    _con = _connect()
                return fn(_con)
            except psycopg.OperationalError:
                _con = None
                if attempt == 2:
                    raise


def _all(sql, args=()):
    return _run(lambda c: c.execute(sql, args).fetchall())


def _one(sql, args=()):
    rows = _all(sql, args)
    return rows[0] if rows else None


def _exec(sql, args=()):
    def go(c):
        cur = c.execute(sql, args)
        return cur.fetchone()["id"] if cur.description else None
    return _run(go)


def ping():
    return _one("SELECT 1 AS ok") is not None


# --- utilisateurs ---------------------------------------------------------------

def get_user(username):
    return _one("SELECT * FROM users WHERE username = %s", (username,))


def get_user_by_id(user_id):
    return _one("SELECT * FROM users WHERE id = %s", (user_id,))


def list_users():
    now = time.time()
    rows = _all("""
        SELECT u.id, u.username, u.role, u.backoffice_enabled, u.created_at,
               COUNT(t.id) AS templates, MAX(t.created_at) AS enrolled_at,
               l.failures, l.locked_until
        FROM users u
        LEFT JOIN face_templates t ON t.user_id = u.id
        LEFT JOIN login_lockouts l ON l.username = u.username
        GROUP BY u.id, l.failures, l.locked_until ORDER BY u.username""")
    for r in rows:
        r["locked_for"] = max(0, int((r["locked_until"] or 0) - now))
    return rows


def create_user(username, password_hash, role="lecteur", backoffice_enabled=True):
    return _exec("INSERT INTO users (username, password_hash, role, backoffice_enabled, created_at) "
                 "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                 (username, password_hash, role, int(backoffice_enabled), time.time()))


def update_user(user_id, **fields):
    allowed = {"role", "backoffice_enabled", "password_hash"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if sets:
        cols = ", ".join(f"{k} = %s" for k in sets)
        _exec(f"UPDATE users SET {cols} WHERE id = %s", (*sets.values(), user_id))


def delete_user(user_id):
    _exec("DELETE FROM users WHERE id = %s", (user_id,))


# --- gabarits ---------------------------------------------------------------------

def templates(user_id):
    return [face.from_blob(bytes(r["embedding"]))
            for r in _all("SELECT embedding FROM face_templates WHERE user_id = %s", (user_id,))]


def replace_templates(user_id, embeddings, created_by=None):
    now = time.time()

    def go(c):
        with c.transaction():
            c.execute("DELETE FROM face_templates WHERE user_id = %s", (user_id,))
            for emb in embeddings:
                c.execute("INSERT INTO face_templates (user_id, embedding, created_at, created_by) "
                          "VALUES (%s, %s, %s, %s)", (user_id, face.to_blob(emb), now, created_by))
    _run(go)


def delete_templates(user_id):
    _exec("DELETE FROM face_templates WHERE user_id = %s", (user_id,))


# --- échecs et blocage --------------------------------------------------------------

def lock_remaining(username):
    row = _one("SELECT locked_until FROM login_lockouts WHERE username = %s", (username,))
    return max(0, int((row["locked_until"] or 0) - time.time())) if row else 0


def record_failure(username):
    """+1 échec. Au MAX_FAILURES-ième : blocage LOCK_S secondes et compteur remis à zéro.
    Renvoie la durée de blocage (0 si pas bloqué)."""
    row = _one("SELECT failures FROM login_lockouts WHERE username = %s", (username,))
    failures = (row["failures"] if row else 0) + 1
    locked_until = None
    if failures >= config.MAX_FAILURES:
        failures, locked_until = 0, time.time() + config.LOCK_S
    _exec("""INSERT INTO login_lockouts (username, failures, locked_until) VALUES (%s, %s, %s)
             ON CONFLICT(username) DO UPDATE SET failures = excluded.failures,
             locked_until = COALESCE(excluded.locked_until, login_lockouts.locked_until)""",
          (username, failures, locked_until))
    return config.LOCK_S if locked_until else 0


def reset_failures(username):
    _exec("DELETE FROM login_lockouts WHERE username = %s", (username,))


def failures(username):
    row = _one("SELECT failures FROM login_lockouts WHERE username = %s", (username,))
    return row["failures"] if row else 0


# --- journal ------------------------------------------------------------------------

def event(username, name, score=None, detail=None):
    """Journal en base + une ligne JSON sur la sortie standard (ramassable par Loki)."""
    ts = time.time()
    _exec("INSERT INTO auth_events (ts, username, event, score, detail) VALUES (%s, %s, %s, %s, %s)",
          (ts, username, name, score, detail))
    print(json.dumps({"ts": ts, "username": username, "event": name, "score": score,
                      "detail": detail}, ensure_ascii=False), flush=True)


def events(limit=50):
    return _all("SELECT * FROM auth_events ORDER BY id DESC LIMIT %s", (limit,))


# --- données du SI (lecture seule) ---------------------------------------------------

def si_summary():
    """Indicateurs de paiement des dernières 24 h, lus dans le métier."""
    return _one("""
        SELECT COUNT(*)                                          AS total,
               COUNT(*) FILTER (WHERE statut = 'COMPLETED')      AS completed,
               COUNT(*) FILTER (WHERE statut = 'REJECTED')       AS rejected,
               COUNT(*) FILTER (WHERE statut = 'PENDING')        AS pending,
               COALESCE(SUM(montant) FILTER (WHERE statut = 'COMPLETED'), 0) AS volume
        FROM public.transactions
        WHERE date_transaction > now() - interval '24 hours'""")


def si_transactions(limit=25):
    return _all("""
        SELECT id_transaction, montant, devise, statut, reference_banque, description, date_transaction
        FROM public.transactions ORDER BY date_transaction DESC LIMIT %s""", (limit,))


def si_merchants():
    return _all("SELECT id_merchant, name, created_at FROM public.merchants ORDER BY name")


def si_security_logs(limit=25):
    return _all("""
        SELECT type_event, niveau, adresse_ip, description, date_log
        FROM public.logs ORDER BY date_log DESC LIMIT %s""", (limit,))
