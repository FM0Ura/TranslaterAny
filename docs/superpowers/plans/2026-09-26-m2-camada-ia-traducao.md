# M2 — Camada de IA e tradução básica · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar a camada de IA via `pydantic-ai-slim` conectando-se ao Ollama local (em container Docker com `translategemma:12b` e `gemma4:12b`) e provedores de nuvem opcionais, com chunking inteligente, cascata de resiliência em 4 níveis e a etapa `translate_dialogue`, produzindo a primeira legenda `.pt-BR.ass` traduzida com tags e estilos preservados.

**Architecture:** Pacote `llm` ganha `PydanticAIClient` implementando a interface `LLMClient` e se comunicando com o endpoint OpenAI-compatible do Ollama (`/v1`). O novo módulo `subtitles/chunking.py` gerencia o agrupamento dinâmico de falas por orçamento de tokens com janela deslizante de contexto. O motor `subtitles/translator.py` orquestra a resiliência em 4 níveis (Tenacity, reconciliação de IDs, bisseção recursiva e fallback para inglês). A nova etapa `stages/translate_dialogue.py` consome os diálogos de `classify`, traduz preservando tags/estilos/tempos ASS e alimenta a gravação (`write`), ativando a marcação de autoria e o remux. O `doctor` é expandido para verificar a conectividade do Ollama, presença dos modelos e status da GPU.

**Tech Stack:** Python 3.14 · uv · pydantic 2 · pydantic-ai-slim[openai] · tenacity · pysubs2 · charset-normalizer · MKVToolNix · pytest · ruff.

**Spec:** [`docs/superpowers/specs/2026-09-26-m2-camada-ia-traducao-design.md`](../specs/2026-09-26-m2-camada-ia-traducao-design.md)

---

## Global Constraints

- `requires-python = ">=3.14"`; gerenciamento exclusivo de dependências via `uv`.
- Dependências novas do M2: `pydantic-ai-slim[openai]>=0.0.1` e `tenacity>=9.0.0`.
- Código, classes, métodos e identificadores em **inglês**; mensagens exibidas ao usuário, logs e erros de validação em **PT-BR**.
- Modelo local padrão de tradução: `translategemma:12b` via Ollama (`http://localhost:11434/v1`).
- Modelo local padrão de revisão: `gemma4:12b` via Ollama.
- Perfil padrão de execução: `local` (100% autônomo, sem requisições externas à internet). Provedores de nuvem (Gemini/OpenAI) só são acionados se as chaves forem explicitamente fornecidas.
- A etapa `translate_dialogue` só traduz unidades onde `type == "dialogue"`. Demais unidades (`sign`, `song`, `karaoke`, `comment`) têm seus textos preservados intactos.
- Timing (`start_ms`, `end_ms`), estilos, camadas, ator e tags de formatação ASS inline (ex.: `{\pos}`, `{\fad}`, `{\an8}`) permanecem intocados — apenas o conteúdo textual é traduzido.
- A gravação (`write`) só insere a marca `; TranslaterAny` quando alimentada por uma etapa de tradução real (`translates = True`).
- Nenhum episódio tem sua execução abortada por falha em uma única fala: se todas as tentativas da cascata falharem, a fala mantém o texto em inglês original e emite log de `WARNING`.
- Testes automatizados da suíte (`pytest`) devem ser 100% sintéticos, rápidos e determinísticos utilizando mocks e `FakeLLM`, sem qualquer dependência de GPU física ou conexão externa de rede.
- Nunca versionar arquivos de vídeo nem legendas reais em `temporada-teste/`.
- Mensagens de commit seguem o padrão convencional (`feat: ...`, `test: ...`, `fix: ...`).

---

## Review Focus

1. **Reconciliação quando o LLM omite IDs** (ex.: bloco de 20 falas, LLM devolve 18) → mini-lote complementar disparado apenas com os IDs ausentes e fusão na ordem original — Tarefa 4 (`test_translator_reconciles_missing_ids`).
2. **Bisseção recursiva em JSON corrompido** (ex.: modelo alucina ou quebra o schema do lote) → lote dividido em duas metades independentes e processadas com sucesso — Tarefa 4 (`test_translator_bisection_on_malformed_json`).
3. **Degradação graciosa em fala atômica irrecuperável** (bloco unitário de 1 fala falha após retries) → texto original em inglês é mantido, log de `WARNING` emitido e o pipeline conclui o episódio sem erro — Tarefa 4 (`test_translator_graceful_degradation_to_original_text`).
4. **Preservação de tags inline complexas no ASS** (ex.: `{\an8\fs24}Texto{\r} mais texto`) → tags preservadas exatamente nas posições corretas no `.ass` final gerado — Tarefa 5 (`test_translate_dialogue_preserves_inline_tags`).
5. **Detecção de legendas do Bazarr** (`.pt-BR.hi.srt`, `.forced.srt`) → identificadas corretamente na descoberta e seleção de faixas sem colidir com legendas PT-BR completas — Tarefa 1 (`test_bazarr_subtitles_detection`).

---

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `pyproject.toml` | Adição das dependências `pydantic-ai-slim[openai]` e `tenacity` |
| `config/model.py` | Modelos Pydantic para `[llm]`: `ProviderConfig`, `ModelConfig`, `ProfileConfig`, `LLMConfig` |
| `config/loader.py` | Tratamento de erros de validação do TOML com mensagens em PT-BR |
| `library/discovery.py` | Suporte a identificação de legendas Bazarr (`.forced.srt`, `.hi.srt`) |
| `llm/client.py` | Atualização das interfaces e exceções da camada de IA |
| `llm/pydantic_ai_client.py` | Implementação do `LLMClient` conectando-se ao Ollama via `pydantic-ai-slim` |
| `subtitles/chunking.py` | Divisão dinâmica de falas por orçamento de tokens e formatação da janela de contexto |
| `subtitles/translator.py` | Motor `DialogueBatchTranslator` com cascata de resiliência em 4 níveis |
| `stages/translate_dialogue.py` | Etapa do pipeline consumindo diálogos, traduzindo e preservando tags ASS |
| `stages/write.py` | Conexão do `translate_dialogue` como fonte de texto (`text_source`) e geração da marca de autoria |
| `util/doctor.py` | Verificações de conectividade do Ollama, modelos baixados e VRAM da GPU |
| `cli/doctor.py` | Exibição das checagens do ambiente no terminal |
| `cli/estimate.py` | Cálculo e exibição da estimativa pré-execução de tokens e custos |
| `tests/test_config_llm.py` | Testes da configuração LLM e mensagens em PT-BR |
| `tests/test_bazarr_subtitles.py` | Testes da identificação de legendas Bazarr |
| `tests/test_llm_pydantic_ai.py` | Testes do cliente `pydantic-ai` e mapeamento de exceções com mocks |
| `tests/test_chunking.py` | Testes do agrupamento em blocos e janela de contexto |
| `tests/test_translator_resilience.py` | Testes da cascata de resiliência (tenacity, IDs faltantes, bisseção, fallback) |
| `tests/test_stages_translate_dialogue.py` | Testes da etapa do pipeline e preservação de tags |
| `tests/test_doctor_llm.py` | Testes das verificações de Ollama e GPU no `doctor` |
| `tests/test_m2_e2e.py` | Teste de integração ponta a ponta do Marco 2 com pipeline completo |

---

### Task 1: Dependências e Configuração de LLM

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/translaterany/config/model.py`
- Modify: `src/translaterany/config/loader.py`
- Modify: `src/translaterany/library/discovery.py`
- Test: `tests/test_config_llm.py`
- Test: `tests/test_bazarr_subtitles.py`

**Interfaces:**
- Consumes: `AppConfig`, `config.toml`
- Produces: `LLMConfig`, `ProviderConfig`, `ModelConfig`, `ProfileConfig` expostos em `AppConfig.llm`.

- [ ] **Step 1: Escrever teste com falha para configuração LLM e legendas Bazarr**

```python
# tests/test_config_llm.py
import pytest
from pydantic import ValidationError
from translaterany.config.loader import load_config_from_str
from translaterany.config.model import AppConfig, LLMConfig


def test_default_llm_config_is_local_with_ollama():
    config = load_config_from_str("")
    assert config.llm.profile == "local"
    assert "ollama" in config.llm.providers
    assert config.llm.providers["ollama"].base_url == "http://localhost:11434/v1"
    assert "translategemma" in config.llm.models
    assert config.llm.models["translategemma"].model == "translategemma:12b"
    assert config.llm.models["translategemma"].num_ctx == 4096
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
```

```python
# tests/test_bazarr_subtitles.py
from translaterany.library.discovery import is_bazarr_auxiliary_subtitle


def test_bazarr_auxiliary_subtitles():
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.hi.srt") is True
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.forced.ass") is True
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.sdh.srt") is True
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.ass") is False
    assert is_bazarr_auxiliary_subtitle("anime.S01E01.pt-BR.srt") is False
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_config_llm.py tests/test_bazarr_subtitles.py -v`
Expected: FAIL (módulos e campos ausentes)

- [ ] **Step 3: Implementar dependências e modelos de configuração**

Adicionar dependências no `pyproject.toml` usando `uv add "pydantic-ai-slim[openai]>=0.0.1" "tenacity>=9.0.0"`.

Atualizar `src/translaterany/config/model.py`:
```python
from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProviderConfig(_Strict):
    base_url: str | None = None
    api_key: str | None = None


class ModelConfig(_Strict):
    provider: str
    model: str
    num_ctx: int = 4096
    temperature: float = 0.3


class ProfileConfig(_Strict):
    translate: str = "translategemma"
    review: str = "gemma4"
    options: dict[str, Any] = Field(default_factory=dict)


class LLMConfig(_Strict):
    profile: Literal["local", "hibrido", "nuvem"] = "local"
    max_cost_usd: float = 5.0
    providers: dict[str, ProviderConfig] = Field(
        default_factory=lambda: {
            "ollama": ProviderConfig(base_url="http://localhost:11434/v1", api_key="ollama"),
            "gemini": ProviderConfig(api_key=None),
            "openai": ProviderConfig(api_key=None),
        }
    )
    models: dict[str, ModelConfig] = Field(
        default_factory=lambda: {
            "translategemma": ModelConfig(provider="ollama", model="translategemma:12b", num_ctx=4096, temperature=0.3),
            "gemma4": ModelConfig(provider="ollama", model="gemma4:12b", num_ctx=8192, temperature=0.7),
        }
    )
    profiles: dict[str, ProfileConfig] = Field(
        default_factory=lambda: {
            "local": ProfileConfig(translate="translategemma", review="gemma4"),
            "hibrido": ProfileConfig(translate="translategemma", review="gemma4"),
            "nuvem": ProfileConfig(translate="translategemma", review="gemma4"),
        }
    )


class GeneralConfig(_Strict):
    data_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class DiscoveryConfig(_Strict):
    min_file_age: float = 120


class PipelineConfig(_Strict):
    stages: list[str]


class StageConfig(_Strict):
    enabled: bool | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class AppConfig(_Strict):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    pipeline: PipelineConfig | None = None
    stages: dict[str, StageConfig] = Field(default_factory=dict)
```

Atualizar `src/translaterany/config/loader.py` com mensagens em PT-BR e `src/translaterany/library/discovery.py` com `is_bazarr_auxiliary_subtitle`.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_config_llm.py tests/test_bazarr_subtitles.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock src/translaterany/config/ src/translaterany/library/ tests/test_config_llm.py tests/test_bazarr_subtitles.py
git commit -m "feat(config): suporte a configuração de LLM e detecção de legendas Bazarr"
```

---

### Task 2: Camada de IA e Cliente (`llm/client.py`, `llm/pydantic_ai_client.py`)

**Files:**
- Modify: `src/translaterany/llm/client.py`
- Create: `src/translaterany/llm/pydantic_ai_client.py`
- Modify: `src/translaterany/llm/__init__.py`
- Test: `tests/test_llm_pydantic_ai.py`

**Interfaces:**
- Consumes: `LLMRequest[T]`, `LLMResponse[T]`, `LLMConfig`
- Produces: `PydanticAIClient` implementando `LLMClient`

- [ ] **Step 1: Escrever teste com falha para o PydanticAIClient com mocks**

```python
# tests/test_llm_pydantic_ai.py
import pytest
from pydantic import BaseModel
from translaterany.config.model import LLMConfig
from translaterany.llm.client import LLMRequest, LLMResponse, LLMTransientError, LLMRefusalError
from translaterany.llm.pydantic_ai_client import PydanticAIClient


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


def test_pydantic_ai_client_maps_connection_error(monkeypatch):
    config = LLMConfig()
    client = PydanticAIClient(config)

    async def mock_run_fail(*args, **kwargs):
        import httpx

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
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_llm_pydantic_ai.py -v`
Expected: FAIL (`PydanticAIClient` não definido)

- [ ] **Step 3: Implementar `PydanticAIClient`**

Criar `src/translaterany/llm/pydantic_ai_client.py`:
```python
import asyncio
from typing import Any
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
import httpx

from translaterany.config.model import LLMConfig
from translaterany.llm.client import (
    LLMClient,
    LLMConfigError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
    Usage,
)


class PydanticAIClient(LLMClient):
    def __init__(self, config: LLMConfig):
        self.config = config

    def _resolve_model(self, model_alias: str) -> tuple[str, str, dict[str, Any]]:
        # Resolve se model_alias for o nome direto ou tarefa do perfil ativo
        active_profile = self.config.profiles.get(self.config.profile)
        if active_profile and hasattr(active_profile, model_alias):
            model_alias = getattr(active_profile, model_alias)

        if model_alias not in self.config.models:
            raise LLMConfigError(f"Modelo '{model_alias}' não configurado em [llm.models].")

        model_cfg = self.config.models[model_alias]
        provider_cfg = self.config.providers.get(model_cfg.provider)
        if not provider_cfg:
            raise LLMConfigError(f"Provedor '{model_cfg.provider}' não configurado em [llm.providers].")

        extra_args: dict[str, Any] = {"temperature": model_cfg.temperature}
        if model_cfg.num_ctx:
            extra_args["extra_body"] = {"num_ctx": model_cfg.num_ctx}

        return model_cfg.model, provider_cfg.base_url or "http://localhost:11434/v1", extra_args

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        model_name, base_url, extra_args = self._resolve_model(request.model)

        model = OpenAIModel(
            model_name=model_name,
            base_url=base_url,
            api_key="ollama",
        )

        agent = Agent(
            model=model,
            system_prompt=request.instructions,
            result_type=request.output_type,
        )

        try:
            # Executa sincronicamente a chamada assíncrona do pydantic-ai
            result = asyncio.run(agent.run(request.prompt))
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise LLMTransientError(f"Erro de conexão com o modelo ({model_name}): {exc}") from exc
        except Exception as exc:
            msg = str(exc).lower()
            if "safety" in msg or "refus" in msg:
                raise LLMRefusalError(f"Requisição recusada pelo modelo: {exc}") from exc
            if "validation" in msg or "json" in msg:
                raise LLMOutputError(f"Falha de validação da saída estruturada: {exc}") from exc
            raise

        usage = Usage(
            input_tokens=getattr(result.usage(), "request_tokens", 0) or 0,
            output_tokens=getattr(result.usage(), "response_tokens", 0) or 0,
        )

        return LLMResponse(
            output=result.data,
            model_id=model_name,
            usage=usage,
        )
```

Exportar `PydanticAIClient` em `src/translaterany/llm/__init__.py`.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_llm_pydantic_ai.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/llm/ tests/test_llm_pydantic_ai.py
git commit -m "feat(llm): implementação de PydanticAIClient com suporte a Ollama"
```

---

### Task 3: Agrupamento em Blocos (Chunking) e Janela Deslizante (`subtitles/chunking.py`)

**Files:**
- Create: `src/translaterany/subtitles/chunking.py`
- Test: `tests/test_chunking.py`

**Interfaces:**
- Consumes: lista de falas (`id`, `text`)
- Produces: `DialogueBatch`, `DialogueLine`, `ContextLine`, `create_dialogue_batches(lines, max_tokens, context_size)`

- [ ] **Step 1: Escrever teste com falha para divisão em blocos e janela deslizante**

```python
# tests/test_chunking.py
from translaterany.subtitles.chunking import DialogueLine, create_dialogue_batches


def test_chunking_creates_batches_with_sliding_context():
    lines = [DialogueLine(id=str(i), text=f"Line number {i} with some english content.") for i in range(1, 61)]
    # Com teto baixo de tokens, deve gerar múltiplos blocos
    batches = create_dialogue_batches(lines, max_tokens_per_batch=150, max_context_lines=5)
    assert len(batches) > 1

    # O primeiro lote não tem contexto anterior
    assert len(batches[0].context) == 0
    assert len(batches[0].lines) > 0

    # O segundo lote deve conter contexto das falas anteriores
    assert len(batches[1].context) > 0
    assert batches[1].context[-1].text == batches[0].lines[-1].text


def test_prompt_formatting():
    from translaterany.subtitles.chunking import format_batch_prompt
    from translaterany.subtitles.chunking import ContextLine

    batch_lines = [DialogueLine(id="1", text="Hello"), DialogueLine(id="2", text="World")]
    context = [ContextLine(text="Previous statement")]
    prompt = format_batch_prompt(batch_lines, context)
    assert "[CONTEXTO RECENTE" in prompt
    assert "Previous statement" in prompt
    assert "[FALAS A TRADUZIR" in prompt
    assert "[1] Hello" in prompt
    assert "[2] World" in prompt
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: FAIL (`chunking.py` não existe)

- [ ] **Step 3: Implementar `subtitles/chunking.py`**

Criar `src/translaterany/subtitles/chunking.py`:
```python
from dataclasses import dataclass
from pydantic import BaseModel


class DialogueLine(BaseModel):
    id: str
    text: str


class ContextLine(BaseModel):
    text: str


@dataclass(frozen=True)
class DialogueBatch:
    lines: list[DialogueLine]
    context: list[ContextLine]


def estimate_tokens(text: str) -> int:
    """Estimativa rápida de tokens (~4 caracteres por token)."""
    return max(1, len(text) // 4)


def create_dialogue_batches(
    lines: list[DialogueLine],
    max_tokens_per_batch: int = 800,
    max_context_lines: int = 5,
) -> list[DialogueBatch]:
    batches: list[DialogueBatch] = []
    current_lines: list[DialogueLine] = []
    current_tokens = 0
    recent_history: list[ContextLine] = []

    for line in lines:
        line_tokens = estimate_tokens(line.text) + 6  # overhead por fala
        if current_lines and (current_tokens + line_tokens > max_tokens_per_batch):
            batches.append(DialogueBatch(lines=current_lines, context=list(recent_history[-max_context_lines:])))
            for cl in current_lines:
                recent_history.append(ContextLine(text=cl.text))
            current_lines = [line]
            current_tokens = line_tokens
        else:
            current_lines.append(line)
            current_tokens += line_tokens

    if current_lines:
        batches.append(DialogueBatch(lines=current_lines, context=list(recent_history[-max_context_lines:])))

    return batches


def format_batch_prompt(lines: list[DialogueLine], context: list[ContextLine]) -> str:
    sections: list[str] = []
    if context:
        sections.append("[CONTEXTO RECENTE - APENAS LEITURA, NÃO TRADUZIR]:")
        for idx, ctx in enumerate(context, 1):
            sections.append(f"[CTX-{idx}] {ctx.text}")
        sections.append("")

    sections.append("[FALAS A TRADUZIR]:")
    for line in lines:
        sections.append(f"[{line.id}] {line.text}")

    return "\n".join(sections)
```

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_chunking.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/chunking.py tests/test_chunking.py
git commit -m "feat(subtitles): agrupamento dinâmico em blocos com janela de contexto"
```

---

### Task 4: Motor de Tradução e Cascata de Resiliência (`subtitles/translator.py`)

**Files:**
- Create: `src/translaterany/subtitles/translator.py`
- Test: `tests/test_translator_resilience.py`

**Interfaces:**
- Consumes: `LLMClient`, `DialogueBatch`, `DialogueLine`
- Produces: `DialogueBatchTranslator.translate_lines(lines) -> dict[str, str]` (mapeamento id → tradução pt-BR)

- [ ] **Step 1: Escrever testes com falha cobrindo os 4 níveis da cascata**

```python
# tests/test_translator_resilience.py
from pydantic import BaseModel
from translaterany.llm.client import LLMClient, LLMRequest, LLMResponse, LLMTransientError, LLMOutputError, Usage
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.translator import DialogueBatchTranslator, TranslationBatch, TranslationItem


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
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_translator_resilience.py -v`
Expected: FAIL (`translator.py` não existe)

- [ ] **Step 3: Implementar `subtitles/translator.py`**

Criar `src/translaterany/subtitles/translator.py`:
```python
import logging
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from translaterany.llm.client import (
    LLMClient,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMTransientError,
    Usage,
)
from translaterany.subtitles.chunking import (
    ContextLine,
    DialogueBatch,
    DialogueLine,
    create_dialogue_batches,
    format_batch_prompt,
)

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = """Você é um tradutor especialista de legendas de animes (Inglês para Português do Brasil).
Sua missão é produzir diálogos naturais, coloquiais e fluidos no estilo de fansubs brasileiros de alta qualidade.
Mantenha rigorosamente o significado pretendido, pontuação expressiva (... ! ?) e estilo de cada personagem.
Você DEVE devolver exclusivamente a estrutura solicitada, contendo a tradução de todas as falas identificadas por seus IDs.
NÃO traduza as falas marcadas como contexto."""


class TranslationItem(BaseModel):
    id: str
    text: str


class TranslationBatch(BaseModel):
    items: list[TranslationItem] = Field(default_factory=list)


class DialogueBatchTranslator:
    def __init__(
        self,
        client: LLMClient,
        model_name: str = "translategemma",
        fallback_model: str | None = None,
        max_tokens_per_batch: int = 800,
        max_context_lines: int = 5,
    ):
        self.client = client
        self.model_name = model_name
        self.fallback_model = fallback_model
        self.max_tokens_per_batch = max_tokens_per_batch
        self.max_context_lines = max_context_lines
        self.total_usage = Usage()
        self.fallback_count = 0

    @retry(
        retry=retry_if_exception_type(LLMTransientError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _call_model(self, prompt: str, target_model: str) -> tuple[TranslationBatch, Usage]:
        req = LLMRequest(
            model=target_model,
            instructions=SYSTEM_INSTRUCTIONS,
            prompt=prompt,
            output_type=TranslationBatch,
        )
        res = self.client.generate(req)
        return res.output, res.usage

    def _process_batch(self, lines: list[DialogueLine], context: list[ContextLine]) -> dict[str, str]:
        if not lines:
            return {}

        prompt = format_batch_prompt(lines, context)
        expected_ids = {l.id for l in lines}
        target_model = self.model_name

        try:
            output, usage = self._call_model(prompt, target_model)
        except LLMRefusalError as exc:
            if self.fallback_model and self.fallback_model != target_model:
                logger.warning("Recusa de modelo de nuvem (%s). Tentando modelo local %s.", exc, self.fallback_model)
                target_model = self.fallback_model
                output, usage = self._call_model(prompt, target_model)
            else:
                output, usage = None, Usage()
        except LLMOutputError:
            output, usage = None, Usage()

        self.total_usage = Usage(
            input_tokens=self.total_usage.input_tokens + usage.input_tokens,
            output_tokens=self.total_usage.output_tokens + usage.output_tokens,
        )

        translations: dict[str, str] = {}
        if output:
            for item in output.items:
                if item.id in expected_ids:
                    translations[item.id] = item.text

        # Nível 2: Reconciliação de IDs ausentes
        missing_ids = expected_ids - set(translations.keys())
        if missing_ids and len(missing_ids) < len(lines):
            missing_lines = [l for l in lines if l.id in missing_ids]
            sub_results = self._process_batch(missing_lines, context)
            translations.update(sub_results)
            missing_ids = expected_ids - set(translations.keys())

        # Nível 3: Bisseção recursiva
        if missing_ids:
            if len(lines) > 1:
                mid = len(lines) // 2
                left = self._process_batch(lines[:mid], context)
                right = self._process_batch(lines[mid:], context)
                left.update(right)
                return left
            else:
                # Nível 4: Degradação graciosa
                failed_line = lines[0]
                logger.warning(
                    "Falha ao traduzir fala id=%s ('%s'). Mantendo original.", failed_line.id, failed_line.text
                )
                self.fallback_count += 1
                return {failed_line.id: failed_line.text}

        return translations

    def translate_lines(self, lines: list[DialogueLine]) -> dict[str, str]:
        batches = create_dialogue_batches(
            lines,
            max_tokens_per_batch=self.max_tokens_per_batch,
            max_context_lines=self.max_context_lines,
        )
        all_translations: dict[str, str] = {}
        recent_context: list[ContextLine] = []

        for batch in batches:
            batch_result = self._process_batch(batch.lines, recent_context)
            all_translations.update(batch_result)
            for line in batch.lines:
                recent_context.append(ContextLine(text=batch_result.get(line.id, line.text)))
            if len(recent_context) > self.max_context_lines:
                recent_context = recent_context[-self.max_context_lines :]

        return all_translations
```

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_translator_resilience.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/translator.py tests/test_translator_resilience.py
git commit -m "feat(subtitles): motor de tradução com resiliência em 4 níveis"
```

---

### Task 5: Etapa de Pipeline `translate_dialogue` (`stages/translate_dialogue.py`, `stages/write.py`)

**Files:**
- Create: `src/translaterany/stages/translate_dialogue.py`
- Modify: `src/translaterany/stages/__init__.py`
- Modify: `src/translaterany/stages/write.py`
- Modify: `src/translaterany/pipeline/registry.py`
- Test: `tests/test_stages_translate_dialogue.py`

**Interfaces:**
- Consumes: artefato `units.json` emitido por `classify`
- Produces: artefato `translated_units.json` com `translates: ClassVar[bool] = True`

- [ ] **Step 1: Escrever teste com falha para a etapa `translate_dialogue`**

```python
# tests/test_stages_translate_dialogue.py
from translaterany.llm.fake import FakeLLM
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.subtitles.classify import ClassifiedUnit, ClassifiedUnitCollection


def test_translate_dialogue_preserves_inline_tags(tmp_path):
    # Unidade com tags de formatação ASS
    unit = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text=r"{\an8}Hello {\b1}world{\b0}!",
        clean_text="Hello world!",
        prefix=r"{\an8}",
        suffix="",
        start_ms=1000,
        end_ms=2500,
        style="Default",
    )
    collection = ClassifiedUnitCollection(units=[unit])

    # FakeLLM devolvendo tradução simples
    fake_llm = FakeLLM(responses={"Hello world!": "Olá mundo!"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated_collection = stage.translate_collection(collection)
    res_unit = translated_collection.units[0]
    assert res_unit.clean_text == "Olá mundo!"
    assert r"{\an8}" in res_unit.raw_text
    assert res_unit.start_ms == 1000
    assert res_unit.end_ms == 2500
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_stages_translate_dialogue.py -v`
Expected: FAIL (`StageTranslateDialogue` não existe)

- [ ] **Step 3: Implementar `stages/translate_dialogue.py` e plugar no `write`**

Criar `src/translaterany/stages/translate_dialogue.py`:
```python
from typing import Any, ClassVar
from pathlib import Path
from translaterany.pipeline.stage import Stage, StageContext
from translaterany.llm.client import LLMClient
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.translator import DialogueBatchTranslator
from translaterany.subtitles.classify import ClassifiedUnit, ClassifiedUnitCollection


class StageTranslateDialogue(Stage):
    name: ClassVar[str] = "translate_dialogue"
    scope: ClassVar[str] = "episode"
    translates: ClassVar[bool] = True
    inputs: ClassVar[list[str]] = ["classify"]
    enabled_by_default: ClassVar[bool] = True

    def __init__(self, client: LLMClient | None = None, options: dict[str, Any] | None = None):
        super().__init__(options)
        self.client = client

    def translate_collection(self, collection: ClassifiedUnitCollection) -> ClassifiedUnitCollection:
        dialogue_units = [u for u in collection.units if u.line_type == "dialogue"]
        if not dialogue_units or not self.client:
            return collection

        lines = [DialogueLine(id=u.id, text=u.clean_text) for u in dialogue_units]
        translator = DialogueBatchTranslator(client=self.client)
        translations = translator.translate_lines(lines)

        new_units: list[ClassifiedUnit] = []
        for u in collection.units:
            if u.id in translations:
                tr_text = translations[u.id]
                # Reinsere prefixos/sufixos de tags
                new_raw = f"{u.prefix}{tr_text}{u.suffix}"
                new_units.append(u.model_copy(update={"clean_text": tr_text, "raw_text": new_raw}))
            else:
                new_units.append(u)

        return ClassifiedUnitCollection(units=new_units)

    def run(self, ctx: StageContext) -> Path:
        input_file = ctx.input_artifacts["classify"]
        data = input_file.read_text(encoding="utf-8")
        collection = ClassifiedUnitCollection.model_validate_json(data)

        translated = self.translate_collection(collection)
        out_path = ctx.artifact_dir / "translated_units.json"
        out_path.write_text(translated.model_dump_json(indent=2), encoding="utf-8")
        return out_path
```

Atualizar `src/translaterany/stages/write.py` para apontar `text_source = "translate_dialogue"` por padrão, e registrar no pipeline registry.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_stages_translate_dialogue.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/ src/translaterany/pipeline/ tests/test_stages_translate_dialogue.py
git commit -m "feat(stages): etapa translate_dialogue integrada ao pipeline e gravação"
```

---

### Task 6: Diagnóstico de IA no `doctor` e Estimativa (`util/doctor.py`, `cli/doctor.py`, `cli/estimate.py`)

**Files:**
- Modify: `src/translaterany/util/doctor.py`
- Modify: `src/translaterany/cli/doctor.py`
- Create: `src/translaterany/cli/estimate.py`
- Modify: `src/translaterany/cli/app.py`
- Test: `tests/test_doctor_llm.py`
- Test: `tests/test_cli_estimate.py`

**Interfaces:**
- Produces: `check_ollama_service()`, `check_ollama_models()`, `check_nvidia_gpu()`, comando CLI `translaterany estimate`

- [ ] **Step 1: Escrever testes com falha para o doctor expandido e comando estimate**

```python
# tests/test_doctor_llm.py
from translaterany.util.doctor import check_ollama_status


def test_check_ollama_status_offline(monkeypatch):
    import httpx

    def mock_get(*args, **kwargs):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "get", mock_get)

    ok, msg = check_ollama_status("http://localhost:11434")
    assert ok is False
    assert "não está acessível" in msg


def test_check_ollama_status_ok(monkeypatch):
    import httpx

    class MockResp:
        status_code = 200

        def json(self):
            return {"models": [{"name": "translategemma:12b"}, {"name": "gemma4:12b"}]}

    monkeypatch.setattr(httpx, "get", lambda *a, **kw: MockResp())

    ok, msg = check_ollama_status("http://localhost:11434")
    assert ok is True
    assert "translategemma:12b" in msg
```

```python
# tests/test_cli_estimate.py
from typer.testing import CliRunner
from translaterany.cli.app import app

runner = CliRunner()


def test_estimate_command_dry_run():
    result = runner.invoke(app, ["estimate", "--help"])
    assert result.exit_code == 0
    assert "estatísticas e estimativa de tokens" in result.output.lower()
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_doctor_llm.py tests/test_cli_estimate.py -v`
Expected: FAIL (funções e comandos não definidos)

- [ ] **Step 3: Implementar checagens de Ollama/GPU no doctor e comando estimate**

Adicionar checagens em `src/translaterany/util/doctor.py`:
- `check_ollama_status(url)`: consulta `/api/version` e `/api/tags`.
- `check_nvidia_gpu()`: executa `nvidia-smi` e extrai modelo e memória livre.
- Integrar no comando `translaterany doctor`.
- Adicionar comando `estimate` no Typer em `src/translaterany/cli/estimate.py`.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_doctor_llm.py tests/test_cli_estimate.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/util/ src/translaterany/cli/ tests/test_doctor_llm.py tests/test_cli_estimate.py
git commit -m "feat(cli): verificações de IA no doctor e comando estimate"
```

---

### Task 7: Testes Ponta a Ponta do M2 e Validação Real

**Files:**
- Create: `tests/test_m2_e2e.py`
- Modify: `STATE.md`

**Interfaces:**
- Teste de integração ponta a ponta: MKV sintético → `extract` → `normalize` → `classify` → `translate_dialogue` → `write` → `.pt-BR.ass` com autoria `; TranslaterAny`.

- [ ] **Step 1: Escrever teste de integração ponta a ponta do M2**

```python
# tests/test_m2_e2e.py
from pathlib import Path
from translaterany.config.loader import load_config_from_str
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.runner import PipelineRunner
from tests.mkvtools import create_synthetic_mkv


def test_m2_pipeline_end_to_end(tmp_path):
    video_path = tmp_path / "Season 1" / "Anime S01E01.mkv"
    create_synthetic_mkv(video_path, dialogues=[("00:00:01.000", "00:00:03.000", "Hello! Good morning.")])

    config = load_config_from_str("")
    fake_llm = FakeLLM(responses={"Hello! Good morning.": "Olá! Bom dia."})
    runner = PipelineRunner(config=config, client=fake_llm)

    result = runner.run_series(tmp_path)
    assert result.status == "success"

    # Verifica se o arquivo .ass gerado contém a tradução e a marca de autoria
    ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text(encoding="utf-8")
    assert "; TranslaterAny" in content
    assert "Olá! Bom dia." in content
```

- [ ] **Step 2: Executar teste de integração**

Run: `uv run pytest tests/test_m2_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Executar a suíte de testes completa do projeto**

Run: `uv run pytest`
Expected: Todos os testes passando (237 do M0/M1 + novos testes do M2).

- [ ] **Step 4: Executar validação de formatação e linter**

Run: `uv run ruff check .`
Expected: Limpo sem erros.

- [ ] **Step 5: Commit e atualização do STATE.md**

```bash
git add tests/test_m2_e2e.py STATE.md
git commit -m "test(m2): teste ponta a ponta do Marco 2 e atualização do estado"
```
