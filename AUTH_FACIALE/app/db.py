"""Base SQLite : utilisateurs, gabarits de visage, compteurs d'échecs, journal."""
import json
import sqlite3
import threading
import time

from . import config, face

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'lecteur' CHECK (role IN ('admin','operateur','lecteur')),
  backoffice_enabled INTEGER NOT NULL DEFAULT 1,
  created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS face_templates (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  embedding BLOB NOT NULL,
  created_at REAL NOT NULL,
  created_by INTEGER REFERENCES users(id));
CREATE TABLE IF NOT EXISTS login_lockouts (
  username TEXT PRIMARY KEY,          -- identifiant SAISI : marche aussi pour les inconnus
  failures INTEGER NOT NULL DEFAULT 0,
  locked_until REAL);
CREATE TABLE IF NOT EXISTS auth_events (
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  username TEXT, event TEXT, score REAL, detail TEXT);
"""

_lock = threading.Lock()
_con = sqlite3.connect(config.DB_PATH, check_same_thread=False, isolation_level=None)
_con.row_factory = sqlite3.Row
_con.execute("PRAGMA foreign_keys = ON")
_con.executescript(SCHEMA)


def _all(sql, args=()):
    with _lock:
        return [dict(r) for r in _con.execute(sql, args).fetchall()]


def _one(sql, args=()):
    rows = _all(sql, args)
    return rows[0] if rows else None


def _exec(sql, args=()):
    with _lock:
        return _con.execute(sql, args).lastrowid


# --- utilisateurs ---------------------------------------------------------------

def get_user(username):
    return _one("SELECT * FROM users WHERE username = ?", (username,))


def get_user_by_id(user_id):
    return _one("SELECT * FROM users WHERE id = ?", (user_id,))


def list_users():
    now = time.time()
    rows = _all("""
        SELECT u.id, u.username, u.role, u.backoffice_enabled, u.created_at,
               COUNT(t.id) AS templates, MAX(t.created_at) AS enrolled_at,
               l.failures, l.locked_until
        FROM users u
        LEFT JOIN face_templates t ON t.user_id = u.id
        LEFT JOIN login_lockouts l ON l.username = u.username
        GROUP BY u.id ORDER BY u.username""")
    for r in rows:
        r["locked_for"] = max(0, int((r["locked_until"] or 0) - now))
    return rows


def create_user(username, password_hash, role="lecteur", backoffice_enabled=True):
    return _exec("INSERT INTO users (username, password_hash, role, backoffice_enabled, created_at) "
                 "VALUES (?, ?, ?, ?, ?)", (username, password_hash, role, int(backoffice_enabled), time.time()))


def update_user(user_id, **fields):
    allowed = {"role", "backoffice_enabled", "password_hash"}
    sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if sets:
        cols = ", ".join(f"{k} = ?" for k in sets)
        _exec(f"UPDATE users SET {cols} WHERE id = ?", (*sets.values(), user_id))


def delete_user(user_id):
    _exec("DELETE FROM users WHERE id = ?", (user_id,))


# --- gabarits ---------------------------------------------------------------------

def templates(user_id):
    return [face.from_blob(r["embedding"])
            for r in _all("SELECT embedding FROM face_templates WHERE user_id = ?", (user_id,))]


def replace_templates(user_id, embeddings, created_by=None):
    now = time.time()
    with _lock:
        _con.execute("BEGIN")
        _con.execute("DELETE FROM face_templates WHERE user_id = ?", (user_id,))
        for emb in embeddings:
            _con.execute("INSERT INTO face_templates (user_id, embedding, created_at, created_by) "
                         "VALUES (?, ?, ?, ?)", (user_id, face.to_blob(emb), now, created_by))
        _con.execute("COMMIT")


def delete_templates(user_id):
    _exec("DELETE FROM face_templates WHERE user_id = ?", (user_id,))


# --- échecs et blocage --------------------------------------------------------------

def lock_remaining(username):
    row = _one("SELECT locked_until FROM login_lockouts WHERE username = ?", (username,))
    return max(0, int((row["locked_until"] or 0) - time.time())) if row else 0


def record_failure(username):
    """+1 échec. Au MAX_FAILURES-ième : blocage LOCK_S secondes et compteur remis à zéro.
    Renvoie la durée de blocage (0 si pas bloqué)."""
    row = _one("SELECT failures FROM login_lockouts WHERE username = ?", (username,))
    failures = (row["failures"] if row else 0) + 1
    locked_until = None
    if failures >= config.MAX_FAILURES:
        failures, locked_until = 0, time.time() + config.LOCK_S
    _exec("""INSERT INTO login_lockouts (username, failures, locked_until) VALUES (?, ?, ?)
             ON CONFLICT(username) DO UPDATE SET failures = excluded.failures,
             locked_until = COALESCE(excluded.locked_until, login_lockouts.locked_until)""",
          (username, failures, locked_until))
    return config.LOCK_S if locked_until else 0


def reset_failures(username):
    _exec("DELETE FROM login_lockouts WHERE username = ?", (username,))


def failures(username):
    row = _one("SELECT failures FROM login_lockouts WHERE username = ?", (username,))
    return row["failures"] if row else 0


# --- journal ------------------------------------------------------------------------

def event(username, name, score=None, detail=None):
    """Journal en base + une ligne JSON sur la sortie standard (ramassable par Loki)."""
    ts = time.time()
    _exec("INSERT INTO auth_events (ts, username, event, score, detail) VALUES (?, ?, ?, ?, ?)",
          (ts, username, name, score, detail))
    print(json.dumps({"ts": ts, "username": username, "event": name, "score": score,
                      "detail": detail}, ensure_ascii=False), flush=True)


def events(limit=50):
    return _all("SELECT * FROM auth_events ORDER BY id DESC LIMIT ?", (limit,))
