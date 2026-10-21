"""Machine à états du poste de connexion (un seul poste, une seule caméra).

    idle ──identify──> verifying ──reconnu──> wait_password ──mot de passe──> idle
                                 └─non reconnu─> cooldown (30 s, caméra allumée) ──> idle

Chaque phrase de la consigne correspond à une transition, voir PLAN.md section 4.
"""
import hashlib
import hmac
import secrets
import threading
import time

import bcrypt

from . import config, db, face, led
from .camera import camera


class Kiosk:
    def __init__(self):
        self.lock = threading.Lock()
        self.state = "idle"
        self.until = 0.0          # fin de l'état courant (cooldown, wait_password)
        self.login = None         # {"id", "user_id", "username"} pendant wait_password
        self._gen = 0             # invalide les minuteries d'un état périmé

    def _schedule(self, delay, fn):
        self._gen += 1
        gen = self._gen
        timer = threading.Timer(delay, lambda: fn(gen))
        timer.daemon = True
        timer.start()

    def _to_idle(self):
        self.state, self.until, self.login = "idle", 0.0, None
        self._gen += 1

    def snapshot(self):
        with self.lock:
            return {"state": self.state, "remaining": max(0, round(self.until - time.time(), 1)),
                    "camera": camera.is_on}


kiosk = Kiosk()


def normalize(username):
    return (username or "").strip().lower()


def _anon(username):
    """Identifiant inconnu : jamais stocké en clair, ce peut être un mot de passe tapé dans le mauvais
    champ (incident du 2026-10-20). Empreinte HMAC avec le secret de session : non réversible, mais
    elle change à chaque redémarrage (les compteurs des identifiants inconnus repartent alors à zéro)."""
    digest = hmac.new(config.SESSION_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    return "inconnu-" + digest[:12]


def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password, password_hash):
    return bcrypt.checkpw((password or "").encode(), password_hash.encode())


def _end_cooldown(gen):
    with kiosk.lock:
        if gen == kiosk._gen and kiosk.state == "cooldown":
            camera.off()                      # « rouge fixe 30 s avant que la caméra ne s'éteigne »
            kiosk._to_idle()


def _expire_login(gen):
    with kiosk.lock:
        if gen != kiosk._gen or kiosk.state != "wait_password":
            return
        username = kiosk.login["username"]
        camera.off()
        led.send("off")
        kiosk._to_idle()
    db.event(username, "password_timeout")


def identify(username):
    """Étape 1 : identifiant saisi -> caméra -> reconnaissance. Renvoie (corps, code HTTP)."""
    username = normalize(username)
    if not username:
        return {"status": "invalid"}, 400
    user = db.get_user(username)
    key = username if user else _anon(username)      # clé du compteur et du journal
    with kiosk.lock:
        if kiosk.state != "idle":
            return {"status": "busy", "state": kiosk.state,
                    "retry_after": max(0, round(kiosk.until - time.time()))}, 409
        locked = db.lock_remaining(key)
        if locked:
            db.event(key, "locked_attempt")
            return {"status": "locked", "retry_after": locked}, 423
        kiosk.state = "verifying"

    try:
        camera.on()
    except RuntimeError as exc:
        with kiosk.lock:
            kiosk._to_idle()
        db.event(key, "camera_error", detail=str(exc))
        return {"status": "camera_error"}, 503

    refs =db.templates(user["id"]) if user and user["backoffice_enabled"] else []
    ok, best = face.verify(camera, refs)

    with kiosk.lock:
        if ok:
            login_id = secrets.token_urlsafe(24)
            kiosk.state, kiosk.until = "wait_password", time.time() + config.PASSWORD_TTL_S
            kiosk.login = {"id": login_id, "user_id": user["id"], "username": username}
            kiosk._schedule(config.PASSWORD_TTL_S, _expire_login)
            led.send("green_blink")
            result = ({"status": "face_ok", "login_id": login_id,
                       "expires_in": config.PASSWORD_TTL_S}, 200)
        else:
            locked_for = db.record_failure(key)
            kiosk.state, kiosk.until = "cooldown", time.time() + config.COOLDOWN_S
            kiosk._schedule(config.COOLDOWN_S, _end_cooldown)
            led.send("red_fixed")
            result = ({"status": "face_ko", "retry_after": config.COOLDOWN_S,
                       "locked_for": locked_for}, 200)
    db.event(key, "face_ok" if ok else "face_ko", score=round(float(best), 3),
             detail=None if user else "identifiant inconnu")
    return result


def password(login_id, password_value):
    """Étape 2 : mot de passe, accepté seulement avec le jeton « visage OK » (usage unique).
    Renvoie (corps, code HTTP, utilisateur si succès)."""
    with kiosk.lock:
        login = kiosk.login
        if kiosk.state != "wait_password" or not login or \
                not hmac.compare_digest(login["id"], login_id or ""):
            return {"status": "invalid"}, 400, None
        kiosk._to_idle()                      # jeton consommé, la phase est terminée dans tous les cas
        camera.off()

    user = db.get_user_by_id(login["user_id"])
    username = login["username"]
    if user and check_password(password_value, user["password_hash"]):
        db.reset_failures(username)
        led.send("green_fixed")
        db.event(username, "login_ok")
        return {"status": "ok", "username": username, "role": user["role"],
                "ready_in": config.BACKOFFICE_DELAY_S}, 200, user

    locked_for = db.record_failure(username)
    led.send("red_blink10")
    db.event(username, "password_ko", detail="bloque" if locked_for else None)
    return {"status": "pwd_ko", "locked_for": locked_for}, 200, None


def enroll(user_id, created_by=None):
    """Enrôlement depuis le back-office : réservé quand le poste est libre."""
    with kiosk.lock:
        if kiosk.state != "idle":
            return {"status": "busy"}, 409
        kiosk.state = "enrolling"
    try:
        camera.on()
        embeddings = face.enroll(camera)
    finally:
        camera.off()
        with kiosk.lock:
            kiosk._to_idle()
    if len(embeddings) < config.ENROLL_SAMPLES:
        return {"status": "failed", "captured": len(embeddings)}, 422
    db.replace_templates(user_id, embeddings, created_by)
    return {"status": "ok", "captured": len(embeddings)}, 200
