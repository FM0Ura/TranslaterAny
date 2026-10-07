from pathlib import Path

import pytest

from translaterany.config.model import AppConfig
from translaterany.memory.models import (
    CharacterEntry,
    CharacterRole,
    EntrySource,
    Gender,
    GlossaryCategory,
    GlossaryEntry,
    StoryMemory,
)
from translaterany.web.services.config_service import ConfigService
from translaterany.web.services.memory_service import MemoryService
from translaterany.web.services.pipeline_service import PipelineService
from translaterany.web.services.series_service import SeriesService


def test_series_service_discovery(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    series_dir = data_dir / "series" / "high-school-of-the-dead"
    ep_dir = series_dir / "episodes" / "S01E01"
    ep_dir.mkdir(parents=True)

    # Cria manifestos simulados
    manifest_series = series_dir / "manifest.json"
    manifest_series.write_text('{"stages": {"metadata": {"status": "completed"}}}', encoding="utf-8")
    manifest_ep = ep_dir / "manifest.json"
    manifest_ep.write_text('{"stages": {"publish": {"status": "completed"}}}', encoding="utf-8")

    svc = SeriesService(data_dir=data_dir)
    series_list = svc.list_series()
    assert len(series_list) == 1
    assert series_list[0].key == "high-school-of-the-dead"
    assert series_list[0].total_episodes == 1
    assert series_list[0].completed_episodes == 1

    detail = svc.get_series("high-school-of-the-dead")
    assert detail is not None
    assert detail.key == "high-school-of-the-dead"
    assert len(detail.episodes) == 1
    assert detail.episodes[0].key == "S01E01"
    assert detail.episodes[0].status == "completed"


def test_memory_service_crud(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    svc = MemoryService(data_dir=data_dir)
    series_key = "test-anime"

    # Carrega vazio
    mem = svc.load_memory(series_key)
    assert mem.characters == []
    assert mem.glossary == {}
    assert mem.story is None

    # Salva personagem
    char = CharacterEntry(
        name="Rei Miyamoto",
        native_name="宮本 麗",
        aliases=["Rei"],
        gender=Gender.FEMALE,
        role=CharacterRole.MAIN,
        speech_style="Informal",
        source=EntrySource.USER,
    )
    svc.save_characters(series_key, [char])

    # Salva glossário
    term = GlossaryEntry(
        term="Zumbi",
        translation="Eles",
        category=GlossaryCategory.GENERAL,
        notes="Chamados de 'They' na série",
        source=EntrySource.USER,
    )
    svc.save_glossary(series_key, {"Zumbi": term})

    # Salva história
    story = StoryMemory(
        title="High School of the Dead",
        synopsis="Um apocalipse zumbi começa na escola.",
    )
    svc.save_story(series_key, story)

    # Recarrega e valida
    reloaded = svc.load_memory(series_key)
    assert len(reloaded.characters) == 1
    assert reloaded.characters[0].name == "Rei Miyamoto"
    assert "Zumbi" in reloaded.glossary
    assert reloaded.glossary["Zumbi"].translation == "Eles"
    assert reloaded.story is not None
    assert reloaded.story.synopsis == "Um apocalipse zumbi começa na escola."


def test_pipeline_service_graph_and_toggle(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    svc = PipelineService(config_path=config_path)

    # Grafo global
    graph = svc.get_pipeline()
    assert len(graph.stages) > 0
    stage_names = [s.name for s in graph.stages]
    assert "extract_voice" in stage_names
    assert "scene_analysis" in stage_names

    # Desativa etapa no global
    svc.set_stage_enabled("scene_analysis", False)
    updated_graph = svc.get_pipeline()
    scene_stage = next(s for s in updated_graph.stages if s.name == "scene_analysis")
    assert scene_stage.enabled is False

    # Ativa novamente
    svc.set_stage_enabled("scene_analysis", True)
    updated_graph2 = svc.get_pipeline()
    scene_stage2 = next(s for s in updated_graph2.stages if s.name == "scene_analysis")
    assert scene_stage2.enabled is True


def test_config_service_read_and_save(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    svc = ConfigService(config_path=config_path)

    cfg = svc.get_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.source_language == "en"
    assert cfg.target_language == "pt-BR"

    # Altera e salva
    cfg_copy = cfg.model_copy(update={"source_language": "ja"})
    svc.save_config(cfg_copy)

    # Recarrega
    saved_cfg = svc.get_config()
    assert saved_cfg.source_language == "ja"


def test_pipeline_service_validation(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    svc = PipelineService(config_path=config_path)

    # Tentar habilitar etapa inexistente deve falhar com ValueError
    with pytest.raises(ValueError, match="etapa desconhecida"):
        svc.set_stage_enabled("malicious_stage_injection", True)

