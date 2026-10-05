from translaterany.stages.extract import ExtractStage
from translaterany.stages.normalize import NormalizeStage
from translaterany.stages.ocr import OCRStage


def test_normalize_binds_to_ocr_when_present() -> None:
    ocr = OCRStage()
    norm = NormalizeStage()
    norm.bind_pipeline([ocr], app=None)
    assert "ocr" in norm.inputs


def test_normalize_binds_to_extract_when_ocr_absent() -> None:
    ext = ExtractStage()
    norm = NormalizeStage()
    norm.bind_pipeline([ext], app=None)
    assert "extract" in norm.inputs
