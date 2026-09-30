"""Cliente nativo do Ollama (/api/chat): num_ctx e think por modelo, saída estruturada via `format`."""

import json

import httpx
import pytest
from pydantic import BaseModel

from translaterany.config.model import LLMConfig, ModelConfig, ProfileConfig
from translaterany.llm.client import LLMConfigError, LLMOutputError, LLMRequest, LLMTransientError
from translaterany.llm.ollama_native import OllamaNativeClient, ollama_root
from translaterany.llm.pydantic_ai_client import PydanticAIClient


class Out(BaseModel):
    terms: list[str]


def reply(content: str, *, done_reason: str = "stop", prompt: int = 100, out: int = 20) -> dict:
    return {
        "message": {"role": "assistant", "content": content},
        "done": True,
        "done_reason": done_reason,
        "prompt_eval_count": prompt,
        "eval_count": out,
    }


def client_with(handler) -> tuple[OllamaNativeClient, list[dict]]:
    sent: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        assert request.url.path == "/api/chat"
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(wrapped), base_url="http://ollama:11434")
    return OllamaNativeClient("http://ollama:11434", http=http), sent


def call(client: OllamaNativeClient, **kw):
    params = dict(model="gemma4:12b", instructions="sys", prompt="user", output_type=Out, num_ctx=16384,
                  temperature=0.7, think=False)  # fmt: skip
    params.update(kw)
    return client.chat(**params)


def test_ollama_root_strips_openai_suffix() -> None:
    assert ollama_root("http://localhost:11434/v1") == "http://localhost:11434"
    assert ollama_root("http://localhost:11434/v1/") == "http://localhost:11434"
    assert ollama_root("http://host:1/") == "http://host:1"


def test_sends_num_ctx_think_and_schema_and_parses_output() -> None:
    client, sent = client_with(lambda r: httpx.Response(200, json=reply('{"terms": ["Yu"]}', prompt=5370, out=362)))
    res = call(client)
    body = sent[0]
    assert body["options"] == {"num_ctx": 16384, "temperature": 0.7}
    assert body["think"] is False
    assert body["stream"] is False
    assert body["format"] == Out.model_json_schema()
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "user"}]
    assert res.output == Out(terms=["Yu"])
    assert res.model_id == "gemma4:12b"
    assert (res.usage.input_tokens, res.usage.output_tokens) == (5370, 362)


def test_retries_once_on_invalid_json_then_fails() -> None:
    answers = iter([reply("não é json"), reply('{"terms": ["ok"]}')])
    client, sent = client_with(lambda r: httpx.Response(200, json=next(answers)))
    assert call(client).output.terms == ["ok"]
    assert len(sent) == 2

    client, sent = client_with(lambda r: httpx.Response(200, json=reply('{"wrong": 1}')))
    with pytest.raises(LLMOutputError, match="inválida"):
        call(client)
    assert len(sent) == 2


def test_length_done_reason_is_output_error_with_num_ctx_hint() -> None:
    client, _ = client_with(lambda r: httpx.Response(200, json=reply('{"terms": [', done_reason="length")))
    with pytest.raises(LLMOutputError, match="num_ctx=16384"):
        call(client)


def test_saturated_context_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = client_with(lambda r: httpx.Response(200, json=reply('{"terms": []}', prompt=4000, out=96)))
    call(client, num_ctx=4096)
    assert any("contexto" in rec.message and "4096" in rec.message for rec in caplog.records)


def test_http_errors_are_mapped() -> None:
    client, _ = client_with(lambda r: httpx.Response(404, json={"error": "model 'x' not found"}))
    with pytest.raises(LLMConfigError, match="not found"):
        call(client)
    client, _ = client_with(lambda r: httpx.Response(500, json={"error": "boom"}))
    with pytest.raises(LLMTransientError):
        call(client)

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("recusado", request=request)

    client, _ = client_with(refuse)
    with pytest.raises(LLMTransientError, match="Ollama"):
        call(client)


def test_pydantic_ai_client_routes_ollama_models_to_native(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_chat(self, **kw):
        seen.update(kw)
        from translaterany.llm.client import LLMResponse, Usage

        return LLMResponse(output=Out(terms=[]), model_id=kw["model"], usage=Usage(1, 1))

    monkeypatch.setattr(OllamaNativeClient, "chat", fake_chat)
    config = LLMConfig(
        models={
            "translategemma": ModelConfig(provider="ollama", model="translategemma:12b", num_ctx=8192, temperature=0.3),
            "gemma4": ModelConfig(provider="ollama", model="gemma4:12b", num_ctx=16384, temperature=0.7, think=True),
        },
        profiles={"local": ProfileConfig(translate="translategemma", review="gemma4")},
    )
    client = PydanticAIClient(config)
    client.generate(LLMRequest(model="review", instructions="i", prompt="p", output_type=Out))
    assert (seen["model"], seen["num_ctx"], seen["think"], seen["temperature"]) == ("gemma4:12b", 16384, True, 0.7)
    client.generate(LLMRequest(model="translate", instructions="i", prompt="p", output_type=Out, temperature=0.1))
    assert (seen["model"], seen["num_ctx"], seen["think"], seen["temperature"]) == (
        "translategemma:12b", 8192, False, 0.1,
    )  # fmt: skip


def test_default_models_have_room_and_no_thinking() -> None:
    models = LLMConfig().models
    assert models["gemma4"].num_ctx == 16384 and models["gemma4"].think is False
    assert models["translategemma"].num_ctx == 8192 and models["translategemma"].think is False
