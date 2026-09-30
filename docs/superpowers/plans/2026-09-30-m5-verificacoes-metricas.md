# M5 — Verificações e métricas · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** medir a qualidade e o processo do pipeline — checagens determinísticas reutilizáveis, métricas de processo no manifest, `metrics.json` por episódio e o comando `translaterany report` com linha de base.

**Architecture:** `MeteredLLM` envolve o `LLMClient` por (etapa, unidade) e o runner grava `llm` + `counters` no `StageRecord` (manifest schema 2). A etapa `quality_checks`, última do pipeline, aplica o pacote puro `translaterany.checks` a cada instantâneo de texto (`produces_texts`) e grava `metrics.json`. `pipeline/report.py` agrega manifests + métricas num `SeriesReport`; `cli/report.py` só formata.

**Tech Stack:** Python 3.14 (`uv`), pydantic 2, typer + rich, pytest, `fonttools` (nova), MKVToolNix (`mkvextract attachments`).

**Spec:** [`docs/superpowers/specs/2026-09-30-m5-verificacoes-metricas-design.md`](../specs/2026-09-30-m5-verificacoes-metricas-design.md)

## Global Constraints

- Python **3.14**, dependências via `uv add`; única dependência nova: `fonttools`.
- Identificadores e código em **inglês**; mensagens ao usuário (CLI, `Finding.message`, logs) em **PT-BR**.
- Limites padrão (Netflix PT-BR): `max_cps = 17.0`, `max_cpl = 42`, `max_lines = 2`; exceder qualquer um é `error`.
- `length_ratio = [0.5, 2.0]`, `length_ratio_min_chars = 10`.
- Testes **somente sintéticos**; nunca versionar mídia nem trechos das legendas reais (`temporada-teste/` fica fora do git).
- Linhas de base versionadas (`docs/baselines/`) contêm só números agregados — `SeriesReport` nunca carrega texto de legenda.
- `quality_checks` nunca derruba o episódio por causa de uma checagem ou de fontes: vira `Finding`.
- O repositório já tem 41 erros antigos de `ruff`; o critério é **nenhum erro novo nos arquivos criados/alterados**: `uv run ruff check <arquivos da tarefa>`.
- Comando de testes: `uv run pytest -q` (a partir da raiz do repositório). Suíte atual: 396 testes passando.
- Commits em português no estilo `tipo(escopo): descrição`, terminando com:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016JxmXtx9vC6M6DTzHoujm8
  ```

## Review Focus

1. **Evento com duração zero ou negativa** (comum em placas/efeitos do fansub) — CPS não é calculado (sem divisão por zero, sem `inf` no JSON); CPL/linhas continuam checados. Teste na Tarefa 3.
2. **Estado sem nenhuma etapa de texto** (pipeline sem `translate_*`/`redistribute`, ou `UnitTexts` vazio) — `quality_checks` grava `metrics.json` válido com `lines = 0` e percentis 0. Teste na Tarefa 10.
3. **Manifest antigo (schema 1) de uma série já traduzida no M4** — `status`, `run` e `report` funcionam; o registro é regravado como 2 sem perder etapas. Teste na Tarefa 6.
4. **Fontes do fansub inválidas ou com nome diferente do estilo** (arquivo corrompido, `@Fonte` vertical, caixa diferente) — vira `info`, casamento sem diferenciar caixa e sem `@`. Teste na Tarefa 4.
5. **Série com parte dos episódios sem `metrics.json` ou com `metrics.json` corrompido** — `report` agrega os demais e lista os ausentes; só sai com código 1 se nenhum tiver métricas. Teste na Tarefa 12.

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/translaterany/config/model.py` (mod.) | `ChecksConfig`; preços em `ModelConfig`; `AppConfig.checks` |
| `src/translaterany/config/loader.py` (mod.) | valida `checks.disabled`; chama `bind_pipeline` |
| `src/translaterany/llm/pricing.py` (novo) | `PriceFn`, `price_lookup(LLMConfig)` |
| `src/translaterany/llm/metered.py` (novo) | `ModelStats`, `LLMStats`, `MeteredLLM` |
| `src/translaterany/pipeline/stage_metrics.py` (novo) | `StageMetrics`, `count(ctx, ...)` |
| `src/translaterany/pipeline/stage.py` (mod.) | `produces_texts`, `bind_pipeline`, `StageContext.metrics` |
| `src/translaterany/pipeline/manifest.py` (mod.) | schema 2, `StageRecord.llm/counters` |
| `src/translaterany/pipeline/runner.py` (mod.) | cria `MeteredLLM`/`StageMetrics` e grava no registro; `prices` |
| `src/translaterany/memory/matching.py` (novo) | `matches_term`, `select_for_text` (antes privados em `translate_dialogue`) |
| `src/translaterany/checks/__init__.py` (novo) | API pública do pacote; importa as regras para registrá-las |
| `src/translaterany/checks/models.py` (novo) | `LineInput`, `CheckEnv`, `Finding`, `Severity` |
| `src/translaterany/checks/text.py` (novo) | texto visível, linhas, palavras |
| `src/translaterany/checks/registry.py` (novo) | `LineCheck`, `CHECKS`, `line_check`, `run_line_checks`, `check_names` |
| `src/translaterany/checks/lexicon.py` (novo) | listas de palavras e regexes |
| `src/translaterany/checks/rules_basic.py` (novo) | `markers`, `untranslated`, `length_ratio`, `numbers`, `negation` |
| `src/translaterany/checks/rules_context.py` (novo) | `names`, `glossary`, `foreign_markers`, `reading_speed` + `measure` |
| `src/translaterany/checks/fonts.py` (novo) | estilos→fonte, `\fn`, faces via fontTools, `check_font_glyphs` |
| `src/translaterany/checks/snapshots.py` (novo) | fontes das linhas, estado acumulado, delta, resumos, CPS |
| `src/translaterany/checks/metrics.py` (novo) | `EpisodeMetrics` e submodelos |
| `src/translaterany/media/mkv.py` (mod.) | `font_attachments`, `extract_attachments` |
| `src/translaterany/stages/quality_checks.py` (novo) | etapa `quality_checks` |
| `src/translaterany/stages/__init__.py` (mod.) | registra e põe `quality_checks` no fim do `DEFAULT_PIPELINE` |
| `src/translaterany/subtitles/translator.py`, `signs.py`, `songs.py` (mod.) | contadores |
| `src/translaterany/stages/{translate_dialogue,translate_signs,translate_songs,classify,translation_memory,merge_sentences,redistribute_sentences}.py` (mod.) | contadores, `produces_texts`, correção `episode.key` |
| `src/translaterany/pipeline/report.py` (novo) | `SeriesReport`, `build_report`, `compare_reports`, `load_episode_metrics` |
| `src/translaterany/cli/report.py` (novo) | comando `report` |
| `src/translaterany/cli/app.py`, `cli/run.py`, `cli/estimate.py` (mod.) | registrar `report`; passar `prices`; preços do config |

---

### Task 1: Configuração — `[checks]`, preços por modelo e `price_lookup`

**Files:**
- Modify: `src/translaterany/config/model.py`
- Create: `src/translaterany/llm/pricing.py`
- Modify: `src/translaterany/cli/estimate.py:110-114`
- Test: `tests/test_config_checks.py`

**Interfaces:**
- Produces: `ChecksConfig` (campos `max_cps: float`, `max_cpl: int`, `max_lines: int`, `length_ratio: tuple[float, float]`, `length_ratio_min_chars: int`, `disabled: list[str]`); `AppConfig.checks: ChecksConfig`; `ModelConfig.input_price_per_mtok: float`, `ModelConfig.output_price_per_mtok: float`; `type PriceFn = Callable[[str], tuple[float, float]]`; `price_lookup(cfg: LLMConfig) -> PriceFn`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_checks.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_checks.py -v`
Expected: FAIL com `ImportError: cannot import name 'ChecksConfig'`.

- [ ] **Step 3: Write minimal implementation**

Em `src/translaterany/config/model.py`, altere `ModelConfig` e acrescente `ChecksConfig` + campo no `AppConfig`:

```python
class ModelConfig(_Strict):
    provider: str
    model: str
    num_ctx: int = 4096
    temperature: float = 0.3
    input_price_per_mtok: float = 0.0  # USD por milhão de tokens de entrada
    output_price_per_mtok: float = 0.0  # USD por milhão de tokens de saída


class ChecksConfig(_Strict):
    """Limites das checagens (M5). Padrão Netflix PT-BR para velocidade de leitura."""

    max_cps: float = 17.0
    max_cpl: int = 42
    max_lines: int = 2
    length_ratio: tuple[float, float] = (0.5, 2.0)
    length_ratio_min_chars: int = 10
    disabled: list[str] = Field(default_factory=list)
```

e no `AppConfig`, depois de `translation`:

```python
    checks: ChecksConfig = Field(default_factory=ChecksConfig)
```

Crie `src/translaterany/llm/pricing.py`:

```python
"""Tabela de preços por apelido de modelo (USD por milhão de tokens)."""

from collections.abc import Callable

from translaterany.config.model import LLMConfig

type PriceFn = Callable[[str], tuple[float, float]]


def price_lookup(cfg: LLMConfig) -> PriceFn:
    """Resolve o apelido como o PydanticAIClient: papel do perfil ativo (translate/review) ou chave de modelo."""

    def prices(alias: str) -> tuple[float, float]:
        profile = cfg.profiles.get(cfg.profile)
        key = alias
        if profile is not None and alias in ("translate", "review"):
            key = getattr(profile, alias)
        model = cfg.models.get(key)
        if model is None:
            return (0.0, 0.0)
        return (model.input_price_per_mtok, model.output_price_per_mtok)

    return prices
```

Em `src/translaterany/cli/estimate.py`, troque o bloco "Custo financeiro":

```python
            # Custo financeiro (preços do config; Ollama tem preço 0 por padrão)
            if model_cfg is None:
                cost_usd = 0.0
            else:
                cost_usd = (
                    input_tokens * model_cfg.input_price_per_mtok + output_tokens * model_cfg.output_price_per_mtok
                ) / 1_000_000
```

e o total (linha ~156):

```python
        total_cost = (
            (total_input_tokens * model_cfg.input_price_per_mtok + total_output_tokens * model_cfg.output_price_per_mtok)
            / 1_000_000
            if model_cfg is not None
            else 0.0
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_checks.py tests/test_cli_estimate.py tests/test_config.py tests/test_config_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/config/model.py src/translaterany/llm/pricing.py tests/test_config_checks.py
git add src/translaterany/config/model.py src/translaterany/llm/pricing.py src/translaterany/cli/estimate.py tests/test_config_checks.py
git commit -m "feat(config): adiciona seção [checks] e preços por modelo"
```

---

### Task 2: Núcleo do pacote `checks` + regras básicas

**Files:**
- Create: `src/translaterany/checks/__init__.py`, `models.py`, `text.py`, `registry.py`, `lexicon.py`, `rules_basic.py`
- Modify: `src/translaterany/config/loader.py` (validação de `checks.disabled`)
- Test: `tests/test_checks_basic.py`, `tests/test_config_checks.py` (novo teste)

**Interfaces:**
- Consumes: `ChecksConfig` (Tarefa 1); `GlossaryEntry` (`memory/models.py`); `MARKER_RE`, `marker_ids` (`subtitles/segments.py`); `LINE_TYPES` (`pipeline/units.py`).
- Produces:
  - `type Severity = Literal["info", "warn", "error"]`
  - `LineInput(id: str, line_type: str, style: str = "", source: str, target: str, duration_ms: int = 0)`
  - `CheckEnv(glossary: list[GlossaryEntry] = [], names: list[list[str]] = [], limits: ChecksConfig = ChecksConfig())` — `names` é uma lista de grupos (nome + aliases de cada personagem)
  - `Finding(check: str, unit_id: str | None = None, severity: Severity, message: str, value: float | None = None, excerpt: str | None = None)`
  - `visible(text) -> str`, `visible_lines(text) -> list[str]`, `plain(text) -> str`, `words(text) -> list[str]`
  - `LineCheck(name, line_types, fn)`, `CHECKS: dict[str, LineCheck]`, `line_check(name, line_types)` (decorador), `EPISODE_CHECKS = ("font_glyphs",)`, `check_names() -> set[str]`, `run_line_checks(lines: Iterable[LineInput], env: CheckEnv) -> list[Finding]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_checks_basic.py
"""Checagens básicas: markers, untranslated, length_ratio, numbers, negation (M5)."""

from translaterany.checks import CheckEnv, Finding, LineInput, check_names, run_line_checks
from translaterany.checks.registry import CHECKS, line_check
from translaterany.checks.text import plain, visible_lines, words
from translaterany.config.model import ChecksConfig


def line(src: str, tgt: str, *, kind: str = "dialogue", dur: int = 3000) -> LineInput:
    return LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=dur)


def only(findings: list[Finding], check: str) -> list[Finding]:
    return [f for f in findings if f.check == check]


ENV = CheckEnv()


def test_text_helpers_strip_tags_markers_and_breaks() -> None:
    assert visible_lines("Olá⟦1⟧ mundo\\Nsegunda {\\i1}linha") == ["Olá mundo", "segunda linha"]
    assert plain("A\\Nb") == "A b"
    assert words("Don't stop, 42 now") == ["don't", "stop", "now"]


def test_markers_ok_and_missing() -> None:
    assert not only(run_line_checks([line("To the ⟦1⟧old⟦2⟧ station", "Para a ⟦1⟧velha⟦2⟧ estação")], ENV), "markers")
    found = only(run_line_checks([line("To the ⟦1⟧old⟦2⟧ station", "Para a velha⟦2⟧ estação")], ENV), "markers")
    assert [f.severity for f in found] == ["error"]


def test_untranslated_identical_and_english_words() -> None:
    same = only(run_line_checks([line("Where are we going?", "where are we  going?")], ENV), "untranslated")
    assert [f.severity for f in same] == ["error"]
    english = only(run_line_checks([line("What is this?", "What is this thing aqui")], ENV), "untranslated")
    assert english and english[0].severity == "error"
    # interjeição curta idêntica não é erro
    assert not only(run_line_checks([line("Huh?", "Huh?")], ENV), "untranslated")
    assert not only(run_line_checks([line("Where are we going?", "Para onde vamos?")], ENV), "untranslated")


def test_length_ratio_bounds_and_min_chars() -> None:
    long_src = "This is a fairly long sentence to translate."
    assert only(run_line_checks([line(long_src, "Curta.")], ENV), "length_ratio")[0].severity == "warn"
    assert not only(run_line_checks([line(long_src, "Esta é uma frase razoavelmente longa para traduzir.")], ENV), "length_ratio")
    assert not only(run_line_checks([line("Hi there", "Oi")], ENV), "length_ratio")  # < 10 caracteres


def test_numbers_missing() -> None:
    found = only(run_line_checks([line("I need 3 of them by 10.", "Preciso de três até as 10.")], ENV), "numbers")
    assert len(found) == 1 and "3" in found[0].message
    assert not only(run_line_checks([line("Room 42", "Sala 42")], ENV), "numbers")


def test_negation_dropped() -> None:
    assert only(run_line_checks([line("I don't know.", "Eu sei.")], ENV), "negation")
    assert only(run_line_checks([line("I don’t know.", "Eu sei.")], ENV), "negation")  # apóstrofo curvo
    assert not only(run_line_checks([line("I don't know.", "Eu não sei.")], ENV), "negation")
    assert not only(run_line_checks([line("I know.", "Eu sei.")], ENV), "negation")


def test_line_types_are_respected() -> None:
    assert not only(run_line_checks([line("I don't know.", "Eu sei.", kind="song")], ENV), "negation")


def test_disabled_checks_are_skipped() -> None:
    env = CheckEnv(limits=ChecksConfig(disabled=["negation"]))
    assert not only(run_line_checks([line("I don't know.", "Eu sei.")], env), "negation")


def test_crashing_check_becomes_finding() -> None:
    @line_check("t_boom", {"dialogue"})
    def boom(line: LineInput, env: CheckEnv) -> list[Finding]:
        raise ValueError("quebrou")

    try:
        found = only(run_line_checks([line("a", "b")], ENV), "check_crashed")
        assert found[0].severity == "error" and "t_boom" in found[0].message
    finally:
        CHECKS.pop("t_boom")


def test_check_names_include_episode_checks() -> None:
    assert {"markers", "untranslated", "length_ratio", "numbers", "negation", "font_glyphs"} <= check_names()
```

Acrescente a `tests/test_config_checks.py`:

```python
import pytest

from translaterany.config.loader import ConfigError, load_config


def test_unknown_disabled_check_is_config_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[checks]\ndisabled = ["nao_existe"]\n', encoding="utf-8")
    with pytest.raises(ConfigError, match="checks.disabled"):
        load_config(path, tmp_path / "data")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_checks_basic.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.checks'`.

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/checks/models.py`:

```python
"""Modelos das checagens: entrada por linha, ambiente do episódio e achados."""

from typing import Literal

from pydantic import BaseModel, Field

from translaterany.config.model import ChecksConfig
from translaterany.memory.models import GlossaryEntry

type Severity = Literal["info", "warn", "error"]


class LineInput(BaseModel):
    id: str  # id da unidade ou id composto ("u1+u2")
    line_type: str
    style: str = ""
    source: str  # EN com marcadores ⟦n⟧
    target: str  # PT-BR com marcadores ⟦n⟧
    duration_ms: int = 0


class CheckEnv(BaseModel):
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    names: list[list[str]] = Field(default_factory=list)  # nome + aliases de cada personagem
    limits: ChecksConfig = Field(default_factory=ChecksConfig)


class Finding(BaseModel):
    check: str
    unit_id: str | None = None  # None em checagens de episódio
    severity: Severity
    message: str
    value: float | None = None
    excerpt: str | None = None  # trecho do PT (só no estado final)
```

`src/translaterany/checks/text.py`:

```python
"""Texto visível de uma linha: sem marcadores, sem tags, com quebras \\N como separador."""

import re

from translaterany.subtitles.segments import MARKER_RE

_TAGS = re.compile(r"\{[^}]*\}")
_BREAK = re.compile(r"\\[Nn]")
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")


def visible(text: str) -> str:
    text = MARKER_RE.sub("", text)
    text = _TAGS.sub("", text)
    return text.replace("\\h", " ").replace("’", "'")


def visible_lines(text: str) -> list[str]:
    return [part.strip() for part in _BREAK.split(visible(text))]


def plain(text: str) -> str:
    return " ".join(part for part in visible_lines(text) if part)


def words(text: str) -> list[str]:
    return _WORD.findall(plain(text).lower())
```

`src/translaterany/checks/registry.py`:

```python
"""Registro das checagens de linha e execução tolerante a falhas."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from translaterany.checks.models import CheckEnv, Finding, LineInput

type CheckFn = Callable[[LineInput, CheckEnv], list[Finding]]

EPISODE_CHECKS: tuple[str, ...] = ("font_glyphs",)


@dataclass(frozen=True)
class LineCheck:
    name: str
    line_types: frozenset[str]
    fn: CheckFn


CHECKS: dict[str, LineCheck] = {}


def line_check(name: str, line_types: Iterable[str]) -> Callable[[CheckFn], CheckFn]:
    def decorator(fn: CheckFn) -> CheckFn:
        CHECKS[name] = LineCheck(name=name, line_types=frozenset(line_types), fn=fn)
        return fn

    return decorator


def check_names() -> set[str]:
    return set(CHECKS) | set(EPISODE_CHECKS)


def run_line_checks(lines: Iterable[LineInput], env: CheckEnv) -> list[Finding]:
    disabled = set(env.limits.disabled)
    findings: list[Finding] = []
    for line in lines:
        for check in CHECKS.values():
            if check.name in disabled or line.line_type not in check.line_types:
                continue
            try:
                findings.extend(check.fn(line, env))
            except Exception as exc:  # checagem com bug não derruba o episódio
                findings.append(
                    Finding(
                        check="check_crashed",
                        unit_id=line.id,
                        severity="error",
                        message=f"checagem '{check.name}' falhou: {type(exc).__name__}: {exc}",
                    )
                )
    return findings
```

`src/translaterany/checks/lexicon.py` (as regras de contexto da Tarefa 3 acrescentam listas aqui):

```python
"""Listas de palavras e padrões usados pelas checagens. Amplie aqui, não nas regras."""

import re

# Palavras funcionais inglesas que não existem como palavra em PT-BR ("a", "do", "no", "me", "se" ficam de fora).
EN_FUNCTION_WORDS = frozenset(
    {
        "the", "and", "you", "your", "is", "are", "was", "were", "to", "of", "what", "that", "this", "it",
        "i", "i'm", "don't", "it's", "with", "for", "have", "be", "will", "can", "my", "we", "they", "he",
        "she", "not", "just", "but", "there", "here", "all", "know", "why", "where", "when", "how",
    }
)  # fmt: skip

EN_NEGATION = re.compile(
    r"\b(?:not|never|no|nobody|nothing|none|neither|nor|without|nowhere|cannot)\b|n't\b", re.IGNORECASE
)
PT_NEGATION = re.compile(r"\b(?:não|nunca|nem|nada|ninguém|nenhum|nenhuma|jamais|sem)\b", re.IGNORECASE)
DIGITS = re.compile(r"\d+")
```

`src/translaterany/checks/rules_basic.py`:

```python
"""Checagens básicas de linha: marcadores, não traduzida, tamanho, números e negação."""

from collections import Counter

from translaterany.checks import lexicon
from translaterany.checks.models import CheckEnv, Finding, LineInput
from translaterany.checks.registry import line_check
from translaterany.checks.text import plain, words
from translaterany.pipeline.units import LINE_TYPES
from translaterany.subtitles.segments import marker_ids


@line_check("markers", LINE_TYPES)
def markers(line: LineInput, env: CheckEnv) -> list[Finding]:
    expected, got = Counter(marker_ids(line.source)), Counter(marker_ids(line.target))
    if expected == got:
        return []
    return [
        Finding(
            check="markers",
            unit_id=line.id,
            severity="error",
            message=f"marcadores divergentes: esperado {sorted(expected.elements())}, obtido {sorted(got.elements())}",
        )
    ]


@line_check("untranslated", {"dialogue", "sign"})
def untranslated(line: LineInput, env: CheckEnv) -> list[Finding]:
    src_words, tgt_words = words(line.source), words(line.target)
    if len(src_words) >= 2 and plain(line.source).casefold().split() == plain(line.target).casefold().split():
        return [Finding(check="untranslated", unit_id=line.id, severity="error", message="linha idêntica ao original")]
    if len(tgt_words) >= 3:
        ratio = sum(w in lexicon.EN_FUNCTION_WORDS for w in tgt_words) / len(tgt_words)
        if ratio >= 0.5:
            return [
                Finding(
                    check="untranslated",
                    unit_id=line.id,
                    severity="error",
                    message=f"texto parece estar em inglês ({ratio:.0%} de palavras funcionais inglesas)",
                    value=round(ratio, 3),
                )
            ]
    return []


@line_check("length_ratio", {"dialogue"})
def length_ratio(line: LineInput, env: CheckEnv) -> list[Finding]:
    src, tgt = plain(line.source), plain(line.target)
    if len(src) < env.limits.length_ratio_min_chars:
        return []
    ratio = len(tgt) / len(src)
    low, high = env.limits.length_ratio
    if low <= ratio <= high:
        return []
    return [
        Finding(
            check="length_ratio",
            unit_id=line.id,
            severity="warn",
            message=f"tamanho anômalo: tradução com {ratio:.2f}× o original",
            value=round(ratio, 3),
        )
    ]


@line_check("numbers", {"dialogue", "sign"})
def numbers(line: LineInput, env: CheckEnv) -> list[Finding]:
    missing = sorted(set(lexicon.DIGITS.findall(plain(line.source))) - set(lexicon.DIGITS.findall(plain(line.target))))
    if not missing:
        return []
    return [
        Finding(
            check="numbers", unit_id=line.id, severity="warn", message=f"número(s) ausente(s): {', '.join(missing)}"
        )
    ]


@line_check("negation", {"dialogue"})
def negation(line: LineInput, env: CheckEnv) -> list[Finding]:
    if lexicon.EN_NEGATION.search(plain(line.source)) and not lexicon.PT_NEGATION.search(plain(line.target)):
        return [
            Finding(check="negation", unit_id=line.id, severity="warn", message="negação do original sumiu na tradução")
        ]
    return []
```

`src/translaterany/checks/__init__.py`:

```python
"""Checagens determinísticas (sem IA, sem I/O), reutilizadas por métricas, triagem, portões e QA."""

from translaterany.checks import rules_basic  # noqa: F401 — registra as checagens
from translaterany.checks.models import CheckEnv, Finding, LineInput, Severity
from translaterany.checks.registry import CHECKS, check_names, run_line_checks

__all__ = ["CHECKS", "CheckEnv", "Finding", "LineInput", "Severity", "check_names", "run_line_checks"]
```

Em `config/loader.py`, função `load_config`, logo antes de `stages = _build_stages(config, registry, where)`:

```python
    from translaterany.checks import check_names  # import tardio: checks depende de config.model

    unknown = sorted(set(config.checks.disabled) - check_names())
    if unknown:
        raise ConfigError(
            _format(where, [f"checks.disabled: checagem desconhecida {', '.join(unknown)} "
                            f"(disponíveis: {', '.join(sorted(check_names()))})"])
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_checks_basic.py tests/test_config_checks.py tests/test_config.py -v`
Expected: PASS (inclusive `test_unknown_disabled_check_is_config_error`).

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/checks src/translaterany/config/loader.py tests/test_checks_basic.py
git add src/translaterany/checks src/translaterany/config/loader.py tests/test_checks_basic.py tests/test_config_checks.py
git commit -m "feat(checks): adiciona núcleo de checagens e regras básicas"
```

---

### Task 3: Checagens de contexto — nomes, glossário, marcadores estrangeiros e velocidade de leitura

**Files:**
- Create: `src/translaterany/memory/matching.py`, `src/translaterany/checks/rules_context.py`
- Modify: `src/translaterany/checks/lexicon.py`, `src/translaterany/checks/__init__.py`, `src/translaterany/stages/translate_dialogue.py:32-38,181-198`
- Test: `tests/test_checks_context.py`

**Interfaces:**
- Consumes: `line_check`, `CheckEnv`, `Finding`, `LineInput`, `visible_lines`, `plain` (Tarefa 2); `GlossaryEntry`, `CharacterEntry`.
- Produces:
  - `matches_term(term: str, text: str) -> bool`
  - `select_for_text(glossary: Iterable[GlossaryEntry], characters: Iterable[CharacterEntry], text: str) -> tuple[list[GlossaryEntry], list[CharacterEntry]]`
  - `measure(text: str, duration_ms: int) -> ReadingMeasure` com `ReadingMeasure(cps: float | None, max_cpl: int, lines: int)` (em `checks/rules_context.py`)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_checks_context.py
"""Checagens de contexto: names, glossary, foreign_markers, reading_speed (M5)."""

import pytest

from translaterany.checks import CheckEnv, Finding, LineInput, run_line_checks
from translaterany.checks.rules_context import measure
from translaterany.memory.matching import matches_term, select_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry


def line(src: str, tgt: str, *, kind: str = "dialogue", dur: int = 3000) -> LineInput:
    return LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=dur)


def only(findings: list[Finding], check: str) -> list[Finding]:
    return [f for f in findings if f.check == check]


def test_matches_term_word_boundaries() -> None:
    assert matches_term("Yu", "Yu, wait!")
    assert not matches_term("Yu", "Yuusuke")
    assert matches_term("Dr. Kim", "Hello Dr. Kim")
    assert not matches_term("", "x")


def test_select_for_text_filters_by_presence() -> None:
    glossary = [GlossaryEntry(term="Ability", translation="Habilidade"), GlossaryEntry(term="Zero", translation="Zero")]
    chars = [CharacterEntry(name="Yu Otosaka", aliases=["Yu"]), CharacterEntry(name="Nao")]
    g, c = select_for_text(glossary, chars, "Yu used his Ability.")
    assert [e.term for e in g] == ["Ability"]
    assert [x.name for x in c] == ["Yu Otosaka"]


def test_names_missing_in_translation() -> None:
    env = CheckEnv(names=[["Yu Otosaka", "Yu"]])
    assert only(run_line_checks([line("Yu, wait!", "Espera!")], env), "names")
    assert not only(run_line_checks([line("Yu, wait!", "Yu, espera!")], env), "names")


def test_glossary_expected_form() -> None:
    env = CheckEnv(
        glossary=[
            GlossaryEntry(term="Student Council", translation="Conselho Estudantil"),
            GlossaryEntry(term="Hoshinoumi", translation="", keep_original=True),
        ]
    )
    assert only(run_line_checks([line("The Student Council is here.", "O grêmio chegou.")], env), "glossary")
    assert not only(run_line_checks([line("The Student Council is here.", "O Conselho Estudantil chegou.")], env), "glossary")
    assert not only(run_line_checks([line("Hoshinoumi Academy", "Academia Hoshinoumi")], env), "glossary")


def test_foreign_markers() -> None:
    env = CheckEnv()
    assert only(run_line_checks([line("I'm on the bus.", "Estou no autocarro.")], env), "foreign_markers")
    assert only(run_line_checks([line("I'm eating.", "Estou a comer.")], env), "foreign_markers")
    assert only(run_line_checks([line("But why?", "¿Pero por qué?")], env), "foreign_markers")
    assert not only(run_line_checks([line("I'm eating.", "Estou comendo.")], env), "foreign_markers")


def test_measure_counts_visible_chars() -> None:
    m = measure("{\\i1}Olá⟦1⟧ mundo\\N  tudo bem? ", 1000)
    assert m.lines == 2
    assert m.max_cpl == len("Olá mundo")
    assert m.cps == pytest.approx(len("Olá mundo") + len("tudo bem?"))


def test_reading_speed_cps_limit_exact() -> None:
    env = CheckEnv()
    ok = run_line_checks([line("x", "a" * 17, dur=1000)], env)  # 17,0 CPS passa
    assert not [f for f in only(ok, "reading_speed") if f.message.startswith("CPS")]
    bad = run_line_checks([line("x", "a" * 171, dur=10_000)], env)  # 17,1 CPS falha
    cps = [f for f in only(bad, "reading_speed") if f.message.startswith("CPS")]
    assert cps and cps[0].severity == "error" and cps[0].value == pytest.approx(17.1)


def test_reading_speed_cpl_and_lines() -> None:
    env = CheckEnv()
    ok = only(run_line_checks([line("x", "a" * 42, dur=10_000)], env), "reading_speed")
    assert not ok
    cpl = only(run_line_checks([line("x", "a" * 43, dur=10_000)], env), "reading_speed")
    assert [f.message.split()[0] for f in cpl] == ["CPL"]
    three = only(run_line_checks([line("x", "a\\Nb\\Nc", dur=10_000)], env), "reading_speed")
    assert [f.message.split()[0] for f in three] == ["linhas:"]


def test_reading_speed_zero_duration_skips_cps() -> None:
    found = only(run_line_checks([line("x", "a" * 30, dur=0)], CheckEnv()), "reading_speed")
    assert found == []
    assert measure("abc", 0).cps is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_checks_context.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.memory.matching'`.

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/memory/matching.py` (lógica movida de `stages/translate_dialogue.py`):

```python
"""Casamento de termos/nomes da memória da série com um texto (palavra inteira, sem diferenciar caixa)."""

import re
from collections.abc import Iterable

from translaterany.memory.models import CharacterEntry, GlossaryEntry


def matches_term(term: str, text: str) -> bool:
    if not term:
        return False
    prefix = r"\b" if re.match(r"^\w", term) else ""
    suffix = r"\b" if re.search(r"\w$", term) else ""
    return bool(re.search(rf"{prefix}{re.escape(term)}{suffix}", text, re.IGNORECASE))


def select_for_text(
    glossary: Iterable[GlossaryEntry], characters: Iterable[CharacterEntry], text: str
) -> tuple[list[GlossaryEntry], list[CharacterEntry]]:
    """Entradas do glossário e personagens mencionados no texto (filtro por episódio)."""
    terms = [e for e in glossary if any(matches_term(t, text) for t in (e.term, *e.aliases))]
    chars = [c for c in characters if any(matches_term(n, text) for n in (c.name, *c.aliases))]
    return terms, chars
```

Em `stages/translate_dialogue.py`: apague a função `_matches_term` (linhas 32-38) e acrescente aos imports `from translaterany.memory.matching import matches_term as _matches_term, select_for_text`. Troque o laço de filtragem (linhas ~187-198) por:

```python
                full_text = "\n".join(u.text for u in dialogue_units)
                matched_glossary, matched_characters = select_for_text(glossary.values(), all_characters, full_text)
                used_terms_dict = {entry.term: entry.content_hash() for entry in matched_glossary}
```

(Mantém `_matches_term` importado com o nome antigo para qualquer uso restante no arquivo; se nenhum restar, remova o alias.)

Acrescente em `checks/lexicon.py`:

```python
PT_PT_WORDS = re.compile(
    r"\b(?:autocarro|comboio|telemóvel|equipa|facto|ecrã|rapariga|casa de banho|pequeno-almoço)\b", re.IGNORECASE
)
PT_PT_PROGRESSIVE = re.compile(r"\b(?:estou|estás|está|estamos|estão|estava|estavam) a \w+(?:ar|er|ir)\b", re.IGNORECASE)
SPANISH = re.compile(r"[¿¡ñÑ]|\b(?:pero|muy|también|usted|gracias|hola)\b", re.IGNORECASE)
```

`src/translaterany/checks/rules_context.py`:

```python
"""Checagens que dependem da memória da série ou dos limites de leitura."""

from dataclasses import dataclass

from translaterany.checks import lexicon
from translaterany.checks.models import CheckEnv, Finding, LineInput
from translaterany.checks.registry import line_check
from translaterany.checks.text import plain, visible_lines
from translaterany.memory.matching import matches_term


@dataclass(frozen=True)
class ReadingMeasure:
    cps: float | None  # None quando a duração é <= 0
    max_cpl: int
    lines: int


def measure(text: str, duration_ms: int) -> ReadingMeasure:
    lines = [part for part in visible_lines(text) if part]
    chars = sum(len(part) for part in lines)
    cps = chars * 1000 / duration_ms if duration_ms > 0 else None
    return ReadingMeasure(cps=cps, max_cpl=max((len(p) for p in lines), default=0), lines=len(lines))


@line_check("names", {"dialogue"})
def names(line: LineInput, env: CheckEnv) -> list[Finding]:
    src, tgt = plain(line.source), plain(line.target)
    findings: list[Finding] = []
    for group in env.names:
        forms = [n for n in group if len(n) >= 2]
        if any(matches_term(n, src) for n in forms) and not any(matches_term(n, tgt) for n in forms):
            findings.append(
                Finding(check="names", unit_id=line.id, severity="warn", message=f"nome '{forms[0]}' ausente na tradução")
            )
    return findings


@line_check("glossary", {"dialogue", "sign"})
def glossary(line: LineInput, env: CheckEnv) -> list[Finding]:
    src, tgt = plain(line.source), plain(line.target)
    findings: list[Finding] = []
    for entry in env.glossary:
        if not any(matches_term(t, src) for t in (entry.term, *entry.aliases)):
            continue
        expected = entry.term if entry.keep_original else entry.translation
        if expected and not matches_term(expected, tgt):
            findings.append(
                Finding(
                    check="glossary",
                    unit_id=line.id,
                    severity="warn",
                    message=f"termo '{entry.term}' deveria aparecer como '{expected}'",
                )
            )
    return findings


@line_check("foreign_markers", {"dialogue", "sign"})
def foreign_markers(line: LineInput, env: CheckEnv) -> list[Finding]:
    tgt = plain(line.target)
    findings: list[Finding] = []
    for pattern, label in (
        (lexicon.PT_PT_WORDS, "português europeu"),
        (lexicon.PT_PT_PROGRESSIVE, "português europeu"),
        (lexicon.SPANISH, "espanhol"),
    ):
        match = pattern.search(tgt)
        if match:
            findings.append(
                Finding(
                    check="foreign_markers",
                    unit_id=line.id,
                    severity="warn",
                    message=f"marcador de {label}: '{match.group(0)}'",
                )
            )
    return findings


@line_check("reading_speed", {"dialogue"})
def reading_speed(line: LineInput, env: CheckEnv) -> list[Finding]:
    m = measure(line.target, line.duration_ms)
    lim = env.limits
    findings: list[Finding] = []
    if m.cps is not None and m.cps > lim.max_cps:
        findings.append(
            Finding(
                check="reading_speed",
                unit_id=line.id,
                severity="error",
                message=f"CPS {m.cps:.1f} acima de {lim.max_cps:g}",
                value=round(m.cps, 2),
            )
        )
    if m.max_cpl > lim.max_cpl:
        findings.append(
            Finding(
                check="reading_speed",
                unit_id=line.id,
                severity="error",
                message=f"CPL {m.max_cpl} acima de {lim.max_cpl}",
                value=float(m.max_cpl),
            )
        )
    if m.lines > lim.max_lines:
        findings.append(
            Finding(
                check="reading_speed",
                unit_id=line.id,
                severity="error",
                message=f"linhas: {m.lines} (máximo {lim.max_lines})",
                value=float(m.lines),
            )
        )
    return findings
```

Em `checks/__init__.py`, troque o import das regras por `from translaterany.checks import rules_basic, rules_context  # noqa: F401 — registra as checagens`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_checks_context.py tests/test_checks_basic.py tests/test_translate_with_glossary.py tests/test_translate_dialogue_contextual.py tests/test_stages_translate_dialogue.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/checks src/translaterany/memory/matching.py src/translaterany/stages/translate_dialogue.py tests/test_checks_context.py
git add src/translaterany/checks src/translaterany/memory/matching.py src/translaterany/stages/translate_dialogue.py tests/test_checks_context.py
git commit -m "feat(checks): adiciona checagens de nomes, glossário, idioma e velocidade de leitura"
```

---

### Task 4: Fontes — extração de anexos e `font_glyphs`

**Files:**
- Modify: `pyproject.toml` (via `uv add fonttools`), `src/translaterany/media/mkv.py`
- Create: `src/translaterany/checks/fonts.py`
- Test: `tests/test_font_glyphs.py`

**Interfaces:**
- Consumes: `Finding` (Tarefa 2); `Attachment`, `MkvInfo`, `_run`, `MediaError` (`media/mkv.py`); `split_lines` (`subtitles/ass.py`); `EventInfo` (`subtitles/normalize.py`).
- Produces:
  - `font_attachments(info: MkvInfo) -> list[Attachment]`
  - `extract_attachments(path: Path, attachments: Sequence[Attachment], dest_dir: Path) -> list[Path]`
  - `style_fonts(ass_data: bytes) -> dict[str, str]` (estilo → família, sem `@`)
  - `event_fonts(event: EventInfo, styles: Mapping[str, str]) -> set[str]` (família do estilo + `\fn` do prefixo/marcadores, em minúsculas e sem `@`)
  - `load_font_faces(paths: Iterable[Path]) -> tuple[dict[str, frozenset[int]], list[Finding]]` (família em minúsculas → codepoints)
  - `check_font_glyphs(chars_by_font: Mapping[str, set[str]], faces: Mapping[str, frozenset[int]]) -> list[Finding]`

- [ ] **Step 1: Add dependency**

Run: `uv add fonttools`
Expected: `pyproject.toml` ganha `fonttools>=…` e `uv.lock` é atualizado.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_font_glyphs.py
"""Checagem de glifos das fontes anexadas (M5). Fontes geradas no teste; nenhum binário no repositório."""

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

from translaterany.checks.fonts import check_font_glyphs, event_fonts, load_font_faces, style_fonts
from translaterany.media.mkv import Attachment, MkvInfo, font_attachments
from translaterany.subtitles.normalize import EventInfo


def make_font(path: Path, family: str, chars: str) -> Path:
    names = [".notdef"] + [f"uni{ord(c):04X}" for c in chars]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(c): f"uni{ord(c):04X}" for c in chars})
    glyphs = {}
    for name in names:
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0))
        pen.lineTo((0, 500))
        pen.lineTo((500, 0))
        pen.closePath()
        glyphs[name] = pen.glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (500, 0) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2()
    fb.setupPost()
    fb.save(str(path))
    return path


ASS = (
    "[Script Info]\nScriptType: v4.00+\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize\n"
    "Style: Default,Open Sans,48\nStyle: Vert,@Gothic,40\n\n[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
).encode()


def event(style: str, prefix: str = "", markers: list[str] | None = None) -> EventInfo:
    return EventInfo(
        index=0, line_no=0, kind="dialogue", style=style, start_ms=0, end_ms=1000, layer=0, name="",
        prefix=prefix, text="x", markers=markers or [], suffix="", drawing=False, unit="u1",
    )  # fmt: skip


def test_style_fonts_strip_vertical_prefix() -> None:
    assert style_fonts(ASS) == {"Default": "Open Sans", "Vert": "Gothic"}


def test_event_fonts_include_inline_fn() -> None:
    styles = style_fonts(ASS)
    assert event_fonts(event("Default"), styles) == {"open sans"}
    assert event_fonts(event("Default", prefix="{\\fnComic Neue\\b1}"), styles) == {"open sans", "comic neue"}
    assert event_fonts(event("Nope", markers=["{\\fn@Arial}"]), styles) == {"arial"}


def test_glyph_present_missing_and_not_attached(tmp_path: Path) -> None:
    font = make_font(tmp_path / "a.ttf", "Open Sans", "abcãç ")
    faces, problems = load_font_faces([font])
    assert problems == []
    assert "open sans" in faces
    found = check_font_glyphs({"open sans": set("abc"), "missing font": set("a")}, faces)
    assert [(f.severity, f.check) for f in found] == [("info", "font_glyphs")]  # só a não anexada
    found = check_font_glyphs({"open sans": set("abcé")}, faces)
    assert found[0].severity == "warn" and "é" in found[0].message


def test_unreadable_font_is_info(tmp_path: Path) -> None:
    bad = tmp_path / "bad.ttf"
    bad.write_bytes(b"\x00\x01\x00\x00fake-font")
    faces, problems = load_font_faces([bad])
    assert faces == {}
    assert problems[0].severity == "info" and "bad.ttf" in problems[0].message


def test_font_attachments_by_mime_or_extension() -> None:
    info = MkvInfo(
        tracks=(),
        attachments=(
            Attachment(1, "a.ttf", "application/x-truetype-font"),
            Attachment(2, "b.OTF", "application/octet-stream"),
            Attachment(3, "cover.jpg", "image/jpeg"),
            Attachment(4, "c", "font/ttf"),
        ),
        duration_ns=None,
    )
    assert [a.id for a in font_attachments(info)] == [1, 2, 4]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_font_glyphs.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.checks.fonts'`.

- [ ] **Step 4: Write minimal implementation**

Acrescente em `src/translaterany/media/mkv.py` (depois de `extract_track`):

```python
_FONT_MIMES = frozenset(
    {"application/x-truetype-font", "application/vnd.ms-opentype", "application/font-sfnt", "application/x-font-ttf"}
)
_FONT_EXTS = (".ttf", ".otf", ".ttc")


def font_attachments(info: MkvInfo) -> list[Attachment]:
    return [
        a
        for a in info.attachments
        if a.content_type.startswith("font/") or a.content_type in _FONT_MIMES or a.file_name.lower().endswith(_FONT_EXTS)
    ]


def extract_attachments(path: Path, attachments: Sequence[Attachment], dest_dir: Path) -> list[Path]:
    """Extrai anexos para dest_dir como '<id>-<nome>'. Devolve os arquivos que de fato existem."""
    if not attachments:
        return []
    dest_dir.mkdir(parents=True, exist_ok=True)
    targets = {a.id: dest_dir / f"{a.id}-{Path(a.file_name).name or 'font'}" for a in attachments}
    result = _run(["mkvextract", str(path), "attachments", *(f"{i}:{p}" for i, p in targets.items())], check=False)
    if result.returncode > 1:
        raise MediaError(f"falha ao extrair anexos de {path.name}: {_first_line(result)}")
    return [p for p in targets.values() if p.exists()]
```

(acrescente `from collections.abc import Sequence` aos imports.)

`src/translaterany/checks/fonts.py`:

```python
"""Fontes do .ass: família por estilo, trocas \\fn e glifos disponíveis (fontTools). Só avisa, nunca bloqueia."""

import re
from collections.abc import Iterable, Mapping
from pathlib import Path

from fontTools.ttLib import TTCollection, TTFont

from translaterany.checks.models import Finding
from translaterany.subtitles.ass import split_lines
from translaterany.subtitles.normalize import EventInfo

_FN = re.compile(r"\\fn([^\\}]+)")
_NAME_IDS = (1, 4, 16)  # família, nome completo, família tipográfica


def _norm(name: str) -> str:
    return name.strip().lstrip("@").strip().lower()


def style_fonts(ass_data: bytes) -> dict[str, str]:
    """Estilo -> família da fonte, lidos da seção [V4+ Styles]/[V4 Styles]."""
    text = ass_data.decode("utf-8-sig", errors="replace")
    fonts: dict[str, str] = {}
    in_styles = False
    fmt: list[str] = []
    for raw in split_lines(text):
        line = raw.strip()
        if line.startswith("["):
            in_styles = line.lower() in ("[v4+ styles]", "[v4 styles]")
            continue
        if not in_styles or ":" not in line:
            continue
        key, _, value = line.partition(":")
        parts = [p.strip() for p in value.split(",")]
        if key.strip().lower() == "format":
            fmt = [p.lower() for p in parts]
        elif key.strip().lower() == "style" and "name" in fmt and "fontname" in fmt:
            fonts[parts[fmt.index("name")]] = parts[fmt.index("fontname")].lstrip("@")
    return fonts


def event_fonts(event: EventInfo, styles: Mapping[str, str]) -> set[str]:
    names = {_norm(styles[event.style])} if event.style in styles else set()
    for block in (event.prefix, *event.markers):
        names.update(_norm(m) for m in _FN.findall(block))
    return {n for n in names if n}


def load_font_faces(paths: Iterable[Path]) -> tuple[dict[str, frozenset[int]], list[Finding]]:
    faces: dict[str, frozenset[int]] = {}
    problems: list[Finding] = []
    for path in paths:
        try:
            fonts = TTCollection(str(path)).fonts if path.suffix.lower() == ".ttc" else [TTFont(str(path), lazy=True)]
            for font in fonts:
                cmap = frozenset((font.getBestCmap() or {}).keys())
                for record in font["name"].names:
                    if record.nameID in _NAME_IDS:
                        faces[_norm(record.toUnicode())] = cmap
        except Exception as exc:  # fonte corrompida/estranha: só informa
            problems.append(
                Finding(check="font_glyphs", severity="info", message=f"fonte ilegível '{path.name}': {type(exc).__name__}")
            )
    return faces, problems


def check_font_glyphs(chars_by_font: Mapping[str, set[str]], faces: Mapping[str, frozenset[int]]) -> list[Finding]:
    findings: list[Finding] = []
    for name in sorted(chars_by_font):
        chars = {c for c in chars_by_font[name] if not c.isspace()}
        cmap = faces.get(name)
        if cmap is None:
            findings.append(
                Finding(check="font_glyphs", severity="info", message=f"fonte '{name}' não está anexada ao MKV")
            )
            continue
        missing = sorted(c for c in chars if ord(c) not in cmap)
        if missing:
            findings.append(
                Finding(
                    check="font_glyphs",
                    severity="warn",
                    message=f"fonte '{name}' sem glifos: {', '.join(missing[:10])}",
                    value=float(len(missing)),
                )
            )
    return findings
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_font_glyphs.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/translaterany/checks/fonts.py src/translaterany/media/mkv.py tests/test_font_glyphs.py
git add pyproject.toml uv.lock src/translaterany/checks/fonts.py src/translaterany/media/mkv.py tests/test_font_glyphs.py
git commit -m "feat(checks): adiciona verificação de glifos das fontes anexadas"
```

---

### Task 5: `MeteredLLM` e `StageMetrics`

**Files:**
- Create: `src/translaterany/llm/metered.py`, `src/translaterany/pipeline/stage_metrics.py`
- Test: `tests/test_metered_llm.py`

**Interfaces:**
- Consumes: `PriceFn` (Tarefa 1); `LLMClient`, `LLMRequest`, `LLMResponse`, erros de `llm/client.py`; `FakeLLM`.
- Produces:
  - `ModelStats(calls, input_tokens, output_tokens, cached_input_tokens: int = 0, cost_usd: float = 0.0)` com `add(other: ModelStats) -> None`
  - `LLMStats(calls: int = 0, errors: dict[str, int] = {}, by_model: dict[str, ModelStats] = {})` com propriedades `input_tokens`, `output_tokens`, `cost_usd` e método `add(other: LLMStats) -> None`
  - `MeteredLLM(inner: LLMClient, prices: PriceFn | None = None)` com atributo `stats: LLMStats` e `generate(request)`
  - `StageMetrics` com `counters: dict[str, int]` e `count(name: str, n: int = 1) -> None`
  - `count(ctx: object, name: str, n: int = 1) -> None` — tolerante a `ctx` sem `metrics` (testes com contexto falso)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_metered_llm.py
"""MeteredLLM e StageMetrics (M5)."""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from translaterany.llm.client import LLMOutputError, LLMRefusalError, LLMRequest, LLMTransientError
from translaterany.llm.fake import FakeLLM
from translaterany.llm.metered import LLMStats, MeteredLLM, ModelStats
from translaterany.pipeline.stage_metrics import StageMetrics, count


class Out(BaseModel):
    text: str = "ok"


def req(model: str = "translate") -> LLMRequest[Out]:
    return LLMRequest(model=model, instructions="x" * 400, prompt="y" * 400, output_type=Out)


def test_counts_tokens_and_cost_by_model() -> None:
    metered = MeteredLLM(FakeLLM([Out(), Out()]), prices=lambda alias: (2.0, 8.0))
    metered.generate(req())
    metered.generate(req())
    stats = metered.stats
    assert stats.calls == 2
    model = stats.by_model["fake:translate"]
    assert model.calls == 2
    assert model.input_tokens == 400  # FakeLLM: (400 + 400) // 4 por chamada
    assert stats.input_tokens == 400
    expected = (model.input_tokens * 2.0 + model.output_tokens * 8.0) / 1_000_000
    assert stats.cost_usd == pytest.approx(expected)


@pytest.mark.parametrize(
    ("error", "kind"),
    [(LLMTransientError("t"), "transient"), (LLMOutputError("o"), "output"), (LLMRefusalError("r"), "refusal"),
     (RuntimeError("x"), "other")],
)  # fmt: skip
def test_errors_are_counted_and_reraised(error: Exception, kind: str) -> None:
    metered = MeteredLLM(FakeLLM([error]))
    with pytest.raises(type(error)):
        metered.generate(req())
    assert metered.stats.calls == 1
    assert metered.stats.errors == {kind: 1}
    assert metered.stats.by_model == {}


def test_config_error_and_no_prices() -> None:
    metered = MeteredLLM(FakeLLM())  # sem provedor: LLMConfigError
    with pytest.raises(Exception):
        metered.generate(req())
    assert metered.stats.errors == {"config": 1}
    ok = MeteredLLM(FakeLLM([Out()]))
    ok.generate(req("desconhecido"))
    assert ok.stats.cost_usd == 0.0


def test_stats_add_merges() -> None:
    a = LLMStats(calls=1, errors={"output": 1}, by_model={"m": ModelStats(calls=1, input_tokens=10, cost_usd=0.5)})
    b = LLMStats(calls=2, errors={"output": 2}, by_model={"m": ModelStats(calls=2, input_tokens=5, cost_usd=0.25)})
    a.add(b)
    assert a.calls == 3 and a.errors == {"output": 3}
    assert a.by_model["m"].input_tokens == 15 and a.cost_usd == pytest.approx(0.75)


def test_stage_metrics_count_and_helper() -> None:
    m = StageMetrics()
    m.count("lines", 3)
    m.count("lines")
    assert m.counters == {"lines": 4}
    ctx = SimpleNamespace(metrics=m)
    count(ctx, "fallback_original")
    assert m.counters["fallback_original"] == 1
    count(SimpleNamespace(), "ignored")  # contexto falso sem metrics: não quebra
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_metered_llm.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.llm.metered'`.

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/llm/metered.py`:

```python
"""Medidor de uso da IA: envolve um LLMClient e conta chamadas, tokens, custo e erros."""

from pydantic import BaseModel, Field

from translaterany.llm.client import (
    LLMClient,
    LLMConfigError,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMResponse,
    LLMTransientError,
)
from translaterany.llm.pricing import PriceFn

_ERROR_KINDS: tuple[tuple[type[Exception], str], ...] = (
    (LLMTransientError, "transient"),
    (LLMOutputError, "output"),
    (LLMRefusalError, "refusal"),
    (LLMConfigError, "config"),
)


class ModelStats(BaseModel):
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, other: "ModelStats") -> None:
        self.calls += other.calls
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cached_input_tokens += other.cached_input_tokens
        self.cost_usd += other.cost_usd


class LLMStats(BaseModel):
    calls: int = 0
    errors: dict[str, int] = Field(default_factory=dict)
    by_model: dict[str, ModelStats] = Field(default_factory=dict)

    @property
    def input_tokens(self) -> int:
        return sum(m.input_tokens for m in self.by_model.values())

    @property
    def output_tokens(self) -> int:
        return sum(m.output_tokens for m in self.by_model.values())

    @property
    def cost_usd(self) -> float:
        return sum(m.cost_usd for m in self.by_model.values())

    def add(self, other: "LLMStats") -> None:
        self.calls += other.calls
        for kind, n in other.errors.items():
            self.errors[kind] = self.errors.get(kind, 0) + n
        for model_id, stats in other.by_model.items():
            self.by_model.setdefault(model_id, ModelStats()).add(stats)


def _error_kind(exc: Exception) -> str:
    return next((kind for cls, kind in _ERROR_KINDS if isinstance(exc, cls)), "other")


class MeteredLLM:
    """Um por (etapa, unidade). Relança os erros: o comportamento das etapas não muda."""

    def __init__(self, inner: LLMClient, prices: PriceFn | None = None) -> None:
        self.inner = inner
        self.prices = prices
        self.stats = LLMStats()

    def generate[T: BaseModel](self, request: LLMRequest[T]) -> LLMResponse[T]:
        self.stats.calls += 1
        try:
            response = self.inner.generate(request)
        except Exception as exc:
            kind = _error_kind(exc)
            self.stats.errors[kind] = self.stats.errors.get(kind, 0) + 1
            raise
        in_price, out_price = self.prices(request.model) if self.prices else (0.0, 0.0)
        usage = response.usage
        model = self.stats.by_model.setdefault(response.model_id, ModelStats())
        model.add(
            ModelStats(
                calls=1,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cost_usd=(usage.input_tokens * in_price + usage.output_tokens * out_price) / 1_000_000,
            )
        )
        return response
```

`src/translaterany/pipeline/stage_metrics.py`:

```python
"""Contadores específicos de uma etapa (fallbacks, acertos na TM...), gravados no manifest."""

from dataclasses import dataclass, field


@dataclass
class StageMetrics:
    counters: dict[str, int] = field(default_factory=dict)

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + n


def count(ctx: object, name: str, n: int = 1) -> None:
    """Conta em ctx.metrics, se existir (etapas também rodam com contextos falsos nos testes)."""
    metrics = getattr(ctx, "metrics", None)
    if isinstance(metrics, StageMetrics):
        metrics.count(name, n)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_metered_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/llm/metered.py src/translaterany/pipeline/stage_metrics.py tests/test_metered_llm.py
git add src/translaterany/llm/metered.py src/translaterany/pipeline/stage_metrics.py tests/test_metered_llm.py
git commit -m "feat(llm): adiciona medidor de uso da IA e contadores por etapa"
```

---

### Task 6: Manifest schema 2 e integração no runner

**Files:**
- Modify: `src/translaterany/pipeline/manifest.py`, `src/translaterany/pipeline/stage.py`, `src/translaterany/pipeline/runner.py`, `src/translaterany/cli/run.py:86`
- Modify: `tests/test_manifest.py:34` (`'"schema": 1'` → `'"schema": 2'`)
- Test: `tests/test_runner_metrics.py`

**Interfaces:**
- Consumes: `LLMStats`, `MeteredLLM`, `StageMetrics` (Tarefa 5); `PriceFn`, `price_lookup` (Tarefa 1).
- Produces:
  - `MANIFEST_SCHEMA = 2`; `StageRecord.llm: LLMStats | None = None`; `StageRecord.counters: dict[str, int] = {}`
  - `StageContext.metrics: StageMetrics` (padrão vazio)
  - `Runner(stages, store, llm, log=None, on_progress=None, prices: PriceFn | None = None)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_runner_metrics.py
"""Runner grava uso da IA e contadores no StageRecord (M5)."""

import json
from pathlib import Path

from fake_stages import SourceStage, Text
from pydantic import BaseModel

from translaterany.library import discover
from translaterany.llm.client import LLMRequest
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import MANIFEST_SCHEMA, UnitInfo, load_manifest
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class Out(BaseModel):
    text: str = "ok"


class AskStage(Stage):
    """Chama a IA uma vez, conta uma linha; falha se o texto da origem pedir."""

    name = "t_ask"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_source",)

    def run(self, ctx: StageContext) -> None:
        text = ctx.inputs.json("t_source", Text).text
        ctx.llm.generate(LLMRequest(model="translate", instructions="i" * 40, prompt="p" * 40, output_type=Out))
        ctx.metrics.count("lines", 2)
        if "BOOM" in text:
            raise RuntimeError("falhou depois de chamar a IA")
        ctx.output.json(Text(text=text))


def _run(data_dir: Path, root: Path, llm: FakeLLM):
    store = ArtifactStore(data_dir)
    series, episodes = discover(root)
    runner = Runner([SourceStage(), AskStage()], store, llm, prices=lambda alias: (1.0, 1.0))
    return runner.run(series, episodes), store, series, episodes


def test_record_has_llm_and_counters(data_dir: Path, series_dir: Path) -> None:
    _, store, series, episodes = _run(data_dir, series_dir, FakeLLM(lambda r: Out()))
    record = store.load_manifest(series, episodes[0]).stages["t_ask"]
    assert record.llm is not None and record.llm.calls == 1
    assert record.llm.by_model["fake:translate"].cost_usd > 0
    assert record.counters == {"lines": 2}
    assert store.load_manifest(series, episodes[0]).stages["t_source"].llm is None  # não chamou IA


def test_cache_hit_keeps_original_numbers(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, FakeLLM(lambda r: Out()))
    summary, store, series, episodes = _run(data_dir, series_dir, FakeLLM())  # sem provedor: não pode ser chamado
    assert summary.stages["t_ask"].cached == 3
    assert store.load_manifest(series, episodes[0]).stages["t_ask"].llm.calls == 1


def test_failed_record_keeps_partial_stats(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("BOOM", encoding="utf-8")
    _, store, series, episodes = _run(data_dir, series_dir, FakeLLM(lambda r: Out()))
    record = store.load_manifest(series, episodes[0]).stages["t_ask"]
    assert record.status == "failed"
    assert record.llm.calls == 1 and record.counters == {"lines": 2}


def test_schema_1_manifest_is_read_and_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"schema": 1, "unit": {"series": "s"}, "stages": {"a": {"status": "done", "key": "k"}}}),
        encoding="utf-8",
    )
    manifest = load_manifest(path, UnitInfo(series="s"))
    assert manifest.stages["a"].llm is None and manifest.stages["a"].counters == {}
    from translaterany.pipeline.manifest import save_manifest

    save_manifest(path, manifest)
    assert json.loads(path.read_text())["schema"] == MANIFEST_SCHEMA == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_runner_metrics.py -v`
Expected: FAIL com `TypeError: Runner.__init__() got an unexpected keyword argument 'prices'`.

- [ ] **Step 3: Write minimal implementation**

`pipeline/manifest.py`:

```python
from translaterany.llm.metered import LLMStats

MANIFEST_SCHEMA = 2
_READABLE_SCHEMAS = frozenset({1, 2})  # schema 1 (até o M4) só não tem llm/counters
```

em `StageRecord`, depois de `error`:

```python
    llm: LLMStats | None = None
    counters: dict[str, int] = Field(default_factory=dict)
```

em `load_manifest`, troque a checagem de versão e normalize para a versão atual:

```python
    if manifest.schema_version not in _READABLE_SCHEMAS:
        raise ManifestError(
            f"manifest em {path} tem schema {manifest.schema_version}; "
            f"esta versão entende os schemas {', '.join(map(str, sorted(_READABLE_SCHEMAS)))}"
        )
    manifest.schema_version = MANIFEST_SCHEMA  # o próximo save grava no formato atual
    return manifest
```

Confira se `tests/test_manifest.py::test_unknown_schema_version` ainda casa `match="schema 99"` (casa: a mensagem começa igual). Atualize a linha 34 para `'"schema": 2'`.

`pipeline/stage.py` — em `StageContext`, acrescente ao fim (com import `from dataclasses import dataclass, field` e `from translaterany.pipeline.stage_metrics import StageMetrics`):

```python
    metrics: StageMetrics = field(default_factory=StageMetrics)
```

`pipeline/runner.py`:
- imports: `from translaterany.llm.metered import MeteredLLM`, `from translaterany.llm.pricing import PriceFn`, `from translaterany.pipeline.stage_metrics import StageMetrics`.
- `__init__` ganha `prices: PriceFn | None = None` (último parâmetro) e `self.prices = prices`.
- Em `_run_unit`, logo antes de `writer = OutputWriter(...)`:

```python
            metered = MeteredLLM(self.llm, self.prices)
            metrics = StageMetrics()
```

  e a chamada vira `ctx = self._context(stage, series, episode, episodes, manifests, writer, previous, force, metered, metrics)`.
- No `except` que segue `stage.run(ctx)` nada muda; a chamada final vira
  `return self._finish(stage, manifests, episode, unit_name, error, digest, key, writer, started, t0, metered, metrics)`.
- `_context` recebe `llm: MeteredLLM, metrics: StageMetrics` e usa `llm=llm, metrics=metrics` no `StageContext`.
- `_finish(..., metered: MeteredLLM | None = None, metrics: StageMetrics | None = None)`: repassa ambos a `_fail` no caminho de erro; no sucesso o `StageRecord` ganha

```python
            llm=_llm_stats(metered),
            counters=dict(metrics.counters) if metrics else {},
```

- `_fail(..., metered: MeteredLLM | None = None, metrics: StageMetrics | None = None)`: idem no `StageRecord` de falha.
- função de módulo:

```python
def _llm_stats(metered: MeteredLLM | None) -> LLMStats | None:
    return metered.stats if metered is not None and metered.stats.calls else None
```

  (importe `LLMStats` de `translaterany.llm.metered`.)
- `PipelineRunner.run_series`: `Runner(self.stages, store, self.client, prices=self.prices)`, com `self.prices = price_lookup(cfg.llm)` quando houver config (`ResolvedConfig.llm` ou `AppConfig.llm`), senão `None`.

`cli/run.py:86`:

```python
        runner = Runner(
            cfg.stages, ArtifactStore(cfg.data_dir), PydanticAIClient(cfg.llm), log, on_progress,
            prices=price_lookup(cfg.llm),
        )  # fmt: skip
```

(com `from translaterany.llm.pricing import price_lookup`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_runner_metrics.py tests/test_manifest.py tests/test_runner.py tests/test_core_m1.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: todos passam (396 + novos).

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/translaterany/pipeline/manifest.py src/translaterany/pipeline/stage.py src/translaterany/pipeline/runner.py src/translaterany/cli/run.py tests/test_runner_metrics.py
git add src/translaterany/pipeline src/translaterany/cli/run.py tests/test_runner_metrics.py tests/test_manifest.py
git commit -m "feat(pipeline): grava uso da IA e contadores no manifest (schema 2)"
```

---

### Task 7: Contadores nas etapas e correção do episódio na TM

**Files:**
- Modify: `src/translaterany/subtitles/translator.py`, `subtitles/signs.py`, `subtitles/songs.py`
- Modify: `src/translaterany/stages/translate_dialogue.py`, `translate_signs.py`, `translate_songs.py`, `classify.py`, `translation_memory.py`, `merge_sentences.py`, `redistribute_sentences.py`
- Test: `tests/test_stage_counters.py`

**Interfaces:**
- Consumes: `StageMetrics`, `count` (Tarefa 5).
- Produces: `DialogueBatchTranslator(..., metrics: StageMetrics | None = None)`; `translate_signs(..., metrics: StageMetrics | None = None)`; `translate_songs(..., metrics: StageMetrics | None = None)`. Nomes de contadores exatamente como na tabela do spec §6.3.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_counters.py
"""Contadores das etapas (M5) e episódio correto na TM (correção do M4)."""

from pathlib import Path

from pydantic import BaseModel

from translaterany.llm.client import LLMOutputError
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.translator import DialogueBatchTranslator, TranslationBatch, TranslationItem


def test_translator_counts_fallback_split_and_reconcile() -> None:
    metrics = StageMetrics()
    lines = [DialogueLine(id="a", text="One"), DialogueLine(id="b", text="Two")]

    def script(req):
        if "[a]" in req.prompt and "[b]" in req.prompt:
            return TranslationBatch(items=[TranslationItem(id="a", text="Um")])  # b faltando
        raise LLMOutputError("sem saída")  # pedido só de b falha

    tr = DialogueBatchTranslator(FakeLLM(script), max_context_lines=0, metrics=metrics)
    result = tr.translate_lines(lines)
    assert result == {"a": "Um", "b": "Two"}
    assert metrics.counters["ids_reconciled"] == 1
    assert metrics.counters["fallback_original"] == 1


def test_translator_counts_batches_split() -> None:
    metrics = StageMetrics()
    lines = [DialogueLine(id="a", text="One"), DialogueLine(id="b", text="Two")]
    calls = {"n": 0}

    def script(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return TranslationBatch(items=[])  # tudo faltando: bisseção
        line_id = "a" if "[a]" in req.prompt else "b"
        return TranslationBatch(items=[TranslationItem(id=line_id, text=line_id.upper())])

    DialogueBatchTranslator(FakeLLM(script), max_context_lines=0, metrics=metrics).translate_lines(lines)
    assert metrics.counters["batches_split"] == 1
```

Acrescente ao mesmo arquivo um teste de etapa real sobre MKV sintético (usa o `synthetic_series` do `conftest.py` e o pipeline do M4 até `redistribute_sentences`), verificando os contadores gravados e o episódio na TM:

```python
import pytest
from mkvtools import needs_mkvtoolnix

from translaterany.library import discover
from translaterany.memory.tm import TranslationMemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.stages.metadata import MetadataStage

from translaterany.stages import DEFAULT_PIPELINE

UP_TO_REDISTRIBUTE = DEFAULT_PIPELINE[: DEFAULT_PIPELINE.index("redistribute_sentences") + 1]


@needs_mkvtoolnix
def test_counters_recorded_and_tm_episode(tmp_path: Path, synthetic_series: Path) -> None:
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(synthetic_series)
    stages = [
        MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
        for n in UP_TO_REDISTRIBUTE
    ]
    llm = FakeLLM(responses={"Where are we going, friend?": "Aonde vamos, amigo?", "Estação Central": "Estação Central!"})
    summary = Runner(stages, store, llm).run(series, episodes)
    assert not summary.failed
    manifest = store.load_manifest(series, episodes[0])
    assert manifest.stages["translate_dialogue"].counters["lines"] >= 1
    assert "tm_candidates" in manifest.stages["translation_memory"].counters
    assert "merged_groups" in manifest.stages["merge_sentences"].counters
    assert manifest.stages["translate_dialogue"].llm is not None
    tm = TranslationMemoryStore(store.series_dir(series.key) / "memory" / "translation_memory.yaml")
    entries = tm.load().entries.values()
    assert any(episodes[0].key in e.episodes for e in entries)  # antes: episódio vazio (bug episode.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_counters.py -v`
Expected: FAIL com `TypeError: DialogueBatchTranslator.__init__() got an unexpected keyword argument 'metrics'`.

- [ ] **Step 3: Write minimal implementation**

`subtitles/translator.py`:
- import `from translaterany.pipeline.stage_metrics import StageMetrics`.
- `__init__` ganha `metrics: StageMetrics | None = None` (último parâmetro) e `self.metrics = metrics`.
- método:

```python
    def _count(self, name: str, n: int = 1) -> None:
        if self.metrics is not None:
            self.metrics.count(name, n)
```

- em `_process_batch`, no bloco "Nível 2" logo após `if missing_ids and len(missing_ids) < len(lines):` acrescente `self._count("ids_reconciled", len(missing_ids))`;
- no "Nível 3", dentro de `if len(lines) > 1:` acrescente `self._count("batches_split")`;
- no "Nível 4", ao lado de `self.fallback_count += 1`, acrescente `self._count("fallback_original")`.

`subtitles/signs.py` e `subtitles/songs.py`: acrescente `metrics: StageMetrics | None = None` ao fim da assinatura de `translate_signs`/`translate_songs`; passe `metrics=metrics` ao `DialogueBatchTranslator`; depois de montar `pending_units`, `if metrics: metrics.count("lines", len(pending_units))`; no ramo em que os marcadores se perdem (`tr = u.text`), `if metrics: metrics.count("markers_lost")`.

`stages/translate_signs.py` / `translate_songs.py`: passe `metrics=ctx.metrics if isinstance(getattr(ctx, "metrics", None), StageMetrics) else None` à função; acrescente `produces_texts: ClassVar[bool] = True` (usado na Tarefa 8 — já declare aqui).

`stages/translate_dialogue.py`:
- `produces_texts: ClassVar[bool] = True`;
- `from translaterany.pipeline.stage_metrics import StageMetrics, count`;
- no `DialogueBatchTranslator(...)` do `run`, `metrics=ctx.metrics if isinstance(getattr(ctx, "metrics", None), StageMetrics) else None`;
- antes de criar o tradutor: `count(ctx, "lines", len(lines))`;
- no ramo `tr = orig_text` por marcadores perdidos: `count(ctx, "markers_lost")`.

`stages/classify.py`: depois de `disambiguate_uncertain_units(...)`:

```python
            count(ctx, "ai_disambiguated", sum(1 for c in res.units.values() if c.rule == "ai_disambiguate"))
```

`stages/translation_memory.py`: no laço, após o filtro de categoria, `candidates += 1` (inicialize `candidates = 0`); ao final, antes de gravar: `count(ctx, "tm_candidates", candidates)` e `count(ctx, "tm_hits", len(matched_units))`.

`stages/merge_sentences.py`: antes de gravar:

```python
        groups = [c for c in merged_doc.units if len(c.unit_ids) > 1]
        count(ctx, "merged_groups", len(groups))
        count(ctx, "merged_units", sum(len(c.unit_ids) for c in groups))
```

`stages/redistribute_sentences.py`:
- `produces_texts: ClassVar[bool] = True`;
- no bloco 1, logo após `final_texts.update(split)`: `count(ctx, "redistributed")` somente quando `len(comp.unit_ids) > 1`;
- **correção:** `ep_id = episode.key if episode is not None else ""` (em vez de `getattr(episode, "id", "")`);
- após cada `tm_store.record_translation(...)`: `count(ctx, "tm_fed")`.

Em todos, `from translaterany.pipeline.stage_metrics import count`. Ainda não existe `Stage.produces_texts` na base — declará-lo nas subclasses agora é inofensivo; a Tarefa 8 o cria na base.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_counters.py tests/test_translator_resilience.py tests/test_translate_signs_songs.py tests/test_redistribute_sentences.py tests/test_translation_memory.py tests/test_merge_sentences.py tests/test_classify_ai.py tests/test_m4_e2e.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/subtitles/translator.py src/translaterany/subtitles/signs.py src/translaterany/subtitles/songs.py src/translaterany/stages tests/test_stage_counters.py
git add src/translaterany/subtitles src/translaterany/stages tests/test_stage_counters.py
git commit -m "feat(stages): registra contadores por etapa e corrige episódio na memória de tradução"
```

---

### Task 8: `produces_texts` e gancho `bind_pipeline` no loader

**Files:**
- Modify: `src/translaterany/pipeline/stage.py`, `src/translaterany/config/loader.py:152`
- Test: `tests/test_bind_pipeline.py`

**Interfaces:**
- Consumes: `AppConfig` (`config/model.py`).
- Produces: `Stage.produces_texts: ClassVar[bool] = False`; `Stage.bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None` (padrão: nada). O loader chama-o com as etapas **habilitadas** anteriores, **antes** de validar `stage.inputs`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_bind_pipeline.py
"""Gancho bind_pipeline e flag produces_texts (M5)."""

from collections.abc import Sequence
from pathlib import Path

from fake_stages import SourceStage, Text

from translaterany.config.loader import load_config
from translaterany.config.model import AppConfig
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class SeesPipeline(Stage):
    name = "t_sees"
    version = "1"
    scope = StageScope.EPISODE
    seen: list[str] = []
    max_cps: float = 0.0

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        type(self).seen = [s.name for s in previous]
        type(self).max_cps = app.checks.max_cps if app else 0.0
        self.inputs = tuple(s.name for s in previous if s.name == "t_source")

    def run(self, ctx: StageContext) -> None:
        ctx.output.json(Text(text=ctx.inputs.json("t_source", Text).text))


def test_produces_texts_flags() -> None:
    assert Stage.produces_texts is False
    for name in ("translate_dialogue", "translate_signs", "translate_songs", "redistribute_sentences"):
        assert REGISTRY.get(name).produces_texts is True
    assert REGISTRY.get("normalize").produces_texts is False


def test_loader_binds_with_enabled_previous_stages(tmp_path: Path) -> None:
    if "t_sees" not in REGISTRY:
        REGISTRY.register(SeesPipeline)
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[pipeline]\nstages = ["t_source", "t_upper", "t_sees"]\n[stages.t_upper]\nenabled = false\n'
        "[checks]\nmax_cps = 15\n",
        encoding="utf-8",
    )
    resolved = load_config(cfg, tmp_path / "data")
    assert [s.name for s in resolved.stages] == ["t_source", "t_sees"]
    assert SeesPipeline.seen == ["t_source"]  # t_upper desabilitada não aparece
    assert SeesPipeline.max_cps == 15.0
    assert resolved.stages[1].inputs == ("t_source",)  # entradas definidas pelo gancho foram validadas
    assert isinstance(resolved.stages[0], SourceStage)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_bind_pipeline.py -v`
Expected: FAIL com `AttributeError: type object 'Stage' has no attribute 'produces_texts'`.

- [ ] **Step 3: Write minimal implementation**

`pipeline/stage.py` — imports `from collections.abc import Sequence` (já existe) e `from translaterany.config.model import AppConfig`; na classe `Stage`, depois de `translates`:

```python
    produces_texts: ClassVar[bool] = False  # artefato é UnitTexts (instantâneo medido pela quality_checks)
```

e depois de `cache_payload`:

```python
    def bind_pipeline(self, previous: Sequence["Stage"], app: AppConfig | None) -> None:
        """Chamado pelo loader com as etapas habilitadas que vêm antes desta e o config.
        Etapas que dependem da composição do pipeline (ex.: quality_checks) ajustam `inputs` aqui."""
```

`config/loader.py`, em `_build_stages`, logo após `stage = cls(options)`:

```python
        stage.bind_pipeline(tuple(stages), config)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_bind_pipeline.py tests/test_config.py tests/test_core_m1.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/pipeline/stage.py src/translaterany/config/loader.py tests/test_bind_pipeline.py
git add src/translaterany/pipeline/stage.py src/translaterany/config/loader.py tests/test_bind_pipeline.py
git commit -m "feat(pipeline): adiciona produces_texts e gancho bind_pipeline"
```

---

### Task 9: Instantâneos — linhas, estado acumulado, delta e resumos (`checks/snapshots.py`, `checks/metrics.py`)

**Files:**
- Create: `src/translaterany/checks/snapshots.py`, `src/translaterany/checks/metrics.py`
- Test: `tests/test_snapshots.py`

**Interfaces:**
- Consumes: `LineInput`, `Finding`, `ChecksConfig` (Tarefas 1–2); `measure` (Tarefa 3); `NormalizedDoc`, `Classification`, `MergedUnitsDoc`.
- Produces (em `checks/metrics.py`):
  - `SeverityCounts(info: int = 0, warn: int = 0, error: int = 0)`
  - `SnapshotDelta(changed: int = 0, edit_ratio: float = 0.0, new: int = 0, resolved: int = 0)`
  - `SnapshotMetrics(stage: str, lines: int, checks: dict[str, SeverityCounts], delta: SnapshotDelta)`
  - `ReadingSpeedStats(cps_p50: float = 0, cps_p95: float = 0, cps_max: float = 0, over_limit: int = 0, cps_histogram: list[int] = [0]*41)`
  - `FinalMetrics(lines: int = 0, by_type: dict[str, int] = {}, checks: dict[str, SeverityCounts] = {}, flagged_lines: SeverityCounts, reading_speed: ReadingSpeedStats, findings: list[Finding] = [])`
  - `EpisodeMetrics(schema_version: int = 1 (alias "schema"), snapshots: list[SnapshotMetrics] = [], final: FinalMetrics, episode_checks: list[Finding] = [])`; constante `METRICS_SCHEMA = 1`; `HISTOGRAM_BINS = 41`
- Produces (em `checks/snapshots.py`):
  - `LineSource(source: str, line_type: str, style: str, duration_ms: int)` (dataclass)
  - `build_sources(doc: NormalizedDoc, classes: Classification, merged: MergedUnitsDoc | None) -> dict[str, LineSource]`
  - `composite_members(merged: MergedUnitsDoc | None) -> dict[str, list[str]]` (só grupos com > 1 unidade)
  - `lines_for(texts: Mapping[str, str], sources: Mapping[str, LineSource]) -> tuple[list[LineInput], list[str]]` (linhas, chaves desconhecidas)
  - `advance_state(state: Mapping[str, str], texts: Mapping[str, str], composites: Mapping[str, list[str]]) -> dict[str, str]`
  - `finding_keys(findings: Iterable[Finding]) -> set[tuple[str, str | None]]`
  - `compute_delta(prev: Mapping[str, str], new: Mapping[str, str], prev_keys: set, new_keys: set) -> SnapshotDelta`
  - `summarize(findings: Iterable[Finding]) -> dict[str, SeverityCounts]`
  - `flagged(findings: Iterable[Finding]) -> SeverityCounts` (unidades distintas por severidade)
  - `reading_speed_stats(lines: Iterable[LineInput], limits: ChecksConfig) -> ReadingSpeedStats`
  - `histogram_percentile(hist: Sequence[int], p: float) -> float`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_snapshots.py
"""Instantâneos de texto: linhas, estado acumulado, delta e resumos (M5)."""

import pytest

from translaterany.checks import Finding, LineInput
from translaterany.checks.metrics import HISTOGRAM_BINS, EpisodeMetrics, FinalMetrics
from translaterany.checks.snapshots import (
    advance_state,
    build_sources,
    composite_members,
    compute_delta,
    finding_keys,
    flagged,
    histogram_percentile,
    lines_for,
    reading_speed_stats,
    summarize,
)
from translaterany.config.model import ChecksConfig
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit


def ev(i: int, unit: str, start: int, end: int, style: str = "Default") -> EventInfo:
    return EventInfo(
        index=i, line_no=i, kind="dialogue", style=style, start_ms=start, end_ms=end, layer=0, name="",
        prefix="", text="t", markers=[], suffix="", drawing=False, unit=unit,
    )  # fmt: skip


DOC = NormalizedDoc(
    encoding=Encoding(bom=False, newline="\n"),
    format=[],
    events=[ev(0, "u1", 0, 2000), ev(1, "u2", 2100, 3000), ev(2, "u3", 5000, 6000, "Sign"), ev(3, "u3", 7000, 7500, "Sign")],
    units=[
        Unit(id="u1", style="Default", text="Wait for me...", markers=0, events=[0]),
        Unit(id="u2", style="Default", text="...I am coming!", markers=0, events=[1]),
        Unit(id="u3", style="Sign", text="Student Council", markers=0, events=[2, 3]),
    ],
)
CLASSES = Classification(
    main_style="Default",
    units={"u1": UnitClass(type="dialogue", uncertain=False, rule="r"), "u2": UnitClass(type="dialogue", uncertain=False, rule="r"),
           "u3": UnitClass(type="sign", uncertain=False, rule="r")},
    counts={}, scenes=[],
)  # fmt: skip
MERGED = MergedUnitsDoc(
    units=[
        CompositeUnit(composite_id="u1+u2", unit_ids=["u1", "u2"], durations_ms=[2000, 900],
                      clean_text="Wait for me... I am coming!", text_with_markers="Wait for me... I am coming!"),
    ],
    merged_count=1,
)  # fmt: skip


def test_build_sources_units_and_composites() -> None:
    sources = build_sources(DOC, CLASSES, MERGED)
    assert sources["u3"].duration_ms == 500  # menor duração entre os eventos
    assert sources["u3"].line_type == "sign"
    assert sources["u1+u2"].duration_ms == 2900
    assert sources["u1+u2"].source == "Wait for me... I am coming!"
    assert sources["u1+u2"].line_type == "dialogue"
    assert composite_members(MERGED) == {"u1+u2": ["u1", "u2"]}
    assert composite_members(None) == {}


def test_lines_for_skips_unknown_keys() -> None:
    lines, unknown = lines_for({"u3": "Conselho", "zz": "?"}, build_sources(DOC, CLASSES, None))
    assert [l.id for l in lines] == ["u3"] and unknown == ["zz"]


def test_advance_state_replaces_composite_with_units() -> None:
    comps = composite_members(MERGED)
    state = advance_state({}, {"u1+u2": "Espere... estou indo!"}, comps)
    assert state == {"u1+u2": "Espere... estou indo!"}
    state = advance_state(state, {"u3": "Conselho"}, comps)
    assert set(state) == {"u1+u2", "u3"}
    state = advance_state(state, {"u1": "Espere...", "u2": "...estou indo!", "u3": "Conselho"}, comps)
    assert set(state) == {"u1", "u2", "u3"}


def test_compute_delta() -> None:
    prev = {"a": "abc", "b": "same"}
    new = {"a": "abd", "b": "same", "c": "novo"}
    delta = compute_delta(prev, new, {("x", "a"), ("y", "b")}, {("x", "a"), ("z", "c")})
    assert delta.changed == 2  # a mudou, c entrou
    assert delta.edit_ratio == pytest.approx((1 - 2 / 3 + 0) / 2, abs=1e-4)  # a: ratio 2/3; b: 0 (arredondado)
    assert (delta.new, delta.resolved) == (1, 1)
    assert compute_delta({}, {"a": "x"}, set(), set()).edit_ratio == 0.0


def test_summaries() -> None:
    findings = [
        Finding(check="negation", unit_id="u1", severity="warn", message="m"),
        Finding(check="reading_speed", unit_id="u1", severity="error", message="CPS"),
        Finding(check="reading_speed", unit_id="u1", severity="error", message="CPL"),
        Finding(check="reading_speed", unit_id="u2", severity="error", message="CPS"),
    ]
    summary = summarize(findings)
    assert summary["reading_speed"].error == 3 and summary["negation"].warn == 1
    assert flagged(findings).error == 2 and flagged(findings).warn == 1
    assert finding_keys(findings) == {("negation", "u1"), ("reading_speed", "u1"), ("reading_speed", "u2")}


def test_reading_speed_stats_and_percentile() -> None:
    lines = [LineInput(id=f"u{i}", line_type="dialogue", source="x", target="a" * cps, duration_ms=1000) for i, cps in
             enumerate([5, 10, 15, 20, 45])] + [LineInput(id="z", line_type="dialogue", source="x", target="aaa", duration_ms=0),
             LineInput(id="s", line_type="sign", source="x", target="a" * 99, duration_ms=1000)]  # fmt: skip
    stats = reading_speed_stats(lines, ChecksConfig())
    assert stats.cps_max == 45.0 and stats.over_limit == 2
    assert stats.cps_p50 == 15.0
    assert len(stats.cps_histogram) == HISTOGRAM_BINS and sum(stats.cps_histogram) == 5
    assert stats.cps_histogram[40] == 1  # 45 CPS cai na última faixa
    assert histogram_percentile(stats.cps_histogram, 0.5) == 16.0  # limite superior da faixa [15,16)
    assert histogram_percentile([0] * HISTOGRAM_BINS, 0.5) == 0.0


def test_metrics_model_roundtrip_uses_schema_alias() -> None:
    m = EpisodeMetrics(final=FinalMetrics())
    raw = m.model_dump_json(by_alias=True)
    assert '"schema":1' in raw.replace(" ", "")
    assert EpisodeMetrics.model_validate_json(raw) == m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_snapshots.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.checks.snapshots'`.

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/checks/metrics.py`:

```python
"""Formato do metrics.json (camada 2) gravado pela etapa quality_checks."""

from pydantic import BaseModel, ConfigDict, Field

from translaterany.checks.models import Finding

METRICS_SCHEMA = 1
HISTOGRAM_BINS = 41  # faixas de 1 CPS: [0,1) ... [39,40), [40, ∞)


class SeverityCounts(BaseModel):
    info: int = 0
    warn: int = 0
    error: int = 0

    def add(self, other: "SeverityCounts") -> None:
        self.info += other.info
        self.warn += other.warn
        self.error += other.error


class SnapshotDelta(BaseModel):
    changed: int = 0
    edit_ratio: float = 0.0
    new: int = 0
    resolved: int = 0


class SnapshotMetrics(BaseModel):
    stage: str
    lines: int = 0
    checks: dict[str, SeverityCounts] = Field(default_factory=dict)
    delta: SnapshotDelta = Field(default_factory=SnapshotDelta)


class ReadingSpeedStats(BaseModel):
    cps_p50: float = 0.0
    cps_p95: float = 0.0
    cps_max: float = 0.0
    over_limit: int = 0
    cps_histogram: list[int] = Field(default_factory=lambda: [0] * HISTOGRAM_BINS)


class FinalMetrics(BaseModel):
    lines: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    checks: dict[str, SeverityCounts] = Field(default_factory=dict)
    flagged_lines: SeverityCounts = Field(default_factory=SeverityCounts)
    reading_speed: ReadingSpeedStats = Field(default_factory=ReadingSpeedStats)
    findings: list[Finding] = Field(default_factory=list)


class EpisodeMetrics(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)  # grava "schema", como o manifest

    schema_version: int = Field(default=METRICS_SCHEMA, alias="schema")
    snapshots: list[SnapshotMetrics] = Field(default_factory=list)
    final: FinalMetrics = Field(default_factory=FinalMetrics)
    episode_checks: list[Finding] = Field(default_factory=list)
```

`src/translaterany/checks/snapshots.py`:

```python
"""Montagem das linhas de cada instantâneo de texto, estado acumulado, delta e resumos."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher

from translaterany.checks.metrics import HISTOGRAM_BINS, ReadingSpeedStats, SeverityCounts, SnapshotDelta
from translaterany.checks.models import Finding, LineInput
from translaterany.checks.rules_context import measure
from translaterany.config.model import ChecksConfig
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc


@dataclass(frozen=True)
class LineSource:
    source: str
    line_type: str
    style: str
    duration_ms: int


def build_sources(doc: NormalizedDoc, classes: Classification, merged: MergedUnitsDoc | None) -> dict[str, LineSource]:
    durations: dict[str, int] = {}
    for event in doc.events:
        if event.unit is not None:
            span = event.end_ms - event.start_ms
            durations[event.unit] = min(span, durations.get(event.unit, span))
    sources: dict[str, LineSource] = {}
    for unit in doc.units:
        kind = classes.units[unit.id].type if unit.id in classes.units else "dialogue"
        sources[unit.id] = LineSource(unit.text, kind, unit.style, durations.get(unit.id, 0))
    for comp in merged.units if merged else []:
        if len(comp.unit_ids) > 1 and comp.unit_ids[0] in sources:
            first = sources[comp.unit_ids[0]]
            sources[comp.composite_id] = LineSource(
                comp.text_with_markers, first.line_type, first.style, sum(comp.durations_ms)
            )
    return sources


def composite_members(merged: MergedUnitsDoc | None) -> dict[str, list[str]]:
    return {c.composite_id: list(c.unit_ids) for c in (merged.units if merged else []) if len(c.unit_ids) > 1}


def lines_for(texts: Mapping[str, str], sources: Mapping[str, LineSource]) -> tuple[list[LineInput], list[str]]:
    lines: list[LineInput] = []
    unknown: list[str] = []
    for key, target in texts.items():
        src = sources.get(key)
        if src is None:
            unknown.append(key)
            continue
        lines.append(
            LineInput(
                id=key, line_type=src.line_type, style=src.style, source=src.source, target=target,
                duration_ms=src.duration_ms,
            )  # fmt: skip
        )
    return lines, unknown


def advance_state(
    state: Mapping[str, str], texts: Mapping[str, str], composites: Mapping[str, list[str]]
) -> dict[str, str]:
    new = dict(state)
    new.update(texts)
    for composite_id, members in composites.items():
        if composite_id in new and any(m in texts for m in members):
            del new[composite_id]
    return new


def finding_keys(findings: Iterable[Finding]) -> set[tuple[str, str | None]]:
    return {(f.check, f.unit_id) for f in findings}


def compute_delta(
    prev: Mapping[str, str], new: Mapping[str, str], prev_keys: set, new_keys: set
) -> SnapshotDelta:
    changed = sum(1 for key, text in new.items() if prev.get(key) != text)
    common = [key for key in new if key in prev]
    ratios = [1 - SequenceMatcher(None, prev[k], new[k]).ratio() for k in common]
    return SnapshotDelta(
        changed=changed,
        edit_ratio=round(sum(ratios) / len(ratios), 4) if ratios else 0.0,
        new=len(new_keys - prev_keys),
        resolved=len(prev_keys - new_keys),
    )


def summarize(findings: Iterable[Finding]) -> dict[str, SeverityCounts]:
    summary: dict[str, SeverityCounts] = {}
    for f in findings:
        counts = summary.setdefault(f.check, SeverityCounts())
        setattr(counts, f.severity, getattr(counts, f.severity) + 1)
    return summary


def flagged(findings: Iterable[Finding]) -> SeverityCounts:
    units: dict[str, set[str | None]] = {"info": set(), "warn": set(), "error": set()}
    for f in findings:
        units[f.severity].add(f.unit_id)
    return SeverityCounts(**{sev: len(ids) for sev, ids in units.items()})


def _index(values: Sequence[float], p: float) -> float:
    return values[int(p * (len(values) - 1))] if values else 0.0


def reading_speed_stats(lines: Iterable[LineInput], limits: ChecksConfig) -> ReadingSpeedStats:
    values: list[float] = []
    for line in lines:
        if line.line_type != "dialogue":
            continue
        cps = measure(line.target, line.duration_ms).cps
        if cps is not None:
            values.append(cps)
    values.sort()
    hist = [0] * HISTOGRAM_BINS
    for v in values:
        hist[min(int(v), HISTOGRAM_BINS - 1)] += 1
    return ReadingSpeedStats(
        cps_p50=round(_index(values, 0.5), 2),
        cps_p95=round(_index(values, 0.95), 2),
        cps_max=round(values[-1], 2) if values else 0.0,
        over_limit=sum(1 for v in values if v > limits.max_cps),
        cps_histogram=hist,
    )


def histogram_percentile(hist: Sequence[int], p: float) -> float:
    """Limite superior da faixa que atinge o percentil p (a última faixa, aberta, vale seu limite inferior)."""
    total = sum(hist)
    if not total:
        return 0.0
    acc = 0
    for i, n in enumerate(hist):
        acc += n
        if acc >= p * total:
            return float(i + 1) if i < len(hist) - 1 else float(i)
    return float(len(hist) - 1)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_snapshots.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/checks/snapshots.py src/translaterany/checks/metrics.py tests/test_snapshots.py
git add src/translaterany/checks/snapshots.py src/translaterany/checks/metrics.py tests/test_snapshots.py
git commit -m "feat(checks): adiciona instantâneos, estado acumulado e formato do metrics.json"
```

---

### Task 10: Etapa `quality_checks`

**Files:**
- Create: `src/translaterany/stages/quality_checks.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_quality_checks_stage.py`

**Interfaces:**
- Consumes: tudo das Tarefas 2–4, 8, 9; `MemoryStore` (`memory/store.py`: `load_glossary() -> dict[str, GlossaryEntry]`, `load_characters() -> list[CharacterEntry]`); `probe`, `font_attachments`, `extract_attachments`, `MediaError` (`media/mkv.py`); `UnitTexts`.
- Produces: etapa registrada `quality_checks` (episódio, `reads_source = True`, `version = "1"`, `Options = QualityChecksOptions(fonts: bool = True)`), atributos `snapshots: list[str]` e `limits: ChecksConfig`; artefato `quality_checks.json` = `EpisodeMetrics`. Constante `DEFAULT_SNAPSHOTS = ("translate_dialogue", "translate_signs", "translate_songs", "redistribute_sentences")`. Última etapa do `DEFAULT_PIPELINE`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_quality_checks_stage.py
"""Etapa quality_checks (M5)."""

from pathlib import Path

from mkvtools import needs_mkvtoolnix

from translaterany.checks.metrics import EpisodeMetrics
from translaterany.config.model import AppConfig, ChecksConfig
from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.units import Series
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.stages.quality_checks import DEFAULT_SNAPSHOTS, QualityChecksStage, assemble_metrics


def test_is_last_in_default_pipeline() -> None:
    assert DEFAULT_PIPELINE[-1] == "quality_checks"


def test_defaults_without_binding() -> None:
    stage = QualityChecksStage()
    assert stage.snapshots == list(DEFAULT_SNAPSHOTS)
    assert set(DEFAULT_SNAPSHOTS) <= set(stage.inputs)
    assert stage.limits == ChecksConfig()


def test_bind_pipeline_discovers_snapshots_and_optional_inputs() -> None:
    previous = [REGISTRY.get(n)() for n in ("select_track", "extract", "normalize", "classify", "translation_memory",
                                             "translate_signs")]  # fmt: skip
    stage = QualityChecksStage()
    stage.bind_pipeline(previous, AppConfig.model_validate({"checks": {"max_cps": 15}}))
    assert stage.snapshots == ["translate_signs"]
    assert stage.inputs == ("normalize", "classify", "extract", "translate_signs")  # sem merge/consolidate
    assert stage.limits.max_cps == 15.0


def test_cache_payload_changes_with_limits() -> None:
    a, b = QualityChecksStage(), QualityChecksStage()
    b.limits = ChecksConfig(max_cps=20)
    series = Series(name="x")
    assert a.cache_payload(series, None) != b.cache_payload(series, None)


ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48
Style: Sign,Arial,40

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:02:00.00,0:02:05.00,Sign,,0,0,0,,Student Council
Dialogue: 0,0:03:00.00,0:03:02.00,Default,,0,0,0,,Wait for me...
Dialogue: 0,0:03:02.20,0:03:04.00,Default,,0,0,0,,...I am coming!
Dialogue: 0,0:04:00.00,0:04:01.00,Default,,0,0,0,,I don't know what you are talking about at all.
"""


@needs_mkvtoolnix
def test_stage_writes_metrics_with_snapshots(tmp_path: Path) -> None:
    from mkvtools import Sub, make_mkv

    root = tmp_path / "lib" / "Show (2020)"
    make_mkv(root / "Season 1" / "Show - S01E01.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)
    stages = []
    for name in DEFAULT_PIPELINE:
        if name == "remux":
            continue
        stages.append(MetadataStage(anilist_client=None, jikan_client=None) if name == "metadata" else REGISTRY.get(name)())
    llm = FakeLLM(responses={
        "Student Council": "Conselho Estudantil",
        "Wait for me... ...I am coming!": "Espere por mim... já estou chegando!",
        "I don't know what you are talking about at all.": "Sei do que você fala, com toda a certeza do mundo.",
    })  # fmt: skip
    summary = Runner(stages, store, llm).run(series, episodes)
    assert not summary.failed, summary
    path = store.artifact_dir(series.key, episodes[0].key) / "quality_checks.json"
    metrics = EpisodeMetrics.model_validate_json(path.read_text(encoding="utf-8"))
    assert [s.stage for s in metrics.snapshots] == list(DEFAULT_SNAPSHOTS)
    assert metrics.final.lines == 4
    assert metrics.final.by_type == {"dialogue": 3, "sign": 1}
    checks = {f.check for f in metrics.final.findings}
    assert "negation" in checks and "reading_speed" in checks  # 50 chars em 1 s
    assert all(f.excerpt is not None for f in metrics.final.findings)
    redistribute = metrics.snapshots[-1]
    assert redistribute.delta.changed >= 2  # composto virou duas unidades
    assert any(f.check == "font_glyphs" for f in metrics.episode_checks)  # fontes falsas do mkvtools: info


def test_empty_snapshots_still_write_valid_metrics() -> None:
    metrics, state = assemble_metrics(
        snapshots=[], sources={}, composites={}, env=QualityChecksStage().env_for([], []), episode_checks=[]
    )
    assert state == {}
    assert metrics.final.lines == 0 and metrics.final.reading_speed.cps_p50 == 0.0
    assert metrics.snapshots == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_quality_checks_stage.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.stages.quality_checks'`.

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/stages/quality_checks.py`:

```python
"""Etapa quality_checks: mede cada instantâneo de texto e grava metrics.json (camada 2). Nunca corrige nada."""

import logging
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.checks import CheckEnv, Finding, run_line_checks
from translaterany.checks.fonts import check_font_glyphs, event_fonts, load_font_faces, style_fonts
from translaterany.checks.metrics import EpisodeMetrics, FinalMetrics, SnapshotMetrics
from translaterany.checks.snapshots import (
    LineSource,
    advance_state,
    build_sources,
    composite_members,
    compute_delta,
    finding_keys,
    flagged,
    lines_for,
    reading_speed_stats,
    summarize,
)
from translaterany.checks.text import plain
from translaterany.config.model import AppConfig, ChecksConfig
from translaterany.media.mkv import MediaError, extract_attachments, font_attachments, probe
from translaterany.memory.matching import select_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOTS: tuple[str, ...] = (
    "translate_dialogue",
    "translate_signs",
    "translate_songs",
    "redistribute_sentences",
)
_OPTIONAL = ("extract", "merge_sentences", "consolidate_memory")
_EXCERPT = 60


class QualityChecksOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fonts: bool = True


def assemble_metrics(
    snapshots: Sequence[tuple[str, Mapping[str, str]]],
    sources: Mapping[str, LineSource],
    composites: Mapping[str, list[str]],
    env: CheckEnv,
    episode_checks: list[Finding],
) -> tuple[EpisodeMetrics, dict[str, str]]:
    """Parte pura da etapa: instantâneos (nome, textos) em ordem -> (métricas, estado final)."""
    state: dict[str, str] = {}
    state_findings: list[Finding] = []
    result: list[SnapshotMetrics] = []
    for name, texts in snapshots:
        delivered, unknown = lines_for(texts, sources)
        if unknown:
            logger.warning("quality_checks: %s tem chaves desconhecidas: %s", name, ", ".join(unknown[:5]))
        new_state = advance_state(state, texts, composites)
        new_findings = run_line_checks(lines_for(new_state, sources)[0], env)
        result.append(
            SnapshotMetrics(
                stage=name,
                lines=len(delivered),
                checks=summarize(run_line_checks(delivered, env)),
                delta=compute_delta(state, new_state, finding_keys(state_findings), finding_keys(new_findings)),
            )
        )
        state, state_findings = new_state, new_findings

    final_lines, _ = lines_for(state, sources)
    for f in state_findings:
        if f.unit_id in state:
            f.excerpt = plain(state[f.unit_id])[:_EXCERPT]
    by_type: dict[str, int] = {}
    for line in final_lines:
        by_type[line.line_type] = by_type.get(line.line_type, 0) + 1
    final = FinalMetrics(
        lines=len(final_lines),
        by_type=by_type,
        checks=summarize(state_findings),
        flagged_lines=flagged(state_findings),
        reading_speed=reading_speed_stats(final_lines, env.limits),
        findings=state_findings,
    )
    return EpisodeMetrics(snapshots=result, final=final, episode_checks=episode_checks), state


@register_stage
class QualityChecksStage(Stage):
    name: ClassVar[str] = "quality_checks"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    reads_source: ClassVar[bool] = True  # extrai as fontes anexadas
    Options: ClassVar[type[BaseModel]] = QualityChecksOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.snapshots: list[str] = list(DEFAULT_SNAPSHOTS)
        self.limits = ChecksConfig()
        self.inputs = ("normalize", "classify", *_OPTIONAL, *self.snapshots)

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        names = [s.name for s in previous]
        self.snapshots = [s.name for s in previous if s.produces_texts]
        self.limits = app.checks if app is not None else ChecksConfig()
        self.inputs = ("normalize", "classify", *(n for n in _OPTIONAL if n in names), *self.snapshots)

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        return {"limits": self.limits.model_dump(mode="json"), "snapshots": self.snapshots}

    def env_for(self, glossary: list[GlossaryEntry], characters: list[CharacterEntry]) -> CheckEnv:
        return CheckEnv(
            glossary=glossary,
            names=[[c.name, *c.aliases] for c in characters],
            limits=self.limits,
        )

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classes = ctx.inputs.json("classify", Classification)
        merged = ctx.inputs.json("merge_sentences", MergedUnitsDoc) if "merge_sentences" in self.inputs else None
        sources = build_sources(doc, classes, merged)
        glossary, characters = self._memory(ctx, "\n".join(u.text for u in doc.units))
        snapshots = [(name, ctx.inputs.json(name, UnitTexts).texts) for name in self.snapshots]
        env = self.env_for(glossary, characters)
        metrics, final_state = assemble_metrics(snapshots, sources, composite_members(merged), env, [])
        if self.options.fonts and "extract" in self.inputs:
            metrics.episode_checks = self._font_checks(ctx, doc, final_state)
        ctx.output.json(metrics)

    def _memory(self, ctx: StageContext, text: str) -> tuple[list[GlossaryEntry], list[CharacterEntry]]:
        store = ctx.store
        if store is None:
            return [], []
        mem_dir = store.series_dir(ctx.series.key) / "memory"
        if not mem_dir.exists():
            return [], []
        mem = MemoryStore(mem_dir)
        return select_for_text(mem.load_glossary().values(), mem.load_characters(), text)

    def _font_checks(self, ctx: StageContext, doc: NormalizedDoc, state: Mapping[str, str]) -> list[Finding]:
        assert ctx.episode is not None
        try:
            styles = style_fonts(ctx.inputs.path("extract").read_bytes())
            chars_by_font: dict[str, set[str]] = {}
            for event in doc.events:
                if event.unit is None or event.unit not in state:
                    continue
                for font in event_fonts(event, styles):
                    chars_by_font.setdefault(font, set()).update(plain(state[event.unit]))
            if not chars_by_font:
                return []
            with tempfile.TemporaryDirectory(prefix="translaterany-fonts-") as tmp:
                files = extract_attachments(ctx.episode.source, font_attachments(probe(ctx.episode.source)), Path(tmp))
                faces, problems = load_font_faces(files)
                return problems + check_font_glyphs(chars_by_font, faces)
        except (MediaError, OSError) as exc:
            return [Finding(check="font_glyphs", severity="info", message=f"fontes não verificadas: {exc}")]
```

`src/translaterany/stages/__init__.py`: acrescente `quality_checks` à lista de imports (ordem alfabética) e `"quality_checks"` como **último** item de `DEFAULT_PIPELINE` (depois de `"remux"`); atualize o comentário: `# Pipeline usado quando não há [pipeline] no config (remux vem desabilitado; quality_checks mede o resultado).`

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_quality_checks_stage.py tests/test_m4_e2e.py tests/test_m3_e2e.py tests/test_m2_e2e.py -v`
Expected: PASS. (Os E2E anteriores montam o `DEFAULT_PIPELINE` e agora também rodam `quality_checks`.)

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: todos passam.

- [ ] **Step 6: Commit**

```bash
uv run ruff check src/translaterany/stages/quality_checks.py src/translaterany/stages/__init__.py tests/test_quality_checks_stage.py
git add src/translaterany/stages/quality_checks.py src/translaterany/stages/__init__.py tests/test_quality_checks_stage.py
git commit -m "feat(stages): adiciona etapa quality_checks com metrics.json por episódio"
```

---

### Task 11: Agregação do relatório (`pipeline/report.py`)

**Files:**
- Create: `src/translaterany/pipeline/report.py`
- Test: `tests/test_report.py`

**Interfaces:**
- Consumes: `ArtifactStore.read_manifest`, `episode_keys`, `artifact_dir`; `LLMStats`, `ModelStats`; `EpisodeMetrics`, `SeverityCounts`, `ReadingSpeedStats`, `HISTOGRAM_BINS`, `histogram_percentile`.
- Produces:
  - `StageSummary(units_done, units_failed, duration_s, llm: LLMStats, counters: dict[str, int])` com propriedade `mean_duration_s`
  - `CheckSummary(counts: SeverityCounts, rate: float)` — `rate = (warn + error) / linhas finais`
  - `SnapshotSummary(episodes, changed, new, resolved, edit_ratio_mean)`
  - `EpisodeRank(episode, lines, error_lines, error_rate)`
  - `SeriesReport(schema_version=1 alias "schema", series, generated_at, episodes, lines, stages, models, final_checks, reading_speed, snapshots, worst_episodes, missing_metrics, warnings)`; `REPORT_SCHEMA = 1`
  - `load_episode_metrics(store, series_key, episode_key) -> EpisodeMetrics | None` (lança `MetricsError` se ilegível)
  - `build_report(store, series_key, series_name, stage_order: Sequence[str], episodes: Sequence[str] | None = None) -> SeriesReport`
  - `DeltaRow(metric: str, current: float, baseline: float)` com propriedade `delta`
  - `compare_reports(current: SeriesReport, baseline: SeriesReport) -> list[DeltaRow]`
  - `class MetricsError(Exception)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report.py
"""Agregação do report (M5): manifests + metrics.json -> SeriesReport."""

from pathlib import Path

import pytest

from translaterany.checks import Finding
from translaterany.checks.metrics import (
    EpisodeMetrics,
    FinalMetrics,
    ReadingSpeedStats,
    SeverityCounts,
    SnapshotDelta,
    SnapshotMetrics,
)
from translaterany.llm.metered import LLMStats, ModelStats
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import Manifest, StageRecord, UnitInfo, save_manifest
from translaterany.pipeline.report import SeriesReport, build_report, compare_reports

SERIES = "show"


def write_episode(store: ArtifactStore, ep: str, *, metrics: EpisodeMetrics | None, cost: float = 0.5,
                  corrupt: bool = False, series: str = SERIES) -> None:  # fmt: skip
    llm = LLMStats(calls=2, errors={"output": 1},
                   by_model={"fake:t": ModelStats(calls=2, input_tokens=100, output_tokens=50, cost_usd=cost)})  # fmt: skip
    stages = {"translate_dialogue": StageRecord(status="done", duration_s=10.0, llm=llm, counters={"lines": 5})}
    if metrics is not None or corrupt:
        stages["quality_checks"] = StageRecord(status="done", artifact="quality_checks.json")
    save_manifest(store.manifest_path(series, ep), Manifest(unit=UnitInfo(series=series, episode=ep), stages=stages))
    path = store.artifact_dir(series, ep) / "quality_checks.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    if corrupt:
        path.write_text("{nao é json", encoding="utf-8")
    elif metrics is not None:
        path.write_text(metrics.model_dump_json(by_alias=True), encoding="utf-8")


def metrics(lines: int, errors: int, hist_bin: int) -> EpisodeMetrics:
    hist = [0] * 41
    hist[hist_bin] = lines
    findings = [Finding(check="reading_speed", unit_id=f"u{i}", severity="error", message="CPS") for i in range(errors)]
    return EpisodeMetrics(
        snapshots=[SnapshotMetrics(stage="translate_dialogue", lines=lines,
                                   delta=SnapshotDelta(changed=lines, edit_ratio=0.2, new=errors))],
        final=FinalMetrics(lines=lines, by_type={"dialogue": lines},
                           checks={"reading_speed": SeverityCounts(error=errors)},
                           flagged_lines=SeverityCounts(error=errors),
                           reading_speed=ReadingSpeedStats(over_limit=errors, cps_max=float(hist_bin), cps_histogram=hist),
                           findings=findings),
    )  # fmt: skip


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    s = ArtifactStore(tmp_path / "data")
    write_episode(s, "S01E01", metrics=metrics(10, 1, 12))
    write_episode(s, "S01E02", metrics=metrics(10, 4, 18))
    write_episode(s, "S01E03", metrics=None)
    write_episode(s, "S01E04", metrics=None, corrupt=True)
    return s


def test_build_report_aggregates(store: ArtifactStore) -> None:
    report = build_report(store, SERIES, "Show", ["translate_dialogue", "quality_checks"])
    td = report.stages["translate_dialogue"]
    assert td.units_done == 4 and td.duration_s == 40.0 and td.mean_duration_s == 10.0
    assert td.llm.calls == 8 and td.llm.errors == {"output": 4} and td.counters == {"lines": 20}
    assert report.models["fake:t"].cost_usd == pytest.approx(2.0)
    assert report.lines == 20 and report.episodes == 4
    assert report.final_checks["reading_speed"].counts.error == 5
    assert report.final_checks["reading_speed"].rate == pytest.approx(5 / 20)
    assert report.reading_speed.over_limit == 5 and report.reading_speed.cps_max == 18.0
    assert report.reading_speed.cps_p50 == 13.0  # metade das linhas na faixa [12,13)
    assert report.snapshots["translate_dialogue"].new == 5
    assert report.snapshots["translate_dialogue"].edit_ratio_mean == pytest.approx(0.2)
    assert [r.episode for r in report.worst_episodes] == ["S01E02", "S01E01"]
    assert report.missing_metrics == ["S01E03", "S01E04"]
    assert any("S01E04" in w for w in report.warnings)


def test_report_has_no_subtitle_text(store: ArtifactStore) -> None:
    raw = build_report(store, SERIES, "Show", []).model_dump_json(by_alias=True)
    assert "findings" not in raw and "excerpt" not in raw


def test_episode_filter(store: ArtifactStore) -> None:
    report = build_report(store, SERIES, "Show", [], episodes=["S01E02"])
    assert report.episodes == 1 and report.lines == 10


def test_json_roundtrip_and_compare(store: ArtifactStore, tmp_path: Path) -> None:
    current = build_report(store, SERIES, "Show", ["translate_dialogue"])
    saved = tmp_path / "base.json"
    saved.write_text(current.model_dump_json(by_alias=True), encoding="utf-8")
    baseline = SeriesReport.model_validate_json(saved.read_text(encoding="utf-8"))
    rows = {r.metric: r for r in compare_reports(current, baseline)}
    assert rows["final.reading_speed.rate"].delta == 0
    baseline.final_checks["reading_speed"].rate = 0.5
    rows = {r.metric: r for r in compare_reports(current, baseline)}
    assert rows["final.reading_speed.rate"].delta == pytest.approx(0.25 - 0.5)
    assert "stage.translate_dialogue.cost_usd" in rows
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.pipeline.report'`.

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/pipeline/report.py`:

```python
"""Agregação do `report`: manifests (camada 1) + metrics.json (camada 2). Sem texto de legenda."""

from collections.abc import Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from translaterany.checks.metrics import HISTOGRAM_BINS, EpisodeMetrics, ReadingSpeedStats, SeverityCounts
from translaterany.checks.snapshots import histogram_percentile
from translaterany.llm.metered import LLMStats, ModelStats
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import StageRecord

REPORT_SCHEMA = 1
METRICS_STAGE = "quality_checks"


class MetricsError(Exception):
    """metrics.json ilegível ou de schema desconhecido."""


class StageSummary(BaseModel):
    units_done: int = 0
    units_failed: int = 0
    duration_s: float = 0.0
    llm: LLMStats = Field(default_factory=LLMStats)
    counters: dict[str, int] = Field(default_factory=dict)

    @property
    def mean_duration_s(self) -> float:
        runs = self.units_done + self.units_failed
        return self.duration_s / runs if runs else 0.0


class CheckSummary(BaseModel):
    counts: SeverityCounts = Field(default_factory=SeverityCounts)
    rate: float = 0.0


class SnapshotSummary(BaseModel):
    episodes: int = 0
    changed: int = 0
    new: int = 0
    resolved: int = 0
    edit_ratio_mean: float = 0.0


class EpisodeRank(BaseModel):
    episode: str
    lines: int
    error_lines: int
    error_rate: float


class SeriesReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schema_version: int = Field(default=REPORT_SCHEMA, alias="schema")
    series: str
    generated_at: datetime = Field(default_factory=datetime.now)
    episodes: int = 0
    lines: int = 0
    stages: dict[str, StageSummary] = Field(default_factory=dict)
    models: dict[str, ModelStats] = Field(default_factory=dict)
    final_checks: dict[str, CheckSummary] = Field(default_factory=dict)
    reading_speed: ReadingSpeedStats = Field(default_factory=ReadingSpeedStats)
    snapshots: dict[str, SnapshotSummary] = Field(default_factory=dict)
    worst_episodes: list[EpisodeRank] = Field(default_factory=list)
    missing_metrics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def load_episode_metrics(store: ArtifactStore, series_key: str, episode_key: str) -> EpisodeMetrics | None:
    manifest = store.read_manifest(series_key, episode_key)
    record = manifest.stages.get(METRICS_STAGE) if manifest else None
    if record is None or record.status != "done" or record.artifact is None:
        return None
    path = store.artifact_dir(series_key, episode_key) / record.artifact
    try:
        metrics = EpisodeMetrics.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, UnicodeDecodeError) as exc:
        raise MetricsError(f"metrics.json ilegível em {episode_key}: {type(exc).__name__}") from exc
    if metrics.schema_version != 1:
        raise MetricsError(f"metrics.json de {episode_key} tem schema {metrics.schema_version} desconhecido")
    return metrics


def _add_stage(summary: StageSummary, record: StageRecord) -> None:
    if record.status == "done":
        summary.units_done += 1
    else:
        summary.units_failed += 1
    summary.duration_s += record.duration_s
    if record.llm is not None:
        summary.llm.add(record.llm)
    for name, n in record.counters.items():
        summary.counters[name] = summary.counters.get(name, 0) + n


def build_report(
    store: ArtifactStore,
    series_key: str,
    series_name: str,
    stage_order: Sequence[str],
    episodes: Sequence[str] | None = None,
) -> SeriesReport:
    report = SeriesReport(series=series_name)
    keys = list(episodes) if episodes is not None else store.episode_keys(series_key)
    manifests = [store.read_manifest(series_key, None)] if episodes is None else []
    manifests += [store.read_manifest(series_key, k) for k in keys]
    stage_names: dict[str, None] = dict.fromkeys(stage_order)
    for manifest in manifests:
        if manifest is None:
            continue
        for name, record in manifest.stages.items():
            stage_names.setdefault(name, None)
            _add_stage(report.stages.setdefault(name, StageSummary()), record)
    report.stages = {n: report.stages[n] for n in stage_names if n in report.stages}
    for summary in report.stages.values():
        for model_id, stats in summary.llm.by_model.items():
            report.models.setdefault(model_id, ModelStats()).add(stats)

    report.episodes = len(keys)
    hist = [0] * HISTOGRAM_BINS
    edit_sums: dict[str, float] = {}
    for key in keys:
        try:
            metrics = load_episode_metrics(store, series_key, key)
        except MetricsError as exc:
            report.warnings.append(str(exc))
            metrics = None
        if metrics is None:
            report.missing_metrics.append(key)
            continue
        final = metrics.final
        report.lines += final.lines
        for check, counts in final.checks.items():
            report.final_checks.setdefault(check, CheckSummary()).counts.add(counts)
        rs = final.reading_speed
        report.reading_speed.over_limit += rs.over_limit
        report.reading_speed.cps_max = max(report.reading_speed.cps_max, rs.cps_max)
        hist = [a + b for a, b in zip(hist, rs.cps_histogram, strict=False)]
        for snap in metrics.snapshots:
            s = report.snapshots.setdefault(snap.stage, SnapshotSummary())
            s.episodes += 1
            s.changed += snap.delta.changed
            s.new += snap.delta.new
            s.resolved += snap.delta.resolved
            edit_sums[snap.stage] = edit_sums.get(snap.stage, 0.0) + snap.delta.edit_ratio
        if final.lines:
            report.worst_episodes.append(
                EpisodeRank(
                    episode=key,
                    lines=final.lines,
                    error_lines=final.flagged_lines.error,
                    error_rate=round(final.flagged_lines.error / final.lines, 4),
                )
            )
    for check in report.final_checks.values():
        check.rate = round((check.counts.warn + check.counts.error) / report.lines, 4) if report.lines else 0.0
    for stage, s in report.snapshots.items():
        s.edit_ratio_mean = round(edit_sums[stage] / s.episodes, 4) if s.episodes else 0.0
    report.reading_speed.cps_histogram = hist
    report.reading_speed.cps_p50 = histogram_percentile(hist, 0.5)
    report.reading_speed.cps_p95 = histogram_percentile(hist, 0.95)
    report.worst_episodes = sorted(report.worst_episodes, key=lambda r: r.error_rate, reverse=True)[:5]
    return report


class DeltaRow(BaseModel):
    metric: str
    current: float
    baseline: float

    @property
    def delta(self) -> float:
        return self.current - self.baseline


def compare_reports(current: SeriesReport, baseline: SeriesReport) -> list[DeltaRow]:
    """Deltas de indicadores e custos. Em todos, valor menor é melhor."""
    rows: list[DeltaRow] = []
    for check in sorted(set(current.final_checks) | set(baseline.final_checks)):
        cur, base = current.final_checks.get(check, CheckSummary()), baseline.final_checks.get(check, CheckSummary())
        rows.append(DeltaRow(metric=f"final.{check}.rate", current=cur.rate, baseline=base.rate))
    rows.append(
        DeltaRow(
            metric="reading_speed.cps_p95",
            current=current.reading_speed.cps_p95,
            baseline=baseline.reading_speed.cps_p95,
        )
    )
    for stage in [s for s in current.stages if s in baseline.stages]:
        cur, base = current.stages[stage], baseline.stages[stage]
        rows.append(DeltaRow(metric=f"stage.{stage}.mean_duration_s", current=cur.mean_duration_s,
                             baseline=base.mean_duration_s))  # fmt: skip
        rows.append(DeltaRow(metric=f"stage.{stage}.output_tokens", current=cur.llm.output_tokens,
                             baseline=base.llm.output_tokens))  # fmt: skip
        rows.append(DeltaRow(metric=f"stage.{stage}.cost_usd", current=cur.llm.cost_usd, baseline=base.llm.cost_usd))
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_report.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/pipeline/report.py tests/test_report.py
git add src/translaterany/pipeline/report.py tests/test_report.py
git commit -m "feat(report): agrega métricas de processo e qualidade por série"
```

---

### Task 12: Comando `translaterany report`

**Files:**
- Create: `src/translaterany/cli/report.py`
- Modify: `src/translaterany/cli/app.py` (última linha de imports)
- Test: `tests/test_cli_report.py`

**Interfaces:**
- Consumes: `build_report`, `compare_reports`, `load_episode_metrics`, `SeriesReport`, `MetricsError` (Tarefa 11); `discover`; `ArtifactStore`; `ManifestError`; `EXIT_*`, `load_or_exit`, `console` (`cli/app.py`).
- Produces: comando `report(path, --episode, --json, --baseline)`; códigos de saída conforme spec §8.3.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_report.py
"""Comando report (M5)."""

import json
from pathlib import Path

from test_report import metrics, write_episode
from typer.testing import CliRunner

from translaterany.cli import app
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore

runner = CliRunner()


def _config(tmp_path: Path, data_dir: Path) -> str:
    path = tmp_path / "config.toml"
    path.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")
    return str(path)


def _invoke(*args: str):
    return runner.invoke(app, list(args), env={"XDG_CONFIG_HOME": "/nao/existe", "TRANSLATERANY_CONFIG": ""})


def _setup(tmp_path: Path, series_dir: Path, *, with_metrics: bool = True) -> tuple[str, ArtifactStore]:
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series, _ = discover(series_dir)
    store.write_series_info(series)
    write_episode(store, "S01E01", metrics=metrics(10, 2, 14) if with_metrics else None, series=series.key)
    write_episode(store, "S01E02", metrics=None, series=series.key)
    return _config(tmp_path, data_dir), store


def test_report_terminal_and_json(tmp_path: Path, series_dir: Path) -> None:
    cfg, _ = _setup(tmp_path, series_dir)
    out = tmp_path / "base.json"
    result = _invoke("--config", cfg, "report", str(series_dir), "--json", str(out))
    assert result.exit_code == 0, result.output
    assert "Processo por etapa" in result.output and "Indicadores finais" in result.output
    assert "S01E02" in result.output  # sem métricas
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["schema"] == 1 and data["lines"] == 10


def test_report_baseline_and_episode(tmp_path: Path, series_dir: Path) -> None:
    cfg, _ = _setup(tmp_path, series_dir)
    out = tmp_path / "base.json"
    _invoke("--config", cfg, "report", str(series_dir), "--json", str(out))
    result = _invoke("--config", cfg, "report", str(series_dir), "--baseline", str(out))
    assert result.exit_code == 0 and "Comparação com a linha de base" in result.output
    ep = _invoke("--config", cfg, "report", str(series_dir), "--episode", "S01E01")
    assert ep.exit_code == 0 and "reading_speed" in ep.output and "Achados" in ep.output


def test_report_exit_codes(tmp_path: Path, series_dir: Path) -> None:
    cfg, _ = _setup(tmp_path, series_dir, with_metrics=False)
    none = _invoke("--config", cfg, "report", str(series_dir))
    assert none.exit_code == 1 and "Nenhuma métrica encontrada" in none.output
    cfg, _ = _setup(tmp_path, series_dir)
    bad = tmp_path / "bad.json"
    bad.write_text("{}", encoding="utf-8")
    assert _invoke("--config", cfg, "report", str(series_dir), "--baseline", str(bad)).exit_code == 2
    never = tmp_path / "lib2" / "Nunca (2021)"
    (never / "Season 1").mkdir(parents=True)
    (never / "Season 1" / "S01E01.mkv").write_text("x", encoding="utf-8")
    assert _invoke("--config", cfg, "report", str(never)).exit_code == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli_report.py -v`
Expected: FAIL (`No such command 'report'`, código 2).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/cli/report.py`:

```python
"""Comando report: processo por etapa, por modelo, indicadores finais e instantâneos."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.table import Table

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.report import (
    REPORT_SCHEMA,
    MetricsError,
    SeriesReport,
    build_report,
    compare_reports,
    load_episode_metrics,
)


def _arrow(delta: float) -> str:
    if abs(delta) < 1e-9:
        return "="
    return "[red]▲[/red]" if delta > 0 else "[green]▼[/green]"


def _render(report: SeriesReport) -> None:
    table = Table(title=f"Processo por etapa — {report.series}")
    for col in ("Etapa", "OK", "Falhas", "Tempo total", "Tempo médio", "Chamadas", "Tokens ent.", "Tokens saída",
                "Custo (USD)", "Erros IA", "Contadores"):  # fmt: skip
        table.add_column(col)
    for name, s in report.stages.items():
        table.add_row(
            name, str(s.units_done), str(s.units_failed), f"{s.duration_s:.1f}s", f"{s.mean_duration_s:.1f}s",
            str(s.llm.calls), str(s.llm.input_tokens), str(s.llm.output_tokens), f"{s.llm.cost_usd:.4f}",
            ", ".join(f"{k}={v}" for k, v in s.llm.errors.items()) or "—",
            ", ".join(f"{k}={v}" for k, v in s.counters.items()) or "—",
        )  # fmt: skip
    console.print(table)

    if report.models:
        models = Table(title="Por modelo")
        for col in ("Modelo", "Chamadas", "Tokens ent.", "Tokens saída", "Custo (USD)"):
            models.add_column(col)
        for model_id, m in report.models.items():
            models.add_row(model_id, str(m.calls), str(m.input_tokens), str(m.output_tokens), f"{m.cost_usd:.4f}")
        console.print(models)

    final = Table(title=f"Indicadores finais — {report.lines} linhas em {report.episodes} episódio(s)")
    for col in ("Checagem", "error", "warn", "info", "Taxa"):
        final.add_column(col)
    for check, c in sorted(report.final_checks.items()):
        final.add_row(check, str(c.counts.error), str(c.counts.warn), str(c.counts.info), f"{c.rate:.1%}")
    console.print(final)
    rs = report.reading_speed
    console.print(f"CPS: p50 ≤ {rs.cps_p50:g} · p95 ≤ {rs.cps_p95:g} · máx {rs.cps_max:g} · acima do limite: {rs.over_limit}")

    if report.snapshots:
        snaps = Table(title="Instantâneos (por etapa de texto)")
        for col in ("Etapa", "Episódios", "Linhas alteradas", "Achados novos", "Resolvidos", "Edição média"):
            snaps.add_column(col)
        for name, s in report.snapshots.items():
            snaps.add_row(name, str(s.episodes), str(s.changed), str(s.new), str(s.resolved), f"{s.edit_ratio_mean:.1%}")
        console.print(snaps)

    if report.worst_episodes:
        worst = Table(title="Piores episódios (linhas com error)")
        for col in ("Episódio", "Linhas", "Com error", "Taxa"):
            worst.add_column(col)
        for r in report.worst_episodes:
            worst.add_row(r.episode, str(r.lines), str(r.error_lines), f"{r.error_rate:.1%}")
        console.print(worst)
    if report.missing_metrics:
        console.print(f"[yellow]Sem métricas (rode `translaterany run`): {', '.join(report.missing_metrics)}[/yellow]")
    for warning in report.warnings:
        console.print(f"[yellow]Aviso: {warning}[/yellow]")


@app.command()
def report(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série.")],
    episode: Annotated[str | None, typer.Option("--episode", help="Só um episódio (ex.: S01E03).")] = None,
    json_out: Annotated[Path | None, typer.Option("--json", help="Grava o relatório (linha de base) em JSON.")] = None,
    baseline: Annotated[Path | None, typer.Option("--baseline", help="Compara com um relatório salvo.")] = None,
) -> None:
    """Mostra métricas de processo e indicadores de qualidade da série."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    store = ArtifactStore(cfg.data_dir)
    try:
        series, _ = discover(path)
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc
    if not store.series_dir(series.key).exists():
        console.print(f"Pasta nunca processada: {series.name}")
        raise typer.Exit(EXIT_FAILURE)

    base: SeriesReport | None = None
    if baseline is not None:
        try:
            base = SeriesReport.model_validate_json(baseline.read_text(encoding="utf-8"))
        except (OSError, ValidationError, UnicodeDecodeError) as exc:
            console.print(f"[red]Linha de base ilegível: {baseline} ({type(exc).__name__})[/red]")
            raise typer.Exit(EXIT_USAGE) from exc
        if base.schema_version != REPORT_SCHEMA:
            console.print(f"[red]Linha de base com schema {base.schema_version}; esperado {REPORT_SCHEMA}.[/red]")
            raise typer.Exit(EXIT_USAGE)

    try:
        result = build_report(store, series.key, series.name, [s.name for s in cfg.stages],
                              episodes=[episode] if episode else None)  # fmt: skip
    except ManifestError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_FAILURE) from exc
    if result.episodes and len(result.missing_metrics) == result.episodes:
        console.print("Nenhuma métrica encontrada — rode `translaterany run` primeiro.")
        raise typer.Exit(EXIT_FAILURE)

    _render(result)
    if episode:
        try:
            metrics = load_episode_metrics(store, series.key, episode)
        except MetricsError as exc:
            console.print(f"[yellow]{exc}[/yellow]")
            metrics = None
        if metrics is not None:
            table = Table(title=f"Achados finais — {episode}")
            for col in ("Unidade", "Checagem", "Severidade", "Mensagem", "Trecho"):
                table.add_column(col)
            for f in metrics.final.findings + metrics.episode_checks:
                table.add_row(f.unit_id or "—", f.check, f.severity, f.message, f.excerpt or "")
            console.print(table)
    if base is not None:
        table = Table(title="Comparação com a linha de base")
        for col in ("Métrica", "Atual", "Base", "Δ", ""):
            table.add_column(col)
        for row in compare_reports(result, base):
            table.add_row(row.metric, f"{row.current:.4g}", f"{row.baseline:.4g}", f"{row.delta:+.4g}", _arrow(row.delta))
        console.print(table)
    if json_out is not None:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(result.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        console.print(f"Relatório salvo em {json_out}")
```

Em `cli/app.py`, última linha: `from translaterany.cli import doctor, estimate, memory, report, retry, run, status  # noqa: E402, F401`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli_report.py tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/cli/report.py src/translaterany/cli/app.py tests/test_cli_report.py
git add src/translaterany/cli/report.py src/translaterany/cli/app.py tests/test_cli_report.py
git commit -m "feat(cli): adiciona comando report com saída JSON e linha de base"
```

---

### Task 13: E2E do M5, documentação e estado

**Files:**
- Create: `tests/test_m5_e2e.py`, `docs/baselines/README.md`
- Modify: `STATE.md`, `README.md` (seção de comandos, se listar comandos)

**Interfaces:**
- Consumes: pipeline completo, `build_report`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m5_e2e.py
"""Ponta a ponta do M5: pipeline completo com FakeLLM -> metrics.json -> report."""

from pathlib import Path

from mkvtools import Sub, make_mkv, needs_mkvtoolnix

from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.report import build_report
from translaterany.pipeline.runner import Runner
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage

pytestmark = needs_mkvtoolnix

ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:00.00,0:01:03.00,Default,,0,0,0,,Where are we going, friend?
Dialogue: 0,0:01:04.00,0:01:04.50,Default,,0,0,0,,I never said that I would come with you today.
"""


def test_m5_pipeline_metrics_and_report(tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Show (2020)"
    for ep in (1, 2):
        make_mkv(root / "Season 1" / f"Show - S01E0{ep}.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)
    stages = [
        MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
        for n in DEFAULT_PIPELINE
        if n != "remux"
    ]
    llm = FakeLLM(responses={
        "Where are we going, friend?": "Aonde vamos, amigo?",
        "I never said that I would come with you today.": "Eu disse que viria com você hoje.",
    })  # fmt: skip
    summary = Runner(stages, store, llm, prices=lambda alias: (1.0, 2.0)).run(series, episodes)
    assert not summary.failed

    report = build_report(store, series.key, series.name, [s.name for s in stages])
    assert report.episodes == 2 and not report.missing_metrics
    assert report.stages["translate_dialogue"].llm.calls >= 2
    assert report.stages["translate_dialogue"].counters["lines"] >= 2
    assert report.stages["translate_dialogue"].llm.cost_usd > 0  # prices=(1.0, 2.0) USD/Mtok
    assert sum(m.cost_usd for m in report.models.values()) >= report.stages["translate_dialogue"].llm.cost_usd
    assert report.final_checks["negation"].counts.warn == 2  # um por episódio
    assert report.final_checks["reading_speed"].counts.error >= 2  # 46 caracteres em 0,5 s
    assert "redistribute_sentences" in report.snapshots
```

- [ ] **Step 2: Run test to verify it passes** (as peças já existem; se falhar, o problema está na integração — use `superpowers:systematic-debugging`, não afrouxe o teste)

Run: `uv run pytest tests/test_m5_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Documentação**

`docs/baselines/README.md`:

```markdown
# Linhas de base de qualidade

Relatórios gerados com `translaterany report <série> --json docs/baselines/<data>-<marco>-<série>.json`
ao fim de cada marco (M5 em diante). Contêm **apenas números agregados** — nunca trechos de legenda.

Comparar um marco com a linha de base anterior:

    translaterany report <série> --baseline docs/baselines/<arquivo>.json
```

`STATE.md`: status do M5 → 🔨 (implementação) com link do plano; "Próxima ação": aceite real (Charlotte com modelos locais + linha de base). No README, se houver lista de comandos, acrescente `report` com uma linha de descrição.

- [ ] **Step 4: Suíte completa e ruff dos arquivos do marco**

Run: `uv run pytest -q`
Expected: todos passam (396 anteriores + novos).

Run: `uv run ruff check src/translaterany/checks src/translaterany/llm/metered.py src/translaterany/llm/pricing.py src/translaterany/pipeline/report.py src/translaterany/pipeline/stage_metrics.py src/translaterany/stages/quality_checks.py src/translaterany/cli/report.py src/translaterany/memory/matching.py tests/test_m5_e2e.py`
Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/test_m5_e2e.py docs/baselines/README.md STATE.md README.md
git commit -m "test(e2e): valida integração ponta a ponta do Marco 5 e atualiza STATE.md"
```

- [ ] **Step 6: Aceite real (manual, com o usuário)**

Não automatizável aqui (Ollama + mídia real). Roteiro para o usuário:

```bash
translaterany run "temporada-teste/Charlotte (2015)"
translaterany report "temporada-teste/Charlotte (2015)" --json docs/baselines/<AAAA-MM-DD>-m5-charlotte.json
```

Conferir que o JSON não contém texto de legenda (`grep -c '"findings"'` → 0), versionar o arquivo e registrar no `STATE.md` os números principais (taxas por checagem, CPS p95, tempo e tokens por etapa).
