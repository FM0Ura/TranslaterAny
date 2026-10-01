# M7 — Refinamento II · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Acabamento profissional com coerência de tratamento (você/tu/gênero), adaptação de velocidade de leitura (CPS > 17), ortografia via LanguageTool local com degradação graciosa e leitura corrida final 100% em PT-BR, antes da redistribuição.

**Architecture:** Quatro novas etapas no pipeline inseridas sequencialmente entre `colloquial` e `redistribute_sentences`: `treatment_consistency`, `adapt`, `orthography` e `final_readthrough`. Todas produzem diálogo (`produces_dialogue = True`), atuam sobre `CompositeUnit` e reutilizam o motor de edições de `translaterany.refine` (`LineEdit`, `apply_edits`). A etapa de ortografia integra-se diretamente ao LanguageTool via HTTP sem consumo de IA. `redistribute_sentences` lê automaticamente a saída da última etapa ativa.

**Tech Stack:** Python 3.14 (`uv`), pydantic 2, pytest, httpx, respx, Ollama (Gemma4 no papel `review`), LanguageTool local via HTTP (`http://localhost:8010/v2/check`).

**Spec:** [`docs/superpowers/specs/2026-10-01-m7-refinamento-ii-design.md`](../specs/2026-10-01-m7-refinamento-ii-design.md)

## Global Constraints

- Python **3.14**; dependência `httpx` (já instalada) e `respx` para mocks nos testes.
- Identificadores/código em **inglês**; mensagens ao usuário, logs e instruções de prompt em **PT-BR**.
- Modelo das etapas com IA: papel **`review`** (Gemma4 no perfil `local`).
- Respostas das etapas com IA: estritamente `edits: list[LineEdit]`.
- Todas as edições passam por validação determinística via `apply_edits` (não piorar sentido, marcadores intactos, sem reversões).
- A etapa `orthography` é determinística (sem IA); se o LanguageTool estiver offline ou em timeout, emite aviso, incrementa `offline = 1` e não aborta o pipeline.
- Testes **somente sintéticos** (`FakeLLM` e mocks HTTP `respx`); nunca versionar mídia nem legendas reais.
- Testes: `uv run pytest -q` na raiz. Suíte atual: 558 passando.
- Commits em português `tipo(escopo): descrição`.

## Review Focus

1. **LanguageTool offline ou em timeout** — a etapa `orthography` emite aviso ao usuário, registra `offline = 1` no manifest e repassa os textos sem erro. Teste na Tarefa 4.
2. **Isenção do LanguageTool** — termos do glossário e nomes de personagens nunca são "corrigidos" pelo LanguageTool. Teste na Tarefa 4.
3. **Falta de consistência pronominal com falante de baixa confiança** — `treatment_consistency` só unifica pares com confiança $\ge 0.7$ no `scene_analysis`, evitando inventar relações. Teste na Tarefa 2.
4. **Encurtamento em `adapt` sem perda semântica** — falas com CPS > 17 são condensadas respeitando o orçamento estrito de caracteres, mas edições que alteram números, negações ou termos são rejeitadas por `apply_edits`. Teste na Tarefa 3.
5. **Config desativa etapas do M7** — se `treatment_consistency`, `adapt`, `orthography` ou `final_readthrough` forem desativadas no TOML, `redistribute_sentences` consome a última ativa sem falha. Teste na Tarefa 7.

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/translaterany/config/schemas.py` (mod.) | Schemas de configuração das 4 etapas (`treatment_consistency`, `adapt`, `orthography`, `final_readthrough`) |
| `src/translaterany/refine/treatment.py` (novo) | Algoritmo de contagem de pronomes, gênero por par e triagem de inconsistências |
| `src/translaterany/stages/treatment_consistency.py` (novo) | Etapa `treatment_consistency` |
| `src/translaterany/stages/adapt.py` (novo) | Etapa `adapt` (condensação para limite de CPS) |
| `src/translaterany/orthography/client.py` (novo) | Cliente HTTP do LanguageTool, filtros de regras e lista de isenções |
| `src/translaterany/stages/orthography.py` (novo) | Etapa `orthography` |
| `src/translaterany/stages/final_readthrough.py` (novo) | Etapa `final_readthrough` (leitura corrida em PT-BR) |
| `src/translaterany/cli/doctor.py` (mod.) | Checagem de conectividade com o LanguageTool no `doctor` |
| `src/translaterany/stages/__init__.py` (mod.) | Registro das etapas e atualização de `DEFAULT_PIPELINE` |
| `src/translaterany/cli/report.py` (mod.) | Exibição das novas métricas de refinamento |

---

### Task 1: Configuração das etapas do M7

**Files:**
- Modify: `src/translaterany/config/schemas.py`
- Test: `tests/test_config_m7.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel`, `StagesConfig`.
- Produces: `TreatmentConsistencyConfig`, `AdaptConfig`, `OrthographyConfig`, `FinalReadthroughConfig` integrados ao `StagesConfig`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config_m7.py
"""Testes de configuração das etapas do M7."""

from translaterany.config import load_config_from_str


def test_m7_default_stage_configs() -> None:
    raw = """
    [library]
    path = "/tmp"
    """
    cfg = load_config_from_str(raw)
    assert cfg.stages.treatment_consistency.enabled is True
    assert cfg.stages.adapt.enabled is True
    assert cfg.stages.adapt.max_cps == 17.0
    assert cfg.stages.orthography.enabled is True
    assert cfg.stages.orthography.url == "http://localhost:8010/v2/check"
    assert cfg.stages.final_readthrough.enabled is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_m7.py -v`
Expected: FAIL (campos ausentes em `StagesConfig`).

- [ ] **Step 3: Write minimal implementation**

Atualizar `src/translaterany/config/schemas.py` com as classes `TreatmentConsistencyConfig`, `AdaptConfig`, `OrthographyConfig` e `FinalReadthroughConfig`, e adicioná-las a `StagesConfig`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_m7.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/config/schemas.py tests/test_config_m7.py
git commit -m "feat(config): adiciona configuracao das quatro etapas do M7"
```

---

### Task 2: Triagem e Etapa `treatment_consistency`

**Files:**
- Create: `src/translaterany/refine/treatment.py`, `src/translaterany/stages/treatment_consistency.py`
- Test: `tests/test_stage_treatment_consistency.py`

**Interfaces:**
- Consumes: `scene_analysis`, `characters.yaml`, `DialogueRefineStage` (ou `apply_edits`).
- Produces: `scan_treatment_consistency`, etapa `treatment_consistency`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_treatment_consistency.py
"""Testes da etapa treatment_consistency."""

from translaterany.refine.treatment import PairTreatment, scan_treatment_consistency


def test_scan_identifies_minority_pronoun() -> None:
    # 3 falas com 'você', 1 com 'tu' para o mesmo par com alta confiança
    lines = [
        {"id": "u1", "speaker": "Alice", "interlocutor": "Bob", "text": "Você viu isso?", "conf": 0.9},
        {"id": "u2", "speaker": "Alice", "interlocutor": "Bob", "text": "Você não sabe?", "conf": 0.9},
        {"id": "u3", "speaker": "Alice", "interlocutor": "Bob", "text": "Tu disseste a verdade?", "conf": 0.9},
        {"id": "u4", "speaker": "Alice", "interlocutor": "Bob", "text": "Você pode vir?", "conf": 0.9},
    ]
    report = scan_treatment_consistency(lines, character_gender={"Alice": "female", "Bob": "male"})
    pair = report.get(("Alice", "Bob"))
    assert pair is not None
    assert pair.canonical_pronoun == "voce"
    assert pair.divergent_ids == ["u3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_treatment_consistency.py -v`
Expected: FAIL (módulo `treatment` não existe).

- [ ] **Step 3: Write minimal implementation**

1. Implementar `src/translaterany/refine/treatment.py`:
   * Identificação de "você/tu/senhor" via regex.
   * Regra da maioria para o par `(speaker, interlocutor)`.
   * Detecção de concordância de gênero entre predicativos e o gênero de `characters.yaml`.
2. Implementar `src/translaterany/stages/treatment_consistency.py`:
   * Herda de `DialogueRefineStage` (ou estrutura similar com `apply_edits`).
   * Quando houver divergências, monta prompt para Gemma4 (papel `review`) solicitando a unificação da fala divergente.
   * Valida via `apply_edits`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_treatment_consistency.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/refine/treatment.py src/translaterany/stages/treatment_consistency.py tests/test_stage_treatment_consistency.py
git commit -m "feat(refine): implementa etapa treatment_consistency para coerencia pronominal e de genero"
```

---

### Task 3: Etapa `adapt` (Velocidade de Leitura / CPS)

**Files:**
- Create: `src/translaterany/stages/adapt.py`
- Test: `tests/test_stage_adapt.py`

**Interfaces:**
- Consumes: `DialogueRefineStage`, `CompositeUnit`, `apply_edits`, `max_cps`.
- Produces: etapa `adapt` que encurta falas com CPS > 17.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_adapt.py
"""Testes da etapa adapt."""

from translaterany.stages.adapt import identify_cps_exceeded


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_adapt.py -v`
Expected: FAIL (`identify_cps_exceeded` não existe).

- [ ] **Step 3: Write minimal implementation**

1. Implementar `identify_cps_exceeded` em `src/translaterany/stages/adapt.py`.
2. Implementar classe `AdaptStage`:
   * Seleciona apenas unidades com CPS > 17.
   * Se nenhuma unidade estourar, retorna com 0 chamadas.
   * Prompt com orçamento estrito de caracteres e proibição explícita de inventar ofensas ou mudar fatos ao resumir.
   * Validação com `apply_edits` exigindo redução de caracteres e preservação de sentido.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_adapt.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/adapt.py tests/test_stage_adapt.py
git commit -m "feat(refine): implementa etapa adapt para condensacao de falas com estouro de CPS"
```

---

### Task 4: Cliente LanguageTool e Filtros de Isenção

**Files:**
- Create: `src/translaterany/orthography/client.py`
- Test: `tests/test_languagetool_client.py`

**Interfaces:**
- Consumes: `httpx`, `glossary.yaml`, `characters.yaml`.
- Produces: `LanguageToolClient`, `check_text`, filtro de categorias (`TYPOS`, `CASING`, `GRAMMAR`) e descarte de termos isentos.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_languagetool_client.py
"""Testes do cliente LanguageTool."""

import respx
from httpx import Response
from translaterany.orthography.client import LanguageToolClient


@respx.mock
def test_languagetool_applies_typo_and_ignores_exemptions() -> None:
    client = LanguageToolClient(url="http://localhost:8010/v2/check", timeout_s=5.0)
    respx.post("http://localhost:8010/v2/check").mock(
        return_value=Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Possível erro de digitação",
                        "offset": 0,
                        "length": 5,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Você"}],
                    },
                    {
                        "message": "Palavra desconhecida",
                        "offset": 8,
                        "length": 6,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Outra"}],
                    },
                ]
            },
        )
    )
    # 'Shana' é nome isento
    text = "Vose e a Shana?"
    corrected, applied = client.correct_text(text, exemptions={"shana"})
    assert "Você" in corrected
    assert "Shana" in corrected  # não alterada
    assert applied == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_languagetool_client.py -v`
Expected: FAIL (`LanguageToolClient` não existe).

- [ ] **Step 3: Write minimal implementation**

1. Implementar `src/translaterany/orthography/client.py`:
   * Chamada HTTP `POST /v2/check`.
   * Filtragem de categorias: permite `TYPOS`, `CASING`, `GRAMMAR`; bloqueia `STYLE`, `COLLOQUIALISMS`.
   * Checagem contra termos isentos (`exemptions`).
   * Tratamento de falhas de conexão/timeout com `offline = True`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_languagetool_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/orthography/client.py tests/test_languagetool_client.py
git commit -m "feat(orthography): implementa cliente LanguageTool com filtro de regras e isencoes"
```

---

### Task 5: Etapa `orthography`

**Files:**
- Create: `src/translaterany/stages/orthography.py`
- Test: `tests/test_stage_orthography.py`

**Interfaces:**
- Consumes: `LanguageToolClient`, `UnitTexts`, `apply_edits`.
- Produces: etapa `orthography` (escopo `episode`, sem IA).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_orthography.py
"""Testes da etapa orthography."""

import respx
from httpx import Response
from translaterany.stages.orthography import OrthographyStage


@respx.mock
def test_orthography_stage_graceful_degradation_when_offline() -> None:
    # Simula servidor offline
    respx.post("http://localhost:8010/v2/check").mock(side_effect=Exception("Connection refused"))
    stage = OrthographyStage()
    # Execução não levanta exceção; repassa texto e registra offline no manifest
    outcome = stage.process_texts({"u1": "Texto normal"})
    assert outcome.texts["u1"] == "Texto normal"
    assert outcome.offline is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_orthography.py -v`
Expected: FAIL (`OrthographyStage` não existe).

- [ ] **Step 3: Write minimal implementation**

Implementar `src/translaterany/stages/orthography.py`:
* Carrega `glossary.yaml` e `characters.yaml` para construir a lista de isenções.
* Chama `LanguageToolClient` para cada fala.
* Aplica substituições seguras via `apply_edits` para certificar integridade de tags e sentido.
* Degradação graciosa em caso de serviço offline.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_orthography.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/orthography.py tests/test_stage_orthography.py
git commit -m "feat(stages): implementa etapa orthography com degradacao graciosa"
```

---

### Task 6: Etapa `final_readthrough` (Leitura Corrida Final)

**Files:**
- Create: `src/translaterany/stages/final_readthrough.py`
- Test: `tests/test_stage_final_readthrough.py`

**Interfaces:**
- Consumes: `DialogueRefineStage`, blocos por cena exclusivamente em PT-BR, `apply_edits`.
- Produces: etapa `final_readthrough`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_final_readthrough.py
"""Testes da etapa final_readthrough."""

from translaterany.stages.final_readthrough import render_readthrough_prompt


def test_prompt_contains_only_portuguese_and_speaker() -> None:
    lines = [
        {"id": "u1", "speaker": "Yuu", "text": "Eu vou conseguir passar na prova."},
        {"id": "u2", "speaker": "Nao", "text": "Tem certeza disso?"},
    ]
    prompt = render_readthrough_prompt(lines, scene_context="Sala de aula")
    assert "Eu vou conseguir passar na prova." in prompt
    assert "Yuu" in prompt
    assert "EN:" not in prompt  # sem texto em inglês no prompt de leitura corrida
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_final_readthrough.py -v`
Expected: FAIL (`render_readthrough_prompt` não existe).

- [ ] **Step 3: Write minimal implementation**

1. Implementar `render_readthrough_prompt` em `src/translaterany/stages/final_readthrough.py`.
2. Implementar `FinalReadthroughStage`:
   * Blocos por cena contendo apenas PT-BR e nomes de personagens.
   * Modelo no papel `review` respondendo com `edits: list[LineEdit]`.
   * Validação rígida com `apply_edits` contra o snapshot da fonte original em inglês.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_final_readthrough.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/final_readthrough.py tests/test_stage_final_readthrough.py
git commit -m "feat(refine): implementa etapa final_readthrough para leitura corrida em PT-BR"
```

---

### Task 7: Registro no Pipeline, CLI `doctor` e `report`

**Files:**
- Modify: `src/translaterany/stages/__init__.py`, `src/translaterany/cli/doctor.py`, `src/translaterany/cli/report.py`
- Test: `tests/test_doctor_m7.py`, `tests/test_report_m7.py`

**Interfaces:**
- Consumes: as 4 etapas novas, comandos CLI.
- Produces: `DEFAULT_PIPELINE` atualizado, checagem do LanguageTool no `doctor`, métricas do M7 no `report`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_doctor_m7.py
"""Testes do doctor com checagem de LanguageTool."""

from translaterany.cli.doctor import check_languagetool_service


def test_doctor_languagetool_check() -> None:
    res = check_languagetool_service("http://localhost:8010/v2/check")
    assert hasattr(res, "ok")
    assert hasattr(res, "message")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_doctor_m7.py -v`
Expected: FAIL (`check_languagetool_service` não existe).

- [ ] **Step 3: Write minimal implementation**

1. Em `src/translaterany/stages/__init__.py`, registrar `treatment_consistency`, `adapt`, `orthography` e `final_readthrough` no `DEFAULT_PIPELINE`.
2. Em `src/translaterany/cli/doctor.py`, adicionar verificação do LanguageTool.
3. Em `src/translaterany/cli/report.py`, exibir métricas do M7 (tratamento, adaptação, ortografia e leitura final).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_doctor_m7.py tests/test_report_m7.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/__init__.py src/translaterany/cli/doctor.py src/translaterany/cli/report.py tests/test_doctor_m7.py tests/test_report_m7.py
git commit -m "feat(pipeline): registra etapas do M7 no pipeline padrao, doctor e report"
```

---

### Task 8: Teste E2E do Pipeline M7

**Files:**
- Create: `tests/test_m7_pipeline.py`

**Interfaces:**
- Consumes: runner, `DEFAULT_PIPELINE`, `FakeLLM`, `respx`.
- Produces: validação ponta a ponta do episódio passando pelas 4 novas etapas até a entrega correta para `redistribute_sentences` e `write`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m7_pipeline.py
"""Teste ponta a ponta do pipeline com as etapas do M7."""

from translaterany.stages import DEFAULT_PIPELINE
from translaterany.config.loader import load_config
from pathlib import Path


def test_m7_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert (
        i("colloquial")
        < i("treatment_consistency")
        < i("adapt")
        < i("orthography")
        < i("final_readthrough")
        < i("redistribute_sentences")
    )


def test_redistribute_reads_final_readthrough(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert stages["redistribute_sentences"].dialogue_input == "final_readthrough"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_m7_pipeline.py -v`
Expected: FAIL (etapas não registradas na ordem esperada em `DEFAULT_PIPELINE`).

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_m7_pipeline.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_m7_pipeline.py
git commit -m "test(e2e): valida integracao ponta a ponta das quatro etapas do M7"
```
