# tests/test_cli_report.py
"""Comando report (M5)."""

import json
from pathlib import Path

from test_report import metrics, write_episode
from typer.testing import CliRunner

from translaterany.cli import app
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore

runner = CliRunner()


def _config(tmp_path: Path, data_dir: Path) -> str:
    path = tmp_path / "config.toml"
    path.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")
    return str(path)


def _invoke(*args: str):
    return runner.invoke(app, list(args), env={"XDG_CONFIG_HOME": "/nao/existe", "TRANSLATERANY_CONFIG": ""})


def _setup(tmp_path: Path, series_dir: Path, *, with_metrics: bool = True) -> tuple[str, ArtifactStore]:
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series, _ = discover(series_dir)
    store.write_series_info(series)
    write_episode(store, "S01E01", metrics=metrics(10, 2, 14) if with_metrics else None, series=series.key)
    write_episode(store, "S01E02", metrics=None, series=series.key)
    return _config(tmp_path, data_dir), store


def test_report_terminal_and_json(tmp_path: Path, series_dir: Path) -> None:
    cfg, _ = _setup(tmp_path, series_dir)
    out = tmp_path / "base.json"
    result = _invoke("--config", cfg, "report", str(series_dir), "--json", str(out))
    assert result.exit_code == 0, result.output
    assert "Processo por etapa" in result.output and "Indicadores finais" in result.output
    assert "S01E02" in result.output  # sem métricas
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == 1 and data["lines"] == 10


def test_report_baseline_and_episode(tmp_path: Path, series_dir: Path) -> None:
    cfg, _ = _setup(tmp_path, series_dir)
    out = tmp_path / "base.json"
    _invoke("--config", cfg, "report", str(series_dir), "--json", str(out))
    result = _invoke("--config", cfg, "report", str(series_dir), "--baseline", str(out))
    assert result.exit_code == 0 and "Comparação com a linha de base" in result.output
    ep = _invoke("--config", cfg, "report", str(series_dir), "--episode", "S01E01")
    assert ep.exit_code == 0 and "reading_speed" in ep.output and "Achados" in ep.output


def test_report_exit_codes(tmp_path: Path, series_dir: Path) -> None:
    cfg, _ = _setup(tmp_path, series_dir, with_metrics=False)
    none = _invoke("--config", cfg, "report", str(series_dir))
    assert none.exit_code == 1 and "Nenhuma métrica encontrada" in none.output
    cfg, _ = _setup(tmp_path, series_dir)
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert _invoke("--config", cfg, "report", str(series_dir), "--baseline", str(bad)).exit_code == 2
    never = tmp_path / "lib2" / "Nunca (2021)"
    (never / "Season 1").mkdir(parents=True)
    (never / "Season 1" / "S01E01.mkv").write_text("x", encoding="utf-8")
    assert _invoke("--config", cfg, "report", str(never)).exit_code == 1
