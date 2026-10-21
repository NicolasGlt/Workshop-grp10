"""Réglages. Chaque valeur peut être surchargée par une variable d'environnement du même nom."""
import os
import re
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Charge auth-faciale/.env (non versionné) sans écraser l'environnement existant."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.split(" #", 1)[0]          # commentaire en fin de ligne
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")


def _env(name, default, cast=str):
    value = os.environ.get(name)
    return cast(value) if value is not None else default


CAM_INDEX = _env("CAM_INDEX", 1, int)                    # webcam USB (index 0 = webcam intégrée)
FACE_THRESHOLD = _env("FACE_THRESHOLD", 0.363, float)    # seuil cosinus SFace
FACE_HITS = _env("FACE_HITS", 3, int)                    # images au-dessus du seuil pour reconnaître
FACE_TIMEOUT_S = _env("FACE_TIMEOUT_S", 5.0, float)      # durée max de la vérification

# Enrôlement guidé : un gabarit par angle (app/enroll.py). Seuils sans unité, relatifs au visage.
ENROLL_ANGLES = [("face", "De face"), ("left", "Tête tournée à gauche"), ("right", "Tête tournée à droite"),
                 ("up", "Tête levée"), ("down", "Tête baissée")]
ENROLL_SAMPLES = len(ENROLL_ANGLES)
ENROLL_ANGLE_TIMEOUT_S = _env("ENROLL_ANGLE_TIMEOUT_S", 20.0, float)   # par angle
ENROLL_HOLD_FRAMES = _env("ENROLL_HOLD_FRAMES", 4, int)      # images consécutives à l'angle avant capture
ENROLL_FRONT_MAX = _env("ENROLL_FRONT_MAX", 0.08, float)     # lacet max de face (nez / écart des yeux)
ENROLL_YAW_MIN = _env("ENROLL_YAW_MIN", 0.15, float)         # lacet min à gauche et à droite (~15-20°)
ENROLL_PITCH_MIN = _env("ENROLL_PITCH_MIN", 0.08, float)     # tangage min en haut et en bas
ENROLL_MIN_FACE_PX = _env("ENROLL_MIN_FACE_PX", 80, int)     # largeur min du visage dans l'image
ENROLL_YAW_SIGN = _env("ENROLL_YAW_SIGN", 1, int)            # -1 si gauche et droite sont inversées

COOLDOWN_S = 30          # rouge fixe : saisie impossible, caméra allumée, puis caméra coupée
LOCK_S = 300             # blocage de l'identifiant
MAX_FAILURES = 2         # « recommencer 1 fois puis bloqué »
PASSWORD_TTL_S = _env("PASSWORD_TTL_S", 30, int)   # ajout hors consigne : délai max pour saisir le mot de passe
BACKOFFICE_DELAY_S = _env("BACKOFFICE_DELAY_S", 0, int)   # 0 ou 30 selon la lecture retenue par l'équipe

LED_URL = _env("LED_URL", "http://192.168.137.200")
LED_TIMEOUT_S = 0.5

# Base : schéma `backoffice` du PostgreSQL du POC, publié sur 127.0.0.1 seulement.
# Mot de passe = BACKOFFICE_DB_PASSWORD du .env de poc-resilience.
DATABASE_URL = _env("DATABASE_URL", "") or (
    f"postgresql://backoffice:{os.environ.get('BACKOFFICE_DB_PASSWORD', '')}"
    f"@{_env('DB_HOST', '127.0.0.1')}:{_env('DB_PORT', '5432')}/{_env('DB_NAME', 'payments')}")

# Liens du back-office vers les outils du SI (PC Hôte)
GRAFANA_URL = _env("GRAFANA_URL", "http://localhost:3000")
PGADMIN_URL = _env("PGADMIN_URL", "http://localhost:5050")
SHOP_URL = _env("SHOP_URL", "http://localhost:8082")
MODELS = ROOT / "models"
SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)


def _led_token():
    """Même jeton que le firmware : lu dans esp8266/include/secrets.h (non versionné)."""
    if os.environ.get("LED_TOKEN"):
        return os.environ["LED_TOKEN"]
    path = ROOT / "esp8266" / "include" / "secrets.h"
    if path.exists():
        match = re.search(r'LED_TOKEN\s+"([^"]+)"', path.read_text(encoding="utf-8"))
        if match:
            return match.group(1)
    return ""


LED_TOKEN = _led_token()
