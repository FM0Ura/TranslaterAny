# tests/test_stage_final_readthrough.py
"""Testes da etapa final_readthrough."""

from translaterany.refine.blocks import ReviewLine
from translaterany.stages.final_readthrough import FinalReadthroughStage, render_readthrough_prompt


def test_prompt_contains_only_portuguese_and_speaker() -> None:
    lines = [
        {"id": "u1", "speaker": "Yuu", "text": "Eu vou conseguir passar na prova."},
        {"id": "u2", "speaker": "Nao", "text": "Tem certeza disso?"},
    ]
    prompt = render_readthrough_prompt(lines, scene_context="Sala de aula")
    assert "Eu vou conseguir passar na prova." in prompt
    assert "Yuu" in prompt
    assert "Nao" in prompt
    assert "EN:" not in prompt
    assert '"en"' not in prompt  # sem campo em inglês


def test_final_readthrough_stage_attributes() -> None:
    stage = FinalReadthroughStage()
    assert stage.name == "final_readthrough"
    assert stage.produces_dialogue is True
    assert stage.default_dialogue_input == "orthography"
    assert "LEITURA CORRIDA" in stage.instructions()


def test_render_readthrough_prompt_with_review_lines() -> None:
    review = [
        ReviewLine(
            id="u1",
            source="I will pass.",
            target="Eu vou passar.",
            speaker="Yuu",
            tone="confident",
            budget=20,
            signals=[],
            editable=True,
        )
    ]
    prompt = render_readthrough_prompt(review)
    assert '"fala": "Eu vou passar."' in prompt
    assert '"en"' not in prompt
