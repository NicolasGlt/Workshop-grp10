"""Crée les .env du projet depuis leurs modèles et remplace chaque valeur change-me par un secret aléatoire.

Usage, depuis la racine du dépôt : `just env` (ou `py -3.12 scripts/init_env.py` sous Windows).
Idempotent : un .env existant est complété, jamais écrasé ; une valeur déjà remplie est gardée.
BACKOFFICE_DB_PASSWORD reçoit la même valeur dans poc-resilience/.env et auth-faciale/.env.
"""

import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICES = ["poc-resilience", "auth-faciale", "rag-assistant"]
LINE = re.compile(r"^(?P<key>[A-Z0-9_]+)=(?P<value>change-me[^\s#]*)(?P<rest>.*)$")


def generate(key: str) -> str:
    if key == "MERCHANT_API_KEY":
        return "pk_" + secrets.token_hex(12)
    return secrets.token_hex(24)  # hexadécimal : sans caractère à échapper dans une URL de base


def read_value(env: Path, key: str) -> str | None:
    if not env.exists():
        return None
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "=") and not line.split("=", 1)[1].startswith("change-me"):
            return line.split("=", 1)[1].split("#", 1)[0].strip()
    return None


def main() -> None:
    shared = {
        "BACKOFFICE_DB_PASSWORD": read_value(ROOT / "poc-resilience/.env", "BACKOFFICE_DB_PASSWORD")
        or read_value(ROOT / "auth-faciale/.env", "BACKOFFICE_DB_PASSWORD")
        or secrets.token_hex(24)
    }
    for service in SERVICES:
        example, env = ROOT / service / ".env.example", ROOT / service / ".env"
        created = not env.exists()
        text = (env if env.exists() else example).read_text(encoding="utf-8")
        out, filled = [], []
        for line in text.splitlines():
            match = LINE.match(line)
            if match:
                key = match["key"]
                value = shared.get(key) or generate(key)
                line = f"{key}={value}{match['rest']}"
                filled.append(key)
            out.append(line)
        # LF imposé : SOPS refuse un .env en CRLF
        env.write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
        state = "créé" if created else "complété"
        print(f"{service}/.env {state} : {len(filled)} secret(s) généré(s) {', '.join(filled)}".rstrip())

    print()
    print("Comptes d'administration (valeurs lues dans poc-resilience/.env) :")
    print(f"  Grafana  http://localhost:3000  admin / {read_value(ROOT / 'poc-resilience/.env', 'GRAFANA_ADMIN_PASSWORD')}")
    print(f"  pgAdmin  http://localhost:5050  {read_value(ROOT / 'poc-resilience/.env', 'PGADMIN_EMAIL')} / "
          f"{read_value(ROOT / 'poc-resilience/.env', 'PGADMIN_PASSWORD')}")


if __name__ == "__main__":
    main()
