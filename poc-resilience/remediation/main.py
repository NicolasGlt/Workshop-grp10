"""remediation-engine — exécute la réponse automatique via des playbooks Ansible.

Reçoit une décision du ml-detector (POST /remediate, protégé par token) et lance
le playbook correspondant. Accès volontairement restreint :
  - pas de port publié (réseau interne remnet uniquement) ;
  - en-tête X-Remediation-Token obligatoire ;
  - garde-fous : IP jamais bloquées (SAFE_IPS), TTL sur les blocages,
    anti-boucle sur les redémarrages.

Le subject autorise ce composant à disposer de droits élevés sur les conteneurs
(accès au socket Docker) — c'est le SEUL composant dans ce cas.
"""

import json
import logging
import os
import re
import subprocess
from collections import Counter
import threading
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

TOKEN = os.environ.get("REMEDIATION_TOKEN", "change-me")
ANSIBLE_DIR = os.getenv("ANSIBLE_DIR", "/srv/ansible")
BLOCKFILE = os.getenv("BLOCKFILE", "/shared/blocklist.map")
BLOCK_TTL = int(os.getenv("BLOCK_TTL", "300"))            # déblocage auto après 5 min
MAX_RESTARTS = int(os.getenv("MAX_RESTARTS", "3"))        # anti-boucle
RESTART_WINDOW = int(os.getenv("RESTART_WINDOW", "600"))
SAFE_IPS = set(filter(None, os.getenv("SAFE_IPS", "127.0.0.1").split(",")))
TOP_TALKER_WINDOW = os.getenv("TOP_TALKER_WINDOW", "60s")
# IP cliente dans les deux formats du WAF : access log nginx et audit ModSecurity (JSON)
_CLIENT_IP = re.compile(r'^(\d{1,3}(?:\.\d{1,3}){3}) - |"client_ip":"(\d{1,3}(?:\.\d{1,3}){3})"')

class JsonFormatter(logging.Formatter):
    def format(self, r):
        p = {"ts": datetime.now(timezone.utc).isoformat(), "level": r.levelname, "event": r.getMessage()}
        p.update(getattr(r, "fields", {}))
        return json.dumps(p, default=str, ensure_ascii=False)

_h = logging.StreamHandler(); _h.setFormatter(JsonFormatter())
log = logging.getLogger("remediation"); log.addHandler(_h); log.setLevel(logging.INFO); log.propagate = False
def audit(event, **f): log.info(event, extra={"fields": f})

STATE = {"actions_total": 0, "blocks_active": 0}
ACTIONS = {}                       # (action,result) -> count, pour /metrics
_blocks = {}                       # ip -> expiry epoch
_restarts = []                     # timestamps des redémarrages récents
_lock = threading.Lock()


def _count(action, result):
    ACTIONS[(action, result)] = ACTIONS.get((action, result), 0) + 1
    STATE["actions_total"] += 1


def run_playbook(name: str, extra: dict) -> tuple[bool, str]:
    cmd = ["ansible-playbook", f"playbooks/{name}"]
    for k, v in extra.items():
        cmd += ["-e", f"{k}={v}"]
    try:
        r = subprocess.run(cmd, cwd=ANSIBLE_DIR, capture_output=True, text=True, timeout=120)
        ok = r.returncode == 0
        return ok, (r.stdout[-500:] if ok else (r.stdout + r.stderr)[-500:])
    except Exception as e:
        return False, str(e)


def top_talker() -> str | None:
    """IP cliente la plus bruyante dans les logs du WAF sur la dernière minute.

    Lu directement par le socket (docker logs) : sous flood, la chaîne Alloy -> Loki
    perd l'essentiel des lignes (mesuré le 21/10 : ~70 lignes/min sur 47 000 requêtes),
    on bloquerait un client légitime. Les logs du conteneur, eux, sont complets.
    """
    try:
        cid = subprocess.run(["docker", "ps", "-q", "-f", "label=com.docker.compose.service=waf"],
                             capture_output=True, text=True, timeout=10).stdout.split()
        if not cid:
            return None
        logs = subprocess.run(["docker", "logs", "--since", TOP_TALKER_WINDOW, cid[0]],
                              capture_output=True, text=True, timeout=30)
    except Exception as e:
        audit("top_talker_failed", error=str(e))
        return None
    counts = Counter()
    for line in (logs.stdout + logs.stderr).splitlines():
        m = _CLIENT_IP.search(line)
        if m:
            counts[m.group(1) or m.group(2)] += 1
    for ip, n in counts.most_common():
        if ip not in SAFE_IPS:
            audit("top_talker", ip=ip, requests=n, window=TOP_TALKER_WINDOW,
                  others=dict(counts.most_common(3)))
            return ip
    return None


def ttl_janitor():
    """Déblocage automatique des IP dont le TTL a expiré."""
    while True:
        now = time.time()
        expired = [ip for ip, exp in list(_blocks.items()) if exp <= now]
        for ip in expired:
            ok, out = run_playbook("unblock_ip.yml", {"ip": ip, "blockfile": BLOCKFILE})
            with _lock:
                _blocks.pop(ip, None)
                STATE["blocks_active"] = len(_blocks)
            audit("ip_unblocked_ttl", ip=ip, ok=ok)
        time.sleep(10)


app = FastAPI(title="Remediation Engine", version="1.0.0")


@app.on_event("startup")
def _start():
    # Blocages hérités d'une instance précédente (la blocklist est un volume) : sans ça,
    # ils ne seraient jamais levés. On leur applique le TTL à partir de maintenant.
    try:
        with open(BLOCKFILE) as f:
            for ip in re.findall(r'^"([^"]+)" 1;', f.read(), re.M):
                _blocks[ip] = time.time() + BLOCK_TTL
        STATE["blocks_active"] = len(_blocks)
    except FileNotFoundError:
        pass
    threading.Thread(target=ttl_janitor, daemon=True).start()
    audit("startup", block_ttl=BLOCK_TTL, max_restarts=MAX_RESTARTS, safe_ips=sorted(SAFE_IPS))


class Decision(BaseModel):
    action: str = Field(pattern="^(block_ip|unblock_ip|restart_service)$")
    ip: str | None = None
    service: str | None = Field(default=None, pattern="^[a-z0-9-]{1,40}$")
    reason: str | None = None


def check_token(tok: str):
    if tok != TOKEN:
        raise HTTPException(status_code=401, detail="Token de remédiation invalide")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/status")
def status():
    return {"blocks_active": sorted(_blocks.keys()), "actions_total": STATE["actions_total"]}


@app.post("/remediate")
def remediate(d: Decision, x_remediation_token: str = Header(default="")):
    check_token(x_remediation_token)

    if d.action == "block_ip":
        if d.ip == "auto":
            d.ip = top_talker()
        if not d.ip:
            raise HTTPException(status_code=422, detail="ip requise (aucun émetteur identifié)")
        if d.ip in SAFE_IPS:
            audit("block_refused_safe_ip", ip=d.ip); _count("block_ip", "refused")
            return {"status": "refused", "reason": "ip protégée (safe list)"}
        ok, out = run_playbook("block_ip.yml", {"ip": d.ip, "blockfile": BLOCKFILE})
        if ok:
            with _lock:
                _blocks[d.ip] = time.time() + BLOCK_TTL
                STATE["blocks_active"] = len(_blocks)
        _count("block_ip", "ok" if ok else "error")
        audit("block_ip", ip=d.ip, reason=d.reason, ok=ok, ttl=BLOCK_TTL)
        return {"status": "applied" if ok else "error", "action": "block_ip", "ip": d.ip, "ttl": BLOCK_TTL, "detail": out}

    if d.action == "unblock_ip":
        ok, out = run_playbook("unblock_ip.yml", {"ip": d.ip, "blockfile": BLOCKFILE})
        with _lock:
            _blocks.pop(d.ip, None); STATE["blocks_active"] = len(_blocks)
        _count("unblock_ip", "ok" if ok else "error")
        return {"status": "applied" if ok else "error", "action": "unblock_ip", "ip": d.ip}

    if d.action == "restart_service":
        svc = d.service or "api"
        now = time.time()
        global _restarts
        _restarts = [t for t in _restarts if now - t < RESTART_WINDOW]
        if len(_restarts) >= MAX_RESTARTS:
            audit("restart_refused_loop_guard", service=svc, count=len(_restarts)); _count("restart_service", "refused")
            return {"status": "refused", "reason": f"anti-boucle : {MAX_RESTARTS} redémarrages déjà en {RESTART_WINDOW}s"}
        ok, out = run_playbook("restart_service.yml", {"service": svc})
        if ok:
            _restarts.append(now)
        _count("restart_service", "ok" if ok else "error")
        audit("restart_service", service=svc, reason=d.reason, ok=ok)
        return {"status": "applied" if ok else "error", "action": "restart_service", "service": svc, "detail": out}


@app.get("/metrics")
def metrics():
    out = [
        "# TYPE remediation_actions_total counter",
    ]
    for (a, r), c in ACTIONS.items():
        out.append(f'remediation_actions_total{{action="{a}",result="{r}"}} {c}')
    out += [
        "# TYPE remediation_blocks_active gauge",
        f'remediation_blocks_active {STATE["blocks_active"]}',
    ]
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("\n".join(out) + "\n")
