"""Pilotage de la LED de l'ESP8266. Jamais bloquant : la LED est un signal, pas un contrôle d'accès."""
import json
import queue
import threading
import time

import httpx

from . import config

_queue = queue.Queue()


def _worker():
    # Un seul thread : les ordres partent dans l'ordre où ils ont été donnés.
    while True:
        mode = _queue.get()
        try:
            httpx.post(f"{config.LED_URL}/led", params={"mode": mode, "k": config.LED_TOKEN},
                       timeout=config.LED_TIMEOUT_S)
        except Exception as exc:
            print(json.dumps({"ts": time.time(), "event": "led_unreachable", "mode": mode,
                              "detail": type(exc).__name__}), flush=True)


threading.Thread(target=_worker, daemon=True).start()


def send(mode):
    _queue.put(mode)


def health():
    try:
        return httpx.get(f"{config.LED_URL}/health", timeout=config.LED_TIMEOUT_S).json()
    except Exception:
        return None
