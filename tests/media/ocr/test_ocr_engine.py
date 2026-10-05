from unittest.mock import patch

from PIL import Image

from translaterany.media.ocr.engine import run_ocr
from translaterany.media.ocr.models import SubtitleDisplaySet


def test_ocr_engine_detects_italics_from_hocr() -> None:
    sample_hocr = """
    <div class='ocr_page'>
      <span class='ocr_line'><em>Hello</em> world</span>
    </div>
    """
    img = Image.new("L", (100, 30), color=255)
    ds = SubtitleDisplaySet(1000, 2000, 0, 900, 100, 30, 1920, 1080, img)

    with patch("translaterany.media.ocr.engine._call_tesseract_hocr", return_value=sample_hocr):
        results = run_ocr([ds], lang="eng", max_workers=1)
        assert len(results) == 1
        assert results[0].text == "{\\i1}Hello{\\i0} world"


def test_ocr_engine_deduplicates_identical_consecutive_frames() -> None:
    img = Image.new("L", (100, 30), color=255)
    ds1 = SubtitleDisplaySet(1000, 2000, 0, 900, 100, 30, 1920, 1080, img)
    ds2 = SubtitleDisplaySet(2000, 3000, 0, 900, 100, 30, 1920, 1080, img)

    with patch("translaterany.media.ocr.engine._call_tesseract_hocr", return_value="<span>Test</span>") as mock_tess:
        results = run_ocr([ds1, ds2], lang="eng", max_workers=1)
        assert len(results) == 1
        assert results[0].start_ms == 1000
        assert results[0].end_ms == 3000
        assert mock_tess.call_count == 1  # Evitou segunda chamada por hash idêntico
