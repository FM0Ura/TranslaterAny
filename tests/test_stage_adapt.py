# tests/test_stage_adapt.py
"""Testes da etapa adapt."""

from translaterany.stages.adapt import AdaptStage, identify_cps_exceeded


def test_identify_cps_exceeded() -> None:
    # duration 1000ms (1s), max_cps 17.0 -> max_chars = 17
    # 25 caracteres -> estourou
    text_long = "Essa frase tem 25 letras!"
    exceeded, budget = identify_cps_exceeded(text_long, duration_ms=1000, max_cps=17.0)
    assert exceeded is True
    assert budget == 17

    # 15 caracteres -> ok
    text_short = "Frase curta ok."
    exceeded, budget = identify_cps_exceeded(text_short, duration_ms=1000, max_cps=17.0)
    assert exceeded is False


def test_adapt_stage_attributes() -> None:
    stage = AdaptStage()
    assert stage.name == "adapt"
    assert stage.produces_dialogue is True
    assert "VELOCIDADE DE LEITURA" in stage.instructions()
