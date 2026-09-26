from translaterany.llm.client import (
    LLMClient,
    LLMOutputError,
    LLMRefusalError,
    LLMResponse,
    LLMTransientError,
    Usage,
)
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.translator import (
    DialogueBatchTranslator,
    TranslationBatch,
    TranslationItem,
)


class MockLLM(LLMClient):
    def __init__(self, behavior_fn):
        self.behavior_fn = behavior_fn
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return self.behavior_fn(self.calls, request)


def test_translator_reconciles_missing_ids():
    # Primeira chamada devolve apenas ID '1', faltando o '2'. Segunda chamada devolve '2'.
    def behavior(call_count, req):
        if call_count == 1:
            return LLMResponse(output=TranslationBatch(items=[TranslationItem(id="1", text="Olá")]), model_id="test")
        return LLMResponse(output=TranslationBatch(items=[TranslationItem(id="2", text="Mundo")]), model_id="test")

    client = MockLLM(behavior)
    translator = DialogueBatchTranslator(client=client, model_name="translategemma")
    lines = [DialogueLine(id="1", text="Hello"), DialogueLine(id="2", text="World")]
    res = translator.translate_lines(lines)
    assert res == {"1": "Olá", "2": "Mundo"}
    assert client.calls == 2


def test_translator_bisection_on_malformed_json():
    # Falha se o bloco tiver tamanho > 1; passa quando dividido em blocos de 1 fala
    def behavior(call_count, req):
        if "Hello" in req.prompt and "World" in req.prompt:
            raise LLMOutputError("JSON quebrado")
        if "Hello" in req.prompt:
            return LLMResponse(output=TranslationBatch(items=[TranslationItem(id="1", text="Olá")]), model_id="test")
        return LLMResponse(output=TranslationBatch(items=[TranslationItem(id="2", text="Mundo")]), model_id="test")

    client = MockLLM(behavior)
    translator = DialogueBatchTranslator(client=client, model_name="translategemma")
    lines = [DialogueLine(id="1", text="Hello"), DialogueLine(id="2", text="World")]
    res = translator.translate_lines(lines)
    assert res == {"1": "Olá", "2": "Mundo"}


def test_translator_graceful_degradation_to_original_text():
    # Simula falha irrecuperável em todas as tentativas
    def behavior(call_count, req):
        raise LLMOutputError("Impossível traduzir")

    client = MockLLM(behavior)
    translator = DialogueBatchTranslator(client=client, model_name="translategemma")
    lines = [DialogueLine(id="1", text="Hello")]
    res = translator.translate_lines(lines)
    # Deve manter o texto original em inglês sem levantar exceção
    assert res == {"1": "Hello"}
    assert translator.fallback_count == 1


def test_translator_refusal_fallback_to_local_model():
    # Simula recusa de modelo de nuvem (ex: filtro de segurança) com fallback para modelo local
    def behavior(call_count, req):
        if req.model == "gemini-flash":
            raise LLMRefusalError("Refusal triggered by safety filter")
        return LLMResponse(
            output=TranslationBatch(items=[TranslationItem(id="1", text="Olá")]),
            model_id="translategemma-local",
            usage=Usage(input_tokens=10, output_tokens=5),
        )

    client = MockLLM(behavior)
    translator = DialogueBatchTranslator(
        client=client,
        model_name="gemini-flash",
        fallback_model="translategemma-local",
    )
    lines = [DialogueLine(id="1", text="Hello")]
    res = translator.translate_lines(lines)
    assert res == {"1": "Olá"}
    assert client.calls == 2
    assert translator.total_usage.input_tokens == 10
    assert translator.total_usage.output_tokens == 5


def test_translator_retries_transient_error(monkeypatch):
    # Simula erro transitório (timeout/rate-limit) resolvido na 2ª chamada via tenacity
    from tenacity import wait_none

    def behavior(call_count, req):
        if call_count == 1:
            raise LLMTransientError("Connection timeout")
        return LLMResponse(
            output=TranslationBatch(items=[TranslationItem(id="1", text="Olá")]),
            model_id="test",
            usage=Usage(input_tokens=12, output_tokens=4),
        )

    client = MockLLM(behavior)
    translator = DialogueBatchTranslator(client=client, model_name="translategemma")
    # Substituir o wait do retry via monkeypatch para evitar vazamento entre testes
    monkeypatch.setattr(translator._call_model.retry, "wait", wait_none())

    lines = [DialogueLine(id="1", text="Hello")]
    res = translator.translate_lines(lines)
    assert res == {"1": "Olá"}
    assert client.calls == 2


def test_translator_max_context_lines_zero():
    # Verifica que com max_context_lines=0 nenhum contexto recente é propagado entre batches
    recorded_prompts: list[str] = []

    def behavior(call_count, req):
        recorded_prompts.append(req.prompt)
        line_id = str(call_count)
        return LLMResponse(
            output=TranslationBatch(items=[TranslationItem(id=line_id, text=f"Texto {line_id}")]),
            model_id="test",
        )

    client = MockLLM(behavior)
    translator = DialogueBatchTranslator(
        client=client,
        model_name="translategemma",
        max_tokens_per_batch=10,
        max_context_lines=0,
    )
    lines = [
        DialogueLine(id="1", text="First line of dialogue"),
        DialogueLine(id="2", text="Second line of dialogue"),
    ]
    res = translator.translate_lines(lines)
    assert res == {"1": "Texto 1", "2": "Texto 2"}
    assert len(recorded_prompts) == 2
    for p in recorded_prompts:
        assert "[CONTEXTO RECENTE" not in p
