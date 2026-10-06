from pathlib import Path
from unittest.mock import MagicMock, patch

from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact
from translaterany.media.audio.models import AcousticSegment
from translaterany.pipeline.stage import StageScope
from translaterany.stages.extract_voice import ExtractVoiceStage
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit


def _make_dummy_doc() -> NormalizedDoc:
    event = EventInfo(
        index=0,
        line_no=1,
        kind="dialogue",
        style="Default",
        start_ms=1000,
        end_ms=2000,
        layer=0,
        name="",
        prefix="",
        text="Olá",
        markers=[],
        suffix="",
        drawing=False,
        unit="u1",
    )
    unit = Unit(id="u1", style="Default", text="Olá", markers=0, events=[0])
    return NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=["Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"],
        events=[event],
        units=[unit],
    )


def test_extract_voice_stage_metadata() -> None:
    assert ExtractVoiceStage.name == "extract_voice"
    assert ExtractVoiceStage.scope == StageScope.EPISODE
    assert "normalize" in ExtractVoiceStage.inputs


def test_extract_voice_stage_handles_missing_audio_gracefully(tmp_path: Path) -> None:
    stage = ExtractVoiceStage()
    ctx = MagicMock()
    ctx.inputs.json.return_value = _make_dummy_doc()
    ctx.episode = MagicMock(source=tmp_path / "nonexistent.mkv", key="S01E01")
    ctx.output = MagicMock()

    with patch.object(stage, "_find_audio_track_index", return_value=None):
        stage.run(ctx)
        assert ctx.output.json.called
        art = ctx.output.json.call_args[0][0]
        assert isinstance(art, VoiceEmbeddingsArtifact)
        assert len(art.segments) == 0


def test_extract_voice_stage_runs_extraction_and_generates_segments(tmp_path: Path) -> None:
    stage = ExtractVoiceStage()
    ctx = MagicMock()
    ctx.inputs.json.return_value = _make_dummy_doc()
    fake_mkv = tmp_path / "video.mkv"
    fake_mkv.touch()
    ctx.episode = MagicMock(source=fake_mkv, key="S01E01")
    ctx.output = MagicMock()

    fake_segments = [
        AcousticSegment(unit_id="u1", start_ms=1000, end_ms=2000, embedding=[0.1, 0.2], acoustic_gender="male")
    ]

    with (
        patch.object(stage, "_find_audio_track_index", return_value=0),
        patch("translaterany.stages.extract_voice.AudioExtractor") as mock_extractor_cls,
        patch("translaterany.stages.extract_voice.create_diarization_engine") as mock_engine_cls,
    ):
        mock_extractor = mock_extractor_cls.return_value
        fake_wav = tmp_path / "temp.wav"
        fake_wav.touch()
        mock_extractor.extract_voice_track.return_value.__enter__.return_value = fake_wav

        mock_engine = mock_engine_cls.return_value
        mock_engine.extract_embeddings.return_value = fake_segments

        stage.run(ctx)

        assert ctx.output.json.called
        art = ctx.output.json.call_args[0][0]
        assert isinstance(art, VoiceEmbeddingsArtifact)
        assert len(art.segments) == 1
        assert art.segments[0].unit_id == "u1"
        assert art.segments[0].acoustic_gender == "male"
