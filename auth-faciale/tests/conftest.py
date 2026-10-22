"""Tests sans caméra ni PostgreSQL : caméra, détection et base sont simulées.
Lancement (depuis auth-faciale/) : uv run --with-requirements requirements.txt --with pytest pytest -q
"""
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, config, db, enroll, face   # noqa: E402

HOLD = config.ENROLL_HOLD_FRAMES


def row(yaw=0.0, pitch=0.55, size=200.0, cx=320.0, cy=240.0):
    """Visage au format YuNet (x, y, w, h, 5 points, score) construit à partir d'un lacet et d'un tangage."""
    iod = 0.4 * size                       # écart entre les yeux
    mouth = 0.9 * iod                      # distance yeux-bouche
    return np.array([cx - size / 2, cy - size / 2, size, size * 1.2,
                     cx - iod / 2, cy, cx + iod / 2, cy,                   # yeux
                     cx + yaw * iod, cy + pitch * mouth,                   # nez
                     cx - 0.3 * iod, cy + mouth, cx + 0.3 * iod, cy + mouth,   # coins de la bouche
                     0.95], np.float32)


# Une pose franche par angle (sens ENROLL_YAW_SIGN = 1)
POSES = {"face": row(), "left": row(yaw=0.30), "right": row(yaw=-0.30),
         "up": row(pitch=0.40), "down": row(pitch=0.72)}


def script(*keys, hold=HOLD):
    """Suite de détections : `hold` images par angle demandé."""
    return [(POSES[k], 1) for k in keys for _ in range(hold)]


class FakeCamera:
    def __init__(self):
        self.is_on, self.opened = False, 0

    def on(self):
        self.is_on, self.opened = True, self.opened + 1

    def off(self):
        self.is_on = False

    def next_frame(self, last_seq=-1, timeout=2.0):
        time.sleep(0.002)
        return last_seq + 1, np.zeros((480, 640, 3), np.uint8)


class FakeDetect:
    """Rejoue une liste de (visage, nombre) ; ensuite `then` (par défaut, plus aucun visage)."""
    def __init__(self, items, then=(None, 0)):
        self.items, self.then = list(items), then

    def __call__(self, frame):
        return self.items.pop(0) if self.items else self.then


def fake_embed(frame, face_row):
    return np.full((1, 128), float(face_row[8]), np.float32)


class FakeDB:
    def __init__(self):
        self.users, self.templates, self.events, self.next_id = {}, {}, [], 1

    def count_users(self):
        return len(self.users)

    def create_first_admin(self, username, password_hash, embeddings):
        if self.users:
            return None
        user_id = self.create_user(username, password_hash, "admin")
        self.templates[user_id] = list(embeddings)
        return user_id

    def create_user(self, username, password_hash, role="lecteur", backoffice_enabled=True):
        user_id, self.next_id = self.next_id, self.next_id + 1
        self.users[user_id] = {"id": user_id, "username": username, "password_hash": password_hash,
                               "role": role, "backoffice_enabled": int(backoffice_enabled)}
        return user_id

    def get_user(self, username):
        return next((u for u in self.users.values() if u["username"] == username), None)

    def get_user_by_id(self, user_id):
        return self.users.get(user_id)

    def replace_templates(self, user_id, embeddings, created_by=None):
        self.templates[user_id] = list(embeddings)

    def event(self, username, name, score=None, detail=None):
        self.events.append((username, name, detail))

    def lock_remaining(self, username):
        return 0

    def names(self):
        return [e[1] for e in self.events]


@pytest.fixture
def fake_db(monkeypatch):
    fake = FakeDB()
    for name in ("count_users", "create_first_admin", "create_user", "get_user", "get_user_by_id",
                 "replace_templates", "event", "lock_remaining"):
        monkeypatch.setattr(db, name, getattr(fake, name))
    return fake


@pytest.fixture
def fake_cam(monkeypatch):
    cam = FakeCamera()
    monkeypatch.setattr(enroll, "camera", cam)
    monkeypatch.setattr(face, "embed_face", fake_embed)
    return cam


@pytest.fixture(autouse=True)
def idle_kiosk():
    with auth.kiosk.lock:
        auth.kiosk._to_idle()
    yield
    with auth.kiosk.lock:
        auth.kiosk._to_idle()


def wait_end(get_state, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        s = get_state()
        if s["status"] in ("done", "failed", "cancelled"):
            return s
        time.sleep(0.02)
    raise AssertionError("enrôlement jamais terminé")


def wait_idle(timeout=2.0):
    end = time.time() + timeout
    while time.time() < end and auth.kiosk.snapshot()["state"] != "idle":
        time.sleep(0.01)
    return auth.kiosk.snapshot()["state"]


__all__ = ["row", "POSES", "script", "FakeCamera", "FakeDetect", "fake_embed", "wait_end", "wait_idle",
           "threading"]
