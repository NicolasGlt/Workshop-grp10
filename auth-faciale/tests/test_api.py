"""Routes d'installation et d'enrôlement, base et caméra simulées (application sans lifespan)."""
import pytest
from fastapi.testclient import TestClient

from app import auth, enroll, face, main
from conftest import FakeDetect, script, wait_end, wait_idle

ALL = ["face", "left", "right", "up", "down"]
SETUP = {"username": "Admin", "password": "motdepasse", "confirm": "motdepasse"}


def client(host="127.0.0.1"):
    return TestClient(main.app, client=(host, 50000), follow_redirects=False)


@pytest.fixture
def faces(monkeypatch, fake_cam):
    def play(*keys):
        monkeypatch.setattr(face, "detect", FakeDetect(script(*keys)))
    return play


def poll(c):
    return wait_end(lambda: c.get("/api/enroll/state").json())


def test_racine_redirige_vers_setup_si_aucun_compte(fake_db):
    r = client().get("/")
    assert r.status_code in (302, 307) and r.headers["location"] == "/setup"


def test_setup_refuse_hors_boucle_locale(fake_db):
    for host in ("192.168.137.12", "10.0.0.5", "testclient"):
        c = client(host)
        assert c.get("/setup").status_code == 403
        assert c.post("/api/setup/start", json=SETUP).status_code == 403
    assert client("::1").get("/setup").status_code == 200
    assert client("127.0.0.2").get("/setup").status_code == 200


@pytest.mark.parametrize("body,detail", [
    ({**SETUP, "username": "  "}, "identifiant"),
    ({**SETUP, "password": "court", "confirm": "court"}, "8"),
    ({**SETUP, "confirm": "autrechose"}, "confirmation"),
])
def test_setup_validation(fake_db, body, detail):
    r = client().post("/api/setup/start", json=body)
    assert r.status_code == 400 and detail in r.json()["detail"]


def test_setup_complet_puis_ferme(fake_db, faces):
    faces(*ALL)
    c = client()
    assert c.get("/setup").status_code == 200
    r = c.post("/api/setup/start", json=SETUP)
    assert r.status_code == 202
    s = poll(c)
    assert s["status"] == "done" and s["captured"] == 5 and s["result"]["username"] == "admin"
    user = fake_db.get_user("admin")
    assert user["role"] == "admin" and auth.check_password("motdepasse", user["password_hash"])
    assert len(fake_db.templates[user["id"]]) == 5
    assert "setup_admin_created" in fake_db.names()
    assert wait_idle() == "idle"
    # fermé définitivement
    r = c.get("/setup")
    assert r.status_code in (302, 307) and r.headers["location"] == "/"
    assert c.post("/api/setup/start", json=SETUP).status_code == 404
    assert c.get("/").status_code == 200                 # page de connexion


def test_setup_ferme_si_un_compte_existe(fake_db):
    fake_db.create_user("bob", auth.hash_password("motdepasse"), "lecteur")
    c = client()
    assert c.get("/setup").headers["location"] == "/"
    assert c.post("/api/setup/start", json=SETUP).status_code == 404


def test_setup_course_un_compte_cree_pendant_l_enrolement(fake_db, faces):
    faces(*ALL)
    c = client()
    original = fake_db.create_first_admin

    def concurrent(*args):
        fake_db.create_user("intrus", "x", "admin")      # compte créé entre le début et la fin
        return original(*args)
    fake_db.create_first_admin = concurrent
    main.db.create_first_admin = concurrent
    assert c.post("/api/setup/start", json=SETUP).status_code == 202
    s = poll(c)
    assert s["status"] == "failed" and "installation fermée" in s["error"]
    assert fake_db.get_user("admin") is None
    assert "setup_admin_created" not in fake_db.names()


def test_etat_reserve_a_la_page_qui_a_lance(fake_db, faces):
    faces(*ALL)
    c = client()
    assert c.post("/api/setup/start", json=SETUP).status_code == 202
    assert client().get("/api/enroll/state").status_code == 404     # autre navigateur, sans le cookie
    assert poll(c)["status"] == "done"


def test_echec_puis_recommencer(fake_db, faces, monkeypatch):
    monkeypatch.setattr(enroll.config, "ENROLL_ANGLE_TIMEOUT_S", 0.3)
    faces("face", "left")                                  # s'arrête avant « droite »
    c = client()
    assert c.post("/api/setup/start", json=SETUP).status_code == 202
    s = poll(c)
    assert s["status"] == "failed" and "droite" in s["error"] and s["captured"] == 2
    assert fake_db.count_users() == 0 and "face_enroll_failed" in fake_db.names()
    assert wait_idle() == "idle"
    faces(*ALL)
    assert c.post("/api/setup/start", json=SETUP).status_code == 202
    assert poll(c)["status"] == "done" and fake_db.count_users() == 1


def test_connexion_occupee_pendant_l_enrolement(fake_db, faces, monkeypatch):
    monkeypatch.setattr(enroll.config, "ENROLL_ANGLE_TIMEOUT_S", 2)
    faces()                                                # aucun visage : l'enrôlement attend
    c = client()
    assert c.post("/api/setup/start", json=SETUP).status_code == 202
    r = c.post("/api/identify", json={"username": "x"})
    assert r.status_code == 409 and r.json()["state"] == "enrolling"
    assert c.post("/api/setup/start", json=SETUP).status_code == 409
    assert c.post("/api/enroll/cancel").status_code == 200
    assert poll(c)["status"] == "cancelled"
    assert wait_idle() == "idle"


def test_enrolement_depuis_admin(fake_db, faces, monkeypatch):
    admin_id = fake_db.create_user("admin", "h", "admin")
    target = fake_db.create_user("carla", "h", "lecteur")
    monkeypatch.setattr(main, "require_admin", lambda request: fake_db.get_user_by_id(admin_id))
    faces(*ALL)
    c = client()
    assert c.post("/api/admin/users/999/face").status_code == 404
    assert c.post(f"/api/admin/users/{target}/face").status_code == 202
    s = poll(c)
    assert s["status"] == "done" and s["target"] == "carla"
    assert len(fake_db.templates[target]) == 5
    assert ("admin", "face_enrolled", "carla : 5 angles") in fake_db.events
