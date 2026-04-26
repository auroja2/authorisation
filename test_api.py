import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)) + "/backend")

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def get_token(username="admin", password="admin123"):
    r = client.post("/auth/token", data={"username": username, "password": password})
    return r.json()["access_token"]


def auth_headers(role="admin"):
    pwd = "admin123" if role == "admin" else "analyst123"
    token = get_token(role, pwd)
    return {"Authorization": f"Bearer {token}"}


# ── Auth tests ────────────────────────────────────────────────────────────────

def test_login_success():
    r = client.post("/auth/token", data={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_login_failure():
    r = client.post("/auth/token", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_me_endpoint():
    r = client.get("/auth/me", headers=auth_headers())
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_unauthorized_access():
    r = client.get("/transactions")
    assert r.status_code == 401


# ── Generator tests ───────────────────────────────────────────────────────────

def test_generate():
    r = client.post("/generate", json={"num_transactions": 20, "seed": 42}, headers=auth_headers())
    assert r.status_code == 200
    data = r.json()
    assert data["platform_count"] == 20
    assert data["bank_count"] > 0


def test_generate_role_restriction():
    # analyst can generate
    r = client.post("/generate", json={"num_transactions": 10, "seed": 1}, headers=auth_headers("analyst"))
    assert r.status_code == 200


# ── Reconciliation tests ──────────────────────────────────────────────────────

def test_reconcile_without_data():
    from main import _state
    _state["platform"] = []
    r = client.post("/reconcile", headers=auth_headers())
    assert r.status_code == 400


def test_full_pipeline():
    headers = auth_headers()
    # Generate
    r = client.post("/generate", json={"num_transactions": 30, "seed": 99}, headers=headers)
    assert r.status_code == 200

    # Reconcile
    r = client.post("/reconcile", headers=headers)
    assert r.status_code == 200
    report = r.json()
    assert "matched" in report
    assert "records" in report
    assert report["total_platform"] == 30

    # Report
    r = client.get("/report", headers=headers)
    assert r.status_code == 200

    # Model info (trained after reconcile)
    r = client.get("/predict/model-info", headers=headers)
    assert r.json()["status"] == "trained"


# ── Reconciler unit tests ─────────────────────────────────────────────────────

def test_reconciler_direct():
    from reconciler import reconcile
    from models import Transaction, Currency
    platform = [
        Transaction(id="P-1", amount=1000, currency=Currency.INR, date="2024-01-15", description="Test", reference="REF1"),
        Transaction(id="P-2", amount=500, currency=Currency.INR, date="2024-01-10", description="Test2", reference="REF2"),
    ]
    bank = [
        Transaction(id="B-1", amount=1000, currency=Currency.INR, date="2024-01-15", description="Test", reference="REF1"),
        # REF2 missing
    ]
    report = reconcile(platform, bank)
    statuses = [r.status.value for r in report.records]
    assert "matched" in statuses
    assert "missing_in_bank" in statuses


def test_generator_deterministic():
    from generator import generate_datasets
    p1, b1 = generate_datasets(20, seed=7)
    p2, b2 = generate_datasets(20, seed=7)
    assert [t.id for t in p1] == [t.id for t in p2]
