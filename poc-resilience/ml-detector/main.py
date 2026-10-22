"""ml-detector — détection d'anomalies (Local Outlier Factor) + déclenchement de la remédiation.

Boucle :
  1. toutes les POLL_SECONDS, construit un vecteur de features depuis Prometheus
     (req/s, taux d'erreurs 5xx, latence p95, taux de 4xx) ;
  2. phase d'apprentissage : collecte WARMUP_SAMPLES points « normaux » puis entraîne
     un Local Outlier Factor (mode novelty) sur les features passées en log puis
     standardisées. Contrairement à un Isolation Forest, dont les coupes restent dans
     la plage apprise, le LOF compare la densité locale : plus un point s'éloigne de
     la normale, plus son score chute, donc un flood x100 n'est pas écrêté ;
     l'entraînement attend une normale qui varie (trafic réel ou service traffic) ;
  3. ensuite, score chaque point ; si anomalie sur ANOMALY_STREAK points consécutifs,
     décide une action (block_ip si flood, sinon restart_service) et appelle le
     moteur de remédiation — SANS intervention humaine ;
  4. période de refroidissement (COOLDOWN_SECONDS) après chaque action.

Expose /metrics (score, état, anomalies, remédiations déclenchées) et /health.
En mode block_ip, l'émetteur à bloquer est désigné par le moteur de remédiation (ip="auto").
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
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

PROM_URL = os.getenv("PROM_URL", "http://prometheus:9090")
REMEDIATION_URL = os.getenv("REMEDIATION_URL", "http://remediation:8000")
REMEDIATION_TOKEN = os.getenv("REMEDIATION_TOKEN", "change-me")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "5"))
WARMUP_SAMPLES = int(os.getenv("WARMUP_SAMPLES", "24"))     # ~2 min à 5 s
ANOMALY_STREAK = int(os.getenv("ANOMALY_STREAK", "3"))      # 3 points consécutifs
COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "60"))
CONTAMINATION = float(os.getenv("CONTAMINATION", "0.02"))
AUTO_REMEDIATE = os.getenv("AUTO_REMEDIATE", "true").lower() == "true"
# Action en cas de flood :
#   - "block_ip" (défaut) : bloque l'IP qui émet le flood, désignée par la remédiation
#   - "restart"          : redémarre le service visé
FLOOD_ACTION = os.getenv("FLOOD_ACTION", "block_ip")

# Garde-fou complémentaire au modèle (sujet §3.3 : la détection reste du ML, on borne seulement
# l'ACTION) : on ne remédie une anomalie que si un symptôme réel l'accompagne — flood, taux
# d'erreur ou latence au-delà d'un plancher. Une anomalie sans symptôme (plateforme au repos)
# est journalisée mais ne déclenche aucune remédiation parasite.
ERR_RATIO_FLOOR = float(os.getenv("ERR_RATIO_FLOOR", "0.05"))     # 5 % de réponses 5xx
P95_LATENCY_FLOOR = float(os.getenv("P95_LATENCY_FLOOR", "1.0"))  # secondes (normale ~0,1 s)

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


def _is_flood(feat: dict, baseline_mean: dict) -> bool:
    return feat["req_rate"] > max(5.0, 3 * baseline_mean.get("req_rate", 0) + 1)


def warrants_action(feat: dict, baseline_mean: dict) -> bool:
    """Symptôme réel justifiant une remédiation (complément du modèle, cf. §3.3).

    Le modèle détecte l'anomalie ; ce garde-fou évite d'agir sur une anomalie sans
    symptôme (plateforme au repos), qui provoquerait une remédiation parasite.
    """
    return (_is_flood(feat, baseline_mean)
            or feat["err_ratio"] >= ERR_RATIO_FLOOR
            or feat["p95_latency"] >= P95_LATENCY_FLOOR)


def decide_action(feat: dict, baseline_mean: dict) -> dict:
    """Choisit la remédiation selon le signal dominant."""
    is_flood = _is_flood(feat, baseline_mean)
    if is_flood and FLOOD_ACTION == "block_ip":
        # L'émetteur est désigné par le moteur de remédiation, qui lit les logs du WAF
        # directement (complets), plutôt que Loki (lignes perdues sous flood).
        return {"action": "block_ip", "ip": "auto", "reason": "flood_http"}
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
                if float(np.ptp(X[:, 0])) == 0.0:
                    # Normale sans aucune variation (stack au repos) : un modèle appris
                    # là-dessus ne distingue rien. On attend du trafic.
                    audit("training_deferred", reason="no_variance", samples=len(window))
                    window.clear()
                    time.sleep(POLL_SECONDS)
                    continue
                model = make_pipeline(
                    FunctionTransformer(np.log1p),
                    StandardScaler(),
                    LocalOutlierFactor(n_neighbors=min(20, len(X) - 1), novelty=True,
                                       contamination=CONTAMINATION),
                ).fit(X)
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
            if not warrants_action(feat, baseline_mean):
                # Anomalie détectée par le modèle mais sans symptôme réel : on n'agit pas,
                # pour ne pas casser le service par une remédiation parasite (faux positif R11).
                audit("remediation_skipped_no_symptom", features=feat)
                streak = 0
                time.sleep(POLL_SECONDS)
                continue
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
