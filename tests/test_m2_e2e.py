"""Testes de integração ponta a ponta do Marco 2 (M2).

Valida a execução completa do pipeline:
inventory -> select_track -> extract -> normalize -> classify -> translate_dialogue -> write -> publish
com produção de legenda .pt-BR.ass contendo a marca de autoria '; TranslaterAny',
tradução dos diálogos e preservação de placas, estilos e temporizações.
"""

from pathlib import Path

from mkvtools import create_synthetic_mkv, needs_mkvtoolnix
from typer.testing import CliRunner

from translaterany.cli import app
from translaterany.config.loader import load_config, load_config_from_str
from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.runner import PipelineRunner, Runner


@needs_mkvtoolnix
def test_m2_pipeline_end_to_end(tmp_path: Path) -> None:
    """Verifica a execução ponta a ponta do pipeline via PipelineRunner."""
    video_path = tmp_path / "Season 1" / "Anime S01E01.mkv"
    create_synthetic_mkv(video_path, dialogues=[("00:00:01.000", "00:00:03.000", "Hello! Good morning.")])

    config = load_config_from_str("")
    fake_llm = FakeLLM(responses={"Hello! Good morning.": "Olá! Bom dia."})
    runner = PipelineRunner(config=config, client=fake_llm)

    result = runner.run_series(tmp_path)
    assert result.status == "success"
    assert not result.failed

    # Verifica se o arquivo .ass gerado contém a tradução e a marca de autoria
    ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text(encoding="utf-8")
    assert "; TranslaterAny" in content
    assert "Olá! Bom dia." in content


@needs_mkvtoolnix
def test_m2_pipeline_preserves_signs_styles_formatting_and_timings(tmp_path: Path) -> None:
    """Verifica preservação de placas, estilos, formatações inline e tempos no arquivo final."""
    series_dir = tmp_path / "My Anime (2024)"
    video_path = series_dir / "Season 1" / "S01E01.mkv"
    # create_synthetic_mkv sem dialogues usa FULL_ASS com Sign-1 (placas) e Default (diálogos com tags)
    create_synthetic_mkv(video_path)

    fake_llm = FakeLLM(
        responses={
            "Where are we going, friend?": "Aonde vamos, amigo?",
            "To the ⟦1⟧old⟦2⟧ station.": "Para a ⟦1⟧velha⟦2⟧ estação.",
        }
    )

    data_dir = tmp_path / "data"
    cfg = load_config(explicit=None, data_dir_override=data_dir, env={})
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)

    runner = Runner(cfg.stages, store, fake_llm)
    summary = runner.run(series, episodes)

    assert not summary.failed
    expected_stages = [
        "inventory",
        "select_track",
        "extract",
        "normalize",
        "classify",
        "translate_dialogue",
        "write",
        "publish",
    ]
    for stage_name in expected_stages:
        assert summary.stages[stage_name].done == 1, f"etapa {stage_name} não concluída"

    published_file = video_path.with_name(video_path.stem + ".pt-BR.ass")
    assert published_file.is_file()
    content = published_file.read_text(encoding="utf-8")

    # Autoria TranslaterAny
    assert "; TranslaterAny" in content

    # Diálogos traduzidos com tags inline preservadas
    assert "Aonde vamos, amigo?" in content
    assert r"{\i1}velha{\i0}" in content

    # Placas não traduzidas preservadas intactas
    assert "Estação Central" in content
    assert r"{\pos(100,100)}Estação Central" in content

    # Estilos originais preservados
    assert "Style: Default,Arial,48" in content
    assert "Style: Sign-1,Arial,40" in content

    # Timings originais preservados
    assert "0:00:01.00,0:00:02.00" in content
    assert "0:00:03.00,0:00:05.00" in content
    assert "0:00:05.50,0:00:07.00" in content


@needs_mkvtoolnix
def test_m2_pipeline_caching_and_idempotency(tmp_path: Path) -> None:
    """Verifica que uma segunda execução reaproveita o cache de todas as etapas."""
    series_dir = tmp_path / "Anime Cached"
    video_path = series_dir / "Season 1" / "S01E01.mkv"
    create_synthetic_mkv(video_path)

    fake_llm = FakeLLM(
        responses={
            "Where are we going, friend?": "Aonde vamos, amigo?",
            "To the ⟦1⟧old⟦2⟧ station.": "Para a ⟦1⟧velha⟦2⟧ estação.",
        }
    )

    data_dir = tmp_path / "data"
    cfg = load_config(explicit=None, data_dir_override=data_dir, env={})
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)

    runner = Runner(cfg.stages, store, fake_llm)

    # Primeira execução: todas as etapas executam
    first_summary = runner.run(series, episodes)
    assert not first_summary.failed
    for stage_name in [
        "inventory",
        "select_track",
        "extract",
        "normalize",
        "classify",
        "translate_dialogue",
        "write",
        "publish",
    ]:
        assert first_summary.stages[stage_name].done == 1

    # Segunda execução: todas as etapas devem vir de cache
    second_summary = runner.run(series, episodes)
    assert not second_summary.failed
    for stage_name in [
        "inventory",
        "select_track",
        "extract",
        "normalize",
        "classify",
        "translate_dialogue",
        "write",
        "publish",
    ]:
        assert second_summary.stages[stage_name].cached == 1
        assert second_summary.stages[stage_name].done == 0

    published_file = video_path.with_name(video_path.stem + ".pt-BR.ass")
    assert published_file.is_file()
    assert "; TranslaterAny" in published_file.read_text(encoding="utf-8")


@needs_mkvtoolnix
def test_m2_pipeline_cli_integration(tmp_path: Path, monkeypatch) -> None:
    """Verifica a execução ponta a ponta através do comando CLI run."""
    series_dir = tmp_path / "Anime CLI"
    video_path = series_dir / "Season 1" / "S01E01.mkv"
    create_synthetic_mkv(video_path, dialogues=[("00:00:01.000", "00:00:03.000", "Good evening.")])

    data_dir = tmp_path / "data"

    # Substitui PydanticAIClient no módulo CLI por um FakeLLM com tradução conhecida
    fake_llm = FakeLLM(responses={"Good evening.": "Boa noite."})
    monkeypatch.setattr("translaterany.cli.run.PydanticAIClient", lambda cfg: fake_llm)

    import httpx

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "translategemma:12b"}, {"name": "gemma4:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())

    cli_runner = CliRunner()
    result = cli_runner.invoke(
        app,
        ["--data-dir", str(data_dir), "run", str(series_dir)],
        env={"XDG_CONFIG_HOME": str(tmp_path / "empty_cfg"), "TRANSLATERANY_CONFIG": ""},
    )
    assert result.exit_code == 0, result.output

    published_file = video_path.with_name(video_path.stem + ".pt-BR.ass")
    assert published_file.is_file()
    content = published_file.read_text(encoding="utf-8")
    assert "; TranslaterAny" in content
    assert "Boa noite." in content
