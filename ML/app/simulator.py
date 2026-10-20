from datetime import datetime, timezone
import random
import uuid
from .schema import LogEvent, Window

SERVICES = ["frontend", "payment-api", "bank-api", "postgres", "nginx", "modsecurity"]
SCENARIOS = ["normal", "api_down", "db_down", "frontend_down", "bank_timeout", "traffic_flood", "auth_abuse", "waf_attack", "memory_pressure", "latency_spike", "unknown_runtime", "silent_failure"]

NORMAL_MESSAGES = {
 "frontend": ["GET / dashboard rendered", "assets bundle served", "payment form displayed"],
 "payment-api": ["GET /health 200", "transaction {id} validated", "account {id} history returned", "login succeeded for account {id}"],
 "bank-api": ["bank validation accepted reference {id}", "balance check completed", "bank health check ok"],
 "postgres": ["transaction committed in {n} ms", "connection returned to pool", "query completed in {n} ms"],
 "nginx": ["request forwarded status 200", "tls connection completed", "upstream responded in {n} ms"],
 "modsecurity": ["request inspected no rule matched", "audit cycle completed"],
}

def _msg(template, rng):
    return template.format(id=str(uuid.UUID(int=rng.getrandbits(128))), n=rng.randint(2, 80), ip=f"10.0.0.{rng.randint(2,250)}")

def _event(service, level, message, rng, status=None, latency=None):
    return LogEvent(datetime.now(timezone.utc).isoformat(), service, level, _msg(message, rng), status, latency)

def generate_window(scenario="normal", seed=None, index=0):
    if scenario not in SCENARIOS: raise ValueError(f"Scenario inconnu: {scenario}")
    rng = random.Random((seed or 0) * 1000003 + index)
    health = {s: 1.0 for s in ["frontend", "payment-api", "bank-api", "postgres", "nginx"]}
    resources = {"cpu_pct": rng.uniform(12, 45), "memory_pct": rng.uniform(25, 58), "connections": rng.uniform(5, 28)}
    events=[]
    base_count=max(8, int(rng.gauss(34, 7)))
    for _ in range(base_count):
        service=rng.choice(SERVICES)
        message=rng.choice(NORMAL_MESSAGES[service])
        status=200 if service in {"frontend","payment-api","nginx"} else None
        latency=max(2, rng.gauss(75, 22)) if status else None
        events.append(_event(service, "INFO", message, rng, status, latency))

    def many(service, level, template, count, status=None, latency=None):
        for _ in range(count): events.append(_event(service, level, template, rng, status, latency() if callable(latency) else latency))

    if scenario == "api_down":
        health["payment-api"]=0.0
        many("nginx","ERROR","upstream payment-api connection refused",rng.randint(22,55),502,lambda:rng.uniform(700,1800))
        many("payment-api","CRITICAL","worker terminated unexpectedly exit code 1",rng.randint(2,8))
    elif scenario == "db_down":
        health["postgres"]=0.0; health["payment-api"]=0.35
        many("payment-api","ERROR","database connection refused at 10.0.0.7",rng.randint(25,65),500,lambda:rng.uniform(600,2200))
        many("postgres","CRITICAL","postgres server is not accepting connections",rng.randint(4,12))
    elif scenario == "frontend_down":
        health["frontend"]=0.0
        many("nginx","ERROR","frontend upstream unavailable",rng.randint(18,45),502,lambda:rng.uniform(400,1400))
    elif scenario == "bank_timeout":
        health["bank-api"]=rng.uniform(0.0,0.4)
        many("payment-api","ERROR","bank validation timed out after 5000 ms",rng.randint(20,55),504,lambda:rng.uniform(4800,6500))
    elif scenario == "traffic_flood":
        resources["cpu_pct"]=rng.uniform(82,99); resources["connections"]=rng.uniform(300,900)
        many("nginx","WARNING","rate limit exceeded for 10.0.0.99",rng.randint(180,360),429,lambda:rng.uniform(50,900))
    elif scenario == "auth_abuse":
        many("payment-api","WARNING","login failed invalid credentials from 10.0.0.66",rng.randint(90,190),401,lambda:rng.uniform(20,180))
    elif scenario == "waf_attack":
        many("modsecurity","CRITICAL","request denied rule 942100 injection pattern from 10.0.0.77",rng.randint(45,120),403)
        many("nginx","WARNING","access forbidden by security policy",rng.randint(20,60),403)
    elif scenario == "memory_pressure":
        resources["memory_pct"]=rng.uniform(94,99.8); resources["cpu_pct"]=rng.uniform(50,90)
        many("payment-api","ERROR","memory allocation failed worker recycling",rng.randint(12,38),500)
    elif scenario == "latency_spike":
        resources["cpu_pct"]=rng.uniform(70,98)
        many("payment-api","WARNING","request processing unusually slow",rng.randint(45,100),200,lambda:rng.uniform(2500,8000))
    elif scenario == "unknown_runtime":
        # Vocabulaire volontairement absent de l'apprentissage.
        health["payment-api"]=rng.uniform(0.1,0.55)
        many("payment-api","CRITICAL","orphaned synchronizer channel entered a quantum deadlock",rng.randint(25,75),500,lambda:rng.uniform(900,4200))
        many("payment-api","ERROR","spectral worker lattice lost consensus epoch",rng.randint(10,35),500)
    elif scenario == "silent_failure":
        health["payment-api"]=0.15
        events=[e for e in events if e.service != "payment-api"]
        many("nginx","WARNING","upstream produced no response before deadline",rng.randint(5,15),504,lambda:rng.uniform(3500,6500))

    rng.shuffle(events)
    return Window(str(uuid.UUID(int=rng.getrandbits(128))), scenario, events, health, resources)
