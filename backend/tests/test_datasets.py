import pytest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_list_datasets():
    response = client.get("/api/datasets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_create_snapshot_edge_case():
    # Attempting to snapshot a non-existent dataset should return 404
    response = client.post("/api/datasets/fake_dataset_123/snapshots")
    assert response.status_code == 404

def test_list_snapshots_edge_case():
    # Attempting to list snapshots for a non-existent dataset should return 404
    response = client.get("/api/datasets/fake_dataset_123/snapshots")
    assert response.status_code == 404

def test_restore_snapshot_edge_case():
    # Attempting to restore a non-existent snapshot should return 404
    response = client.post("/api/datasets/fake_dataset_123/snapshots/fake_snapshot/restore")
    assert response.status_code == 404
