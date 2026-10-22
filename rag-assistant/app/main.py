"""Interface de l'assistant RAG : FastAPI sur 127.0.0.1:8001 et POST /api/ask.

Lancement (depuis rag-assistant/) :
    .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
Écoute sur 127.0.0.1 seulement : l'assistant n'est pas exposé sur le réseau.
"""
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, rag

STATIC = config.ROOT / "app" / "static"

app = FastAPI(title="Assistant RAG des opérateurs — RESILIENCE-ALPHA")

_store = None


def _get_store():
    """Charge l'index une fois et le garde en mémoire pour les requêtes suivantes."""
    global _store
    if _store is None:
        _store = rag.load_store()
    return _store


@app.get("/")
def page():
    return FileResponse(STATIC / "index.html")


class AskIn(BaseModel):
    question: str


@app.post("/api/ask")
def api_ask(body: AskIn):
    question = body.question.strip()
    if not question:
        raise HTTPException(400, "question vide")
    try:
        store = _get_store()
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc))
    try:
        return rag.answer(question, store=store)
    except Exception as exc:                            # Ollama injoignable, modèle absent…
        raise HTTPException(502, f"Impossible d'interroger le modèle : {exc}")


@app.get("/api/health")
def health():
    return {
        "index": config.INDEX_PATH.exists(),
        "ollama_url": config.OLLAMA_URL,
        "rag_model": config.RAG_MODEL or None,
        "embed_model": config.EMBED_MODEL,
    }
