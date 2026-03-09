import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "blueprint"}

def test_hardware_capabilities():
    response = client.get("/api/system/capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "gpu_available" in data
    assert "usable_memory_gb" in data
    assert "max_model_size" in data
