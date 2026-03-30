"""Tests for selected helpers inside current Studio API modules."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from sage.studio.api import canvas as api
from sage.studio.api.app import app

client = TestClient(app)


def test_get_user_pipelines_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "_get_sage_dir", lambda: tmp_path)
    path = api.get_user_pipelines_dir("u1")
    assert path == tmp_path / "users" / "u1" / "pipelines"
    assert path.exists()


def test_submit_pipeline_persists_file(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "get_user_pipelines_dir", lambda _uid: tmp_path)

    payload = {"name": "Flow", "nodes": [], "edges": []}

    response = client.post("/api/pipeline/submit", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "success"

    saved_files = list(tmp_path.glob("pipeline_*.json"))
    assert saved_files, "Pipeline file should be saved"
    loaded = json.loads(saved_files[0].read_text())
    assert loaded["name"] == "Flow"


def test_data_root_exists(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(api, "get_common_user_data_dir", lambda: tmp_path)
    root = api._data_root()
    assert root.exists()
