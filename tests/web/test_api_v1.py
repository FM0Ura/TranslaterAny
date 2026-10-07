from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from translaterany.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    app = create_app(data_dir=data_dir, config_path=config_path, start_worker=False)
    return TestClient(app)


def test_api_v1_pipeline(client: TestClient) -> None:
    resp = client.get("/api/v1/pipeline")
    assert resp.status_code == 200
    data = resp.json()
    assert "stages" in data
    assert any(s["name"] == "scene_analysis" for s in data["stages"])

    # Toggle da etapa
    toggle_resp = client.put(
        "/api/v1/pipeline/toggle",
        json={"stage_name": "scene_analysis", "enabled": False},
    )
    assert toggle_resp.status_code == 200
    t_data = toggle_resp.json()
    stage = next(s for s in t_data["stages"] if s["name"] == "scene_analysis")
    assert stage["enabled"] is False


def test_api_v1_doctor(client: TestClient) -> None:
    resp = client.get("/api/v1/doctor")
    assert resp.status_code == 200
    data = resp.json()
    assert "checks" in data
    assert isinstance(data["checks"], list)


def test_api_v1_config(client: TestClient) -> None:
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    cfg = resp.json()
    assert cfg["source_language"] == "en"
    assert cfg["target_language"] == "pt-BR"

    # Atualiza config
    cfg["source_language"] = "ja"
    put_resp = client.put("/api/v1/config", json=cfg)
    assert put_resp.status_code == 200
    assert put_resp.json()["source_language"] == "ja"


def test_api_v1_series_and_memory(client: TestClient, tmp_path: Path) -> None:
    # Cria estrutura de teste
    series_dir = tmp_path / "data" / "series" / "test-anime"
    ep_dir = series_dir / "episodes" / "S01E01"
    ep_dir.mkdir(parents=True)
    (series_dir / "manifest.json").write_text('{"stages": {}}', encoding="utf-8")
    (ep_dir / "manifest.json").write_text('{"stages": {}}', encoding="utf-8")

    # List series
    list_resp = client.get("/api/v1/series")
    assert list_resp.status_code == 200
    series = list_resp.json()
    assert len(series) == 1
    assert series[0]["key"] == "test-anime"

    # Get series detail
    detail_resp = client.get("/api/v1/series/test-anime")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["key"] == "test-anime"

    # Get memory
    mem_resp = client.get("/api/v1/series/test-anime/memory")
    assert mem_resp.status_code == 200
    assert mem_resp.json()["characters"] == []

    # Post character
    char_payload = {
        "name": "Takashi Komuro",
        "role": "main",
        "gender": "male",
        "source": "user",
    }
    c_resp = client.post("/api/v1/series/test-anime/memory/characters", json=char_payload)
    assert c_resp.status_code == 200

    # Delete character
    del_c_resp = client.delete("/api/v1/series/test-anime/memory/characters/Takashi Komuro")
    assert del_c_resp.status_code == 200

    # Post glossary
    glossary_payload = {
        "term": "Them",
        "translation": "Eles",
        "category": "general",
        "source": "user",
    }
    g_resp = client.post("/api/v1/series/test-anime/memory/glossary", json=glossary_payload)
    assert g_resp.status_code == 200

    # Delete glossary
    del_g_resp = client.delete("/api/v1/series/test-anime/memory/glossary/Them")
    assert del_g_resp.status_code == 200


def test_api_v1_jobs_lifecycle(client: TestClient) -> None:
    # Cria job
    run_resp = client.post(
        "/api/v1/jobs/run",
        json={"series_key": "test-anime", "episode_key": "S01E01"},
    )
    assert run_resp.status_code == 200
    job = run_resp.json()
    job_id = job["id"]
    assert job["status"] == "pending"

    # Pause
    p_resp = client.post(f"/api/v1/jobs/{job_id}/pause")
    assert p_resp.status_code == 200
    assert p_resp.json()["status"] == "paused"

    # Resume
    r_resp = client.post(f"/api/v1/jobs/{job_id}/resume")
    assert r_resp.status_code == 200
    assert r_resp.json()["status"] in ("pending", "running")

    # Cancel
    c_resp = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert c_resp.status_code == 200
    assert c_resp.json()["status"] == "cancelled"

    # List jobs
    list_jobs = client.get("/api/v1/jobs")
    assert list_jobs.status_code == 200
    assert any(j["id"] == job_id for j in list_jobs.json())
