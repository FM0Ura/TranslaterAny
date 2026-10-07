from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from translaterany.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    series_dir = data_dir / "series" / "test-anime"
    series_dir.mkdir(parents=True)
    (series_dir / "manifest.json").write_text('{"stages": {}}', encoding="utf-8")

    app = create_app(data_dir=data_dir, config_path=config_path, start_worker=False)
    return TestClient(app)


def test_pipeline_graph_page(client: TestClient) -> None:
    resp = client.get("/pipeline")
    assert resp.status_code == 200
    assert "extract_voice" in resp.text
    assert "scene_analysis" in resp.text
    assert "pipeline-node" in resp.text.lower()


def test_series_pipeline_graph_page(client: TestClient) -> None:
    resp = client.get("/series/test-anime/pipeline")
    assert resp.status_code == 200
    assert "test-anime" in resp.text
    assert "extract_voice" in resp.text
    assert "pipeline-node" in resp.text.lower()
