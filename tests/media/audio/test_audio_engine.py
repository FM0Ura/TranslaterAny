from pathlib import Path
from unittest.mock import patch

import pytest

from translaterany.media.audio.engine import create_diarization_engine
from translaterany.media.audio.models import UnitTiming
from translaterany.media.audio.onnx_engine import OnnxAudioDiarizer
from translaterany.media.audio.pyannote_engine import PyAnnoteAudioDiarizer


def test_create_engine_default_returns_onnx() -> None:
    engine = create_diarization_engine(engine_name="onnx")
    assert isinstance(engine, OnnxAudioDiarizer)


def test_create_engine_pyannote_without_token_falls_back_to_onnx(caplog: pytest.LogCaptureFixture) -> None:
    with patch.dict("os.environ", {}, clear=True):
        engine = create_diarization_engine(engine_name="pyannote", hf_token=None)
        assert isinstance(engine, OnnxAudioDiarizer)
        assert "HF_TOKEN ausente" in caplog.text


def test_create_engine_pyannote_with_token_returns_pyannote() -> None:
    engine = create_diarization_engine(engine_name="pyannote", hf_token="hf_secret")
    assert isinstance(engine, PyAnnoteAudioDiarizer)


def test_onnx_engine_extracts_embeddings_mocked(tmp_path: Path) -> None:
    wav_file = tmp_path / "speech.wav"
    wav_file.touch()
    engine = OnnxAudioDiarizer()
    timings = [UnitTiming("u1", 1000, 3000), UnitTiming("u2", 3500, 4500)]

    segments = engine.extract_embeddings(wav_file, timings)
    assert len(segments) == 2
    assert segments[0].unit_id == "u1"
    assert segments[0].acoustic_gender in ("male", "female", "unknown")
    assert len(segments[0].embedding) > 0
