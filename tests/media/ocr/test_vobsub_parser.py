from pathlib import Path

from translaterany.media.ocr.models import SubtitleDisplaySet
from translaterany.media.ocr.vobsub import parse_vobsub


def test_parse_vobsub_synthetic(tmp_path: Path) -> None:
    from ocr_helpers import make_synthetic_vobsub

    sub_path = tmp_path / "test.sub"
    idx_path = tmp_path / "test.idx"
    make_synthetic_vobsub(sub_path, idx_path, start_ms=1000, end_ms=3000)

    items = parse_vobsub(sub_path, idx_path)
    assert len(items) == 1
    assert isinstance(items[0], SubtitleDisplaySet)
    assert items[0].start_ms == 1000
    assert items[0].end_ms == 3000
    assert items[0].width > 0
    assert items[0].height > 0
