"""Reconstruit l'index vectoriel depuis le corpus. Utilisé par `just assistant-index`.

Lancement : .venv/bin/python scripts/index_corpus.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, corpus, rag          # noqa: E402


def main():
    sources = corpus.list_sources()
    print(f"Corpus : {len(sources)} fichier(s)")
    for s in sources:
        print(f"  - {s}")
    print(f"Modèle d'embeddings : {config.EMBED_MODEL} ({config.OLLAMA_URL})")
    n = rag.build_index()
    print(f"Index construit : {n} morceau(x) -> {config.INDEX_PATH}")


if __name__ == "__main__":
    main()
