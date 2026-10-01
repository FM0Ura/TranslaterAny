# tests/test_config_m7.py
"""Testes de configuração das etapas do M7."""

from translaterany.config.model import (
    AdaptOptions,
    FinalReadthroughOptions,
    OrthographyOptions,
    TreatmentConsistencyOptions,
)


def test_m7_options_defaults() -> None:
    treatment = TreatmentConsistencyOptions()
    assert treatment is not None

    adapt = AdaptOptions()
    assert adapt.max_cps == 17.0

    ortho = OrthographyOptions()
    assert ortho.url == "http://localhost:8010/v2/check"
    assert ortho.timeout_s == 5.0
    assert ortho.language == "pt-BR"

    readthrough = FinalReadthroughOptions()
    assert readthrough is not None
