"""Réglages de l'orchestrateur d'incident.

L'orchestrateur est un composant de CONFIANCE, déterministe (comme le ml-detector) :
c'est lui — et jamais le LLM — qui détient le jeton de remédiation et appelle l'API.
Le LLM ne fait que proposer une explication ou une décision que l'orchestrateur valide
contre un catalogue fermé avant d'agir (sujet §3.3).

Chaque valeur est surchargeable par une variable d'environnement du même nom.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent      # incident-orchestrator/
REPO = ROOT.parent                                 # racine du dépôt


def _env(name, default):
    v = os.environ.get(name)
    return v if v is not None else default


def _read_token():
    """Jeton de remédiation : variable d'environnement, sinon poc-resilience/.env (ignoré par git)."""
    tok = os.environ.get("REMEDIATION_TOKEN")
    if tok:
        return tok
    envfile = REPO / "poc-resilience" / ".env"
    try:
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("REMEDIATION_TOKEN="):
                return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return ""


# --- cibles (toutes en loopback sur le PC Hôte) --------------------------------------
ASSISTANT_URL = _env("ASSISTANT_URL", "http://127.0.0.1:8001")      # assistant RAG (le LLM)
REMEDIATION_URL = _env("REMEDIATION_URL", "http://127.0.0.1:8099")  # API remédiation (port loopback)
PROM_URL = _env("PROM_URL", "http://127.0.0.1:9090")                # Prometheus
REMEDIATION_TOKEN = _read_token()
COMPOSE_PROJECT = _env("COMPOSE_PROJECT", "resilience-alpha")

# --- serveur -------------------------------------------------------------------------
HOST = _env("HOST", "127.0.0.1")
PORT = int(_env("PORT", "8002"))

# --- services suivis / catalogue d'actions fermé -------------------------------------
# Services applicatifs surveillés (santé Docker) et autorisés au redémarrage automatique.
# La base `db` est volontairement HORS de ce périmètre (redémarrage à décision humaine).
MONITORED_SERVICES = _env(
    "MONITORED_SERVICES", "api,bank,merchant,frontend,waf,accounts-api,clientapp"
).split(",")
ALLOWED_RESTART = set(MONITORED_SERVICES)           # garde-fou : whitelist de l'orchestrateur

# --- cadences & garde-fous -----------------------------------------------------------
CHAOS_POLL = float(_env("CHAOS_POLL", "3"))         # sondage santé (s)
ATTACK_POLL = float(_env("ATTACK_POLL", "4"))       # sondage blocages (s)
CHAOS_COOLDOWN = float(_env("CHAOS_COOLDOWN", "90"))
RECOVERY_TIMEOUT = float(_env("RECOVERY_TIMEOUT", "75"))   # attente retour en bonne santé (s)
LLM_TIMEOUT = float(_env("LLM_TIMEOUT", "120"))     # le 9B local peut être lent
MAX_EVENTS = int(_env("MAX_EVENTS", "500"))
