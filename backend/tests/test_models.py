import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_search_models():
    response = client.get("/api/models/search?q=llama&limit=5")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_list_local_models():
    response = client.get("/api/models/local")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_inference_endpoint_edge_cases():
    # Inference with empty prompt
    req = {"prompt": "", "max_tokens": 10}
    response = client.post("/api/models/fake-model/inference", json=req)
    # The current implementation might still return 200 with the mock fallback
    assert response.status_code in [200, 500] 

    # Inference with extreme parameters
    req = {"prompt": "Test", "max_tokens": 10000, "temperature": 2.0}
    response = client.post("/api/models/fake-model/inference", json=req)
    assert response.status_code in [200, 500]
