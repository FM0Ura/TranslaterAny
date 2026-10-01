"""Testes de exibição do QA no comando report."""

import json
from pathlib import Path
from typer.testing import CliRunner

from translaterany.cli import app
from translaterany.cli.report import format_qa_summary
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.qa_loop import QAReport


def test_format_qa_summary_with_warning() -> None:
    rep = QAReport(
        rounds_executed=1,
        extra_calls_used=4,
        blame_summary={"translate_dialogue": 3},
        interventions=[],
        edit_rate=0.30,  # 30% > limiar de 25%
    )
    output = format_qa_summary(rep, threshold=0.25)
    assert "Taxa de edição alta" in output
    assert "translate_dialogue: 3" in output


def test_format_qa_summary_without_warning() -> None:
    rep = QAReport(
        rounds_executed=1,
        extra_calls_used=1,
        blame_summary={"orthography": 1},
        interventions=[{"unit_id": "u1", "blamed_stage": "orthography", "outcome": "fixed"}],
        edit_rate=0.05,  # 5% <= limiar de 25%
    )
    output = format_qa_summary(rep, threshold=0.25)
    assert "Taxa de edição alta" not in output
    assert "orthography: 1" in output
    assert "Rodadas executadas: 1" in output
    assert "Chamadas extras usadas: 1" in output


def test_qa_loop_in_default_pipeline() -> None:
    assert "qa_loop" in DEFAULT_PIPELINE
    idx_redistribute = DEFAULT_PIPELINE.index("redistribute_sentences")
    idx_qa = DEFAULT_PIPELINE.index("qa_loop")
    idx_qc = DEFAULT_PIPELINE.index("quality_checks")
    assert idx_redistribute < idx_qa < idx_qc


def test_cli_report_displays_qa_summary_when_present(tmp_path: Path, series_dir: Path) -> None:
    runner = CliRunner()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series, _ = discover(series_dir)
    store.write_series_info(series)

    from test_report import metrics, write_episode
    write_episode(store, "S01E01", metrics=metrics(10, 2, 14), series=series.key)

    ep_dir = store.artifact_dir(series.key, "S01E01")
    qa_rep = QAReport(
        rounds_executed=2,
        extra_calls_used=3,
        blame_summary={"colloquial": 2},
        interventions=[],
        edit_rate=0.10,
    )
    (ep_dir / "qa_report.json").write_text(json.dumps(qa_rep.to_dict()), encoding="utf-8")

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    res = runner.invoke(
        app,
        ["--config", str(cfg_path), "report", str(series_dir), "--episode", "S01E01"],
        env={"XDG_CONFIG_HOME": "/nao/existe", "TRANSLATERANY_CONFIG": ""},
    )
    assert res.exit_code == 0, res.output
    assert "Resumo do QA Loop" in res.output
    assert "colloquial: 2" in res.output
