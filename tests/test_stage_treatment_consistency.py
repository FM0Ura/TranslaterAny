# tests/test_stage_treatment_consistency.py
"""Testes da etapa treatment_consistency."""

from translaterany.refine.treatment import scan_treatment_consistency


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


def test_scan_skips_medium_confidence() -> None:
    lines = [
        {"id": "u1", "speaker": "Alice", "listener": "Bob", "text": "Você viu isso?", "confidence": "high"},
        {"id": "u2", "speaker": "Alice", "listener": "Bob", "text": "Você não sabe?", "confidence": "high"},
        {"id": "u3", "speaker": "Alice", "listener": "Bob", "text": "Tu disseste a verdade?", "confidence": "medium"},
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


def test_scan_identifies_article_mismatch_for_character_or_alias() -> None:
    lines = [
        {
            "id": "u1",
            "speaker": "Issei",
            "listener": "Bob",
            "text": "O presidente só está preocupado com você.",
            "confidence": "high",
        },
        {"id": "u2", "speaker": "Bob", "listener": "Issei", "text": "A Issei chegou agora.", "confidence": "high"},
    ]
    report = scan_treatment_consistency(
        lines, character_gender={"Presidente": "female", "Issei": "male", "Bob": "male"}
    )
    pair1 = report.get(("Issei", "Bob"))
    assert pair1 is not None
    assert "u1" in pair1.divergent_ids
    assert any(
        "artigo masculino usado para personagem feminina 'Presidente'" in r for r in pair1.divergent_reasons["u1"]
    )

    pair2 = report.get(("Bob", "Issei"))
    assert pair2 is not None
    assert "u2" in pair2.divergent_ids
    assert any("artigo feminino usado para personagem masculino 'Issei'" in r for r in pair2.divergent_reasons["u2"])


def test_scan_identifies_expanded_predicates() -> None:
    lines = [
        {
            "id": "u1",
            "speaker": "Motohama",
            "listener": "Issei",
            "text": "Você tá me deixando vazia.",
            "confidence": "high",
        },
    ]
    report = scan_treatment_consistency(lines, character_gender={"Motohama": "male", "Issei": "male"})
    pair = report.get(("Motohama", "Issei"))
    assert pair is not None
    assert "u1" in pair.divergent_ids
    assert any("gênero feminino usado por falante masculino" in r for r in pair.divergent_reasons["u1"])


def test_scan_identifies_determiners_and_possessives() -> None:
    lines = [
        {
            "id": "u1",
            "speaker": "Issei",
            "listener": "Asia",
            "text": "Levei bronca do presidente.",
            "confidence": "high",
        },
        {
            "id": "u2",
            "speaker": "Kiba",
            "listener": "Issei",
            "text": "Machucou nosso presidente!",
            "confidence": "high",
        },
        {
            "id": "u3",
            "speaker": "Issei",
            "listener": "Kiba",
            "text": "Ao contrário do presidente...",
            "confidence": "high",
        },
    ]
    report = scan_treatment_consistency(lines, character_gender={"Presidente": "female"})
    all_divergent = {lid for p in report.values() for lid in p.divergent_ids}
    assert {"u1", "u2", "u3"}.issubset(all_divergent)


def test_treatment_consistency_select_targets_includes_all_dialogue_lines() -> None:
    from translaterany.checks.models import LineInput
    from translaterany.memory.models import CharacterEntry, Gender
    from translaterany.stages.refine_base import RefineData
    from translaterany.stages.treatment_consistency import TreatmentConsistencyStage

    stage = TreatmentConsistencyStage()
    lines = [
        LineInput(id="u1", source="Hello", target="Olá.", line_type="dialogue", duration_ms=1000),
        LineInput(
            id="u2",
            source="You are a straight-A student.",
            target="Você é um aluno exemplar.",
            line_type="dialogue",
            duration_ms=2000,
        ),
    ]
    data = RefineData(
        sources={},
        lines=lines,
        env=None,  # type: ignore
        speaker_of={"u1": "Takashi", "u2": "Takashi"},
        listener_of={"u1": "Rei", "u2": "Rei"},
        confidence_of={"u1": "high", "u2": "high"},
        characters=[
            CharacterEntry(name="Takashi", gender=Gender.MALE),
            CharacterEntry(name="Rei", gender=Gender.FEMALE),
        ],
        ctx=None,
    )
    targets = stage.select_targets(["u1", "u2"], data)
    assert "u1" in targets
    assert "u2" in targets


def test_render_treatment_instructions_includes_character_genders() -> None:
    from translaterany.languages.registry import LanguageRegistry
    from translaterany.memory.models import CharacterEntry, Gender
    from translaterany.stages.treatment_consistency import render_treatment_instructions

    src = LanguageRegistry.resolve("en")
    tgt = LanguageRegistry.resolve("pt-BR")
    characters = [
        CharacterEntry(name="Takashi Komuro", gender=Gender.MALE),
        CharacterEntry(name="Rei Miyamoto", gender=Gender.FEMALE),
    ]
    instructions = render_treatment_instructions(src, tgt, characters=characters)
    assert "Takashi Komuro: masculino" in instructions
    assert "Rei Miyamoto: feminino" in instructions
    assert "COERÊNCIA DE TRATAMENTO" in instructions


def test_render_block_prompt_includes_listener() -> None:
    import json

    from translaterany.refine.blocks import ReviewLine, render_block_prompt

    line = ReviewLine(
        id="u35",
        source="You're a straight-A student.",
        target="Você é um aluno exemplar.",
        speaker="Takashi Komuro",
        tone="matter-of-fact",
        budget=40,
        signals=[],
        editable=True,
        listener="Rei Miyamoto",
    )
    rendered = render_block_prompt([line])
    parsed = json.loads(rendered)
    assert len(parsed) == 1
    assert parsed[0]["id"] == "u35"
    assert parsed[0]["falante"] == "Takashi Komuro"
    assert parsed[0]["ouvinte"] == "Rei Miyamoto"
