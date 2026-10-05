from pathlib import Path

from mkvtools import FULL_ASS, SIGNS_ASS, Sub, make_mkv, needs_mkvtoolnix
from typer.testing import CliRunner

from translaterany.cli import app

runner = CliRunner()


def _config(tmp_path: Path, data_dir: Path, stages: str = '"t_source", "t_upper"') -> Path:
    path = tmp_path / "config.toml"
    text = f'[general]\ndata_dir = "{data_dir}"\n[discovery]\nmin_file_age = 0\n[pipeline]\nstages = [{stages}]\n'
    path.write_text(text, encoding="utf-8")
    return path


def _invoke(*args: str):
    return runner.invoke(app, list(args), env={"XDG_CONFIG_HOME": "/nao/existe", "TRANSLATERANY_CONFIG": ""})


def test_run_then_cached_then_status(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    first = _invoke("--config", cfg, "run", str(series_dir))
    assert first.exit_code == 0, first.output
    assert "3 episódio(s)" in first.output
    second = _invoke("--config", cfg, "run", str(series_dir))
    assert second.exit_code == 0
    status = _invoke("--config", cfg, "status", str(series_dir))
    assert status.exit_code == 0
    assert "t_upper" in status.output
    all_status = _invoke("--config", cfg, "status")
    assert "Minha Série (2020)" in all_status.output
    assert list((data_dir / "logs").glob("run-*.log"))


def test_run_with_failure_exit_1(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("FAIL", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    assert result.exit_code == 1


def test_run_interrupted_exit_130(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E02.mkv").write_text("INTERRUPT", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    assert result.exit_code == 130
    assert "retomar" in result.output


def test_run_invalid_config_exit_2(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir, '"nope"')), "run", str(series_dir))
    assert result.exit_code == 2
    assert "etapa desconhecida" in result.output


def test_run_not_a_directory_exit_2(tmp_path: Path, data_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(tmp_path / "nao-existe"))
    assert result.exit_code == 2


def test_retry_forces_rerun(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    result = _invoke("--config", cfg, "retry", str(series_dir), "--from", "t_upper")
    assert result.exit_code == 0, result.output
    assert "4 unidade(s)" in result.output  # 3 episódios + a série
    bad = _invoke("--config", cfg, "retry", str(series_dir), "--from", "nope")
    assert bad.exit_code == 2


def test_doctor_ok_and_config_failure(tmp_path: Path, data_dir: Path) -> None:
    ok = _invoke("--config", str(_config(tmp_path, data_dir)), "doctor")
    assert ok.exit_code == 0, ok.output
    assert "configuração válida" in ok.output
    bad = _invoke("--config", str(_config(tmp_path, data_dir, '"nope"')), "doctor")
    assert bad.exit_code == 1


@needs_mkvtoolnix
def test_default_config_runs_m1_pipeline(tmp_path: Path, monkeypatch) -> None:
    import httpx

    from translaterany.llm.fake import FakeLLM

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "translategemma:12b"}, {"name": "gemma4:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())
    monkeypatch.setattr("translaterany.cli.run.PydanticAIClient", lambda cfg: FakeLLM(responses={}))

    root = tmp_path / "lib" / "Serie"
    make_mkv(root / "S01E01.mkv", [Sub(SIGNS_ASS, "S&S", default=True), Sub(FULL_ASS, "Dialog - ENG")])
    env = {"XDG_CONFIG_HOME": str(tmp_path / "sem-config"), "TRANSLATERANY_CONFIG": ""}
    result = runner.invoke(app, ["--data-dir", str(tmp_path / "d"), "run", str(root)], env=env)
    assert result.exit_code == 0, result.output
    for stage in ("inventory", "select_track", "extract", "normalize", "classify", "write", "publish"):
        assert stage in result.output
    assert "remux" not in result.output  # desligado por padrão
    status = runner.invoke(app, ["--data-dir", str(tmp_path / "d"), "status", str(root)], env=env)
    assert "Dialog - ENG" in status.output and "quality_checks" in status.output
    assert not list(root.glob("*.pt-BR.ass"))


def test_run_empty_folder(tmp_path: Path, data_dir: Path) -> None:
    empty = tmp_path / "Vazia"
    empty.mkdir()
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(empty))
    assert result.exit_code == 0, result.output
    assert "Nenhuma série encontrada" in result.output


def test_corrupted_manifest_gives_clear_error(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    manifest = next((data_dir / "series").glob("*/episodes/*/manifest.json"))
    manifest.write_text("{corrompido", encoding="utf-8")
    for args in (
        ["run", str(series_dir)],
        ["status", str(series_dir)],
        ["retry", str(series_dir), "--from", "t_upper"],
    ):
        result = _invoke("--config", cfg, *args)
        assert result.exit_code == 1, (args, result.output)
        assert "manifest inválido" in result.output
        assert "Traceback" not in result.output


def test_run_unreadable_source_no_traceback(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    bad = series_dir / "Season 1" / "S01E02.mkv"
    bad.chmod(0)
    try:
        result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    finally:
        bad.chmod(0o644)
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    assert "Resumo" in result.output


def test_non_utf8_manifest_gives_clear_error(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    manifest = next((data_dir / "series").glob("*/episodes/*/manifest.json"))
    manifest.write_bytes(
        manifest.read_text(encoding="utf-8")
        .replace('"skip_reason": null', '"skip_reason": "episódio"')
        .encode("latin-1")
    )
    for args in (
        ["run", str(series_dir)],
        ["status", str(series_dir)],
        ["retry", str(series_dir), "--from", "t_upper"],
    ):
        result = _invoke("--config", cfg, *args)
        assert result.exit_code == 1, (args, result.output)
        assert "manifest inválido" in result.output
        assert "Traceback" not in result.output


def test_status_with_corrupted_series_json(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    series_json = next((data_dir / "series").glob("*/series.json"))
    series_json.write_text("{", encoding="utf-8")
    result = _invoke("--config", cfg, "status")
    assert result.exit_code == 0, result.output
    assert series_json.parent.name[:12] in result.output
    assert "Traceback" not in result.output


def test_run_unwritable_data_dir_reports_doctor_failure(tmp_path: Path, series_dir: Path) -> None:
    locked = tmp_path / "ro"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        result = _invoke("--config", str(_config(tmp_path, locked / "data")), "run", str(series_dir))
    finally:
        locked.chmod(0o755)
    assert result.exit_code == 2, result.output
    assert "data_dir" in result.output
    assert "Traceback" not in result.output


def test_status_never_processed(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "status", str(series_dir))
    assert result.exit_code == 0 and "Pasta nunca processada" in result.output


def test_status_marks_missing_file(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    (series_dir / "Season 1" / "S01E03.mkv").unlink()
    result = _invoke("--config", cfg, "status", str(series_dir))
    assert "arquivo ausente" in result.output


def test_run_library_with_broken_series_toml(tmp_path: Path, data_dir: Path) -> None:
    lib = tmp_path / "Anime"
    (lib / "Boa" / "Season 1").mkdir(parents=True)
    (lib / "Boa" / "Season 1" / "S01E01.mkv").write_text("episodio", encoding="utf-8")
    (lib / "Ruim" / "Season 1").mkdir(parents=True)
    (lib / "Ruim" / "Season 1" / "S01E01.mkv").write_text("episodio", encoding="utf-8")
    (lib / "Ruim" / "series.toml").write_text("[subtitles\n", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(lib))
    assert result.exit_code == 1, result.output
    assert "Série: Boa" in result.output and "Resumo — Boa" in result.output
    assert "series.toml" in result.output and "Resumo — Ruim" not in result.output


def test_run_lists_ignored_files(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01 - outra versão.mkv").write_text("dup", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    assert result.exit_code == 0, result.output
    assert "ignorado nesta execução" in result.output and "duplicado" in result.output
    assert "2 episódio(s)" in result.output


def test_run_filters_by_episode(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir), "--episode", "S01E01")
    assert result.exit_code == 0, result.output
    assert "1 episódio(s)" in result.output
