"""Enrôlement guidé : un gabarit SFace par angle (face, gauche, droite, haut, bas).

La capture tourne dans un thread. La page affiche le flux MJPEG dès l'allumage de la caméra et
interroge GET /api/enroll/state (angle demandé, visage détecté, un seul visage, angle atteint).
Un angle est capturé après `ENROLL_HOLD_FRAMES` images consécutives à la bonne orientation,
dans la limite de `ENROLL_ANGLE_TIMEOUT_S`. Un seul enrôlement à la fois : le poste passe à l'état
`enrolling` et la connexion répond « occupé » pendant ce temps.
"""
import secrets
import threading
import time

from . import auth, config, face
from .camera import camera


class Refused(Exception):
    """Refus métier au moment d'enregistrer (ex. : un compte a été créé entre-temps)."""


class Enrollment:
    def __init__(self, target, on_success, on_failure=None, purpose="admin",
                 cam=None, detect=None, embed=None):
        self.id = secrets.token_urlsafe(16)
        self.target, self.purpose = target, purpose
        self._on_success, self._on_failure = on_success, on_failure
        self._cam = cam or camera
        self._detect = detect or face.detect
        self._embed = embed or face.embed_face
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.status = "starting"        # starting, running, done, failed, cancelled
        self.step = 0
        self.done_steps = []
        self.embeddings = []
        self.deadline = 0.0
        self.feedback = {"faces": 0, "face_ok": False, "single": False, "angle_ok": False,
                         "message": "Allumage de la caméra…", "yaw": None, "pitch": None}
        self.error = None
        self.result = None

    # --- lecture par la page -----------------------------------------------------------

    def snapshot(self):
        with self._lock:
            steps = [{"key": k, "label": label, "done": k in self.done_steps}
                     for k, label in config.ENROLL_ANGLES]
            running = self.status == "running"
            return {"id": self.id, "purpose": self.purpose, "target": self.target,
                    "status": self.status, "step": self.step, "steps": steps,
                    "instruction": steps[self.step]["label"] if running else None,
                    "remaining": max(0, round(self.deadline - time.time(), 1)) if running else 0,
                    "feedback": dict(self.feedback), "captured": len(self.embeddings),
                    "camera": self._cam.is_on, "error": self.error, "result": self.result}

    def cancel(self):
        self._cancel.set()

    # --- capture ------------------------------------------------------------------------

    def _set(self, **fields):
        with self._lock:
            for key, value in fields.items():
                setattr(self, key, value)

    def _fb(self, **fields):
        with self._lock:
            self.feedback.update(fields)

    def run(self):
        """Exécution complète, bloquante (thread de `start()` ou script en ligne de commande)."""
        try:
            self._cam.on()
        except RuntimeError as exc:
            return self._fail(f"caméra indisponible ({exc})")
        try:
            self._set(status="running")
            reason = self._capture()
        finally:
            self._cam.off()
        if reason:
            return self._fail(reason, cancelled=reason == "annulé")
        try:
            result = self._on_success(list(self.embeddings))
        except Refused as exc:
            return self._fail(str(exc))
        except Exception as exc:           # base indisponible, compte supprimé entre-temps…
            return self._fail(f"enregistrement impossible ({type(exc).__name__})")
        self._set(status="done", result=result)

    def _fail(self, reason, cancelled=False):
        self._set(status="cancelled" if cancelled else "failed", error=reason)
        if self._on_failure:
            try:
                self._on_failure(reason)
            except Exception:
                pass

    def _capture(self):
        """Parcourt les angles. Renvoie None si tout est capturé, sinon la raison de l'échec."""
        seq, baseline = -1, None
        for index, (key, label) in enumerate(config.ENROLL_ANGLES):
            self._set(step=index, deadline=time.time() + config.ENROLL_ANGLE_TIMEOUT_S)
            hold = 0
            while True:
                if self._cancel.is_set():
                    return "annulé"
                if time.time() > self.deadline:
                    return f"angle « {label} » non atteint en {config.ENROLL_ANGLE_TIMEOUT_S:.0f} s"
                seq, frame = self._cam.next_frame(seq, timeout=0.5)
                if frame is None:
                    self._fb(message="En attente d'une image de la caméra…")
                    continue
                row, count = self._detect(frame)
                if row is None:
                    hold = 0
                    self._fb(faces=0, face_ok=False, single=False, angle_ok=False,
                             yaw=None, pitch=None, message="Aucun visage détecté")
                    continue
                if count > 1:
                    hold = 0
                    self._fb(faces=count, face_ok=True, single=False, angle_ok=False,
                             message="Une seule personne devant la caméra")
                    continue
                p = face.pose(row)
                ok, hint = face.check_angle(key, p, baseline)
                hold = hold + 1 if ok else 0
                self._fb(faces=1, face_ok=True, single=True, angle_ok=ok, message=hint,
                         yaw=round(p["yaw"], 3), pitch=round(p["pitch"], 3))
                if hold >= config.ENROLL_HOLD_FRAMES:
                    emb = self._embed(frame, row)
                    with self._lock:
                        self.embeddings.append(emb)
                        self.done_steps.append(key)
                    if key == "face":
                        baseline = p
                    break
        return None


_current = None
_current_lock = threading.Lock()


def current():
    return _current


def start(target, on_success, on_failure=None, purpose="admin", **kwargs):
    """Lance un enrôlement en arrière-plan si le poste est libre ; None s'il est occupé."""
    global _current
    with auth.kiosk.lock:
        if auth.kiosk.state != "idle":
            return None
        auth.kiosk.state = "enrolling"
    session = Enrollment(target, on_success, on_failure, purpose, **kwargs)
    with _current_lock:
        _current = session
    threading.Thread(target=_run_then_release, args=(session,), daemon=True).start()
    return session


def _run_then_release(session):
    try:
        session.run()
    except Exception as exc:
        session._fail(f"erreur interne ({type(exc).__name__})")
    finally:
        with auth.kiosk.lock:
            auth.kiosk._to_idle()
