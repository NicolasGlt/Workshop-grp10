"""Reconnaissance faciale : YuNet (détection, 5 points de repère) + SFace (vecteur de 128 nombres,
similarité cosinus). L'enrôlement guidé est dans `app/enroll.py`."""
import threading
import time

import cv2
import numpy as np

from . import config

_det = cv2.FaceDetectorYN.create(
    str(config.MODELS / "face_detection_yunet_2023mar.onnx"), "", (640, 480), 0.9)
_rec = cv2.FaceRecognizerSF.create(
    str(config.MODELS / "face_recognition_sface_2021dec.onnx"), "")
_lock = threading.Lock()


def embed(frame):
    """(vecteur du plus grand visage ou None, nombre de visages détectés)."""
    with _lock:
        h, w = frame.shape[:2]
        _det.setInputSize((w, h))
        _, faces = _det.detect(frame)
        if faces is None:
            return None, 0
        face = max(faces, key=lambda f: f[2] * f[3])
        return _rec.feature(_rec.alignCrop(frame, face)).copy(), len(faces)


def score(emb, refs):
    with _lock:
        return max(_rec.match(emb, r, cv2.FaceRecognizerSF_FR_COSINE) for r in refs)


def verify(cam, refs, threshold=None, hits_needed=None, timeout=None):
    """Vérification 1:1 contre les gabarits d'UN utilisateur. Reconnu si `hits_needed` images
    dépassent le seuil avant `timeout`. Sans gabarit (identifiant inconnu), on attend quand même
    jusqu'au timeout pour ne pas révéler l'existence du compte par le temps de réponse."""
    threshold = config.FACE_THRESHOLD if threshold is None else threshold
    hits_needed = config.FACE_HITS if hits_needed is None else hits_needed
    end = time.time() + (config.FACE_TIMEOUT_S if timeout is None else timeout)
    hits, best, seq = 0, 0.0, -1
    while time.time() < end:
        seq, frame = cam.next_frame(seq)
        if frame is None:
            continue
        emb, _ = embed(frame)
        if emb is None or not refs:
            continue
        s = score(emb, refs)
        best = max(best, s)
        if s >= threshold:
            hits += 1
            if hits >= hits_needed:
                return True, best
    return False, best


def detect(frame):
    """(plus grand visage au format YuNet ou None, nombre de visages détectés)."""
    with _lock:
        h, w = frame.shape[:2]
        _det.setInputSize((w, h))
        _, faces = _det.detect(frame)
    if faces is None:
        return None, 0
    return max(faces, key=lambda f: f[2] * f[3]), len(faces)


def embed_face(frame, face_row):
    """Gabarit SFace d'un visage déjà détecté (évite une seconde détection)."""
    with _lock:
        return _rec.feature(_rec.alignCrop(frame, face_row)).copy()


def pose(face_row):
    """Orientation de la tête d'après les 5 points de repère de YuNet, sans unité :
    - `yaw` (lacet) : décalage horizontal du nez par rapport au milieu des yeux, divisé par
      l'écart entre les yeux. Positif quand le nez part vers la droite de l'IMAGE ;
    - `pitch` (tangage) : position verticale du nez entre la ligne des yeux (0) et celle de la
      bouche (1). Elle baisse quand on lève la tête, monte quand on la baisse ;
    - `size` : largeur du cadre du visage, en pixels.
    Ratios entre points du visage : indépendants de la distance à la caméra."""
    x, y, w, h = (float(v) for v in face_row[:4])
    rex, rey, lex, ley, nx, ny, rmx, rmy, lmx, lmy = (float(v) for v in face_row[4:14])
    eye_x, eye_y = (rex + lex) / 2, (rey + ley) / 2
    mouth_y = (rmy + lmy) / 2
    iod = max(((lex - rex) ** 2 + (ley - rey) ** 2) ** 0.5, 1e-6)
    return {"yaw": (nx - eye_x) / iod,
            "pitch": (ny - eye_y) / max(mouth_y - eye_y, 1e-6),
            "size": w}


def check_angle(step, p, baseline=None):
    """L'angle demandé est-il atteint ? Renvoie (atteint, consigne de correction).
    `baseline` = pose mesurée de face : les angles se jugent par rapport à elle, pas dans l'absolu.
    Le sens du lacet suit `ENROLL_YAW_SIGN` (1 : image non retournée, la gauche de la personne
    est la droite de l'image)."""
    if p["size"] < config.ENROLL_MIN_FACE_PX:
        return False, "Rapprochez-vous de la caméra"
    sign = config.ENROLL_YAW_SIGN
    if step == "face":
        if abs(p["yaw"]) > config.ENROLL_FRONT_MAX:
            return False, "Regardez droit vers la caméra"
        return True, "Ne bougez plus"
    base = baseline or {"yaw": 0.0, "pitch": p["pitch"]}
    dyaw = sign * (p["yaw"] - base["yaw"])
    dpitch = p["pitch"] - base["pitch"]
    if step == "left":
        ok = dyaw >= config.ENROLL_YAW_MIN
        return ok, "Ne bougez plus" if ok else "Tournez encore la tête vers votre gauche"
    if step == "right":
        ok = -dyaw >= config.ENROLL_YAW_MIN
        return ok, "Ne bougez plus" if ok else "Tournez encore la tête vers votre droite"
    if step == "up":
        ok = -dpitch >= config.ENROLL_PITCH_MIN
        return ok, "Ne bougez plus" if ok else "Levez encore un peu la tête"
    if step == "down":
        ok = dpitch >= config.ENROLL_PITCH_MIN
        return ok, "Ne bougez plus" if ok else "Baissez encore un peu la tête"
    raise ValueError(f"angle inconnu : {step}")


def to_blob(emb):
    return np.asarray(emb, np.float32).tobytes()


def from_blob(blob):
    return np.frombuffer(blob, np.float32).reshape(1, -1)
