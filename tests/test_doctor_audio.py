from unittest.mock import MagicMock, patch

from translaterany.util.doctor import check_audio_runtimes, check_ffmpeg_audio_codecs


def test_doctor_ffmpeg_audio_codecs_ok() -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="DEA... flac\nDEA... aac\n", stderr="")
        res = check_ffmpeg_audio_codecs()
        assert res.status == "ok"
        assert "audio" in res.message.lower() or "ffmpeg" in res.message.lower()


def test_doctor_audio_runtimes_reports_status() -> None:
    with patch.dict("os.environ", {"HF_TOKEN": "hf_test"}, clear=True):
        res = check_audio_runtimes()
        assert res.status in ("ok", "info", "warn")
        assert "HF_TOKEN" in res.message
