"""Mesure de l'angle à partir des 5 points de repère de YuNet."""
import numpy as np
import pytest

from app import config, face
from conftest import POSES, row


def test_frontal():
    p = face.pose(row())
    assert p["yaw"] == pytest.approx(0, abs=1e-6)
    assert p["pitch"] == pytest.approx(0.55, abs=1e-6)
    assert p["size"] == 200


def test_independant_de_la_distance():
    near, far = face.pose(row(yaw=0.2, pitch=0.6, size=300)), face.pose(row(yaw=0.2, pitch=0.6, size=100))
    assert near["yaw"] == pytest.approx(far["yaw"], abs=1e-4)
    assert near["pitch"] == pytest.approx(far["pitch"], abs=1e-4)


def test_independant_de_la_position():
    a, b = face.pose(row(yaw=0.2, cx=150, cy=120)), face.pose(row(yaw=0.2, cx=500, cy=350))
    assert a["yaw"] == pytest.approx(b["yaw"], abs=1e-4)


def test_tete_inclinee_mesure_par_ecart_reel_des_yeux():
    r = row(yaw=0.2)
    r[7] += 20            # œil gauche plus bas : l'écart des yeux grandit, le lacet reste mesurable
    assert 0.1 < face.pose(r)["yaw"] < 0.2


@pytest.mark.parametrize("step", ["face", "left", "right", "up", "down"])
def test_chaque_angle_atteint_par_sa_pose(step):
    base = face.pose(POSES["face"])
    ok, _ = face.check_angle(step, face.pose(POSES[step]), base)
    assert ok


@pytest.mark.parametrize("step,other", [("left", "right"), ("right", "left"), ("up", "down"),
                                        ("down", "up"), ("left", "face"), ("up", "face"),
                                        ("face", "left"), ("face", "right")])
def test_mauvais_angle_refuse(step, other):
    base = face.pose(POSES["face"])
    ok, hint = face.check_angle(step, face.pose(POSES[other]), base)
    assert not ok and hint


def test_seuil_relatif_a_la_pose_de_face():
    # Personne dont le nez est naturellement décalé : le lacet se juge par rapport à SA pose de face.
    base = face.pose(row(yaw=0.05))
    assert not face.check_angle("left", face.pose(row(yaw=0.05 + config.ENROLL_YAW_MIN - 0.01)), base)[0]
    assert face.check_angle("left", face.pose(row(yaw=0.05 + config.ENROLL_YAW_MIN + 0.01)), base)[0]
    base = face.pose(row(pitch=0.65))
    assert not face.check_angle("up", face.pose(row(pitch=0.60)), base)[0]
    assert face.check_angle("up", face.pose(row(pitch=0.65 - config.ENROLL_PITCH_MIN - 0.01)), base)[0]


def test_visage_trop_petit():
    ok, hint = face.check_angle("face", face.pose(row(size=config.ENROLL_MIN_FACE_PX - 1)))
    assert not ok and "Rapprochez" in hint


def test_sens_du_lacet_inversable(monkeypatch):
    base = face.pose(POSES["face"])
    monkeypatch.setattr(config, "ENROLL_YAW_SIGN", -1)
    assert face.check_angle("right", face.pose(POSES["left"]), base)[0]
    assert not face.check_angle("left", face.pose(POSES["left"]), base)[0]


def test_angle_inconnu():
    with pytest.raises(ValueError):
        face.check_angle("diagonale", face.pose(row()))


def test_modeles_charges_image_vide():
    assert face.detect(np.zeros((480, 640, 3), np.uint8)) == (None, 0)


def test_cinq_angles():
    assert config.ENROLL_SAMPLES == 5
    assert [k for k, _ in config.ENROLL_ANGLES] == ["face", "left", "right", "up", "down"]
