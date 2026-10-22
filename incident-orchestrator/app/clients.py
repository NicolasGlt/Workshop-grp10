"""Accès au système pour l'orchestrateur (composant de confiance, côté hôte).

- santé des conteneurs  : CLI Docker (le PC Hôte a accès au démon)
- signaux               : Prometheus (déjà publié en loopback)
- remédiation           : API de remédiation (port loopback, jeton + catalogue fermé)
- LLM                   : assistant RAG (le LLM n'a, lui, aucun accès système — M11)
"""
import subprocess

import httpx

from . import config


# --- santé des services (Docker) -----------------------------------------------------

def _run(cmd, timeout=10):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def service_state(service: str) -> dict:
    """État d'un service : {service, state, health, degraded}.

    state : running | exited | created | absent …   health : healthy | unhealthy | starting | none
    """
    try:
        ids = _run(["docker", "ps", "-a",
                    "--filter", f"label=com.docker.compose.project={config.COMPOSE_PROJECT}",
                    "--filter", f"label=com.docker.compose.service={service}",
                    "--format", "{{.ID}}"]).stdout.split()
        if not ids:
            return {"service": service, "state": "absent", "health": "none", "degraded": True}
        fmt = "{{.State.Status}};{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
        out = _run(["docker", "inspect", "-f", fmt, ids[0]]).stdout.strip()
        state, _, health = out.partition(";")
        state, health = state or "unknown", health or "none"
    except Exception as e:
        return {"service": service, "state": "erreur", "health": str(e), "degraded": False}
    degraded = (state != "running") or (health == "unhealthy")
    return {"service": service, "state": state, "health": health, "degraded": degraded}


def health_snapshot() -> dict:
    """État de tous les services suivis : {service: {state, health, degraded}}."""
    snap = {}
    for svc in config.MONITORED_SERVICES:
        s = service_state(svc)
        snap[svc] = {"state": s["state"], "health": s["health"], "degraded": s["degraded"]}
    return snap


def degraded_services(snap: dict) -> list:
    return [svc for svc, s in snap.items() if s["degraded"]]


# --- signaux Prometheus ---------------------------------------------------------------

def prom(expr: str) -> float:
    try:
        r = httpx.get(f"{config.PROM_URL}/api/v1/query", params={"query": expr}, timeout=4.0)
        res = r.json()["data"]["result"]
        if not res:
            return 0.0
        v = float(res[0]["value"][1])
        return 0.0 if (v != v or v in (float("inf"), float("-inf"))) else v
    except Exception:
        return 0.0


def attack_signals() -> dict:
    """Signaux agrégés utiles pour expliquer une attaque (flood)."""
    j = 'job="payment-api"'
    return {
        "req_rate_per_s": round(prom(f"sum(rate(http_requests_total{{{j}}}[1m]))"), 2),
        "err_ratio": round(prom(
            f'sum(rate(http_requests_total{{{j},status=~"5.."}}[1m])) '
            f'/ clamp_min(sum(rate(http_requests_total{{{j}}}[1m])),1e-9)'), 3),
        "anomaly_score": round(prom("ml_detector_anomaly_score"), 3),
        "remediations_total": int(prom("ml_detector_remediations_total")),
    }


# --- API de remédiation (jeton + catalogue fermé) ------------------------------------

def remediation_status() -> dict:
    try:
        return httpx.get(f"{config.REMEDIATION_URL}/status", timeout=5.0).json()
    except Exception as e:
        return {"error": str(e), "blocks_active": [], "actions_total": 0}


def restart_service(service: str, reason: str) -> dict:
    """Appelle l'API de remédiation pour redémarrer un service (seul l'orchestrateur a le jeton)."""
    r = httpx.post(
        f"{config.REMEDIATION_URL}/remediate",
        json={"action": "restart_service", "service": service, "reason": reason},
        headers={"X-Remediation-Token": config.REMEDIATION_TOKEN},
        timeout=90.0,
    )
    r.raise_for_status()
    return r.json()


# --- LLM : assistant RAG (il n'a aucun accès système) --------------------------------

def llm_explain(incident: dict) -> dict:
    r = httpx.post(f"{config.ASSISTANT_URL}/api/explain",
                   json={"incident": incident}, timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()


def llm_decide(symptom: str, health: dict, candidates: list) -> dict:
    r = httpx.post(f"{config.ASSISTANT_URL}/api/decide",
                   json={"symptom": symptom, "health": health, "candidates": candidates},
                   timeout=config.LLM_TIMEOUT)
    r.raise_for_status()
    return r.json()
