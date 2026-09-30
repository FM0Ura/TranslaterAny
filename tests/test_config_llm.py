import pytest

from translaterany.config.loader import load_config_from_str
from translaterany.config.model import AppConfig, LLMConfig


def test_default_llm_config_is_local_with_ollama():
    config = load_config_from_str("")
    assert isinstance(config, AppConfig)
    assert isinstance(config.llm, LLMConfig)
    assert config.llm.profile == "local"
    assert "ollama" in config.llm.providers
    assert config.llm.providers["ollama"].base_url == "http://localhost:11434/v1"
    assert "translategemma" in config.llm.models
    assert config.llm.models["translategemma"].model == "translategemma:12b"
    assert config.llm.models["translategemma"].num_ctx == 8192
    assert config.llm.profiles["local"].translate == "translategemma"
    assert config.llm.profiles["local"].review == "gemma4"


def test_custom_llm_config_toml():
    toml_text = """
    [llm]
    profile = "hibrido"
    max_cost_usd = 10.0

    [llm.providers.ollama]
    base_url = "http://localhost:11434/v1"

    [llm.providers.gemini]
    api_key = "test-key"

    [llm.models.translategemma]
    provider = "ollama"
    model = "translategemma:12b"
    num_ctx = 4096

    [llm.models.gemini_flash]
    provider = "gemini"
    model = "gemini-2.5-flash"
    num_ctx = 8192

    [llm.profiles.hibrido]
    translate = "translategemma"
    review = "gemini_flash"
    """
    config = load_config_from_str(toml_text)
    assert config.llm.profile == "hibrido"
    assert config.llm.max_cost_usd == 10.0
    assert config.llm.providers["gemini"].api_key == "test-key"
    assert config.llm.profiles["hibrido"].review == "gemini_flash"


def test_portuguese_validation_error_message():
    invalid_toml = """
    [llm]
    profile = "invalido"
    """
    with pytest.raises(ValueError, match="Perfil de IA desconhecido|Campo inválido"):
        load_config_from_str(invalid_toml)
