import pytest
from pydantic import BaseModel

from translaterany.config.model import LLMConfig, ModelConfig
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

try:
    import httpx
except ModuleNotFoundError:
    import httpx2 as httpx


class ItemOut(BaseModel):
    id: str
    text: str


class BatchOut(BaseModel):
    items: list[ItemOut]


def test_pydantic_ai_client_resolution_and_generation(monkeypatch):
    config = LLMConfig()
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
    config = LLMConfig()
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
    config = LLMConfig()
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


def test_pydantic_ai_client_maps_refusal_error(monkeypatch):
    config = LLMConfig()
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


def test_pydantic_ai_client_maps_validation_error(monkeypatch):
    config = LLMConfig()
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
    config = LLMConfig(profile="local")
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


def test_pydantic_ai_client_implements_protocol():
    config = LLMConfig()
    client = PydanticAIClient(config)
    assert isinstance(client, LLMClient)
