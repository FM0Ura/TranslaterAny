from pathlib import Path
from unittest.mock import MagicMock, patch

from translaterany.media.audio.extractor import AudioExtractor
from translaterany.media.audio.models import AcousticSegment, UnitTiming


def test_audio_models_instantiation() -> None:
    timing = UnitTiming(unit_id="u001", start_ms=1000, end_ms=2500)
    assert timing.unit_id == "u001"
    assert timing.duration_ms == 1500

    segment = AcousticSegment(
        unit_id="u001",
        start_ms=1000,
        end_ms=2500,
        embedding=[0.1, 0.2, 0.3],
        acoustic_gender="female",
        has_speech=True,
    )
    assert segment.acoustic_gender == "female"
    assert len(segment.embedding) == 3


def test_audio_extractor_generates_correct_ffmpeg_command(tmp_path: Path) -> None:
    mkv_file = tmp_path / "test.mkv"
    mkv_file.touch()

    extractor = AudioExtractor()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with extractor.extract_voice_track(mkv_file, track_index=1) as wav_path:
            assert wav_path.name.endswith(".wav")
            assert mock_run.called
            cmd = mock_run.call_args[0][0]
            assert "ffmpeg" in cmd[0]
            assert "-ac" in cmd and "1" in cmd
            assert "-ar" in cmd and "16000" in cmd
