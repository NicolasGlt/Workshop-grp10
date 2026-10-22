"""Réglages de l'assistant RAG.

Chaque valeur peut être surchargée par une variable d'environnement du même nom,
ou par rag-assistant/.env (non versionné, copié depuis .env.example).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent          # rag-assistant/
REPO = ROOT.parent                                     # racine du dépôt


def _load_dotenv(path):
    """Charge rag-assistant/.env sans écraser l'environnement déjà défini."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            value = value.split(" #", 1)[0]            # commentaire en fin de ligne
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv(ROOT / ".env")


def _env(name, default, cast=str):
    value = os.environ.get(name)
    return cast(value) if value is not None else default


# --- Ollama et modèles (PC Hôte) ------------------------------------------------------
OLLAMA_URL = _env("OLLAMA_URL", "http://127.0.0.1:11434")
# RAG_MODEL : aucune valeur par défaut inventée. Copier le nom exact donné par
# `ollama list` sur le PC Hôte (par ex. le Qwen 9B déjà présent).
RAG_MODEL = _env("RAG_MODEL", "")
EMBED_MODEL = _env("EMBED_MODEL", "nomic-embed-text")

# --- Serveur --------------------------------------------------------------------------
HOST = _env("HOST", "127.0.0.1")                       # 8000 est pris par le back-office
PORT = _env("PORT", 8001, int)

# --- Découpage et recherche -----------------------------------------------------------
CHUNK_SIZE = _env("CHUNK_SIZE", 600, int)              # taille max d'un morceau (caractères)
CHUNK_OVERLAP = _env("CHUNK_OVERLAP", 100, int)        # assez fin pour isoler une ligne de tableau
TOP_K = _env("TOP_K", 4, int)                          # morceaux les plus proches retenus

# --- Chemins --------------------------------------------------------------------------
INDEX_PATH = ROOT / "index" / "index.json"             # index vectoriel sauvé en JSON
CORPUS_DIR = ROOT / "corpus"                           # textes libres déposés par l'équipe

# Documents de l'équipe pris dans le corpus (lecture seule), relatifs à la racine du dépôt.
# Les motifs avec * sont développés par pathlib.glob au moment de l'indexation.
CORPUS_SOURCES = [
    "README.md",
    "docs/demo-jour-j.md",
    "poc-resilience/README.md",
    "poc-resilience/docs/*.md",
    "poc-resilience/secrets/README.md",
    "auth-faciale/README.md",
    "auth-faciale/docs/*.md",
    "ml-lab/README.md",
]
