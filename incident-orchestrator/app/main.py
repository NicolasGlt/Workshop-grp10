"""Orchestrateur d'incident — API + vue live de la timeline (http://127.0.0.1:8002).

Démarre les deux boucles autonomes (attaque informatif / chaos décideur) et sert une
timeline qui s'abonne aux événements en SSE : alerte → raisonnement du LLM → action →
reprise → explication.
"""
import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

from . import clients, config, events, loops

STATIC = config.ROOT / "app" / "static"

app = FastAPI(title="Orchestrateur d'incident — RESILIENCE-ALPHA")


@app.on_event("startup")
def _startup():
    loops.start()


@app.get("/")
def page():
    return FileResponse(STATIC / "index.html")


@app.get("/api/state")
def state():
    """Historique des événements + état courant (santé, blocages)."""
    snap = clients.health_snapshot()
    return {
        "events": events.snapshot(),
        "health": snap,
        "degraded": clients.degraded_services(snap),
        "remediation": clients.remediation_status(),
        "config": {
            "assistant": config.ASSISTANT_URL,
            "remediation": config.REMEDIATION_URL,
            "monitored": config.MONITORED_SERVICES,
        },
    }


@app.get("/api/stream")
async def stream():
    """Flux SSE : renvoie l'historique puis les nouveaux événements au fil de l'eau."""
    async def gen():
        cursor = 0
        # petit battement de cœur pour garder la connexion ouverte derrière un proxy
        while True:
            for ev in events.since(cursor):
                cursor = ev["id"]
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.5)
            yield ": ping\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/health")
def health():
    return {"status": "ok", "assistant": config.ASSISTANT_URL,
            "remediation": config.REMEDIATION_URL,
            "token_present": bool(config.REMEDIATION_TOKEN)}
