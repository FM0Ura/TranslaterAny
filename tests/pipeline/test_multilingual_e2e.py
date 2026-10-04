# tests/pipeline/test_multilingual_e2e.py
from pathlib import Path

from mkvtools import Sub, ass, create_synthetic_mkv, needs_mkvtoolnix

from translaterany.config import load_config_from_str
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.runner import PipelineRunner


def test_multilingual_pipeline_runner_initialization() -> None:
    raw_cfg = """
    source_language = "ja"
    target_language = "es"
    """
    cfg = load_config_from_str(raw_cfg)
    assert cfg.source_language == "ja"
    assert cfg.target_language == "es"

    runner = PipelineRunner(cfg)
    assert runner.source_language.code == "ja"
    assert runner.target_language.code == "es"
    assert runner.target_profile.info.code == "es"


@needs_mkvtoolnix
def test_multilingual_e2e_pipeline_execution(tmp_path: Path) -> None:
    video_path = tmp_path / "Season 1" / "Anime S01E01.mkv"
    ja_events = ["Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,こんにちは、世界！"]
    ja_sub = Sub(content=ass(ja_events), name="Dialog - JAP", lang="ja", default=True)

    create_synthetic_mkv(video_path, subs=[ja_sub])

    raw_cfg = """
    source_language = "ja"
    target_language = "es"
    """
    cfg = load_config_from_str(raw_cfg)
    fake_llm = FakeLLM(responses={"こんにちは、世界！": "¡Hola, mundo!"})
    runner = PipelineRunner(config=cfg, client=fake_llm)

    result = runner.run_series(tmp_path)
    assert result.status == "success"
    assert not result.failed

    es_ass_files = list(tmp_path.glob("**/*.es.ass"))
    assert len(es_ass_files) == 1
    content = es_ass_files[0].read_text(encoding="utf-8")
    assert "; TranslaterAny" in content
    assert "¡Hola, mundo!" in content

    # Confirma que não gerou pt-BR por engano
    pt_ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
    assert len(pt_ass_files) == 0
