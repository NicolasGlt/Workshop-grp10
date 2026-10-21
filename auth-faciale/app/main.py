"""Application d'authentification du back-office (consigne additionnelle 1).

Lancement (depuis la racine du dossier) :
    .venv\\Scripts\\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
Écoute sur 127.0.0.1 seulement : le back-office n'est pas exposé sur le point d'accès.
"""
import threading
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, db, led
from .camera import camera

STATIC = config.ROOT / "app" / "static"


@asynccontextmanager
async def lifespan(_app):
    led.send("off")                               # LED éteinte par défaut
    threading.Thread(target=camera.warm_up, daemon=True).start()
    yield
    camera.off()


app = FastAPI(title="Back-office, authentification renforcée", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=config.SESSION_SECRET,
                   same_site="strict", max_age=8 * 3600)


# --- session --------------------------------------------------------------------------

def current_user(request: Request):
    user_id = request.session.get("user_id")
    user = db.get_user_by_id(user_id) if user_id else None
    if not user or not user["backoffice_enabled"]:
        return None
    if time.time() < request.session.get("ready_at", 0):
        return None
    return user


def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(401, "authentification requise")
    return user


def require_admin(request: Request):
    user = require_user(request)
    if user["role"] != "admin":
        raise HTTPException(403, "réservé aux administrateurs")
    return user


# --- pages ------------------------------------------------------------------------------

def _page(name):
    path = STATIC / name
    if not path.exists():
        raise HTTPException(404, f"page {name} pas encore écrite")
    return FileResponse(path)


@app.get("/")
def page_login():
    return _page("login.html")


@app.get("/backoffice")
def page_backoffice(request: Request):
    return _page("backoffice.html") if current_user(request) else RedirectResponse("/")


@app.get("/admin")
def page_admin(request: Request):
    user = current_user(request)
    if not user or user["role"] != "admin":
        return RedirectResponse("/")
    return _page("admin.html")


@app.get("/monitor")
def page_monitor():
    """Moniteur de test : état du poste + flux caméra (local uniquement, l'app écoute sur 127.0.0.1)."""
    return _page("monitor.html")


@app.get("/camera/stream")
def camera_stream():
    if not camera.is_on:
        raise HTTPException(404, "caméra éteinte")
    return StreamingResponse(camera.mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame")


# --- authentification -------------------------------------------------------------------

class IdentifyIn(BaseModel):
    username: str


class PasswordIn(BaseModel):
    login_id: str
    password: str


@app.post("/api/identify")
def api_identify(body: IdentifyIn):
    payload, code = auth.identify(body.username)
    return JSONResponse(payload, status_code=code)


@app.post("/api/password")
def api_password(body: PasswordIn, request: Request):
    payload, code, user = auth.password(body.login_id, body.password)
    if user:
        request.session.clear()
        request.session.update({"user_id": user["id"],
                                "ready_at": time.time() + config.BACKOFFICE_DELAY_S})
    return JSONResponse(payload, status_code=code)


@app.post("/api/logout")
def api_logout(request: Request):
    request.session.clear()
    return {"status": "ok"}


@app.get("/api/me")
def api_me(request: Request):
    user = require_user(request)
    return {"username": user["username"], "role": user["role"]}


# --- back-office du SI de paiement (lecture seule, rôle backoffice en base) -------------
# Habilitations : lecteur = indicateurs et liens, operateur = + transactions et journal
# sécurité, admin = + gestion des habilitations.

def require_role(request: Request, *roles):
    user = require_user(request)
    if user["role"] not in roles:
        raise HTTPException(403, "habilitation insuffisante")
    return user


@app.get("/api/si/summary")
def si_summary(request: Request):
    require_user(request)
    summary = db.si_summary()
    summary["merchants"] = db.si_merchants()
    summary["links"] = {"grafana": config.GRAFANA_URL, "pgadmin": config.PGADMIN_URL,
                        "shop": config.SHOP_URL}
    return summary


@app.get("/api/si/transactions")
def si_transactions(request: Request):
    require_role(request, "operateur", "admin")
    return db.si_transactions()


@app.get("/api/si/security")
def si_security(request: Request):
    require_role(request, "operateur", "admin")
    return db.si_security_logs()


@app.get("/api/state")
def api_state():
    return auth.kiosk.snapshot()


@app.get("/api/health")
def api_health():
    try:
        database = db.ping()
    except Exception:
        database = False
    return {"camera_on": camera.is_on, "camera_index": config.CAM_INDEX,
            "led": led.health(), "database": database, "kiosk": auth.kiosk.snapshot()["state"]}


# --- habilitations (rôle admin) -------------------------------------------------------

class UserIn(BaseModel):
    username: str
    password: str
    role: str = "lecteur"
    backoffice_enabled: bool = True


class UserPatch(BaseModel):
    role: Optional[str] = None
    backoffice_enabled: Optional[bool] = None
    password: Optional[str] = None


ROLES = {"admin", "operateur", "lecteur"}


@app.get("/api/admin/users")
def admin_users(request: Request):
    require_admin(request)
    return db.list_users()


@app.post("/api/admin/users")
def admin_create_user(body: UserIn, request: Request):
    admin = require_admin(request)
    username = auth.normalize(body.username)
    if not username or body.role not in ROLES or len(body.password) < 8:
        raise HTTPException(400, "identifiant vide, rôle inconnu ou mot de passe < 8 caractères")
    if db.get_user(username):
        raise HTTPException(409, "identifiant déjà utilisé")
    user_id = db.create_user(username, auth.hash_password(body.password), body.role, body.backoffice_enabled)
    db.event(admin["username"], "user_created", detail=username)
    return {"id": user_id}


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, body: UserPatch, request: Request):
    admin = require_admin(request)
    target = db.get_user_by_id(user_id) or {}
    if not target:
        raise HTTPException(404, "utilisateur inconnu")
    if body.role is not None and body.role not in ROLES:
        raise HTTPException(400, "rôle inconnu")
    if body.password is not None and len(body.password) < 8:
        raise HTTPException(400, "mot de passe < 8 caractères")
    if user_id == admin["id"] and (body.role not in (None, "admin") or body.backoffice_enabled is False):
        raise HTTPException(400, "un admin ne peut pas retirer ses propres droits")
    db.update_user(user_id, role=body.role,
                   backoffice_enabled=None if body.backoffice_enabled is None else int(body.backoffice_enabled),
                   password_hash=auth.hash_password(body.password) if body.password else None)
    db.event(admin["username"], "user_updated", detail=target["username"])
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, request: Request):
    admin = require_admin(request)
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "utilisateur inconnu")
    if user_id == admin["id"]:
        raise HTTPException(400, "un admin ne peut pas se supprimer lui-même")
    db.delete_user(user_id)
    db.event(admin["username"], "user_deleted", detail=target["username"])
    return {"status": "ok"}


@app.post("/api/admin/users/{user_id}/face")
def admin_enroll(user_id: int, request: Request):
    admin = require_admin(request)
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "utilisateur inconnu")
    payload, code = auth.enroll(user_id, created_by=admin["id"])
    db.event(admin["username"], "face_enrolled" if code == 200 else "face_enroll_failed",
             detail=target["username"])
    return JSONResponse(payload, status_code=code)


@app.delete("/api/admin/users/{user_id}/face")
def admin_delete_face(user_id: int, request: Request):
    admin = require_admin(request)
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "utilisateur inconnu")
    db.delete_templates(user_id)
    db.event(admin["username"], "face_deleted", detail=target["username"])
    return {"status": "ok"}


@app.post("/api/admin/users/{user_id}/unlock")
def admin_unlock(user_id: int, request: Request):
    admin = require_admin(request)
    target = db.get_user_by_id(user_id)
    if not target:
        raise HTTPException(404, "utilisateur inconnu")
    db.reset_failures(target["username"])
    db.event(admin["username"], "user_unlocked", detail=target["username"])
    return {"status": "ok"}


@app.post("/api/admin/led/test")
def admin_led_test(request: Request):
    require_admin(request)

    def run():
        for mode, pause in (("green_blink", 3), ("red_blink10", 6), ("off", 0)):
            led.send(mode)
            time.sleep(pause)
    threading.Thread(target=run, daemon=True).start()
    return {"status": "ok"}


@app.get("/api/admin/events")
def admin_events(request: Request):
    require_admin(request)
    return db.events()
