from translaterany.util.doctor import check_nvidia_gpu, check_ollama_models, check_ollama_status


def test_check_ollama_status_offline(monkeypatch):
    import httpx

    def mock_get(*args, **kwargs):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "get", mock_get)

    ok, msg = check_ollama_status("http://localhost:11434")
    assert ok is False
    assert "não está acessível" in msg


def test_check_ollama_status_ok(monkeypatch):
    import httpx

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "translategemma:12b"}, {"name": "gemma4:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())

    ok, msg = check_ollama_status("http://localhost:11434")
    assert ok is True
    assert "translategemma:12b" in msg


def test_check_ollama_status_with_version(monkeypatch):
    import httpx

    def mock_get(url, *args, **kwargs):
        class MockResp:
            status_code = 200

            def json(self):
                if "/api/version" in url:
                    return {"version": "0.3.14"}
                return {"models": [{"name": "translategemma:12b"}]}

        return MockResp()

    monkeypatch.setattr(httpx, "get", mock_get)

    ok, msg = check_ollama_status("http://localhost:11434")
    assert ok is True
    assert "v0.3.14" in msg
    assert "translategemma:12b" in msg


def test_check_ollama_models_present(monkeypatch):
    import httpx

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "translategemma:12b"}, {"name": "gemma4:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())

    ok, msg = check_ollama_models("http://localhost:11434", ["translategemma:12b", "gemma4:12b"])
    assert ok is True
    assert "translategemma:12b" in msg
    assert "gemma4:12b" in msg


def test_check_ollama_models_missing(monkeypatch):
    import httpx

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "other-model:latest"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())

    ok, msg = check_ollama_models("http://localhost:11434", ["translategemma:12b"])
    assert ok is False
    assert "ausentes" in msg.lower()
    assert "translategemma:12b" in msg


def test_check_nvidia_gpu_success(monkeypatch):
    import subprocess

    class MockProcess:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 3060, 12288, 11000\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockProcess())

    ok, msg = check_nvidia_gpu()
    assert ok is True
    assert "RTX 3060" in msg
    assert "11000" in msg


def test_check_nvidia_gpu_not_found(monkeypatch):
    import subprocess

    def mock_run(*a, **kw):
        raise FileNotFoundError("nvidia-smi not found")

    monkeypatch.setattr(subprocess, "run", mock_run)

    ok, msg = check_nvidia_gpu()
    assert ok is False
    assert "nvidia-smi" in msg.lower()


def test_doctor_command_integration(monkeypatch, tmp_path):
    import subprocess

    import httpx
    from typer.testing import CliRunner

    from translaterany.cli.app import app

    runner = CliRunner()

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "translategemma:12b"}, {"name": "gemma4:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())

    class MockProcess:
        returncode = 0
        stdout = "NVIDIA GeForce RTX 4090, 24576, 22000\n"
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: MockProcess())
    monkeypatch.setattr("translaterany.media.mkv.tool_available", lambda tool: f"/usr/bin/{tool}")

    stages = (
        '["inventory", "metadata", "select_track", "extract", '
        '"normalize", "classify", "extract_terms", "consolidate_memory", "translate_dialogue"]'
    )
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        f'[general]\ndata_dir = "{tmp_path}/data"\n[pipeline]\nstages = {stages}\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["--config", str(cfg_file), "doctor"])
    assert result.exit_code == 0, result.output
    assert "ollama" in result.output
    assert "RTX 4090" in result.output
    assert "translategemma:12b" in result.output
