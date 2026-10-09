from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from translaterany.web.app import create_app


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    data_dir = tmp_path / "data"
    config_path = tmp_path / "config.toml"
    # Cria uma série e episódio para teste
    series_dir = data_dir / "series" / "test-anime"
    ep_dir = series_dir / "episodes" / "S01E01"
    ep_dir.mkdir(parents=True)
    (series_dir / "manifest.json").write_text('{"stages": {}}', encoding="utf-8")
    (ep_dir / "manifest.json").write_text('{"stages": {}}', encoding="utf-8")

    app = create_app(data_dir=data_dir, config_path=config_path, start_worker=False)
    return TestClient(app)


def test_dashboard_page_renders_html(client: TestClient) -> None:
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "TranslaterAny" in resp.text
    assert "htmx" in resp.text.lower()


def test_settings_page_renders_html(client: TestClient) -> None:
    resp = client.get("/settings")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Configurações" in resp.text


def test_series_page_renders_html(client: TestClient) -> None:
    resp = client.get("/series/test-anime")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "test-anime" in resp.text or "Test Anime" in resp.text


def test_memory_page_renders_html(client: TestClient) -> None:
    resp = client.get("/series/test-anime/memory")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Memória da Série" in resp.text


def test_inspector_page_renders_html(client: TestClient) -> None:
    resp = client.get("/series/test-anime/episodes/S01E01")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "S01E01" in resp.text
