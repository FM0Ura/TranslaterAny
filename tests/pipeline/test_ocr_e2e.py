"""Testes ponta a ponta (E2E) do Marco 10: OCR para legendas gráficas (PGS/VobSub)."""

from pathlib import Path
from unittest.mock import patch

from mkvtools import Sub, create_synthetic_mkv, needs_mkvtoolnix
from ocr_helpers import make_synthetic_sup

from translaterany.config import load_config_from_str
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.runner import PipelineRunner


@needs_mkvtoolnix
def test_pipeline_runs_pgs_end_to_end(tmp_path: Path) -> None:
    """Valida o fluxo completo do pipeline com faixa gráfica PGS até publicação .pt-BR.ass."""
    sup_file = tmp_path / "test.sup"
    make_synthetic_sup(sup_file, width=200, height=50)

    video = tmp_path / "Season 1" / "Anime S01E01.mkv"
    create_synthetic_mkv(video, subs=[Sub(content=sup_file.read_bytes(), name="PGS", ext=".sup")])

    cfg = load_config_from_str("")
    fake_llm = FakeLLM(responses={"Hello world": "Olá mundo"})
    store = ArtifactStore(tmp_path / "data")

    with patch("translaterany.media.ocr.engine._call_tesseract_hocr", return_value="<span>Hello world</span>"):
        runner = PipelineRunner(config=cfg, client=fake_llm, store=store)
        res = runner.run_series(tmp_path)
        assert res.status == "success"
        assert not res.failed

        ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
        assert len(ass_files) == 1
        content = ass_files[0].read_text(encoding="utf-8")
        assert "Olá mundo" in content


@needs_mkvtoolnix
def test_pipeline_prioritizes_pgs_over_signs_end_to_end(tmp_path: Path) -> None:
    """Garante que entre uma faixa de sinais em texto e um diálogo completo em PGS, o PGS é selecionado e processado."""
    signs_ass = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Sign,Arial,40

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Sign,,0,0,0,,Signs only
"""
    sup_file = tmp_path / "dialogue.sup"
    make_synthetic_sup(sup_file, width=200, height=50)

    video = tmp_path / "Season 1" / "Anime S01E01.mkv"
    create_synthetic_mkv(
        video,
        subs=[
            Sub(content=signs_ass, name="Signs & Songs", default=True, ext=".ass"),
            Sub(content=sup_file.read_bytes(), name="Full PGS Dialogue", default=False, ext=".sup"),
        ],
    )

    cfg = load_config_from_str("")
    fake_llm = FakeLLM(responses={"Full dialogue line": "Linha completa de diálogo"})
    store = ArtifactStore(tmp_path / "data")

    with patch(
        "translaterany.media.ocr.engine._call_tesseract_hocr",
        return_value="<span>Full dialogue line</span>",
    ):
        runner = PipelineRunner(config=cfg, client=fake_llm, store=store)
        res = runner.run_series(tmp_path)
        assert res.status == "success"
        assert not res.failed

        ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
        assert len(ass_files) == 1
        content = ass_files[0].read_text(encoding="utf-8")
        assert "Linha completa de diálogo" in content
        # Não deve conter a tradução da faixa de sinais
        assert "Signs only" not in content


@needs_mkvtoolnix
def test_pipeline_bypasses_ocr_for_text_tracks_end_to_end(tmp_path: Path) -> None:
    """Garante que faixas de texto padrão (ASS) passam pelo OCRStage via bypass sem erros."""
    text_ass = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Standard text line
"""
    video = tmp_path / "Season 1" / "Anime S01E01.mkv"
    create_synthetic_mkv(
        video,
        subs=[Sub(content=text_ass, name="Full Dialogue", default=True, ext=".ass")],
    )

    cfg = load_config_from_str("")
    fake_llm = FakeLLM(responses={"Standard text line": "Linha padrão de texto"})
    store = ArtifactStore(tmp_path / "data")

    runner = PipelineRunner(config=cfg, client=fake_llm, store=store)
    res = runner.run_series(tmp_path)
    assert res.status == "success"
    assert not res.failed

    ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text(encoding="utf-8")
    assert "Linha padrão de texto" in content
