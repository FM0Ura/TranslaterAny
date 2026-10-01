# M8 — Portões e laço do QA · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Concluir a versão 1.0 (v1) do TranslaterAny com controle de qualidade em duas camadas: portões por etapa (`StageGate`) com escalonamento local e laço de QA final (`QALoopStage`) com checagens exclusivas de ASS, rastreio de culpa (*blame*), cascata de reprocessamento focada na linha e persistência de `qa_report.json`.

**Architecture:** O `StageGate` atua nas etapas de IA (`translate_dialogue` e especializações de `DialogueRefineStage`), interceptando saídas e acionando escalonamento em caso de erros severos (`prompt_leak`, marcadores corrompidos, não traduzido, violação de glossário) com detecção de oscilação e regra "nunca piorar". A etapa `qa_loop` é inserida no pipeline após `redistribute_sentences` e antes de `quality_checks`, auditando tags ASS, integridade de eventos e executando reprocessamento em cascata apenas para as linhas com culpa identificada.

**Tech Stack:** Python 3.14 (`uv`), pydantic 2, pytest, Ollama / FakeLLM, pysubs2.

**Spec:** [`docs/superpowers/specs/2026-10-01-m8-portoes-qa-design.md`](../specs/2026-10-01-m8-portoes-qa-design.md)

## Global Constraints

- Python **3.14**; dependências existentes (`pydantic`, `pysubs2`, `httpx`).
- Identificadores/código em **inglês**; mensagens ao usuário, logs e instruções de prompt em **PT-BR**.
- Escalonamento no perfil local sem troca de modelo na GPU: nível 1 = feedback no prompt; nível 2 = redução para bloco unitário (`batch_size=1`).
- Critério estrito de "Nunca Piorar" determinístico via pontuação de severidade de achados.
- Testes **somente sintéticos** (`FakeLLM`); nunca versionar mídia nem legendas reais.
- Testes: `uv run pytest -q` na raiz. Suíte atual: 583 passando.
- Commits em português: `tipo(escopo): descrição`.

## Review Focus

1. **Garantia de término sob modelo adverso:** Se um modelo gerar erros severos continuamente, `StageGate` e `qa_loop` esgotam estritamente em `max_retries` / `max_rounds` / `max_extra_calls`, sem qualquer possibilidade de laço infinito. Testado na Tarefa 2 e 6.
2. **Critério "Nunca Piorar":** Uma retentativa que introduza novo erro severo (ex: quebrar marcador que estava são) é descartada em favor da versão com menor severidade. Testado na Tarefa 2.
3. **Detecção de Oscilação:** Se a saída do modelo retornar a um texto idêntico ao já visto no loop (mesmo hash sha256), o escalonamento para imediatamente. Testado na Tarefa 2.
4. **Precisão do Blame:** A identificação da etapa causadora no histórico de artefatos localiza a primeira etapa onde o defeito se manifestou, sem culpar etapas inocentes anteriores ou posteriores. Testado na Tarefa 5.
5. **Degradação graciosa quando desativado:** Se `gates.enabled = false` ou `stages.qa_loop.enabled = false`, o pipeline executa normalmente sem falhar. Testado na Tarefa 1 e 7.

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/translaterany/config/model.py` (mod.) | Configuração de `GatesConfig` e `QALoopOptions` em `AppConfig` |
| `src/translaterany/pipeline/gates.py` (novo) | Motor do portão `StageGate`, detecção de erros severos, escada de escalonamento e oscilação |
| `src/translaterany/stages/translate_dialogue.py` (mod.) | Integração de `StageGate` na geração inicial de diálogo |
| `src/translaterany/stages/refine_base.py` (mod.) | Integração de `StageGate` nas etapas de refinamento (`DialogueRefineStage`) |
| `src/translaterany/checks/final_qa.py` (novo) | Checagens exclusivas finais: sintaxe ASS, balanceamento de chaves, integridade de eventos e timing |
| `src/translaterany/quality/blame.py` (novo) | Algoritmo de atribuição de culpa retroativa inspecionando histórico de artefatos |
| `src/translaterany/stages/qa_loop.py` (novo) | Etapa `qa_loop`: auditoria final, blame, cascata focada na linha e persistência de `qa_report.json` |
| `src/translaterany/stages/__init__.py` (mod.) | Inserção de `qa_loop` em `DEFAULT_PIPELINE` e encadeamento |
| `src/translaterany/cli/report.py` (mod.) | Exibição do resumo de QA e aviso de modelo com taxa de edição excessiva |

---

### Task 1: Configuração dos Portões e do QA

**Files:**
- Modify: `src/translaterany/config/model.py`
- Test: `tests/test_config_m8.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel`, `AppConfig`.
- Produces: `GatesConfig`, `QALoopOptions` integrados ao modelo de configuração.

- [x] **Step 1: Write the failing test**

```python
# tests/test_config_m8.py
"""Testes de configuração do Marco 8 (Portões e QA Loop)."""

from translaterany.config import load_config_from_str


def test_m8_default_configs() -> None:
    raw = """
    [library]
    path = "/tmp"
    """
    cfg = load_config_from_str(raw)
    assert hasattr(cfg, "gates")
    assert cfg.gates.enabled is True
    assert cfg.gates.max_retries == 2
    qa_opt = cfg.stages.get("qa_loop")
    assert qa_opt is not None
    assert qa_opt.options["max_rounds"] == 2
    assert qa_opt.options["max_extra_calls"] == 30
    assert qa_opt.options["warn_edit_rate_threshold"] == 0.25
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config_m8.py -v`
Expected: FAIL (campos `gates` ou `qa_loop` ausentes).

- [x] **Step 3: Write minimal implementation**

Em `src/translaterany/config/model.py`:
1. Definir `class GatesConfig(BaseModel): enabled: bool = True; max_retries: int = 2`.
2. Adicionar `gates: GatesConfig = Field(default_factory=GatesConfig)` em `AppConfig`.
3. Adicionar valores padrão para `qa_loop` em `_STAGE_OPTION_DEFAULTS`:
   `"qa_loop": {"max_rounds": 2, "max_extra_calls": 30, "warn_edit_rate_threshold": 0.25}`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config_m8.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/translaterany/config/model.py tests/test_config_m8.py
git commit -m "feat(config): adiciona configuracao de gates e qa_loop para o M8"
```

---

### Task 2: Motor de Portão por Etapa (`StageGate`) e Escalonamento

**Files:**
- Create: `src/translaterany/pipeline/gates.py`
- Test: `tests/test_stage_gate.py`

**Interfaces:**
- Consumes: `CheckEnv`, `Finding`, `run_line_checks`.
- Produces: `StageGate`, `GateDecision`, `filter_blocking_findings`, `severity_score`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_stage_gate.py
"""Testes unitários do StageGate e escada de escalonamento."""

from translaterany.checks import CheckEnv, Finding
from translaterany.pipeline.gates import (
    BLOCKING_CHECKS,
    StageGate,
    filter_blocking_findings,
    severity_score,
)


def test_filter_blocking_findings() -> None:
    findings = [
        Finding(unit_id="u1", check="prompt_leak", message="instrução vazada", severity="error"),
        Finding(unit_id="u2", check="cps", message="leitura rápida", severity="warning"),
        Finding(unit_id="u3", check="markers_broken", message="tag perdida", severity="error"),
    ]
    blocking = filter_blocking_findings(findings)
    assert len(blocking) == 2
    assert {f.check for f in blocking} == {"prompt_leak", "markers_broken"}


def test_severity_score_comparison() -> None:
    f_clean: list[Finding] = []
    f_warning = [Finding(unit_id="u1", check="cps", message="aviso", severity="warning")]
    f_severe = [Finding(unit_id="u1", check="prompt_leak", message="erro", severity="error")]
    assert severity_score(f_clean) < severity_score(f_warning) < severity_score(f_severe)


def test_oscillation_detection() -> None:
    gate = StageGate(max_retries=2)
    assert gate.is_oscillating("u1", "Texto A") is False
    assert gate.is_oscillating("u1", "Texto B") is False
    assert gate.is_oscillating("u1", "Texto A") is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_gate.py -v`
Expected: FAIL (`translaterany.pipeline.gates` não existe).

- [x] **Step 3: Write minimal implementation**

Criar `src/translaterany/pipeline/gates.py`:
- `BLOCKING_CHECKS = frozenset({"prompt_leak", "markers_broken", "format_mismatch", "untranslated", "glossary_violation", "cpl_lines_exceeded"})`
- `filter_blocking_findings(findings: Sequence[Finding]) -> list[Finding]`
- `severity_score(findings: Sequence[Finding]) -> int` (error = 10, warning = 1)
- `class StageGate`: mantém `seen_hashes: dict[str, set[str]]` para oscilação, método `evaluate(lines, env)` e gerador de feedback pontual.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_gate.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/translaterany/pipeline/gates.py tests/test_stage_gate.py
git commit -m "feat(gates): implementa motor StageGate com deteccao de oscilacao e nunca piorar"
```

---

### Task 3: Checagens Exclusivas Finais do QA

**Files:**
- Create: `src/translaterany/checks/final_qa.py`
- Test: `tests/test_final_qa_checks.py`

**Interfaces:**
- Consumes: Linhas/Eventos ASS finais, `CheckEnv`.
- Produces: `check_ass_syntax`, `check_event_integrity`, `check_timing_bounds`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_final_qa_checks.py
"""Testes de checagens exclusivas do resultado final da legenda."""

from translaterany.checks.final_qa import (
    check_ass_syntax,
    check_event_integrity,
    check_timing_bounds,
)


def test_check_ass_syntax_unbalanced_braces() -> None:
    findings = check_ass_syntax("u1", r"{\pos(100,200)Texto sem fechar chave")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_double_linebreaks() -> None:
    findings = check_ass_syntax("u2", r"Primeira linha\N\NSegunda linha")
    assert any(f.check == "ass_syntax" for f in findings)


def test_check_ass_syntax_valid() -> None:
    findings = check_ass_syntax("u3", r"{\an8}Texto correto\Nsegunda linha.")
    assert len(findings) == 0


def test_check_timing_bounds_invalid() -> None:
    findings = check_timing_bounds("u1", start_ms=5000, end_ms=4000)
    assert any(f.check == "timing_bounds" for f in findings)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_final_qa_checks.py -v`
Expected: FAIL (`translaterany.checks.final_qa` não existe).

- [x] **Step 3: Write minimal implementation**

Criar `src/translaterany/checks/final_qa.py`:
- `check_ass_syntax(unit_id: str, text: str) -> list[Finding]`: valida balanceamento de `{` e `}`, detecção de `\N\N`, validação de comandos ASS básicos.
- `check_timing_bounds(unit_id: str, start_ms: int, end_ms: int) -> list[Finding]`: assegura `start_ms < end_ms` e duração mínima > 0.
- `check_event_integrity(expected_count: int, actual_count: int) -> list[Finding]`: compara quantidade de falas para alertar se houver perda.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_final_qa_checks.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/translaterany/checks/final_qa.py tests/test_final_qa_checks.py
git commit -m "feat(checks): implementa checagens exclusivas finais de sintaxe ASS e timing"
```

---

### Task 4: Integração do `StageGate` em `translate_dialogue` e `DialogueRefineStage`

**Files:**
- Modify: `src/translaterany/stages/translate_dialogue.py`
- Modify: `src/translaterany/stages/refine_base.py`
- Test: `tests/test_stage_gate_integration.py`

**Interfaces:**
- Consumes: `StageGate`, `AppConfig.gates`.
- Produces: `translate_dialogue` e etapas de refinamento executando retentativas sob erro severo.

- [x] **Step 1: Write the failing test**

```python
# tests/test_stage_gate_integration.py
"""Testes de integracao do StageGate nas etapas com IA."""

from translaterany.llm.client import FakeLLM
from translaterany.pipeline.gates import StageGate
from translaterany.stages.refine_base import apply_edits_with_gate
from translaterany.refine.edits import LineEdit


def test_apply_edits_with_gate_rejects_severe_degradation() -> None:
    # Edição tenta introduzir um prompt_leak
    original = {"u1": "Olá mundo."}
    edits = [LineEdit(id="u1", text="máx. 10 caracteres Olá mundo.")]
    result = apply_edits_with_gate(original, edits, gate=StageGate())
    # O portão deve barrar a piora e manter a versão limpa original
    assert result["u1"] == "Olá mundo."
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_gate_integration.py -v`
Expected: FAIL (`apply_edits_with_gate` não existe).

- [x] **Step 3: Write minimal implementation**

1. Em `src/translaterany/stages/refine_base.py`, adicionar suporte a `StageGate` em `apply_edits_with_gate` para filtrar edições que introduzam achados bloqueantes.
2. Em `src/translaterany/stages/translate_dialogue.py`, integrar o portão ao final da tradução para re-tentar falas unitárias com feedback antes de entregar o `UnitTexts`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_gate_integration.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/translaterany/stages/refine_base.py src/translaterany/stages/translate_dialogue.py tests/test_stage_gate_integration.py
git commit -m "feat(stages): integra StageGate em translate_dialogue e etapas de refinamento"
```

---

### Task 5: Algoritmo de Atribuição de Culpa (*Blame*)

**Files:**
- Create: `src/translaterany/quality/blame.py`
- Test: `tests/test_blame.py`

**Interfaces:**
- Consumes: Histórico cronológico de instantâneos `(stage_name, dict[unit_id, text])`, `Finding`.
- Produces: `attribute_blame(unit_id: str, finding: Finding, history: Sequence[tuple[str, Mapping[str, str]]]) -> str`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_blame.py
"""Testes de atribuicao de culpa (blame) a partir do historico de artefatos."""

from translaterany.checks import Finding
from translaterany.quality.blame import attribute_blame


def test_attribute_blame_finds_origin_stage() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto perfeito."}),
        ("review_meaning", {"u1": "Texto perfeito."}),
        ("colloquial", {"u1": "máx. 20 Texto perfeito."}),  # Defeito surgiu aqui
        ("adapt", {"u1": "máx. 20 Texto perfeito."}),
    ]
    finding = Finding(unit_id="u1", check="prompt_leak", message="vazamento", severity="error")
    blamed = attribute_blame("u1", finding, history)
    assert blamed == "colloquial"
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_blame.py -v`
Expected: FAIL (`translaterany.quality.blame` não existe).

- [x] **Step 3: Write minimal implementation**

Criar `src/translaterany/quality/blame.py`:
- Função `attribute_blame`: percorre a lista de snapshots do mais antigo para o mais novo. Avalia a checagem do finding em cada versão do texto. A primeira etapa em que a checagem falhar é retornada como a causadora. Se não falhar em nenhuma etapa intermediária (ex: defeito exclusivo de redistribuição/timing), retorna a última etapa (`redistribute_sentences`).

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_blame.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/translaterany/quality/blame.py tests/test_blame.py
git commit -m "feat(quality): implementa algoritmo de blame retroativo para o QA"
```

---

### Task 6: Etapa `QALoopStage` e Relatório `qa_report.json`

**Files:**
- Create: `src/translaterany/stages/qa_loop.py`
- Test: `tests/test_stage_qa_loop.py`

**Interfaces:**
- Consumes: Artefatos do episódio, `DEFAULT_PIPELINE`, `StageContext`.
- Produces: `qa_report.json`, diálogo corrigido entregue a `quality_checks`.

- [x] **Step 1: Write the failing test**

```python
# tests/test_stage_qa_loop.py
"""Testes da etapa QALoopStage."""

from translaterany.stages.qa_loop import QALoopStage, QAReport
from translaterany.checks import Finding


def test_qa_report_serialization() -> None:
    report = QAReport(
        rounds_executed=1,
        extra_calls_used=2,
        blame_summary={"colloquial": 1},
        interventions=[{"unit_id": "u1", "blamed_stage": "colloquial", "outcome": "fixed"}],
        edit_rate=0.05,
    )
    data = report.to_dict()
    assert data["rounds_executed"] == 1
    assert data["blame_summary"]["colloquial"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_qa_loop.py -v`
Expected: FAIL (`translaterany.stages.qa_loop` não existe).

- [x] **Step 3: Write minimal implementation**

Criar `src/translaterany/stages/qa_loop.py`:
- `class QAReport`: modelo de dados com serialização para JSON.
- `class QALoopStage(Stage)`:
  - `name = "qa_loop"`, `produces_dialogue = True`.
  - Executa até `max_rounds`.
  - Audita o texto pós-redistribuição usando `check_ass_syntax`, `check_timing_bounds` e checagens severas de `run_line_checks`.
  - Para cada falha: atribui *blame*, reexecuta a linha pontual com feedback, passa pelas etapas posteriores ativas e revalida.
  - Grava `qa_report.json` no store do episódio.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_qa_loop.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/translaterany/stages/qa_loop.py tests/test_stage_qa_loop.py
git commit -m "feat(stages): implementa etapa qa_loop com reprocessamento e qa_report.json"
```

---

### Task 7: Encaixe no Pipeline, Doctor e Report

**Files:**
- Modify: `src/translaterany/stages/__init__.py`
- Modify: `src/translaterany/cli/report.py`
- Test: `tests/test_report_m8.py`

**Interfaces:**
- Consumes: `QALoopStage`, `AppConfig`.
- Produces: Pipeline padrão contendo `qa_loop`, comando `report` exibindo resumo de QA e aviso de modelo.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_report_m8.py
"""Testes de exibição do QA no comando report."""

from translaterany.cli.report import format_qa_summary
from translaterany.stages.qa_loop import QAReport


def test_format_qa_summary_with_warning() -> None:
    rep = QAReport(
        rounds_executed=1,
        extra_calls_used=4,
        blame_summary={"translate_dialogue": 3},
        interventions=[],
        edit_rate=0.30,  # 30% > limiar de 25%
    )
    output = format_qa_summary(rep, threshold=0.25)
    assert "Taxa de edição alta" in output
    assert "translate_dialogue: 3" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_report_m8.py -v`
Expected: FAIL (`format_qa_summary` não existe).

- [ ] **Step 3: Write minimal implementation**

1. Em `src/translaterany/stages/__init__.py`:
   - Registrar `QALoopStage` no `DEFAULT_PIPELINE` entre `redistribute_sentences` e `quality_checks`.
   - Atualizar a amarração dinâmica de etapas.
2. Em `src/translaterany/cli/report.py`:
   - Adicionar `format_qa_summary` e exibir a seção de QA quando `qa_report.json` estiver presente.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_report_m8.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/__init__.py src/translaterany/cli/report.py tests/test_report_m8.py
git commit -m "feat(pipeline): registra qa_loop no pipeline padrao e adiciona secao no report"
```

---

### Task 8: Teste de Integração Ponta a Ponta do M8

**Files:**
- Create: `tests/test_m8_pipeline.py`

**Interfaces:**
- Consumes: Runner completo, `DEFAULT_PIPELINE`, `FakeLLM`.
- Produces: Validação E2E com simulação de erro sanado pelo QA loop e gravação do `.pt-BR.ass` e `qa_report.json`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m8_pipeline.py
"""Teste ponta a ponta do pipeline com StageGate e QALoopStage."""

from translaterany.stages import DEFAULT_PIPELINE
from translaterany.config.loader import load_config
from pathlib import Path


def test_m8_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert (
        i("final_readthrough")
        < i("redistribute_sentences")
        < i("qa_loop")
        < i("quality_checks")
        < i("write")
    )


def test_qa_loop_in_default_config(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert "qa_loop" in stages
    assert stages["quality_checks"].inputs is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_m8_pipeline.py -v`
Expected: FAIL (ordem em `DEFAULT_PIPELINE` sem `qa_loop`).

- [ ] **Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_m8_pipeline.py -v`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_m8_pipeline.py
git commit -m "test(e2e): valida integracao ponta a ponta do pipeline M8 com QA Loop"
```
