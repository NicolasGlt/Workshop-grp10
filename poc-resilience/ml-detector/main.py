"""ml-detector — détection d'anomalies (Isolation Forest) + déclenchement de la remédiation.

Boucle :
  1. toutes les POLL_SECONDS, construit un vecteur de features depuis Prometheus
     (req/s, taux d'erreurs 5xx, latence p95, taux de 4xx) ;
  2. phase d'apprentissage : collecte WARMUP_SAMPLES points « normaux » puis entraîne
     un Isolation Forest ;
  3. ensuite, score chaque point ; si anomalie sur ANOMALY_STREAK points consécutifs,
     décide une action (block_ip si flood, sinon restart_service) et appelle le
     moteur de remédiation — SANS intervention humaine ;
  4. période de refroidissement (COOLDOWN_SECONDS) après chaque action.

Expose /metrics (score, état, anomalies, remédiations déclenchées) et /health.
Logue en JSON sur stdout (service=ml-detector -> Loki).
"""

import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone

import httpx
import numpy as np
from flask import Flask, Response
from sklearn.ensemble import IsolationForest

PROM_URL = os.getenv("PROM_URL", "http://prometheus:9090")
LOKI_URL = os.getenv("LOKI_URL", "http://loki:3100")
REMEDIATION_URL = os.getenv("REMEDIATION_URL", "http://remediation:8000")
REMEDIATION_TOKEN = os.getenv("REMEDIATION_TOKEN", "change-me")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
WARMUP_SAMPLES = int(os.getenv("WARMUP_SAMPLES", "24"))     # ~2 min à 5 s
ANOMALY_STREAK = int(os.getenv("ANOMALY_STREAK", "3"))      # 3 points consécutifs
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "60"))
CONTAMINATION = float(os.getenv("CONTAMINATION", "0.02"))
AUTO_REMEDIATE = os.getenv("AUTO_REMEDIATE", "true").lower() == "true"
# Action en cas de flood :
#   - "restart" (défaut) : redémarre le service — sûr en local mono-poste
#   - "block_ip"         : bloque l'IP source (vrai setup 2 PC, IP attaquant distincte)
FLOOD_ACTION = os.getenv("FLOOD_ACTION", "restart")

# --- logs JSON
class JsonFormatter(logging.Formatter):
    def format(self, r):
        p = {"ts": datetime.now(timezone.utc).isoformat(), "level": r.levelname, "event": r.getMessage()}
        p.update(getattr(r, "fields", {}))
        return json.dumps(p, default=str, ensure_ascii=False)

_h = logging.StreamHandler(); _h.setFormatter(JsonFormatter())
log = logging.getLogger("ml-detector"); log.addHandler(_h); log.setLevel(logging.INFO); log.propagate = False
def audit(event, **f): log.info(event, extra={"fields": f})

# --- état partagé (exposé en métriques)
STATE = {
    "trained": 0, "samples": 0, "anomaly": 0, "score": 0.0,
    "anomalies_total": 0, "remediations_total": 0,
    "last_features": {}, "last_action": "",
}
FEATURE_NAMES = ["req_rate", "err_ratio", "p95_latency", "client_err_rate"]


def prom_query(expr: str) -> float:
    try:
        r = httpx.get(f"{PROM_URL}/api/v1/query", params={"query": expr}, timeout=4.0)
        res = r.json()["data"]["result"]
        if not res:
            return 0.0
        v = float(res[0]["value"][1])
        return 0.0 if (v != v or v in (float("inf"), float("-inf"))) else v   # NaN/inf -> 0
    except Exception:
        return 0.0


def collect_features() -> dict:
    j = 'job="payment-api"'
    return {
        "req_rate": prom_query(f"sum(rate(http_requests_total{{{j}}}[1m]))"),
        "err_ratio": prom_query(
            f'sum(rate(http_requests_total{{{j},status=~"5.."}}[1m])) '
            f'/ clamp_min(sum(rate(http_requests_total{{{j}}}[1m])),1e-9)'),
        "p95_latency": prom_query(
            f"histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{j}}}[1m])))"),
        "client_err_rate": prom_query(f'sum(rate(http_requests_total{{{j},status=~"4.."}}[1m]))'),
    }


def top_attacker_ip() -> str | None:
    """Récupère l'IP la plus bruyante depuis les access logs du WAF (remote_addr réel)."""
    expr = ('topk(1, sum by (ip) (count_over_time('
            '{service="waf"} | regexp `^(?P<ip>[0-9.]+)` [1m])))')
    try:
        r = httpx.get(f"{LOKI_URL}/loki/api/v1/query", params={"query": expr}, timeout=4.0)
        res = r.json()["data"]["result"]
        if res:
            ip = res[0]["metric"].get("ip")
            if ip and ip not in ("127.0.0.1", "::1"):
                return ip
    except Exception:
        pass
    return None


def decide_action(feat: dict, baseline_mean: dict) -> dict:
    """Choisit la remédiation selon le signal dominant."""
    is_flood = feat["req_rate"] > max(5.0, 3 * baseline_mean.get("req_rate", 0) + 1)
    if is_flood and FLOOD_ACTION == "block_ip":
        ip = top_attacker_ip()
        if ip:
            return {"action": "block_ip", "ip": ip, "reason": "flood_http"}
    # Flood en mode restart, ou service dégradé (erreurs / latence) -> redémarrage ciblé
    reason = "flood_http" if is_flood else "service_degraded"
    return {"action": "restart_service", "service": "api", "reason": reason}


def remediate(decision: dict):
    STATE["last_action"] = decision["action"]
    if not AUTO_REMEDIATE:
        audit("remediation_skipped_dry_run", **decision)
        return
    try:
        r = httpx.post(f"{REMEDIATION_URL}/remediate", json=decision,
                       headers={"X-Remediation-Token": REMEDIATION_TOKEN}, timeout=60.0)
        r.raise_for_status()
        STATE["remediations_total"] += 1
        audit("remediation_triggered", result="ok", response=r.json(), **decision)
    except Exception as e:
        audit("remediation_failed", error=str(e), **decision)


def detector_loop():
    window = deque(maxlen=WARMUP_SAMPLES)
    model = None
    streak = 0
    cooldown_until = 0.0
    baseline_mean = {}
    audit("startup", prom=PROM_URL, warmup=WARMUP_SAMPLES, auto_remediate=AUTO_REMEDIATE)

    while True:
        feat = collect_features()
        vec = [feat[k] for k in FEATURE_NAMES]
        STATE["last_features"] = feat
        STATE["samples"] += 1

        if model is None:
            window.append(vec)
            if len(window) >= WARMUP_SAMPLES:
                X = np.array(window)
                model = IsolationForest(contamination=CONTAMINATION, random_state=42).fit(X)
                baseline_mean = {k: float(np.mean([w[i] for w in window])) for i, k in enumerate(FEATURE_NAMES)}
                STATE["trained"] = 1
                audit("model_trained", baseline=baseline_mean)
            time.sleep(POLL_SECONDS)
            continue

        score = float(model.score_samples([vec])[0])   # plus négatif = plus anormal
        pred = int(model.predict([vec])[0])             # -1 anomalie, 1 normal
        STATE["score"] = score
        is_anom = pred == -1
        STATE["anomaly"] = int(is_anom)

        if is_anom:
            streak += 1
            STATE["anomalies_total"] += 1
            audit("anomaly_detected", score=round(score, 4), streak=streak, features=feat)
        else:
            streak = 0

        now = time.time()
        if streak >= ANOMALY_STREAK and now >= cooldown_until:
            decision = decide_action(feat, baseline_mean)
            audit("decision", **decision, features=feat)
            remediate(decision)
            cooldown_until = now + COOLDOWN_SECONDS
            streak = 0

        time.sleep(POLL_SECONDS)


# --- serveur métriques / santé
app = Flask(__name__)

@app.get("/health")
def health():
    return {"status": "ok", "trained": bool(STATE["trained"])}

@app.get("/metrics")
def metrics():
    lines = [
        "# HELP ml_detector_trained 1 si le modèle est entraîné",
        "# TYPE ml_detector_trained gauge",
        f'ml_detector_trained {STATE["trained"]}',
        "# TYPE ml_detector_samples_total counter",
        f'ml_detector_samples_total {STATE["samples"]}',
        "# TYPE ml_detector_anomaly gauge",
        f'ml_detector_anomaly {STATE["anomaly"]}',
        "# TYPE ml_detector_anomaly_score gauge",
        f'ml_detector_anomaly_score {STATE["score"]}',
        "# TYPE ml_detector_anomalies_total counter",
        f'ml_detector_anomalies_total {STATE["anomalies_total"]}',
        "# TYPE ml_detector_remediations_total counter",
        f'ml_detector_remediations_total {STATE["remediations_total"]}',
    ]
    for k, v in STATE["last_features"].items():
        lines.append(f'ml_detector_feature{{name="{k}"}} {v}')
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


if __name__ == "__main__":
    threading.Thread(target=detector_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
