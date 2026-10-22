"""Diagnostic de l'assistant : dit précisément ce qui manque. `just assistant-check`.

Vérifie dans l'ordre : Ollama joignable, les deux modèles présents, index construit,
puis pose une question test et affiche la réponse avec ses sources.
Sortie non nulle au premier point bloquant.

Lancement : .venv/bin/python scripts/check.py
"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Console Windows (cp1252) : forcer UTF-8, sinon l'affichage des sources plante sur
# des caractères comme « → » (UnicodeEncodeError).
for _flux in (sys.stdout, sys.stderr):
    try:
        _flux.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from app import config, rag          # noqa: E402

OK, KO = "[ OK ]", "[MANQUE]"
QUESTION = "Que faire si la démo ne détecte pas le flood ?"


def echec(message, aide):
    print(f"{KO} {message}")
    print(f"       -> {aide}")
    sys.exit(1)


def modeles_ollama():
    """Noms des modèles présents selon l'API Ollama, ou None si injoignable."""
    url = config.OLLAMA_URL.rstrip("/") + "/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=5) as rep:
            data = json.load(rep)
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return [m.get("name", "") for m in data.get("models", [])]


def present(nom, disponibles):
    """Modèle présent ? Tolère l'absence du tag (:latest implicite)."""
    return nom in disponibles or f"{nom}:latest" in disponibles


def main():
    print(f"Ollama : {config.OLLAMA_URL}")
    noms = modeles_ollama()
    if noms is None:
        echec("Ollama injoignable",
              "démarrer `ollama serve` (ou vérifier OLLAMA_URL dans rag-assistant/.env)")
    print(f"{OK} Ollama joignable ({len(noms)} modèle(s) : {', '.join(noms) or 'aucun'})")

    if not config.RAG_MODEL:
        echec("RAG_MODEL non défini",
              "copier dans rag-assistant/.env le nom exact donné par `ollama list`")
    if not present(config.RAG_MODEL, noms):
        echec(f"Modèle de réponse absent : {config.RAG_MODEL}",
              f"`ollama pull {config.RAG_MODEL}` sur le PC Hôte")
    print(f"{OK} Modèle de réponse présent : {config.RAG_MODEL}")

    if not present(config.EMBED_MODEL, noms):
        echec(f"Modèle d'embeddings absent : {config.EMBED_MODEL}",
              f"`ollama pull {config.EMBED_MODEL}`")
    print(f"{OK} Modèle d'embeddings présent : {config.EMBED_MODEL}")

    if not config.INDEX_PATH.exists():
        echec("Index non construit",
              "`just assistant-index`")
    print(f"{OK} Index présent : {config.INDEX_PATH}")

    print(f"\nQuestion test : « {QUESTION} »")
    try:
        res = rag.answer(QUESTION)
    except Exception as exc:
        echec(f"Échec de la question test : {exc}",
              "vérifier qu'Ollama répond et que les modèles sont chargés")
    print(f"\nRéponse :\n{res['answer']}")
    print("\nSources :")
    for s in res["sources"]:
        print(f"  - {s['source']} — {s['title']}")
    print(f"\n{OK} Assistant opérationnel.")


if __name__ == "__main__":
    main()
