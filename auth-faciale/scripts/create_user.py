"""Crée un utilisateur et enrôle son visage, en ligne de commande (application arrêtée : la caméra
ne peut servir qu'à un programme à la fois). Secours : le premier admin se crée normalement dans
la page /setup de l'application. Même enrôlement guidé sur 5 angles, consignes dans la console.

Usage (depuis la racine du dossier) :
    .venv\\Scripts\\python scripts\\create_user.py <identifiant> [--role admin|operateur|lecteur]
                                                  [--password-file FICHIER]

Sans --password-file, le mot de passe est demandé au clavier (masqué).
Avec --password-file, un mot de passe aléatoire est généré et écrit dans ce fichier (comptes de test).
"""
import argparse
import getpass
import secrets
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, config, db, enroll   # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--role", default="lecteur", choices=["admin", "operateur", "lecteur"])
    parser.add_argument("--password-file")
    args = parser.parse_args()

    username = auth.normalize(args.username)
    if args.password_file:
        password = secrets.token_urlsafe(12)
        Path(args.password_file).write_text(f"{username}\n{password}\n", encoding="utf-8")
        print(f"mot de passe genere et ecrit dans {args.password_file}")
    else:
        password = getpass.getpass("Mot de passe (8 caracteres min.) : ")
        if len(password) < 8 or password != getpass.getpass("Confirmation : "):
            sys.exit("mot de passe trop court ou confirmation differente")

    user = db.get_user(username)
    if user:
        db.update_user(user["id"], role=args.role, password_hash=auth.hash_password(password))
        user_id = user["id"]
        print(f"utilisateur {username} existant : role et mot de passe mis a jour")
    else:
        user_id = db.create_user(username, auth.hash_password(password), args.role)
        print(f"utilisateur {username} cree (role {args.role})")

    print(f"Enrolement du visage : seul face a la webcam USB, a 50 cm environ, {config.ENROLL_SAMPLES} angles.")

    def on_success(embeddings):
        db.replace_templates(user_id, embeddings)
        db.event(username, "face_enrolled", detail=f"create_user.py : {len(embeddings)} angles")

    session = enroll.Enrollment(username, on_success, purpose="cli")
    worker = threading.Thread(target=session.run)
    worker.start()
    last = None
    while worker.is_alive():
        s = session.snapshot()
        if s["status"] == "running":
            line = f"  [{s['step'] + 1}/{len(s['steps'])}] {s['instruction']} : {s['feedback']['message']}"
            if line != last:
                print(line)
                last = line
        time.sleep(0.2)
    s = session.snapshot()
    if s["status"] != "done":
        sys.exit(f"echec : {s['error']} ({s['captured']} angle(s) sur {config.ENROLL_SAMPLES}), recommence")
    print(f"visage enrole : {s['captured']} gabarits")


if __name__ == "__main__":
    main()
