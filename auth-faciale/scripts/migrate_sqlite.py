"""Reprend une ancienne base SQLite (auth.db) dans le schéma backoffice du PostgreSQL du POC.

Comptes, rôles, mots de passe (hachés) et gabarits de visage : pas besoin de réenrôler.
Les comptes déjà présents côté PostgreSQL sont laissés tels quels.

Usage (depuis la racine du dossier, base du POC démarrée) :
    .venv\\Scripts\\python scripts\\migrate_sqlite.py auth.db
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db, face                # noqa: E402


def main(path):
    src = sqlite3.connect(path)
    src.row_factory = sqlite3.Row
    users = src.execute("SELECT * FROM users").fetchall()
    moved = 0
    for u in users:
        if db.get_user(u["username"]):
            print(f"  {u['username']} : déjà présent, ignoré")
            continue
        new_id = db.create_user(u["username"], u["password_hash"], u["role"], bool(u["backoffice_enabled"]))
        rows = src.execute("SELECT embedding FROM face_templates WHERE user_id = ?", (u["id"],)).fetchall()
        db.replace_templates(new_id, [face.from_blob(r["embedding"]) for r in rows])
        db.event(u["username"], "migrated_from_sqlite", detail=f"{len(rows)} gabarits")
        print(f"  {u['username']} ({u['role']}) : {len(rows)} gabarits")
        moved += 1
    print(f"{moved} compte(s) repris sur {len(users)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "auth.db")
