from pathlib import Path

from translaterany.media.ocr.models import SubtitleDisplaySet
from translaterany.media.ocr.pgs import decode_rle, parse_pgs


def test_decode_rle_simple_line() -> None:
    # Bytes de exemplo de linha RLE padrão PGS: run de 5 pixels da cor 1
    raw = bytes([0x00, 0x85, 0x01])
    pixels = decode_rle(raw, width=5)
    assert len(pixels) == 5
    assert pixels == [1, 1, 1, 1, 1]


def test_parse_pgs_synthetic_packets(tmp_path: Path) -> None:
    sup_file = tmp_path / "test.sup"
    from ocr_helpers import make_synthetic_sup

    make_synthetic_sup(sup_file, width=100, height=30, text_color=1)

    displays = parse_pgs(sup_file)
    assert len(displays) == 1
    assert isinstance(displays[0], SubtitleDisplaySet)
    assert displays[0].width == 100
    assert displays[0].height == 30
    assert displays[0].start_ms == 1000
    assert displays[0].end_ms == 2000
    assert displays[0].image.size == (100, 30)
