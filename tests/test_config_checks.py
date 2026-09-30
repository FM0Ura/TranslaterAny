"""Seção [checks] e preços por modelo (M5)."""

from translaterany.config.model import AppConfig, ChecksConfig, LLMConfig, ModelConfig, ProfileConfig
from translaterany.llm.pricing import price_lookup


def test_checks_defaults_follow_netflix() -> None:
    cfg = AppConfig()
    assert cfg.checks == ChecksConfig()
    assert cfg.checks.max_cps == 17.0
    assert cfg.checks.max_cpl == 42
    assert cfg.checks.max_lines == 2
    assert cfg.checks.length_ratio == (0.5, 2.0)
    assert cfg.checks.length_ratio_min_chars == 10
    assert cfg.checks.disabled == []


def test_checks_from_dict() -> None:
    cfg = AppConfig.model_validate({"checks": {"max_cps": 20, "disabled": ["negation"]}})
    assert cfg.checks.max_cps == 20.0
    assert cfg.checks.disabled == ["negation"]


def test_model_prices_default_zero() -> None:
    m = ModelConfig(provider="ollama", model="x")
    assert m.input_price_per_mtok == 0.0
    assert m.output_price_per_mtok == 0.0


def test_price_lookup_resolves_profile_role_and_model_key() -> None:
    llm = LLMConfig(
        models={
            "cheap": ModelConfig(provider="openai", model="m", input_price_per_mtok=1.0, output_price_per_mtok=4.0),
        },
        profiles={"local": ProfileConfig(translate="cheap", review="cheap")},
    )
    prices = price_lookup(llm)
    assert prices("translate") == (1.0, 4.0)  # papel do perfil ativo
    assert prices("cheap") == (1.0, 4.0)  # chave direta
    assert prices("desconhecido") == (0.0, 0.0)
