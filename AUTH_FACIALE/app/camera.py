"""Webcam USB : allumage/extinction réels, un thread garde la dernière image."""
import os
import sys
import threading
import time

os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")   # ouverture plus rapide (mesuré, étape 1)
import cv2

from . import config

# Backend vidéo selon l'OS : MSMF sous Windows (PC Hôte de la démo), V4L2 sous Linux.
_BACKEND = {"win32": cv2.CAP_MSMF, "linux": cv2.CAP_V4L2}.get(sys.platform, cv2.CAP_ANY)


class Camera:
    def __init__(self, index):
        self.index = index
        self._cap = None
        self._frame = None
        self._seq = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

    @property
    def is_on(self):
        return self._running

    def on(self):
        with self._lock:
            if self._running:
                return
            cap = cv2.VideoCapture(self.index, _BACKEND)
            if not cap.isOpened():
                raise RuntimeError(f"camera {self.index} indisponible")
            self._cap, self._frame, self._running = cap, None, True
            self._thread = threading.Thread(target=self._loop, daemon=True)
            self._thread.start()

    def off(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
            self._thread.join(timeout=2)
            self._cap.release()
            self._cap = self._frame = None

    def _loop(self):
        while self._running:
            ok, frame = self._cap.read()
            if ok:
                self._frame = frame
                self._seq += 1
            else:
                time.sleep(0.01)

    def next_frame(self, last_seq=-1, timeout=2.0):
        """Image suivante (jamais deux fois la même), ou (last_seq, None) après timeout."""
        end = time.time() + timeout
        while time.time() < end:
            frame, seq = self._frame, self._seq
            if frame is not None and seq != last_seq:
                return seq, frame.copy()
            time.sleep(0.005)
        return last_seq, None

    def warm_up(self):
        """La 1re ouverture à froid prend ~4 s : on la fait au démarrage, pas devant l'utilisateur."""
        self.on()
        self.next_frame()
        self.off()

    def mjpeg(self):
        """Flux MJPEG pour l'aperçu dans la page de login, tant que la caméra est allumée."""
        while self._running:
            frame = self._frame
            if frame is not None:
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                if ok:
                    yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
            time.sleep(0.05)


camera = Camera(config.CAM_INDEX)
