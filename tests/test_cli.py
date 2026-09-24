from pathlib import Path

from typer.testing import CliRunner

from translaterany.cli import app

runner = CliRunner()


def _config(tmp_path: Path, data_dir: Path, stages: str = '"t_source", "t_upper"') -> Path:
    path = tmp_path / "config.toml"
    path.write_text(f'[general]\ndata_dir = "{data_dir}"\n[pipeline]\nstages = [{stages}]\n', encoding="utf-8")
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


def test_default_config_runs_inventory(tmp_path: Path, series_dir: Path) -> None:
    result = runner.invoke(
        app,
        ["--data-dir", str(tmp_path / "d"), "run", str(series_dir)],
        env={"XDG_CONFIG_HOME": str(tmp_path / "sem-config"), "TRANSLATERANY_CONFIG": ""},
    )
    assert result.exit_code == 0, result.output
    assert "inventory" in result.output


def test_run_empty_folder(tmp_path: Path, data_dir: Path) -> None:
    empty = tmp_path / "Vazia"
    empty.mkdir()
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(empty))
    assert result.exit_code == 0, result.output
    assert "0 episódio(s)" in result.output


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
