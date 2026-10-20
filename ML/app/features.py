from collections import Counter
import math
import numpy as np
from .normalizer import normalize_message

NUMERIC_FEATURES = [
 "event_count","error_ratio","warning_ratio","critical_ratio","unique_template_ratio",
 "service_count","dominant_template_ratio","template_entropy","http_4xx_ratio","http_5xx_ratio",
 "latency_mean","latency_p95","silent_service_count","min_health","health_mean",
 "cpu_pct","memory_pct","connections"
]

def _entropy(counts):
    total=sum(counts)
    if not total: return 0.0
    return -sum((c/total)*math.log(c/total+1e-12) for c in counts)

def extract(window):
    events=window.events; n=max(1,len(events))
    levels=Counter(e.level.upper() for e in events)
    templates=Counter(normalize_message(e.message) for e in events)
    services=Counter(e.service for e in events)
    status=[e.status_code for e in events if e.status_code is not None]
    lat=[e.latency_ms for e in events if e.latency_ms is not None]
    monitored={"frontend","payment-api","bank-api","postgres","nginx"}
    values={
      "event_count":len(events), "error_ratio":levels["ERROR"]/n,
      "warning_ratio":levels["WARNING"]/n, "critical_ratio":levels["CRITICAL"]/n,
      "unique_template_ratio":len(templates)/n, "service_count":len(services),
      "dominant_template_ratio":max(templates.values(),default=0)/n,
      "template_entropy":_entropy(templates.values()),
      "http_4xx_ratio":sum(400<=s<500 for s in status)/max(1,len(status)),
      "http_5xx_ratio":sum(500<=s<600 for s in status)/max(1,len(status)),
      "latency_mean":float(np.mean(lat)) if lat else 0.0,
      "latency_p95":float(np.percentile(lat,95)) if lat else 0.0,
      "silent_service_count":len(monitored-set(services)),
      "min_health":min(window.health.values()), "health_mean":float(np.mean(list(window.health.values()))),
      "cpu_pct":window.resources["cpu_pct"], "memory_pct":window.resources["memory_pct"],
      "connections":window.resources["connections"],
    }
    document=" ".join(normalize_message(e.message) for e in events)
    return values, document
