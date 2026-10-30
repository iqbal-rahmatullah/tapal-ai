from pathlib import Path

from fastapi.testclient import TestClient

from api.main import app

ROOT = Path(__file__).resolve().parent.parent
client = TestClient(app)


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "versi_model": "tapal-1.0"}


def test_web_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>TAPAL</title>" in r.text


def test_no_data_sampel_files():
    assert not [p for p in ROOT.rglob("*.dta") if "node_modules" not in p.parts]
