"""Les deux boucles autonomes de l'orchestrateur (sans intervention humaine).

1. ATTAQUE (flood) — le LLM est INFORMATIF
   La boucle déterministe ml-detector -> remediation (block_ip) reste inchangée et instantanée :
   l'orchestrateur ne s'y insère PAS. Il OBSERVE a posteriori qu'un blocage a eu lieu, puis
   demande au LLM d'EXPLIQUER la décision (via le RAG). Le LLM ne décide ni n'exécute rien.

2. CHAOS (service tombé) — le LLM est DÉCIDEUR du service
   L'orchestrateur détecte la dégradation (santé Docker), demande au LLM QUEL service relancer
   (RAG sur l'architecture api->bank + l'état de santé), VALIDE la réponse contre un catalogue
   fermé, puis appelle l'API de remédiation. Le LLM ne touche jamais le système.
"""
import threading
import time

from . import clients, config, events


# ---------------------------------------------------------------- ATTAQUE (informatif)

def attack_observer():
    """Observe les blocages déterministes et fait expliquer la décision par le LLM."""
    # On part de l'état courant : on n'explique pas des blocages antérieurs au démarrage.
    seen = set(clients.remediation_status().get("blocks_active", []))
    while True:
        try:
            blocks = set(clients.remediation_status().get("blocks_active", []))
            nouveaux = blocks - seen
            for ip in sorted(nouveaux):
                _explain_block(ip)
            seen = blocks
        except Exception as e:
            events.emit("info", "attaque", "Observateur attaque : erreur", str(e))
        time.sleep(config.ATTACK_POLL)


def _explain_block(ip: str):
    sig = clients.attack_signals()
    events.emit("alert", "attaque",
                f"Flood détecté — IP {ip} bloquée",
                "Boucle déterministe ml-detector → remediation (block_ip). "
                "Action instantanée, hors chemin du LLM.",
                target_ip=ip, signals=sig)
    incident = {
        "type": "flood_http",
        "action": "block_ip",
        "target_ip": ip,
        "signals": sig,
        "chemin": "déterministe (ml-detector → remediation), le LLM n'est pas dans la boucle",
    }
    try:
        res = clients.llm_explain(incident)
        events.emit("explanation", "attaque",
                    "Explication du LLM (via RAG)",
                    res.get("explanation", ""),
                    sources=res.get("sources", []), grounded=res.get("grounded"))
    except Exception as e:
        events.emit("info", "attaque", "Explication LLM indisponible", str(e))


# ---------------------------------------------------------------- CHAOS (décideur)

_state = {"handling": False, "cooldown_until": 0.0}


def chaos_detector():
    """Détecte une dégradation de service et pilote la reprise décidée par le LLM."""
    prev_degraded = set(clients.degraded_services(clients.health_snapshot()))
    while True:
        try:
            snap = clients.health_snapshot()
            degraded = set(clients.degraded_services(snap))
            # déclenchement sur TRANSITION : un service sain qui devient dégradé
            nouveaux = degraded - prev_degraded
            prev_degraded = degraded
            now = time.time()
            if nouveaux and not _state["handling"] and now >= _state["cooldown_until"]:
                _state["handling"] = True
                try:
                    _handle_chaos(sorted(nouveaux), snap)
                finally:
                    _state["handling"] = False
                    _state["cooldown_until"] = time.time() + config.CHAOS_COOLDOWN
        except Exception as e:
            events.emit("info", "chaos", "Détecteur chaos : erreur", str(e))
        time.sleep(config.CHAOS_POLL)


def _handle_chaos(degraded: list, snap: dict):
    symptom = "Service(s) dégradé(s) : " + ", ".join(
        f"{s} ({snap[s]['state']}/{snap[s]['health']})" for s in degraded
    )
    events.emit("alert", "chaos", "Dégradation de service détectée", symptom,
                degraded=degraded, health=snap)

    # 1) le LLM PROPOSE (RAG sur l'architecture + état de santé) — sortie JSON contrainte
    chosen, source, reason, llm_res = None, "fallback", "", {}
    try:
        llm_res = clients.llm_decide(symptom, snap, degraded)
        decision = llm_res.get("decision")
        events.emit("reasoning", "chaos", "Raisonnement du LLM (via RAG)",
                    (decision and f"Propose : restart_service {decision.get('service')} — "
                                  f"{decision.get('reason','')}") or
                    "Le LLM n'a pas renvoyé de décision exploitable.",
                    decision=decision, raw=llm_res.get("raw", ""),
                    sources=llm_res.get("sources", []), grounded=llm_res.get("grounded"))
        # 2) l'orchestrateur VALIDE contre le catalogue fermé
        chosen, source, reason = _validate(decision, degraded)
    except Exception as e:
        events.emit("info", "chaos", "Décision LLM indisponible — repli déterministe", str(e))

    if chosen is None:
        # repli sûr : le service réellement dégradé (reprise garantie sans humain)
        chosen, source = degraded[0], "fallback"
        reason = reason or "repli : service observé dégradé"

    events.emit("action", "chaos",
                f"Décision retenue : redémarrer « {chosen} » ({_src_label(source)})",
                reason, service=chosen, decided_by=source)

    # 3) l'orchestrateur AGIT via l'API de remédiation (jeton + anti-boucle)
    try:
        rep = clients.restart_service(chosen, f"[{source}] {reason}"[:200])
        events.emit("action", "chaos", "Remédiation appelée (API fermée)",
                    f"status={rep.get('status')}", response=rep)
    except Exception as e:
        events.emit("info", "chaos", "Échec de l'appel de remédiation", str(e))
        return

    # 4) vérification de la reprise (santé Docker)
    ok = _wait_recovery(chosen)
    events.emit("recovery", "chaos",
                f"Service « {chosen} » {'rétabli' if ok else 'non rétabli dans le délai'}",
                f"state/health après remédiation : {clients.service_state(chosen)['state']}/"
                f"{clients.service_state(chosen)['health']}", recovered=ok, service=chosen)

    # 5) le LLM informe (explication finale)
    try:
        res = clients.llm_explain({
            "type": "service_degraded", "action": "restart_service", "service": chosen,
            "symptom": symptom, "decided_by": source, "reason": reason, "recovered": ok,
        })
        events.emit("explanation", "chaos", "Explication du LLM (via RAG)",
                    res.get("explanation", ""),
                    sources=res.get("sources", []), grounded=res.get("grounded"))
    except Exception as e:
        events.emit("info", "chaos", "Explication LLM indisponible", str(e))


def _validate(decision, degraded):
    """Garde-fou de l'orchestrateur : on n'exécute que ce qui est dans le catalogue fermé.

    Renvoie (service|None, source, reason).
    """
    if not decision:
        return None, "fallback", ""
    if decision.get("action") != "restart_service":
        return None, "fallback", f"action hors catalogue : {decision.get('action')!r}"
    svc = decision.get("service", "")
    reason = decision.get("reason", "")
    if svc not in config.ALLOWED_RESTART:
        return None, "fallback", f"service hors whitelist : {svc!r}"
    if svc not in degraded:
        # Le LLM désigne un service sain : on ne redémarre pas à l'aveugle un service qui va bien.
        return None, "fallback", f"service proposé ({svc}) non dégradé — rejeté par garde-fou"
    return svc, "llm", reason


def _wait_recovery(service: str) -> bool:
    deadline = time.time() + config.RECOVERY_TIMEOUT
    while time.time() < deadline:
        s = clients.service_state(service)
        if s["state"] == "running" and s["health"] in ("healthy", "none"):
            return True
        time.sleep(2)
    return False


def _src_label(source: str) -> str:
    return "décidé par le LLM" if source == "llm" else "repli déterministe"


def start():
    threading.Thread(target=attack_observer, daemon=True, name="attack-observer").start()
    threading.Thread(target=chaos_detector, daemon=True, name="chaos-detector").start()
    events.emit("info", "chaos", "Orchestrateur démarré",
                f"Services suivis : {', '.join(config.MONITORED_SERVICES)}")
