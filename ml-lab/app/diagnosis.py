from collections import Counter
from .normalizer import normalize_message

ACTIONS={
 "payment-api":"restart_payment_api", "postgres":"restart_postgres",
 "frontend":"restart_frontend", "bank-api":"open_bank_circuit_breaker",
 "nginx":"reload_nginx", "security":"enable_temporary_rate_limit",
 "unknown":"collect_evidence_and_alert"
}

def diagnose(window, result):
    if not result["is_anomaly"]:
        return {"component":"none","action":"none","reason":"comportement normal"}
    h=window.health
    if h.get("postgres",1)<0.5: component="postgres"
    elif h.get("payment-api",1)<0.5: component="payment-api"
    elif h.get("frontend",1)<0.5: component="frontend"
    elif h.get("bank-api",1)<0.5: component="bank-api"
    else:
        messages=" ".join(normalize_message(e.message) for e in window.events)
        if "rate limit" in messages or "login failed" in messages or "request denied" in messages: component="security"
        elif window.resources.get("memory_pct",0)>90 or window.resources.get("cpu_pct",0)>90: component="payment-api"
        else: component="unknown"
    return {"component":component,"action":ACTIONS[component],"reason":"action abstraite issue de la liste blanche; aucune commande n'est exécutée"}
