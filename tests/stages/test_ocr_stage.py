from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from translaterany.media.ocr.engine import OCRResultLine
from translaterany.stages.ocr import OCRArtifact, OCRStage, _build_ass_event


def test_ocr_stage_bypasses_text_track(tmp_path: Path) -> None:
    ass_file = tmp_path / "track.ass"
    ass_file.write_text("[Events]\nDialogue: ...", encoding="utf-8")

    stage = OCRStage()
    mock_inputs = SimpleNamespace(path=lambda name: ass_file)
    mock_output = MagicMock()
    ctx = SimpleNamespace(
        inputs=mock_inputs,
        output=mock_output,
        episode=SimpleNamespace(source=Path("video.mkv")),
        log=MagicMock(),
    )

    stage.run(ctx)
    art = mock_output.json.call_args[0][0]
    assert isinstance(art, OCRArtifact)
    assert art.bypassed is True
    assert art.path == str(ass_file)


def test_ocr_stage_infers_position_styles(tmp_path: Path) -> None:
    # Valida que linha Y < 25% vira estilo Top / \an8 e Y > 65% vira Default
    top_line = OCRResultLine(
        start_ms=1000,
        end_ms=2000,
        x=100,
        y=50,
        w=200,
        h=40,
        video_w=1920,
        video_h=1080,
        text="Top Title",
    )
    ev_top = _build_ass_event(top_line)
    assert "\\an8" in ev_top.text or ev_top.style == "Top"

    bottom_line = OCRResultLine(
        start_ms=3000,
        end_ms=4000,
        x=100,
        y=900,
        w=200,
        h=40,
        video_w=1920,
        video_h=1080,
        text="Dialogue",
    )
    ev_bottom = _build_ass_event(bottom_line)
    assert ev_bottom.style == "Default"
