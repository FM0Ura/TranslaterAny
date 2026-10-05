from unittest.mock import MagicMock, patch

from translaterany.util.doctor import check_tesseract_installed


def test_tesseract_check_ok_when_installed() -> None:
    with patch("shutil.which", return_value="/usr/bin/tesseract"), patch("subprocess.run") as mock_run:
        # First call: version, second call: list-langs
        def fake_run(cmd, *args, **kwargs):
            if "--version" in cmd:
                return MagicMock(returncode=0, stdout="tesseract 5.5.0\n", stderr="")
            if "--list-langs" in cmd:
                return MagicMock(returncode=0, stdout="List of available languages (2):\neng\nosd\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run
        res = check_tesseract_installed("eng")
        assert res.status == "ok"
        assert "tesseract" in res.message.lower()


def test_tesseract_check_warn_or_fail_when_missing() -> None:
    with patch("shutil.which", return_value=None):
        res = check_tesseract_installed("eng")
        assert res.status in ("warn", "fail")
        assert "brew install tesseract" in res.message or "não encontrado" in res.message


def test_tesseract_check_warns_when_language_pack_missing() -> None:
    with patch("shutil.which", return_value="/usr/bin/tesseract"), patch("subprocess.run") as mock_run:

        def fake_run(cmd, *args, **kwargs):
            if "--version" in cmd:
                return MagicMock(returncode=0, stdout="tesseract 5.5.0\n", stderr="")
            if "--list-langs" in cmd:
                return MagicMock(returncode=0, stdout="List of available languages (1):\nosd\n", stderr="")
            return MagicMock(returncode=0, stdout="", stderr="")

        mock_run.side_effect = fake_run
        res = check_tesseract_installed("eng")
        assert res.status == "warn"
        assert "eng" in res.message
