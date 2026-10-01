# tests/test_stage_treatment_consistency.py
"""Testes da etapa treatment_consistency."""

from translaterany.refine.treatment import PairTreatment, scan_treatment_consistency


def test_scan_identifies_minority_pronoun() -> None:
    lines = [
        {"id": "u1", "speaker": "Alice", "listener": "Bob", "text": "Você viu isso?", "confidence": "high"},
        {"id": "u2", "speaker": "Alice", "listener": "Bob", "text": "Você não sabe?", "confidence": "high"},
        {"id": "u3", "speaker": "Alice", "listener": "Bob", "text": "Tu disseste a verdade?", "confidence": "high"},
        {"id": "u4", "speaker": "Alice", "listener": "Bob", "text": "Você pode vir?", "confidence": "high"},
    ]
    report = scan_treatment_consistency(lines, character_gender={"Alice": "female", "Bob": "male"})
    pair = report.get(("Alice", "Bob"))
    assert pair is not None
    assert pair.canonical_pronoun == "voce"
    assert pair.divergent_ids == ["u3"]


def test_scan_skips_low_confidence_or_unknown() -> None:
    lines = [
        {"id": "u1", "speaker": "Alice", "listener": "Unknown", "text": "Tu disseste isso?", "confidence": "high"},
        {"id": "u2", "speaker": "Alice", "listener": "Bob", "text": "Tu disseste aquilo?", "confidence": "low"},
    ]
    report = scan_treatment_consistency(lines, character_gender={"Alice": "female", "Bob": "male"})
    assert report == {}


def test_scan_identifies_gender_mismatch_for_speaker() -> None:
    lines = [
        {"id": "u1", "speaker": "Alice", "listener": "Bob", "text": "Eu estou cansado demais.", "confidence": "high"},
    ]
    # Alice é mulher, mas falou "cansado" (masculino)
    report = scan_treatment_consistency(lines, character_gender={"Alice": "female", "Bob": "male"})
    pair = report.get(("Alice", "Bob"))
    assert pair is not None
    assert "u1" in pair.divergent_ids


def test_treatment_consistency_stage_attributes() -> None:
    from translaterany.stages.treatment_consistency import TreatmentConsistencyStage

    stage = TreatmentConsistencyStage()
    assert stage.name == "treatment_consistency"
    assert stage.produces_dialogue is True
    assert "COERÊNCIA DE TRATAMENTO" in stage.instructions()

