import asyncio

import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai.exceptions import ContentFilterError, UnexpectedModelBehavior

from translaterany.config.model import LLMConfig, ModelConfig, ProviderConfig
from translaterany.llm.client import (
    LLMClient,
    LLMConfigError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
)
from translaterany.llm.pydantic_ai_client import PydanticAIClient


def _cloud_config(**kw) -> LLMConfig:
    """Modelos num provedor de nuvem: o caminho pydantic-ai atende só nuvem (Ollama vai pela API nativa)."""
    return LLMConfig(
        providers={"openai": ProviderConfig(api_key="sk-test")},
        models={"translategemma": ModelConfig(provider="openai", model="translategemma:12b")},
        **kw,
    )


class ItemOut(BaseModel):
    id: str
    text: str


class BatchOut(BaseModel):
    items: list[ItemOut]


def test_pydantic_ai_client_resolution_and_generation(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    # Mock da geração do agent
    async def mock_run(*args, **kwargs):
        class MockRunResult:
            data = BatchOut(items=[ItemOut(id="1", text="Olá mundo")])

            def usage(self):
                class MockUsage:
                    request_tokens = 10
                    response_tokens = 5

                return MockUsage()

        return MockRunResult()

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run)

    req = LLMRequest(
        model="translategemma",
        instructions="Traduza para pt-BR",
        prompt="1: Hello world",
        output_type=BatchOut,
    )
    res = client.generate(req)
    assert isinstance(res, LLMResponse)
    assert len(res.output.items) == 1
    assert res.output.items[0].text == "Olá mundo"
    assert res.usage.input_tokens > 0
    assert res.usage.output_tokens > 0
    assert res.model_id == "translategemma:12b"


def test_pydantic_ai_client_maps_connection_error(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run_fail(*args, **kwargs):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run_fail)

    req = LLMRequest(
        model="translategemma",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMTransientError, match="Erro de conexão"):
        client.generate(req)


def test_pydantic_ai_client_maps_timeout_error(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Request timed out")

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run_timeout)

    req = LLMRequest(
        model="translategemma",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMTransientError, match="Erro de conexão"):
        client.generate(req)


def test_pydantic_ai_client_maps_content_filter_error(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run_refusal(*args, **kwargs):
        raise ContentFilterError("Content filter triggered")

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run_refusal)

    req = LLMRequest(
        model="translategemma",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMRefusalError, match="Requisição recusada"):
        client.generate(req)


def test_pydantic_ai_client_maps_string_refusal_error(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run_refusal(*args, **kwargs):
        raise RuntimeError("Safety policy violation: model refusal")

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run_refusal)

    req = LLMRequest(
        model="translategemma",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMRefusalError, match="Requisição recusada"):
        client.generate(req)


def test_pydantic_ai_client_maps_unexpected_model_behavior_error(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run_validation(*args, **kwargs):
        raise UnexpectedModelBehavior("Malformed model output structure")

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run_validation)

    req = LLMRequest(
        model="translategemma",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMOutputError, match="Falha de validação"):
        client.generate(req)


def test_pydantic_ai_client_maps_validation_error(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run_validation(*args, **kwargs):
        raise ValueError("Invalid JSON response or validation failed")

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run_validation)

    req = LLMRequest(
        model="translategemma",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMOutputError, match="Falha de validação"):
        client.generate(req)


def test_pydantic_ai_client_unknown_model_raises_config_error():
    config = LLMConfig()
    client = PydanticAIClient(config)

    req = LLMRequest(
        model="unknown_model",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMConfigError, match="não configurado em \\[llm\\.models\\]"):
        client.generate(req)


def test_pydantic_ai_client_unknown_provider_raises_config_error():
    config = LLMConfig()
    config.models["bad_provider_model"] = ModelConfig(
        provider="missing_provider",
        model="test:model",
    )
    client = PydanticAIClient(config)

    req = LLMRequest(
        model="bad_provider_model",
        instructions="Instruções",
        prompt="Texto",
        output_type=BatchOut,
    )
    with pytest.raises(LLMConfigError, match="não configurado em \\[llm\\.providers\\]"):
        client.generate(req)


def test_pydantic_ai_client_resolves_profile_task_alias(monkeypatch):
    config = _cloud_config(profile="local")
    client = PydanticAIClient(config)

    async def mock_run(*args, **kwargs):
        class MockRunResult:
            data = BatchOut(items=[ItemOut(id="1", text="Olá mundo")])

            def usage(self):
                class MockUsage:
                    request_tokens = 10
                    response_tokens = 5

                return MockUsage()

        return MockRunResult()

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run)

    # Note: request.model is the task alias "translate" from profile local
    req = LLMRequest(
        model="translate",
        instructions="Traduza para pt-BR",
        prompt="1: Hello world",
        output_type=BatchOut,
    )
    res = client.generate(req)
    assert res.model_id == "translategemma:12b"


def test_pydantic_ai_client_resolves_cloud_provider_and_env_vars(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test-key")
    config = LLMConfig()
    config.models["gpt-4o"] = ModelConfig(
        provider="openai",
        model="gpt-4o",
    )
    client = PydanticAIClient(config)

    model_name, base_url, api_key, extra_args = client._resolve_model("gpt-4o")
    assert model_name == "gpt-4o"
    assert base_url is None  # standard OpenAI endpoint
    assert api_key == "sk-openai-test-key"


def test_pydantic_ai_client_resolves_custom_base_url_and_api_key():
    config = LLMConfig()
    config.providers["custom"] = ProviderConfig(
        base_url="https://custom.llm.example/v1",
        api_key="secret-key",
    )
    config.models["custom-model"] = ModelConfig(
        provider="custom",
        model="custom-model:v1",
    )
    client = PydanticAIClient(config)

    model_name, base_url, api_key, extra_args = client._resolve_model("custom-model")
    assert model_name == "custom-model:v1"
    assert base_url == "https://custom.llm.example/v1"
    assert api_key == "secret-key"


def test_pydantic_ai_client_generate_inside_running_event_loop(monkeypatch):
    config = _cloud_config()
    client = PydanticAIClient(config)

    async def mock_run(*args, **kwargs):
        class MockRunResult:
            data = BatchOut(items=[ItemOut(id="1", text="Em loop")])

            def usage(self):
                class MockUsage:
                    request_tokens = 2
                    response_tokens = 2

                return MockUsage()

        return MockRunResult()

    monkeypatch.setattr("pydantic_ai.Agent.run", mock_run)

    async def run_in_loop():
        req = LLMRequest(
            model="translategemma",
            instructions="Instruções",
            prompt="Texto",
            output_type=BatchOut,
        )
        return client.generate(req)

    res = asyncio.run(run_in_loop())
    assert res.output.items[0].text == "Em loop"


def test_pydantic_ai_client_implements_protocol():
    config = LLMConfig()
    client = PydanticAIClient(config)
    assert isinstance(client, LLMClient)


def test_pydantic_ai_client_cloud_provider_missing_api_key_raises_config_error(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    config = LLMConfig()
    config.models["gpt-4o"] = ModelConfig(
        provider="openai",
        model="gpt-4o",
    )
    client = PydanticAIClient(config)

    with pytest.raises(LLMConfigError, match="Chave de API não configurada para o provedor 'openai'"):
        client._resolve_model("gpt-4o")
