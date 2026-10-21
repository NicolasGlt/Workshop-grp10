"""Étape 2 : enrôler un visage puis afficher le score de reconnaissance en direct.

Usage :
    python scripts/test_face.py <fichier_gabarits.npy> [index_camera] [etiquette_de_depart]

    etiquette_de_depart : 0 (aucune, par défaut), 1 (moi) ou 2 (autre). Pratique pour une session
    entière avec une seule personne, sans dépendre des touches.

Touches (fenêtre au premier plan) :
    e  enrôler : 5 captures espacées de 0,5 s
    1  étiquette « moi » (la personne enrôlée est devant la caméra)
    2  étiquette « autre » (une autre personne est devant la caméra)
    0  pas d'étiquette
    q  quitter et afficher le bilan des scores par étiquette

Les gabarits sont des vecteurs SFace (128 nombres), jamais des photos.
"""
import os
import sys
import time

os.environ["OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS"] = "0"
import cv2
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THRESHOLD = 0.363                            # seuil cosinus SFace de référence (LFW)
LABELS = {0: "sans etiquette", 1: "moi", 2: "autre"}

det = cv2.FaceDetectorYN.create(
    os.path.join(ROOT, "models", "face_detection_yunet_2023mar.onnx"), "", (640, 480), 0.9)
rec = cv2.FaceRecognizerSF.create(
    os.path.join(ROOT, "models", "face_recognition_sface_2021dec.onnx"), "")


def largest_face(frame):
    """Renvoie (plus grand visage, nombre de visages détectés)."""
    h, w = frame.shape[:2]
    det.setInputSize((w, h))
    _, faces = det.detect(frame)
    if faces is None:
        return None, 0
    return max(faces, key=lambda f: f[2] * f[3]), len(faces)


def main():
    path = sys.argv[1]
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    refs = list(np.load(path)) if os.path.exists(path) else []
    cap = cv2.VideoCapture(index, cv2.CAP_MSMF)

    label = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    scores = {k: [] for k in LABELS}
    multi = {k: 0 for k in LABELS}           # images où plusieurs visages sont détectés
    enrolling, last_capture, new_refs = 0, 0.0, []

    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        face, n_faces = largest_face(frame)
        if n_faces > 1:
            multi[label] += 1
        text, color = "aucun visage", (0, 0, 255)

        if face is not None:
            x, y, w, h = face[:4].astype(int)
            emb = rec.feature(rec.alignCrop(frame, face)).copy()   # copie : la sortie peut partager la mémoire du réseau
            if enrolling and time.time() - last_capture > 0.5:
                new_refs.append(emb)
                last_capture = time.time()
                enrolling -= 1
                if enrolling == 0:
                    refs = new_refs
                    np.save(path, np.array(refs))
                    print(f"enrolement termine : {len(refs)} gabarits -> {path}", flush=True)
            if refs:
                s = max(rec.match(emb, r, cv2.FaceRecognizerSF_FR_COSINE) for r in refs)
                scores[label].append(s)
                recognized = s >= THRESHOLD
                text = f"score {s:.3f}  {'RECONNU' if recognized else 'non reconnu'}"
                color = (0, 200, 0) if recognized else (0, 0, 255)
            else:
                text, color = "pas de gabarit : touche e", (0, 200, 255)
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)

        if enrolling:
            text = f"enrolement... {enrolling} captures restantes"
        cv2.putText(frame, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(frame, f"visages detectes : {n_faces}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    (0, 200, 255) if n_faces > 1 else (255, 255, 255), 2)
        cv2.putText(frame, f"etiquette : {LABELS[label]}   1 moi / 2 autre / 0 aucune / e enroler / q quitter",
                    (10, frame.shape[0] - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        cv2.imshow("test reconnaissance", frame)

        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("e"):
            enrolling, last_capture, new_refs = 5, 0.0, []
        if k in (ord("0"), ord("1"), ord("2")):
            label = k - ord("0")

    cap.release()
    cv2.destroyAllWindows()
    print(f"seuil utilise : {THRESHOLD}")
    for k, v in scores.items():
        if v:
            above = sum(s >= THRESHOLD for s in v) / len(v)
            print(f"{LABELS[k]:>15} : {len(v)} images, min {min(v):.3f}, "
                  f"moyenne {np.mean(v):.3f}, max {max(v):.3f}, "
                  f"au-dessus du seuil {above:.0%}, images a plusieurs visages {multi[k]}")


if __name__ == "__main__":
    main()
