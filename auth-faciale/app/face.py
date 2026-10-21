"""Reconnaissance faciale : YuNet (détection) + SFace (vecteur de 128 nombres, similarité cosinus)."""
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


def enroll(cam, samples=None, interval=0.5, timeout=15.0):
    """Capture `samples` gabarits espacés de `interval` s, uniquement quand un seul visage est visible."""
    samples = config.ENROLL_SAMPLES if samples is None else samples
    out, seq, last, end = [], -1, 0.0, time.time() + timeout
    while len(out) < samples and time.time() < end:
        seq, frame = cam.next_frame(seq)
        if frame is None or time.time() - last < interval:
            continue
        emb, n = embed(frame)
        if emb is not None and n == 1:
            out.append(emb)
            last = time.time()
    return out


def to_blob(emb):
    return np.asarray(emb, np.float32).tobytes()


def from_blob(blob):
    return np.frombuffer(blob, np.float32).reshape(1, -1)
