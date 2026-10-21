"""Étape 1 : repérer l'index de la webcam USB et mesurer son temps d'ouverture.

Usage :
    python scripts/test_camera.py <dossier_sortie>      # sonde les index 0 à 3, enregistre une image par caméra
    python scripts/test_camera.py --show <index>        # aperçu en direct d'un index (touche q pour quitter)
"""
import os
import sys
import time

import cv2

_BACKEND = {"win32": cv2.CAP_MSMF, "linux": cv2.CAP_V4L2}.get(sys.platform, cv2.CAP_ANY)   # comme app/camera.py


def probe(index, out_dir):
    t0 = time.perf_counter()
    cap = cv2.VideoCapture(index, _BACKEND)
    opened = cap.isOpened()
    t_open = time.perf_counter() - t0
    if not opened:
        print(f"index {index} : rien")
        return
    frame = None
    for _ in range(30):                      # laisse l'auto-exposition se stabiliser
        ok, img = cap.read()
        if ok:
            frame = img
    t_ready = time.perf_counter() - t0
    cap.release()
    if frame is None:
        print(f"index {index} : ouvert en {t_open:.2f} s mais aucune image lue")
        return
    h, w = frame.shape[:2]
    path = os.path.join(out_dir, f"camera_{index}.jpg")
    cv2.imwrite(path, frame)
    print(f"index {index} : {w}x{h}, ouverture {t_open:.2f} s, image stable après {t_ready:.2f} s -> {path}")


def show(index):
    cap = cv2.VideoCapture(index, _BACKEND)
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        cv2.imshow(f"camera {index} (q pour quitter)", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--show":
        show(int(sys.argv[2]))
    elif len(sys.argv) == 2:
        os.makedirs(sys.argv[1], exist_ok=True)
        for i in range(4):
            probe(i, sys.argv[1])
    else:
        print(__doc__)
