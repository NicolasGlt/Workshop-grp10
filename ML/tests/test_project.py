from app.normalizer import normalize_message
from app.simulator import generate_window
from app.features import extract
from app.diagnosis import diagnose

def test_normalization():
    msg=normalize_message("Connection 10.0.0.4 transaction 12345")
    assert "<IP>" in msg and "<NUM>" in msg

def test_generator():
    w=generate_window("api_down",42,1)
    assert w.health["payment-api"] == 0.0
    assert len(w.events)>10

def test_features_finite():
    values,_=extract(generate_window("normal",42,2))
    assert all(v == v for v in values.values())

def test_whitelist_unknown():
    w=generate_window("normal",42,3)
    d=diagnose(w,{"is_anomaly":True})
    assert d["action"] in {"collect_evidence_and_alert","restart_payment_api","restart_postgres","restart_frontend","open_bank_circuit_breaker","reload_nginx","enable_temporary_rate_limit"}
