"""Crée un utilisateur et enrôle son visage, en ligne de commande (application arrêtée : la caméra
ne peut servir qu'à un programme à la fois). Sert surtout à créer le premier admin, sans qui
personne ne pourrait se connecter au back-office pour enrôler les autres.

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
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import auth, db, face          # noqa: E402
from app.camera import camera           # noqa: E402


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

    print("Enrolement du visage : place-toi seul face a la webcam USB, a 50 cm environ.")
    for i in (3, 2, 1):
        print(f"  {i}...")
        time.sleep(1)
    camera.on()
    try:
        embeddings = face.enroll(camera)
    finally:
        camera.off()
    if len(embeddings) < 5:
        sys.exit(f"echec : {len(embeddings)} capture(s) sur 5, recommence (un seul visage, bien eclaire)")
    db.replace_templates(user_id, embeddings)
    db.event(username, "face_enrolled", detail="create_user.py")
    print(f"visage enrole : {len(embeddings)} gabarits")


if __name__ == "__main__":
    main()
