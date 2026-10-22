"""Bus d'événements de la timeline d'incident.

Liste en mémoire, protégée par un verrou (les boucles tournent dans des threads).
Chaque événement porte un id croissant : le flux SSE n'a qu'à renvoyer ceux dont
l'id dépasse le curseur du client, ce qui donne gratuitement l'historique au
rafraîchissement de la page.
"""
import threading
import time
from datetime import datetime, timezone

from . import config

_lock = threading.Lock()
_events = []            # liste de dicts {id, ts, phase, scenario, title, detail, data}
_next_id = 1


# Phases de la timeline (ordre d'affichage côté UI)
PHASES = ("alert", "reasoning", "action", "recovery", "explanation", "info")


def emit(phase: str, scenario: str, title: str, detail: str = "", **data) -> dict:
    """Ajoute un événement et le renvoie."""
    global _next_id
    with _lock:
        ev = {
            "id": _next_id,
            "ts": datetime.now(timezone.utc).isoformat(),
            "mono": time.time(),
            "phase": phase,
            "scenario": scenario,     # "attaque" | "chaos"
            "title": title,
            "detail": detail,
            "data": data,
        }
        _events.append(ev)
        _next_id += 1
        if len(_events) > config.MAX_EVENTS:
            del _events[: len(_events) - config.MAX_EVENTS]
        return ev


def since(cursor: int):
    """Événements dont l'id est strictement supérieur à `cursor`."""
    with _lock:
        return [e for e in _events if e["id"] > cursor]


def snapshot():
    with _lock:
        return list(_events)
