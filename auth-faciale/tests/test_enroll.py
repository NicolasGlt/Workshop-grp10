"""Parcours d'enrôlement guidé, caméra et détection simulées."""
import threading

import pytest

from app import auth, config, enroll
from conftest import POSES, FakeCamera, FakeDetect, fake_embed, script, wait_end, wait_idle

ALL = ["face", "left", "right", "up", "down"]


def session(items, on_success=None, on_failure=None, cam=None, then=(None, 0)):
    results = {}

    def ok(embs):
        results["embs"] = embs
        return on_success(embs) if on_success else {"n": len(embs)}

    def ko(reason):
        results["reason"] = reason
        if on_failure:
            on_failure(reason)

    s = enroll.Enrollment("alice", ok, ko, cam=cam or FakeCamera(), detect=FakeDetect(items, then), embed=fake_embed)
    return s, results


def test_cinq_angles_un_gabarit_chacun():
    cam = FakeCamera()
    s, res = session(script(*ALL), cam=cam)
    s.run()
    snap = s.snapshot()
    assert snap["status"] == "done", snap
    assert snap["captured"] == 5 and len(res["embs"]) == 5
    assert all(st["done"] for st in snap["steps"])
    # Un gabarit par angle, dans l'ordre (le faux gabarit porte l'abscisse du nez)
    assert [float(e[0, 0]) for e in res["embs"]] == [float(POSES[k][8]) for k in ALL]
    assert cam.opened == 1 and not cam.is_on            # caméra coupée à la fin


def test_capture_seulement_quand_l_angle_est_tenu(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_ANGLE_TIMEOUT_S", 0.5)
    # face tenue, puis gauche jamais tenue assez longtemps (interrompue par un retour de face)
    items = script("face") + script("left", hold=config.ENROLL_HOLD_FRAMES - 1) + script("face", hold=1) \
        + script("left", hold=config.ENROLL_HOLD_FRAMES - 1)
    s, res = session(items)
    s.run()
    snap = s.snapshot()
    assert snap["status"] == "failed" and snap["captured"] == 1
    assert "gauche" in snap["error"] and "non atteint" in res["reason"]


def test_plusieurs_visages_bloquent_la_capture(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_ANGLE_TIMEOUT_S", 0.3)
    s, _ = session([], then=(POSES["face"], 2))
    s.run()
    snap = s.snapshot()
    assert snap["status"] == "failed" and snap["captured"] == 0
    assert snap["feedback"]["faces"] == 2 and not snap["feedback"]["single"]
    assert "Une seule personne" in snap["feedback"]["message"]


def test_aucun_visage(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_ANGLE_TIMEOUT_S", 0.2)
    s, _ = session([])
    s.run()
    snap = s.snapshot()
    assert snap["status"] == "failed" and snap["feedback"]["face_ok"] is False
    assert "De face" in snap["error"]


def test_annulation(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_ANGLE_TIMEOUT_S", 5)
    s, res = session([])
    t = threading.Thread(target=s.run)
    t.start()
    s.cancel()
    t.join(2)
    assert s.snapshot()["status"] == "cancelled" and res["reason"] == "annulé"


def test_refus_a_l_enregistrement():
    def refuse(_):
        raise enroll.Refused("un compte existe déjà : installation fermée")
    s, _ = session(script(*ALL), on_success=refuse)
    s.run()
    assert s.snapshot()["status"] == "failed"
    assert "installation fermée" in s.snapshot()["error"]


def test_camera_indisponible():
    class Broken(FakeCamera):
        def on(self):
            raise RuntimeError("camera 1 indisponible")
    s, res = session([], cam=Broken())
    s.run()
    assert s.snapshot()["status"] == "failed" and "caméra indisponible" in res["reason"]


def test_retour_en_direct_pendant_l_angle(monkeypatch):
    monkeypatch.setattr(config, "ENROLL_ANGLE_TIMEOUT_S", 0.3)
    s, _ = session(script("face"), then=(POSES["face"], 1))
    t = threading.Thread(target=s.run)
    t.start()
    t.join(2)
    snap = s.snapshot()
    # bloqué sur « gauche » : visage vu, un seul, angle pas atteint, consigne de correction
    assert snap["step"] == 1 and snap["captured"] == 1
    fb = snap["feedback"]
    assert fb["face_ok"] and fb["single"] and not fb["angle_ok"]
    assert "gauche" in fb["message"] and fb["yaw"] == pytest.approx(0, abs=1e-3)


def test_start_reserve_le_poste_et_le_libere(fake_cam, monkeypatch):
    monkeypatch.setattr(enroll.face, "detect", FakeDetect(script(*ALL)))
    done = threading.Event()
    s = enroll.start("alice", lambda e: done.set() or {"n": len(e)})
    assert s is not None and enroll.current() is s
    assert enroll.start("bob", lambda e: None) is None           # un seul enrôlement à la fois
    assert wait_end(s.snapshot)["status"] == "done"
    assert wait_idle() == "idle"


def test_start_refuse_si_poste_occupe(fake_cam):
    with auth.kiosk.lock:
        auth.kiosk.state = "wait_password"
    assert enroll.start("alice", lambda e: None) is None
