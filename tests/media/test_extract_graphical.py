from pathlib import Path
from unittest.mock import MagicMock, patch

from translaterany.media.extract import extract_track


def test_extract_track_extracts_sup_for_pgs(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        out_path = extract_track(tmp_path / "video.mkv", track_id=3, codec_id="S_HDMV/PGS", out_dir=tmp_path)
        assert out_path.suffix == ".sup"
        assert "3:" in mock_run.call_args[0][0][3]


def test_extract_track_extracts_sub_for_vobsub(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        out_path = extract_track(tmp_path / "video.mkv", track_id=2, codec_id="S_VOBSUB", out_dir=tmp_path)
        assert out_path.suffix == ".sub"
