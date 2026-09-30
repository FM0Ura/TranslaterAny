# M6 — Refinamento I · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** revisão de sentido (todas as falas) e coloquialidade (falas triadas) com resposta só com edições, validadas localmente, antes da redistribuição.

**Architecture:** pacote puro `translaterany.refine` (edições, triagem, blocos por cena) + uma base de etapa `DialogueRefineStage` com duas subclasses (`review_meaning`, `colloquial`) que recebem o mapa de diálogo da etapa anterior e devolvem o mapa completo editado. `redistribute_sentences` passa a ler a última etapa com `produces_dialogue`. Nova checagem `profanity_added` no pacote `checks`.

**Tech Stack:** Python 3.14 (`uv`), pydantic 2, pytest, Ollama (Gemma4 no papel `review`) via `LLMClient`.

**Spec:** [`docs/superpowers/specs/2026-09-30-m6-refinamento-i-design.md`](../specs/2026-09-30-m6-refinamento-i-design.md)

## Global Constraints

- Python **3.14**; nenhuma dependência nova.
- Identificadores/código em **inglês**; mensagens ao usuário, logs e instruções de prompt em **PT-BR**.
- Modelo das etapas novas: apelido **`review`** (Gemma4 no perfil `local`); tradução continua em `translate` (TranslateGemma).
- `max_lines_per_block = 30` (padrão das duas etapas).
- Checagens de sentido usadas na validação "piora": `markers`, `numbers`, `negation`, `names`, `glossary`, `profanity_added`.
- Motivos de rejeição, exatamente: `unknown_id`, `empty`, `unchanged`, `markers`, `reversal`, `worse`.
- Contadores, exatamente: `lines_read`, `lines_targeted`, `blocks`, `blocks_failed`, `edits_proposed`, `edits_applied`, `rejected_<motivo>`, `reversals` (só `colloquial`).
- Uma falha de bloco nunca derruba o episódio: o bloco passa sem mudanças e `blocks_failed` sobe.
- Testes **somente sintéticos** (`FakeLLM`); nunca versionar mídia nem trechos de legendas reais.
- O repositório tem 38 erros antigos de `ruff`; critério: nenhum erro novo nos arquivos tocados (`uv run ruff check <arquivos>`).
- Testes: `uv run pytest -q` na raiz. Suíte atual: 510 passando.
- Commits em português `tipo(escopo): descrição`, terminando com:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_016JxmXtx9vC6M6DTzHoujm8
  ```

## Review Focus

1. **Modelo edita uma fala que era só contexto** (na `colloquial`, falas não triadas vão como contexto) — a edição é rejeitada como `unknown_id`, nunca aplicada. Teste na Tarefa 7.
2. **Mapa de diálogo misto**: ids compostos (`u2+u3`) junto com ids simples resolvidos pela TM que não estão em nenhum composto — todos precisam de cena, fonte EN e orçamento. Teste na Tarefa 2.
3. **Episódio sem diálogo a revisar** (tudo resolvido pela TM ou sem diálogo) — a etapa grava o mapa de entrada inalterado sem chamar o modelo. Teste na Tarefa 6.
4. **Config desliga `review_meaning` e/ou `colloquial`** — `redistribute_sentences` passa a ler `translate_dialogue` (ou a que sobrar) e o pipeline carrega sem erro. Teste na Tarefa 8.
5. **Edição que devolve a fala ao inglês original** (o modelo "desiste" de traduzir) — rejeitada como `worse` por regra explícita (texto igual à fonte EN, normalizado), já que `untranslated` não está entre as checagens de "piora". Teste na Tarefa 3.

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/translaterany/checks/lexicon.py` (mod.) | léxicos de palavrões PT/EN |
| `src/translaterany/checks/rules_context.py` (mod.) | checagem `profanity_added` |
| `src/translaterany/subtitles/scenes.py` (novo) | cena de cada fala (`scene_index_of`) e grupos (`group_by_scene`) |
| `src/translaterany/subtitles/scene_analysis.py` (mod.) | usa `subtitles/scenes.py` |
| `src/translaterany/memory/matching.py` (mod.) | `load_memory_for_text` (compartilhado) |
| `src/translaterany/stages/quality_checks.py` (mod.) | usa `load_memory_for_text` |
| `src/translaterany/refine/__init__.py` (novo) | API do pacote |
| `src/translaterany/refine/edits.py` (novo) | `LineEdit`, `EditsResponse`, `apply_edits` |
| `src/translaterany/refine/lexicon.py` (novo) | padrões de texto duro/literal |
| `src/translaterany/refine/triage.py` (novo) | `meaning_signals`, `colloquial_signals` |
| `src/translaterany/refine/blocks.py` (novo) | `ReviewLine`, `build_blocks`, `render_block_prompt` |
| `src/translaterany/pipeline/stage.py` (mod.) | `produces_dialogue` |
| `src/translaterany/stages/translate_dialogue.py` (mod.) | `produces_dialogue = True` |
| `src/translaterany/stages/refine_base.py` (novo) | `DialogueRefineStage` (base comum) |
| `src/translaterany/stages/review_meaning.py` (novo) | etapa `review_meaning` |
| `src/translaterany/stages/colloquial.py` (novo) | etapa `colloquial` |
| `src/translaterany/stages/redistribute_sentences.py` (mod.) | entrada de diálogo via `bind_pipeline` |
| `src/translaterany/stages/__init__.py` (mod.) | registro + `DEFAULT_PIPELINE` |

---

### Task 1: Checagem `profanity_added`

**Files:**
- Modify: `src/translaterany/checks/lexicon.py`, `src/translaterany/checks/rules_context.py`
- Test: `tests/test_check_profanity.py`

**Interfaces:**
- Consumes: `line_check`, `LineInput`, `CheckEnv`, `Finding`, `plain` (pacote `checks`).
- Produces: checagem registrada `profanity_added` (tipos `{"dialogue"}`, severidade `warn`); `lexicon.PT_PROFANITY`, `lexicon.EN_PROFANITY` (regex compiladas).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_profanity.py
"""Checagem profanity_added (M6)."""

from translaterany.checks import CheckEnv, LineInput, check_names, run_line_checks


def found(src: str, tgt: str, kind: str = "dialogue") -> list:
    line = LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=3000)
    return [f for f in run_line_checks([line], CheckEnv()) if f.check == "profanity_added"]


def test_flags_profanity_absent_in_source() -> None:
    hits = found("You've been using it to cheat on all your tests.", "Você colou em tudo, seu merda.")
    assert len(hits) == 1 and hits[0].severity == "warn" and "merda" in hits[0].message


def test_accepts_profanity_present_in_source() -> None:
    assert not found("Damn it!", "Droga, porra!")
    assert not found("You idiot!", "Seu idiota!")


def test_clean_lines_and_other_types_are_ignored() -> None:
    assert not found("Great!", "Ótimo!")
    assert found("Hello", "Olá, cacete", kind="sign") == []  # placas não são checadas


def test_word_boundaries() -> None:
    assert not found("Classic", "Clássico")  # "ass" não casa dentro de "Classic"
    assert not found("Hello there", "Olá")  # "hell" não casa dentro de "Hello"


def test_registered() -> None:
    assert "profanity_added" in check_names()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_check_profanity.py -v`
Expected: FAIL (nenhum achado `profanity_added`; `test_registered` falha).

- [ ] **Step 3: Write minimal implementation**

Acrescente a `src/translaterany/checks/lexicon.py`:

```python
PT_PROFANITY = re.compile(
    r"\b(?:merda|porra|caralho|puta|puto|foda|foder|fodido|fodida|cacete|desgraça|desgraçado|desgraçada|"
    r"arrombado|arrombada|babaca|idiota|imbecil|otário|otária|vadia|cuzão)\b",
    re.IGNORECASE,
)
EN_PROFANITY = re.compile(
    r"\b(?:shit|fuck\w*|damn\w*|bitch\w*|bastard\w*|ass|asshole|crap|idiot\w*|moron\w*|jerk\w*|hell|"
    r"dumbass|screw\w*|piss\w*|dick\w*|stupid)\b",
    re.IGNORECASE,
)
```

Acrescente a `src/translaterany/checks/rules_context.py`:

```python
@line_check("profanity_added", {"dialogue"})
def profanity_added(line: LineInput, env: CheckEnv) -> list[Finding]:
    if lexicon.EN_PROFANITY.search(plain(line.source)):
        return []
    match = lexicon.PT_PROFANITY.search(plain(line.target))
    if not match:
        return []
    return [
        Finding(
            check="profanity_added",
            unit_id=line.id,
            severity="warn",
            message=f"palavrão sem equivalente no original: '{match.group(0)}'",
        )
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_check_profanity.py tests/test_checks_basic.py tests/test_checks_context.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/checks tests/test_check_profanity.py
git add src/translaterany/checks tests/test_check_profanity.py
git commit -m "feat(checks): adiciona checagem profanity_added"
```

---

### Task 2: Cenas compartilhadas e memória por texto

**Files:**
- Create: `src/translaterany/subtitles/scenes.py`
- Modify: `src/translaterany/subtitles/scene_analysis.py` (remover `_scene_groups`, usar o novo módulo), `src/translaterany/memory/matching.py`, `src/translaterany/stages/quality_checks.py` (`_memory` passa a usar `load_memory_for_text`)
- Test: `tests/test_scenes_shared.py`

**Interfaces:**
- Consumes: `Scene` (`subtitles/classify.py`), `MergedUnitsDoc`, `MemoryStore`, `select_for_text`.
- Produces:
  - `scene_index_of(ids: Iterable[str], members: Mapping[str, list[str]], unit_events: Mapping[str, list[int]], scenes: Sequence[Scene]) -> dict[str, int]` — para cada id (composto ou simples), o índice da cena do 1º evento da 1ª unidade; sem cena → `len(scenes)`.
  - `group_by_scene(ids: Sequence[str], scene_of: Mapping[str, int], max_lines: int) -> list[list[str]]` — mantém a ordem de `ids` dentro de cada cena, cenas em ordem crescente, fatias de até `max_lines`.
  - `load_memory_for_text(store: ArtifactStore | None, series_key: str, text: str) -> tuple[list[GlossaryEntry], list[CharacterEntry]]` em `memory/matching.py` (vazio sem store ou sem pasta `memory/`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scenes_shared.py
"""Agrupamento por cena compartilhado (M6) e memória por texto."""

from pathlib import Path

from translaterany.memory.matching import load_memory_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.scenes import group_by_scene, scene_index_of

SCENES = [Scene(id="s1", start_ms=0, end_ms=1, events=[0, 1, 2]), Scene(id="s2", start_ms=2, end_ms=3, events=[3])]
EVENTS = {"u1": [0], "u2": [1], "u3": [2], "u4": [3], "u5": [9]}


def test_scene_index_handles_composites_and_plain_ids() -> None:
    members = {"u2+u3": ["u2", "u3"]}
    got = scene_index_of(["u1", "u2+u3", "u4", "u5", "u9"], members, EVENTS, SCENES)
    assert got == {"u1": 0, "u2+u3": 0, "u4": 1, "u5": 2, "u9": 2}  # u5 fora de cena; u9 sem evento


def test_group_by_scene_keeps_order_and_slices() -> None:
    scene_of = {"u1": 0, "u2+u3": 0, "u4": 1, "u5": 2}
    assert group_by_scene(["u1", "u2+u3", "u4", "u5"], scene_of, 30) == [["u1", "u2+u3"], ["u4"], ["u5"]]
    assert group_by_scene(["u1", "u2+u3", "u4"], scene_of, 1) == [["u1"], ["u2+u3"], ["u4"]]


def test_load_memory_for_text(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    assert load_memory_for_text(None, "s", "x") == ([], [])
    assert load_memory_for_text(store, "s", "x") == ([], [])
    mem = MemoryStore(store.series_dir("s") / "memory")
    mem.save_glossary([GlossaryEntry(term="Ability", translation="Habilidade")])
    mem.save_characters([CharacterEntry(name="Yu"), CharacterEntry(name="Nao")])
    glossary, chars = load_memory_for_text(store, "s", "Yu used an Ability")
    assert [g.term for g in glossary] == ["Ability"] and [c.name for c in chars] == ["Yu"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scenes_shared.py -v`
Expected: FAIL (`ModuleNotFoundError: translaterany.subtitles.scenes`).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/subtitles/scenes.py`:

```python
"""Cena de cada fala (por id simples ou composto) e agrupamento por cena para chamadas de IA."""

from collections.abc import Iterable, Mapping, Sequence

from translaterany.subtitles.classify import Scene


def scene_index_of(
    ids: Iterable[str],
    members: Mapping[str, list[str]],
    unit_events: Mapping[str, list[int]],
    scenes: Sequence[Scene],
) -> dict[str, int]:
    """Índice da cena do 1º evento da 1ª unidade de cada id; sem cena (ou sem evento) -> len(scenes)."""
    scene_of_event = {ev: i for i, sc in enumerate(scenes) for ev in sc.events}
    result: dict[str, int] = {}
    for item in ids:
        units = members.get(item, [item])
        events = unit_events.get(units[0], []) if units else []
        result[item] = scene_of_event.get(events[0], len(scenes)) if events else len(scenes)
    return result


def group_by_scene(ids: Sequence[str], scene_of: Mapping[str, int], max_lines: int) -> list[list[str]]:
    by_scene: dict[int, list[str]] = {}
    for item in ids:
        by_scene.setdefault(scene_of.get(item, 1 << 30), []).append(item)
    step = max(1, max_lines)
    return [group[i : i + step] for _, group in sorted(by_scene.items()) for i in range(0, len(group), step)]
```

Em `src/translaterany/subtitles/scene_analysis.py`, apague `_scene_groups` e troque o laço de `analyze_scenes` por:

```python
    by_id = {u.composite_id: u for u in merged_doc.units}
    members = {u.composite_id: list(u.unit_ids) for u in merged_doc.units}
    ids = [u.composite_id for u in merged_doc.units]
    scene_of = scene_index_of(ids, members, unit_events or {}, scenes)
    for id_group in group_by_scene(ids, scene_of, max_lines_per_call):
        group = [by_id[i] for i in id_group]
        parsed = _analyze_group(group, char_list, synopsis, client, model)
        for k, v in parsed.lines.items():
            if k in final_lines and k in id_group:
                final_lines[k] = v
```

(importe `from translaterany.subtitles.scenes import group_by_scene, scene_index_of`; remova imports que ficarem sem uso.)

Em `src/translaterany/memory/matching.py` acrescente:

```python
def load_memory_for_text(
    store: "ArtifactStore | None", series_key: str, text: str
) -> tuple[list[GlossaryEntry], list[CharacterEntry]]:
    """Glossário e personagens da série mencionados no texto (filtro por episódio)."""
    if store is None:
        return [], []
    mem_dir = store.series_dir(series_key) / "memory"
    if not mem_dir.exists():
        return [], []
    from translaterany.memory.store import MemoryStore  # import tardio: evita ciclo memory <-> pipeline

    mem = MemoryStore(mem_dir)
    return select_for_text(mem.load_glossary().values(), mem.load_characters(), text)
```

(com `from typing import TYPE_CHECKING` e `if TYPE_CHECKING: from translaterany.pipeline.artifacts import ArtifactStore`.)

Em `src/translaterany/stages/quality_checks.py`, o corpo de `_memory` vira:

```python
        return load_memory_for_text(ctx.store, ctx.series.key, text)
```

(importe `load_memory_for_text`; remova `MemoryStore`/`select_for_text` se ficarem sem uso.)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_scenes_shared.py tests/test_scene_analysis.py tests/test_alignment_and_scenes.py tests/test_quality_checks_stage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/subtitles/scenes.py src/translaterany/subtitles/scene_analysis.py src/translaterany/memory/matching.py src/translaterany/stages/quality_checks.py tests/test_scenes_shared.py
git add src/translaterany/subtitles src/translaterany/memory/matching.py src/translaterany/stages/quality_checks.py tests/test_scenes_shared.py
git commit -m "refactor(subtitles): agrupamento por cena e memória por texto compartilhados"
```

---

### Task 3: Protocolo de edições (`refine/edits.py`)

**Files:**
- Create: `src/translaterany/refine/__init__.py`, `src/translaterany/refine/edits.py`
- Test: `tests/test_refine_edits.py`

**Interfaces:**
- Consumes: `LineSource` (`checks/snapshots.py`), `LineInput`, `CheckEnv`, `run_line_checks`, `marker_ids`, `plain`.
- Produces:
  - `LineEdit(id: str, new: str, reason: str = "")`, `EditsResponse(edits: list[LineEdit] = [])`
  - `type RejectReason = Literal["unknown_id", "empty", "unchanged", "markers", "reversal", "worse"]`
  - `REJECT_REASONS: tuple[RejectReason, ...]` (na ordem acima)
  - `WORSE_CHECKS = frozenset({"markers", "numbers", "negation", "names", "glossary", "profanity_added"})`
  - `@dataclass EditOutcome(texts: dict[str, str], applied: dict[str, str], rejected: dict[str, int])`
  - `apply_edits(texts, edits, targets, sources, env, forbidden=None) -> EditOutcome`
  - `normalize_edit_id(raw: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_refine_edits.py
"""Protocolo de edições do M6: validação fala a fala."""

from translaterany.checks import CheckEnv
from translaterany.checks.snapshots import LineSource
from translaterany.refine.edits import LineEdit, apply_edits

SOURCES = {
    "u1": LineSource("I don't know.", "dialogue", "Default", 2000),
    "u2": LineSource("To the ⟦1⟧old⟦2⟧ station.", "dialogue", "Default", 2000),
    "u3": LineSource("You cheated on all your tests.", "dialogue", "Default", 2000),
}
TEXTS = {"u1": "Eu não sei.", "u2": "Para a ⟦1⟧velha⟦2⟧ estação.", "u3": "Você colou em tudo, seu merda."}
ENV = CheckEnv()


def run(*edits: LineEdit, targets=frozenset(SOURCES), forbidden=None):
    return apply_edits(TEXTS, edits, set(targets), SOURCES, ENV, forbidden=forbidden)


def test_valid_edit_is_applied_and_map_stays_complete() -> None:
    out = run(LineEdit(id="[u3]", new="Você colou em todas as provas."))
    assert out.applied == {"u3": "Você colou em todas as provas."}
    assert out.texts == {**TEXTS, "u3": "Você colou em todas as provas."}
    assert sum(out.rejected.values()) == 0


def test_rejection_reasons() -> None:
    out = run(
        LineEdit(id="u9", new="x"),  # unknown_id
        LineEdit(id="u1", new="  "),  # empty
        LineEdit(id="u2", new="Para a ⟦1⟧velha⟦2⟧ estação."),  # unchanged
        LineEdit(id="u2", new="Para a velha estação."),  # markers (a última edição de u2 vale)
    )
    assert out.rejected == {"unknown_id": 1, "empty": 1, "unchanged": 0, "markers": 1, "reversal": 0, "worse": 0}
    assert out.applied == {}


def test_edit_outside_targets_is_unknown() -> None:
    out = run(LineEdit(id="u1", new="Não sei."), targets={"u3"})
    assert out.rejected["unknown_id"] == 1 and out.applied == {}


def test_worse_negation_and_profanity_are_rejected() -> None:
    out = run(LineEdit(id="u1", new="Eu sei."), LineEdit(id="u3", new="Colou, porra."))
    assert out.rejected["worse"] == 2 and out.applied == {}


def test_edit_back_to_english_is_worse() -> None:
    out = run(LineEdit(id="u1", new="I don't know."))
    assert out.rejected["worse"] == 1


def test_reversal_is_rejected() -> None:
    texts = {**TEXTS, "u3": "Você colou em todas as provas."}
    out = apply_edits(texts, [LineEdit(id="u3", new="Você colou em tudo, seu  merda.")], {"u3"}, SOURCES, ENV,
                      forbidden={"u3": "Você colou em tudo, seu merda."})  # fmt: skip
    assert out.rejected["reversal"] == 1 and out.applied == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refine_edits.py -v`
Expected: FAIL (`ModuleNotFoundError: translaterany.refine`).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/refine/__init__.py`:

```python
"""Refinamento (M6): protocolo de edições, triagem por regras e blocos de revisão por cena."""
```

`src/translaterany/refine/edits.py`:

```python
"""Protocolo "só edições": o modelo devolve {id, new, reason}; cada edição é validada antes de aplicar."""

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from translaterany.checks import CheckEnv, LineInput, run_line_checks
from translaterany.checks.snapshots import LineSource
from translaterany.checks.text import plain
from translaterany.subtitles.segments import marker_ids

type RejectReason = Literal["unknown_id", "empty", "unchanged", "markers", "reversal", "worse"]
REJECT_REASONS: tuple[RejectReason, ...] = ("unknown_id", "empty", "unchanged", "markers", "reversal", "worse")
WORSE_CHECKS = frozenset({"markers", "numbers", "negation", "names", "glossary", "profanity_added"})
_SPACES = re.compile(r"\s+")


class LineEdit(BaseModel):
    id: str
    new: str
    reason: str = ""


class EditsResponse(BaseModel):
    edits: list[LineEdit] = Field(default_factory=list)


@dataclass
class EditOutcome:
    texts: dict[str, str]
    applied: dict[str, str] = field(default_factory=dict)
    rejected: dict[str, int] = field(default_factory=lambda: dict.fromkeys(REJECT_REASONS, 0))


def normalize_edit_id(raw: str) -> str:
    return raw.strip().strip("[]").strip()


def _norm(text: str) -> str:
    return _SPACES.sub(" ", text).strip()


def _meaning_findings(item: str, text: str, src: LineSource, env: CheckEnv) -> set[str]:
    line = LineInput(id=item, line_type=src.line_type, style=src.style, source=src.source, target=text,
                     duration_ms=src.duration_ms, composite=src.composite)  # fmt: skip
    return {f.check for f in run_line_checks([line], env) if f.check in WORSE_CHECKS}


def apply_edits(
    texts: Mapping[str, str],
    edits: Iterable[LineEdit],
    targets: set[str],
    sources: Mapping[str, LineSource],
    env: CheckEnv,
    forbidden: Mapping[str, str] | None = None,
) -> EditOutcome:
    outcome = EditOutcome(texts=dict(texts))
    latest: dict[str, str] = {}
    unknown = 0
    for edit in edits:
        item = normalize_edit_id(edit.id)
        if item not in targets or item not in texts or item not in sources:
            unknown += 1
            continue
        latest[item] = edit.new
    outcome.rejected["unknown_id"] = unknown
    for item, new in latest.items():
        current, src = texts[item], sources[item]
        reason: RejectReason | None = None
        if not new.strip():
            reason = "empty"
        elif _norm(new) == _norm(current):
            reason = "unchanged"
        elif Counter(marker_ids(new)) != Counter(marker_ids(src.source)):
            reason = "markers"
        elif forbidden and item in forbidden and _norm(new) == _norm(forbidden[item]):
            reason = "reversal"
        elif _norm(plain(new)).casefold() == _norm(plain(src.source)).casefold() or (
            _meaning_findings(item, new, src, env) - _meaning_findings(item, current, src, env)
        ):
            reason = "worse"
        if reason is not None:
            outcome.rejected[reason] += 1
            continue
        outcome.texts[item] = new
        outcome.applied[item] = new
    return outcome
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_refine_edits.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/refine tests/test_refine_edits.py
git add src/translaterany/refine tests/test_refine_edits.py
git commit -m "feat(refine): adiciona protocolo de edições validadas fala a fala"
```

---

### Task 4: Triagem (`refine/lexicon.py`, `refine/triage.py`)

**Files:**
- Create: `src/translaterany/refine/lexicon.py`, `src/translaterany/refine/triage.py`
- Test: `tests/test_refine_triage.py`

**Interfaces:**
- Consumes: `LineInput`, `CheckEnv`, `run_line_checks`, `plain`.
- Produces:
  - `MEANING_SIGNALS = frozenset({"negation", "numbers", "names", "glossary", "length_ratio", "untranslated", "profanity_added"})`
  - `meaning_signals(lines: Sequence[LineInput], env: CheckEnv) -> dict[str, list[str]]` (só ids com sinal; nomes em ordem alfabética, sem repetição)
  - `colloquial_signals(lines: Sequence[LineInput], speaker_of: Mapping[str, str], speakers_with_style: set[str]) -> dict[str, list[str]]` com sinais `formal_connective`, `enclisis`, `redundant_subject`, `archaic_pronoun`, `too_long`, `speech_style`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_refine_triage.py
"""Triagem por regras do M6."""

from translaterany.checks import CheckEnv, LineInput
from translaterany.refine.triage import colloquial_signals, meaning_signals


def line(i: str, src: str, tgt: str) -> LineInput:
    return LineInput(id=i, line_type="dialogue", source=src, target=tgt, duration_ms=3000)


def test_meaning_signals_from_checks() -> None:
    lines = [line("u1", "I don't know.", "Eu sei."), line("u2", "Great!", "Ótimo!"),
             line("u3", "You cheated on 3 tests.", "Você colou, seu merda.")]  # fmt: skip
    got = meaning_signals(lines, CheckEnv())
    assert got == {"u1": ["negation"], "u3": ["numbers", "profanity_added"]}


def test_colloquial_signals() -> None:
    lines = [
        line("u1", "However, I found it.", "No entanto, eu encontrei."),
        line("u2", "I'll do it.", "Vou fazê-lo."),
        line("u3", "I'm tired.", "Eu estou cansado."),
        line("u4", "Are you coming?", "Tu vens?"),
        line("u5", "Thanks for the help.", "Muito obrigado mesmo por toda essa ajuda que você me deu hoje."),
        line("u6", "Let's go.", "Vamos."),
        line("u7", "Let's go.", "Vamos."),
    ]
    got = colloquial_signals(lines, speaker_of={"u7": "Yu"}, speakers_with_style={"Yu"})
    assert got == {
        "u1": ["formal_connective"],
        "u2": ["enclisis"],
        "u3": ["redundant_subject"],
        "u4": ["archaic_pronoun"],
        "u5": ["too_long"],
        "u7": ["speech_style"],
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refine_triage.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/refine/lexicon.py`:

```python
"""Padrões de PT-BR duro/literal que indicam candidatas à coloquialidade. Amplie aqui."""

import re

FORMAL_CONNECTIVE = re.compile(r"\b(?:no entanto|entretanto|contudo|todavia|a fim de|portanto)\b", re.IGNORECASE)
ENCLISIS = re.compile(r"\b\w+[aeiouáéêíóô]-(?:lo|la|los|las|se|me|te|nos)\b|^\s*\w+-se\b", re.IGNORECASE)
REDUNDANT_SUBJECT = re.compile(r"^\s*eu (?:estou|sou|vou|tenho)\b", re.IGNORECASE)
ARCHAIC_PRONOUN = re.compile(r"\b(?:tu|vós|convosco)\b", re.IGNORECASE)
TOO_LONG_RATIO = 1.3
TOO_LONG_MIN_CHARS = 10
```

`src/translaterany/refine/triage.py`:

```python
"""Triagem sem IA: destaques para a revisão de sentido e alvos da coloquialidade."""

from collections.abc import Mapping, Sequence

from translaterany.checks import CheckEnv, LineInput, run_line_checks
from translaterany.checks.text import plain
from translaterany.refine import lexicon

MEANING_SIGNALS = frozenset(
    {"negation", "numbers", "names", "glossary", "length_ratio", "untranslated", "profanity_added"}
)


def meaning_signals(lines: Sequence[LineInput], env: CheckEnv) -> dict[str, list[str]]:
    found: dict[str, set[str]] = {}
    for f in run_line_checks(lines, env):
        if f.check in MEANING_SIGNALS and f.unit_id is not None:
            found.setdefault(f.unit_id, set()).add(f.check)
    return {k: sorted(v) for k, v in found.items()}


def colloquial_signals(
    lines: Sequence[LineInput], speaker_of: Mapping[str, str], speakers_with_style: set[str]
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for line in lines:
        pt, en = plain(line.target), plain(line.source)
        signals: list[str] = []
        if lexicon.FORMAL_CONNECTIVE.search(pt):
            signals.append("formal_connective")
        if lexicon.ENCLISIS.search(pt):
            signals.append("enclisis")
        if lexicon.REDUNDANT_SUBJECT.search(pt):
            signals.append("redundant_subject")
        if lexicon.ARCHAIC_PRONOUN.search(pt):
            signals.append("archaic_pronoun")
        if len(en) >= lexicon.TOO_LONG_MIN_CHARS and len(pt) > lexicon.TOO_LONG_RATIO * len(en):
            signals.append("too_long")
        if speaker_of.get(line.id) in speakers_with_style:
            signals.append("speech_style")
        if signals:
            result[line.id] = signals
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_refine_triage.py -v`
Expected: PASS. Se o regex de `ENCLISIS` marcar palavras hifenizadas comuns (ex.: "guarda-chuva") em algum teste existente, não mude o teste: restrinja o regex ao sufixo pronominal após vogal acentuada ou `r` final (`\w+[aeiouáéêíóôr]-(?:lo|la|…)`) e registre no relatório.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/refine tests/test_refine_triage.py
git add src/translaterany/refine tests/test_refine_triage.py
git commit -m "feat(refine): adiciona triagem por regras para sentido e coloquialidade"
```

---

### Task 5: Blocos de revisão (`refine/blocks.py`) e `produces_dialogue`

**Files:**
- Create: `src/translaterany/refine/blocks.py`
- Modify: `src/translaterany/pipeline/stage.py`, `src/translaterany/stages/translate_dialogue.py`
- Test: `tests/test_refine_blocks.py`

**Interfaces:**
- Consumes: `group_by_scene` (Tarefa 2), `flatten_breaks`.
- Produces:
  - `@dataclass ReviewLine(id, source, target, speaker, tone, budget: int | None, signals: list[str], editable: bool)`
  - `build_blocks(ids: Sequence[str], targets: set[str], scene_of: Mapping[str, int], max_lines: int) -> list[list[str]]` — grupos por cena **com as falas não-alvo da cena** (para contexto), fatiados de forma que cada bloco tenha no máximo `max_lines` **alvos**; blocos sem alvo descartados.
  - `render_block_prompt(lines: Sequence[ReviewLine]) -> str` — JSON (lista) com chaves `id`, `en`, `pt`, `falante`, `tom`, `limite_caracteres`, `sinais`, `editavel`.
  - `Stage.produces_dialogue: ClassVar[bool] = False`; `StageTranslateDialogue.produces_dialogue = True`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_refine_blocks.py
"""Blocos por cena do M6."""

import json

from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage import Stage
from translaterany.refine.blocks import ReviewLine, build_blocks, render_block_prompt


def test_blocks_by_scene_keep_context_and_drop_scenes_without_targets() -> None:
    ids = ["a", "b", "c", "d", "e"]
    scene_of = {"a": 0, "b": 0, "c": 0, "d": 1, "e": 2}
    assert build_blocks(ids, {"a", "c", "e"}, scene_of, 30) == [["a", "b", "c"], ["e"]]


def test_blocks_limit_targets_per_block() -> None:
    ids = ["a", "b", "c", "d"]
    scene_of = dict.fromkeys(ids, 0)
    assert build_blocks(ids, set(ids), scene_of, 2) == [["a", "b"], ["c", "d"]]


def test_render_block_prompt_is_json_with_flags() -> None:
    line = ReviewLine(id="u1", source="Hi\\Nthere", target="Oi", speaker="Yu", tone="calm", budget=20,
                      signals=["negation"], editable=True)  # fmt: skip
    data = json.loads(render_block_prompt([line]))
    assert data == [{"id": "u1", "en": "Hi there", "pt": "Oi", "falante": "Yu", "tom": "calm",
                     "limite_caracteres": 20, "sinais": ["negation"], "editavel": True}]  # fmt: skip


def test_produces_dialogue_flag() -> None:
    import translaterany.stages  # noqa: F401

    assert Stage.produces_dialogue is False
    assert REGISTRY.get("translate_dialogue").produces_dialogue is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_refine_blocks.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/refine/blocks.py`:

```python
"""Blocos de revisão por cena: alvos editáveis + contexto só de leitura da mesma cena."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from translaterany.subtitles.linebreak import flatten_breaks
from translaterany.subtitles.scenes import group_by_scene


@dataclass
class ReviewLine:
    id: str
    source: str
    target: str
    speaker: str
    tone: str
    budget: int | None
    signals: list[str]
    editable: bool


def build_blocks(ids: Sequence[str], targets: set[str], scene_of: Mapping[str, int], max_lines: int) -> list[list[str]]:
    blocks: list[list[str]] = []
    for scene in group_by_scene(ids, scene_of, len(ids) or 1):
        current: list[str] = []
        count = 0
        for item in scene:
            if item in targets and count >= max(1, max_lines):
                blocks.append(current)
                current, count = [], 0
            current.append(item)
            count += item in targets
        if current:
            blocks.append(current)
    return [b for b in blocks if any(i in targets for i in b)]


def render_block_prompt(lines: Sequence[ReviewLine]) -> str:
    payload = [
        {
            "id": ln.id,
            "en": flatten_breaks(ln.source),
            "pt": flatten_breaks(ln.target),
            "falante": ln.speaker,
            "tom": ln.tone,
            "limite_caracteres": ln.budget,
            "sinais": ln.signals,
            "editavel": ln.editable,
        }
        for ln in lines
    ]
    return json.dumps(payload, ensure_ascii=False)
```

`src/translaterany/pipeline/stage.py`, depois de `produces_texts`:

```python
    produces_dialogue: ClassVar[bool] = False  # artefato é o mapa de diálogo por frase (entrada da redistribuição)
```

`src/translaterany/stages/translate_dialogue.py`, na classe, depois de `produces_texts`:

```python
    produces_dialogue: ClassVar[bool] = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_refine_blocks.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/refine src/translaterany/pipeline/stage.py src/translaterany/stages/translate_dialogue.py tests/test_refine_blocks.py
git add src/translaterany/refine src/translaterany/pipeline/stage.py src/translaterany/stages/translate_dialogue.py tests/test_refine_blocks.py
git commit -m "feat(refine): adiciona blocos de revisão por cena e flag produces_dialogue"
```

---

### Task 6: Base `DialogueRefineStage` + etapa `review_meaning`

**Files:**
- Create: `src/translaterany/stages/refine_base.py`, `src/translaterany/stages/review_meaning.py`
- Modify: `src/translaterany/stages/__init__.py` (importar `review_meaning`; **não** mexer no `DEFAULT_PIPELINE` ainda)
- Test: `tests/test_stage_review_meaning.py`

**Interfaces:**
- Consumes: Tarefas 1–5; `build_sources`, `composite_members` (`checks/snapshots.py`); `char_budget`; `SceneAnalysisDoc`; `load_memory_for_text`; `count`; `LLMRequest`.
- Produces:
  - `RefineOptions(model: str = "review", max_lines_per_block: int = 30)` (extra=forbid)
  - `class DialogueRefineStage(Stage)` com atributos de instância `dialogue_input: str`, `max_cps: float`, `max_cpl: int`; métodos a sobrescrever: `instructions() -> str`, `select_targets(ids, lines, ctx_data) -> dict[str, list[str]]` (id → sinais; ids fora do dict não são alvo), `forbidden_texts(ctx, texts) -> dict[str, str] | None`; `ClassVar` `default_dialogue_input: str`, `optional_inputs`.
  - `ReviewMeaningStage` registrada como `review_meaning`, `version = "1"`, `default_dialogue_input = "translate_dialogue"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_review_meaning.py
"""Etapa review_meaning (M6)."""

from types import SimpleNamespace

from translaterany.config.model import AppConfig
from translaterany.llm.client import LLMOutputError
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages.review_meaning import ReviewMeaningStage
from translaterany.subtitles.classify import Classification, Scene, UnitClass
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit
from translaterany.subtitles.scene_analysis import LineContext, SceneAnalysisDoc
from translaterany.subtitles.texts import UnitTexts


def ev(i: int, unit: str) -> EventInfo:
    return EventInfo(index=i, line_no=i, kind="dialogue", style="Default", start_ms=i * 3000, end_ms=i * 3000 + 2500,
                     layer=0, name="", prefix="", text="t", markers=[], suffix="", drawing=False, unit=unit)  # fmt: skip


DOC = NormalizedDoc(
    encoding=Encoding(bom=False, newline="\n"), format=[],
    events=[ev(0, "u1"), ev(1, "u2"), ev(2, "u3"), ev(3, "u4")],
    units=[Unit(id="u1", style="Default", text="What's this I hear?", markers=0, events=[0]),
           Unit(id="u2", style="Default", text="You cheated on all your tests.", markers=0, events=[1]),
           Unit(id="u3", style="Default", text="Wait for me...", markers=0, events=[2]),
           Unit(id="u4", style="Default", text="...I'm coming!", markers=0, events=[3])],
)  # fmt: skip
CLASSES = Classification(main_style="Default", counts={},
                         units={u: UnitClass(type="dialogue", uncertain=False, rule="r") for u in ("u1", "u2", "u3", "u4")},
                         scenes=[Scene(id="s1", start_ms=0, end_ms=6000, events=[0, 1]),
                                 Scene(id="s2", start_ms=6000, end_ms=12000, events=[2, 3])])  # fmt: skip
MERGED = MergedUnitsDoc(units=[
    CompositeUnit(composite_id="u1", unit_ids=["u1"], durations_ms=[2500], clean_text="", text_with_markers="What's this I hear?"),
    CompositeUnit(composite_id="u2", unit_ids=["u2"], durations_ms=[2500], clean_text="", text_with_markers="You cheated on all your tests."),
    CompositeUnit(composite_id="u3+u4", unit_ids=["u3", "u4"], durations_ms=[2500, 2500], clean_text="",
                  text_with_markers="Wait for me... ...I'm coming!"),
], merged_count=1)  # fmt: skip
SCENE = SceneAnalysisDoc(lines={"u1": LineContext(speaker="Yumi", tone="teasing")})
DIALOGUE = UnitTexts(texts={"u1": "Que barulho é esse?", "u2": "Você colou em tudo, seu merda.",
                            "u3+u4": "Espera... já vou!"}, used_terms={"Yu": "abc"})  # fmt: skip


class Inputs:
    def __init__(self, dialogue: UnitTexts = DIALOGUE) -> None:
        self.data = {"normalize": DOC, "classify": CLASSES, "merge_sentences": MERGED, "scene_analysis": SCENE,
                     "translate_dialogue": dialogue}  # fmt: skip

    def json(self, name, model):
        return self.data[name]


class Output:
    doc: UnitTexts | None = None

    def json(self, model) -> None:
        Output.doc = model


def run(llm, dialogue: UnitTexts = DIALOGUE):
    stage = ReviewMeaningStage()
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(dialogue), output=Output(), llm=llm, metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    return Output.doc, metrics.counters, stage


def test_applies_valid_edits_per_scene_block() -> None:
    prompts = []

    def script(req):
        prompts.append(req.prompt)
        if '"u2"' in req.prompt:
            return EditsResponse(edits=[LineEdit(id="u1", new="Que história é essa?"),
                                        LineEdit(id="u2", new="Você colou em todas as provas.")])  # fmt: skip
        return EditsResponse()

    doc, counters, _ = run(FakeLLM(script))
    assert len(prompts) == 2  # uma chamada por cena
    assert doc.texts == {"u1": "Que história é essa?", "u2": "Você colou em todas as provas.", "u3+u4": "Espera... já vou!"}
    assert doc.used_terms == {"Yu": "abc"}
    assert counters["lines_read"] == 3 and counters["lines_targeted"] == 3
    assert counters["blocks"] == 2 and counters["edits_proposed"] == 2 and counters["edits_applied"] == 2
    assert '"sinais": ["profanity_added"]' in prompts[0] and "Yumi" in prompts[0]


def test_invalid_edit_rejected_and_failed_block_passes_through() -> None:
    def script(req):
        if '"u2"' in req.prompt:
            return EditsResponse(edits=[LineEdit(id="u1", new="Que porra é essa?")])  # piora: palavrão novo em u1
        raise LLMOutputError("json inválido")

    doc, counters, _ = run(FakeLLM(script))
    assert doc.texts == DIALOGUE.texts
    assert counters["rejected_worse"] == 1 and counters["blocks_failed"] == 1 and counters["edits_applied"] == 0


def test_nothing_to_review_writes_input_without_calls() -> None:
    llm = FakeLLM()  # qualquer chamada lançaria LLMConfigError
    doc, counters, _ = run(llm, UnitTexts())
    assert doc.texts == {} and llm.calls == [] and counters.get("blocks", 0) == 0


def test_bind_pipeline_picks_last_dialogue_stage_and_limits() -> None:
    from translaterany.pipeline.registry import REGISTRY

    previous = [REGISTRY.get(n)() for n in ("normalize", "classify", "translate_dialogue")]
    stage = ReviewMeaningStage()
    stage.bind_pipeline(previous, AppConfig.model_validate({"checks": {"max_cps": 15}}))
    assert stage.dialogue_input == "translate_dialogue" and stage.max_cps == 15.0
    assert "merge_sentences" not in stage.inputs and "translate_dialogue" in stage.inputs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_review_meaning.py -v`
Expected: FAIL (`ModuleNotFoundError: translaterany.stages.review_meaning`).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/stages/refine_base.py`:

```python
"""Base das etapas de refinamento do diálogo (M6): blocos por cena, resposta só com edições validadas."""

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.checks import CheckEnv, LineInput
from translaterany.checks.snapshots import LineSource, build_sources, composite_members, lines_for
from translaterany.config.model import AppConfig, ChecksConfig
from translaterany.llm.client import LLMRequest
from translaterany.memory.matching import load_memory_for_text
from translaterany.memory.models import CharacterEntry
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.refine.blocks import ReviewLine, build_blocks, render_block_prompt
from translaterany.refine.edits import REJECT_REASONS, EditsResponse, apply_edits
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.linebreak import char_budget
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.scene_analysis import SceneAnalysisDoc
from translaterany.subtitles.scenes import scene_index_of
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

_OPTIONAL = ("merge_sentences", "scene_analysis", "consolidate_memory")


class RefineOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = "review"
    max_lines_per_block: int = 30


@dataclass
class RefineData:
    """O que as subclasses usam para escolher alvos."""

    sources: dict[str, LineSource]
    lines: list[LineInput]
    env: CheckEnv
    speaker_of: dict[str, str]
    characters: list[CharacterEntry] = field(default_factory=list)


class DialogueRefineStage(Stage):
    scope: ClassVar[StageScope] = StageScope.EPISODE
    produces_texts: ClassVar[bool] = True
    produces_dialogue: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = RefineOptions
    default_dialogue_input: ClassVar[str] = "translate_dialogue"

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.dialogue_input = self.default_dialogue_input
        self.max_cps, self.max_cpl = 17.0, 42
        self.limits = ChecksConfig()
        self.inputs = ("normalize", "classify", *_OPTIONAL, *self._extra_inputs(), self.dialogue_input)

    # --- a sobrescrever -------------------------------------------------------------------------
    def instructions(self) -> str:
        raise NotImplementedError

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        raise NotImplementedError

    def forbidden_texts(self, ctx: StageContext, texts: Mapping[str, str]) -> dict[str, str] | None:
        return None

    def _extra_inputs(self) -> tuple[str, ...]:
        return ()

    # --- pipeline ------------------------------------------------------------------------------
    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        names = [s.name for s in previous]
        dialogue = [s.name for s in previous if s.produces_dialogue]
        if dialogue:
            self.dialogue_input = dialogue[-1]
        if app is not None:
            self.limits = app.checks
            self.max_cps, self.max_cpl = app.checks.max_cps, app.checks.max_cpl
        self._bind_extra(previous)
        optional = tuple(n for n in _OPTIONAL if n in names)
        self.inputs = ("normalize", "classify", *optional, *self._extra_inputs(), self.dialogue_input)

    def _bind_extra(self, previous: Sequence[Stage]) -> None:
        return None

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        return {"input": self.dialogue_input, "limits": self.limits.model_dump(mode="json")}

    # --- execução ------------------------------------------------------------------------------
    def run(self, ctx: StageContext) -> None:
        dialogue = ctx.inputs.json(self.dialogue_input, UnitTexts)
        texts = dict(dialogue.texts)
        if not texts:
            ctx.output.json(UnitTexts(texts={}, used_terms=dialogue.used_terms))
            return
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classes = ctx.inputs.json("classify", Classification)
        merged = ctx.inputs.json("merge_sentences", MergedUnitsDoc) if "merge_sentences" in self.inputs else None
        scene_doc = ctx.inputs.json("scene_analysis", SceneAnalysisDoc) if "scene_analysis" in self.inputs else None
        sources = build_sources(doc, classes, merged)
        ids = [i for i in texts if i in sources]
        glossary, characters = load_memory_for_text(
            getattr(ctx, "store", None), ctx.series.key, "\n".join(sources[i].source for i in ids)
        )
        env = CheckEnv(glossary=glossary, names=[[c.name, *c.aliases] for c in characters], limits=self.limits)
        contexts = scene_doc.lines if scene_doc else {}
        speaker_of = {i: contexts[i].speaker for i in ids if i in contexts}
        lines, _ = lines_for({i: texts[i] for i in ids}, sources)
        data = RefineData(sources=sources, lines=lines, env=env, speaker_of=speaker_of, characters=characters)
        targets = self.select_targets(ids, data)
        count(ctx, "lines_read", len(ids))
        count(ctx, "lines_targeted", len(targets))
        members = composite_members(merged)
        scene_of = scene_index_of(ids, members, {u.id: u.events for u in doc.units}, classes.scenes)
        forbidden = self.forbidden_texts(ctx, texts)
        for block in build_blocks(ids, set(targets), scene_of, self.options.max_lines_per_block):
            count(ctx, "blocks")
            review = [
                ReviewLine(
                    id=i,
                    source=sources[i].source,
                    target=texts[i],
                    speaker=contexts[i].speaker if i in contexts else "Unknown",
                    tone=contexts[i].tone if i in contexts else "neutral",
                    budget=char_budget(sources[i].duration_ms, max_cps=self.max_cps, max_cpl=self.max_cpl),
                    signals=targets.get(i, []),
                    editable=i in targets,
                )
                for i in block
            ]
            try:
                response = ctx.llm.generate(
                    LLMRequest(model=self.options.model, instructions=self.instructions(),
                               prompt=render_block_prompt(review), output_type=EditsResponse, tag=self.name)  # fmt: skip
                ).output
            except Exception as exc:  # bloco com falha passa sem mudanças
                logger.warning("%s: bloco a partir de %s falhou (%s); mantendo o texto.", self.name, block[0], exc)
                count(ctx, "blocks_failed")
                continue
            count(ctx, "edits_proposed", len(response.edits))
            editable = {i for i in block if i in targets}
            outcome = apply_edits(texts, response.edits, editable, sources, env, forbidden=forbidden)
            texts = outcome.texts
            count(ctx, "edits_applied", len(outcome.applied))
            for reason in REJECT_REASONS:
                if outcome.rejected[reason]:
                    count(ctx, f"rejected_{reason}", outcome.rejected[reason])
            if forbidden is not None and outcome.rejected["reversal"]:
                count(ctx, "reversals", outcome.rejected["reversal"])
        ctx.output.json(UnitTexts(texts=texts, used_terms=dialogue.used_terms))
```

`src/translaterany/stages/review_meaning.py`:

```python
"""Etapa review_meaning: revisão de fidelidade de todas as falas, respondendo só com edições."""

from collections.abc import Sequence
from typing import ClassVar

from translaterany.pipeline.registry import register_stage
from translaterany.refine.triage import meaning_signals
from translaterany.stages.refine_base import DialogueRefineStage, RefineData

INSTRUCTIONS = """Você é revisor de legendas de anime (inglês -> português do Brasil).
Revise SOMENTE a fidelidade de cada fala "editavel": omissões, acréscimos (inclusive ofensas ou palavrões
que não existem no original), sentido trocado, gênero ou número errado quando o contexto deixa claro.
NÃO reescreva estilo nem troque palavras por gosto. Mantenha os marcadores ⟦n⟧ exatamente como estão.
Respeite "limite_caracteres" quando houver. "sinais" indicam onde há risco. Falas com "editavel": false são
só contexto. Responda apenas com as falas que precisam mudar; se nenhuma precisar, devolva a lista vazia."""


@register_stage
class ReviewMeaningStage(DialogueRefineStage):
    name: ClassVar[str] = "review_meaning"
    version: ClassVar[str] = "1"

    def instructions(self) -> str:
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        signals = meaning_signals(data.lines, data.env)
        return {i: signals.get(i, []) for i in ids}  # todas as falas; sinais como destaque
```

Em `src/translaterany/stages/__init__.py`, acrescente `review_meaning` à lista de imports (ordem alfabética). Não altere o `DEFAULT_PIPELINE` nesta tarefa.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_review_meaning.py -v` e depois `uv run pytest -q`
Expected: PASS; suíte completa verde.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/stages/refine_base.py src/translaterany/stages/review_meaning.py src/translaterany/stages/__init__.py tests/test_stage_review_meaning.py
git add src/translaterany/stages tests/test_stage_review_meaning.py
git commit -m "feat(stages): adiciona etapa review_meaning com edições validadas por cena"
```

---

### Task 7: Etapa `colloquial`

**Files:**
- Create: `src/translaterany/stages/colloquial.py`
- Modify: `src/translaterany/stages/__init__.py` (importar `colloquial`)
- Test: `tests/test_stage_colloquial.py`

**Interfaces:**
- Consumes: `DialogueRefineStage`, `RefineData` (Tarefa 6); `colloquial_signals` (Tarefa 4).
- Produces: `ColloquialStage` registrada como `colloquial`, `version = "1"`, `default_dialogue_input = "review_meaning"`; atributo `pre_review_input: str | None` (padrão `"translate_dialogue"`), definido em `_bind_extra` como a última etapa com `produces_dialogue` **antes** de `review_meaning` (ou `None` se `review_meaning` não estiver no pipeline).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_stage_colloquial.py
"""Etapa colloquial (M6)."""

from types import SimpleNamespace

from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages.colloquial import ColloquialStage
from translaterany.subtitles.texts import UnitTexts

import test_stage_review_meaning as base  # reaproveita DOC, CLASSES, MERGED, SCENE

PRE = UnitTexts(texts={"u1": "No entanto, que história é essa?", "u2": "Você colou em tudo, seu merda.",
                       "u3+u4": "Espera... já vou!"})  # fmt: skip
REVIEWED = UnitTexts(texts={"u1": "No entanto, que história é essa?", "u2": "Você colou em todas as provas.",
                            "u3+u4": "Espera... já vou!"})  # fmt: skip


class Inputs(base.Inputs):
    def __init__(self) -> None:
        super().__init__()
        self.data["translate_dialogue"] = PRE
        self.data["review_meaning"] = REVIEWED


def run(llm):
    stage = ColloquialStage()
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(), output=base.Output(), llm=llm, metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    return base.Output.doc, metrics.counters


def test_only_triaged_lines_are_editable_and_context_edits_are_rejected() -> None:
    prompts = []

    def script(req):
        prompts.append(req.prompt)
        return EditsResponse(edits=[LineEdit(id="u1", new="Mas que história é essa?"),
                                    LineEdit(id="u3+u4", new="Peraí... tô indo!")])  # u3+u4 não é alvo  # fmt: skip

    doc, counters = run(FakeLLM(script))
    assert len(prompts) == 1  # a cena 2 não tem alvo: nenhuma chamada
    assert '"editavel": false' in prompts[0]  # u2 vai como contexto
    assert doc.texts["u1"] == "Mas que história é essa?" and doc.texts["u3+u4"] == "Espera... já vou!"
    assert counters["lines_targeted"] == 1 and counters["rejected_unknown_id"] == 1


def test_reversal_to_pre_review_text_is_blocked_and_counted() -> None:
    def script(req):
        return EditsResponse(edits=[LineEdit(id="u2", new="Você colou em tudo, seu merda.")])

    stage = ColloquialStage()
    stage.select_targets = lambda ids, data: {i: ["speech_style"] for i in ids}  # todos alvo
    metrics = StageMetrics()
    ctx = SimpleNamespace(inputs=Inputs(), output=base.Output(), llm=FakeLLM(script), metrics=metrics, store=None,
                          series=SimpleNamespace(key="s"), episode=SimpleNamespace(key="S01E01"))  # fmt: skip
    stage.run(ctx)
    assert base.Output.doc.texts["u2"] == "Você colou em todas as provas."
    assert metrics.counters["reversals"] >= 1


def test_bind_pipeline_finds_pre_review_stage() -> None:
    names = ("normalize", "classify", "translate_dialogue", "review_meaning")
    stage = ColloquialStage()
    stage.bind_pipeline([REGISTRY.get(n)() for n in names], None)
    assert stage.dialogue_input == "review_meaning" and stage.pre_review_input == "translate_dialogue"
    assert "translate_dialogue" in stage.inputs
    alone = ColloquialStage()
    alone.bind_pipeline([REGISTRY.get(n)() for n in ("normalize", "classify", "translate_dialogue")], None)
    assert alone.dialogue_input == "translate_dialogue" and alone.pre_review_input is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_stage_colloquial.py -v`
Expected: FAIL (`ModuleNotFoundError: translaterany.stages.colloquial`).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/stages/colloquial.py`:

```python
"""Etapa colloquial: naturalidade PT-BR só nas falas triadas, sem mudar o sentido."""

from collections.abc import Mapping, Sequence
from typing import ClassVar

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext
from translaterany.refine.triage import colloquial_signals
from translaterany.stages.refine_base import DialogueRefineStage, RefineData
from translaterany.subtitles.texts import UnitTexts

INSTRUCTIONS = """Você é adaptador de legendas de anime para português do Brasil falado.
Deixe cada fala "editavel" mais natural, no tom do personagem ("falante", "tom"), SEM mudar o sentido,
sem acrescentar gírias, ofensas ou palavrões que não existem no original ("en"), dentro de
"limite_caracteres" quando houver. Mantenha os marcadores ⟦n⟧ exatamente como estão. Falas com
"editavel": false são só contexto. Responda apenas com as falas que mudar; se nenhuma, lista vazia."""


@register_stage
class ColloquialStage(DialogueRefineStage):
    name: ClassVar[str] = "colloquial"
    version: ClassVar[str] = "1"
    default_dialogue_input: ClassVar[str] = "review_meaning"

    def __init__(self, options=None) -> None:
        self.pre_review_input: str | None = "translate_dialogue"
        super().__init__(options)

    def _extra_inputs(self) -> tuple[str, ...]:
        if self.pre_review_input and self.pre_review_input != self.dialogue_input:
            return (self.pre_review_input,)
        return ()

    def _bind_extra(self, previous: Sequence[Stage]) -> None:
        names = [s.name for s in previous]
        if "review_meaning" not in names:
            self.pre_review_input = None
            return
        before = previous[: names.index("review_meaning")]
        dialogue = [s.name for s in before if s.produces_dialogue]
        self.pre_review_input = dialogue[-1] if dialogue else None

    def instructions(self) -> str:
        return INSTRUCTIONS

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        styled = {c.name for c in data.characters if c.speech_style}
        return colloquial_signals(data.lines, data.speaker_of, styled)

    def forbidden_texts(self, ctx: StageContext, texts: Mapping[str, str]) -> dict[str, str] | None:
        if not self.pre_review_input or self.pre_review_input == self.dialogue_input:
            return None
        before = ctx.inputs.json(self.pre_review_input, UnitTexts).texts
        return {i: t for i, t in before.items() if i in texts and texts[i] != t}
```

Atenção à ordem: `pre_review_input` é definido **antes** de `super().__init__`, porque a base monta `inputs` chamando `_extra_inputs()`.

Em `src/translaterany/stages/__init__.py`, acrescente `colloquial` aos imports (ordem alfabética).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_stage_colloquial.py tests/test_stage_review_meaning.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/stages/colloquial.py src/translaterany/stages/__init__.py tests/test_stage_colloquial.py
git add src/translaterany/stages tests/test_stage_colloquial.py
git commit -m "feat(stages): adiciona etapa colloquial triada com bloqueio de reversões"
```

---

### Task 8: Encaixe no pipeline + E2E

**Files:**
- Modify: `src/translaterany/stages/redistribute_sentences.py`, `src/translaterany/stages/__init__.py` (`DEFAULT_PIPELINE`), `tests/test_inventory.py` (tupla esperada do `DEFAULT_PIPELINE`)
- Test: `tests/test_m6_pipeline.py`

**Interfaces:**
- Consumes: tudo acima.
- Produces: `RedistributeSentencesStage.dialogue_input: str` (padrão `"translate_dialogue"`; `bind_pipeline` escolhe a última etapa com `produces_dialogue`); `version = "3"`; `DEFAULT_PIPELINE` com `"review_meaning", "colloquial"` logo antes de `"redistribute_sentences"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_m6_pipeline.py
"""Encaixe do M6 no pipeline e ponta a ponta com FakeLLM."""

import re
from pathlib import Path

from mkvtools import Sub, make_mkv, needs_mkvtoolnix

from translaterany.config.loader import load_config
from translaterany.library import discover
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.report import build_report
from translaterany.pipeline.runner import Runner
from translaterany.refine.edits import EditsResponse, LineEdit
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.stages.metadata import MetadataStage
from translaterany.subtitles.translator import TranslationBatch, TranslationItem


def test_default_pipeline_order() -> None:
    i = DEFAULT_PIPELINE.index
    assert i("translate_songs") < i("review_meaning") < i("colloquial") < i("redistribute_sentences")


def test_redistribute_reads_last_dialogue_stage(tmp_path: Path) -> None:
    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert stages["redistribute_sentences"].dialogue_input == "colloquial"
    cfg.write_text("[stages.colloquial]\nenabled = false\n[stages.review_meaning]\nenabled = false\n", encoding="utf-8")
    stages = {s.name: s for s in load_config(cfg, tmp_path / "d").stages}
    assert stages["redistribute_sentences"].dialogue_input == "translate_dialogue"
    assert "review_meaning" not in stages


ASS = """[Script Info]
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize
Style: Default,Arial,48

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:00.00,0:01:03.00,Default,,0,0,0,,You've been using it to cheat on all your tests.
Dialogue: 0,0:01:04.00,0:01:07.00,Default,,0,0,0,,However, I found it.
"""


def script(req):
    if req.output_type is TranslationBatch:
        items = []
        for line in req.prompt.splitlines():
            m = re.match(r"^\[(u[^\]]+)\]\s*(.*)$", line.strip())
            if m:
                pt = {"You've": "Você andou colando em tudo, seu merda.", "However": "No entanto, eu encontrei."}
                items.append(TranslationItem(id=m.group(1), text=next(v for k, v in pt.items() if m.group(2).startswith(k))))
        return TranslationBatch(items=items)
    if req.output_type is EditsResponse and req.tag == "review_meaning" and "merda" in req.prompt:
        uid = re.search(r'"id": "(u\d+)", "en": "You', req.prompt).group(1)
        return EditsResponse(edits=[LineEdit(id=uid, new="Você andou colando em todas as provas.")])
    if req.output_type is EditsResponse and req.tag == "colloquial":
        uid = re.search(r'"id": "(u\d+)", "en": "However', req.prompt).group(1)
        return EditsResponse(edits=[LineEdit(id=uid, new="Mas eu achei.")])
    try:
        return req.output_type()
    except Exception:
        return req.output_type.model_construct()


@needs_mkvtoolnix
def test_m6_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Show (2020)"
    make_mkv(root / "Season 1" / "Show - S01E01.mkv", [Sub(ASS, "Full", default=True)])
    store = ArtifactStore(tmp_path / "data")
    series, episodes = discover(root)
    stages = [MetadataStage(anilist_client=None, jikan_client=None) if n == "metadata" else REGISTRY.get(n)()
              for n in DEFAULT_PIPELINE if n != "remux"]  # fmt: skip
    for index, stage in enumerate(stages):  # como o loader faz: redistribute passa a ler a colloquial
        stage.bind_pipeline(stages[:index], None)
    summary = Runner(stages, store, FakeLLM(script)).run(series, episodes)
    assert not summary.failed
    final = (store.artifact_dir(series.key, episodes[0].key) / "redistribute_sentences.json").read_text()
    assert "merda" not in final and "todas as provas" in final and "Mas eu achei." in final
    manifest = store.load_manifest(series, episodes[0])
    assert manifest.stages["review_meaning"].counters["edits_applied"] == 1
    assert manifest.stages["colloquial"].counters["edits_applied"] == 1
    report = build_report(store, series.key, series.name, [s.name for s in stages])
    assert {"review_meaning", "colloquial"} <= set(report.snapshots)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_m6_pipeline.py -v`
Expected: FAIL (`review_meaning` fora do `DEFAULT_PIPELINE`; `dialogue_input` inexistente).

- [ ] **Step 3: Write minimal implementation**

`src/translaterany/stages/redistribute_sentences.py`:
- `version` → `"3"  # 3: diálogo da última etapa com produces_dialogue`;
- em `__init__`: `self.dialogue_input = "translate_dialogue"`;
- troque a tupla `inputs` da classe por uma montada em `__init__` e `bind_pipeline`:

```python
_FIXED = ("normalize", "classify", "translation_memory", "merge_sentences")
_OTHER_TEXTS = ("translate_signs", "translate_songs")
```

```python
    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.max_cpl = 42
        self.dialogue_input = "translate_dialogue"
        self.inputs = (*_FIXED, self.dialogue_input, *_OTHER_TEXTS)

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        if app is not None:
            self.max_cpl = app.checks.max_cpl
        dialogue = [s.name for s in previous if s.produces_dialogue]
        if dialogue:
            self.dialogue_input = dialogue[-1]
        self.inputs = (*_FIXED, self.dialogue_input, *_OTHER_TEXTS)

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        return {"max_cpl": self.max_cpl, "dialogue_input": self.dialogue_input}
```

- em `run`, troque `ctx.inputs.json("translate_dialogue", UnitTexts)` por `ctx.inputs.json(self.dialogue_input, UnitTexts)`;
- remova o atributo de classe `inputs` antigo.

`src/translaterany/stages/__init__.py`: em `DEFAULT_PIPELINE`, insira `"review_meaning", "colloquial",` entre `"translate_songs"` e `"redistribute_sentences"`.

`tests/test_inventory.py`: atualize a tupla esperada do `DEFAULT_PIPELINE` com as duas etapas na mesma posição.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_m6_pipeline.py -v` e depois `uv run pytest -q`
Expected: PASS; suíte completa verde (os E2E do M2–M5 passam a rodar as duas etapas; com `FakeLLM(responses=…)` elas recebem `EditsResponse()` vazio e não mudam nada).

- [ ] **Step 5: Commit**

```bash
uv run ruff check src/translaterany/stages tests/test_m6_pipeline.py tests/test_inventory.py
git add src/translaterany/stages tests/test_m6_pipeline.py tests/test_inventory.py
git commit -m "feat(pipeline): encaixa review_meaning e colloquial antes da redistribuição"
```

---

### Task 9: Estado e documentação

**Files:**
- Modify: `STATE.md`

- [ ] **Step 1: Atualizar `STATE.md`**
  - M6 → 🔨 com link do plano e "implementado; aceite real pendente (N testes)";
  - "Onde estamos": M6 implementado na branch `m6-refinamento-i`; próxima ação: aceite real (Charlotte S01E01 + `report --baseline docs/baselines/2026-09-30-m5-charlotte-s01e01.json`);
  - "Registro de decisões": linha de 2026-09-30 resumindo o M6 (D1–D8 do spec).

- [ ] **Step 2: Suíte e ruff**

Run: `uv run pytest -q` → tudo passando.
Run: `uv run ruff check src tests | grep Found` → no máximo 38.

- [ ] **Step 3: Commit**

```bash
git add STATE.md
git commit -m "docs(state): registra implementação do M6"
```

- [ ] **Step 4: Aceite real (manual, pelo controlador com o usuário)**

```bash
translaterany run "<scratch>/lib/Charlotte (2015)"
translaterany report "<scratch>/lib/Charlotte (2015)" --baseline docs/baselines/2026-09-30-m5-charlotte-s01e01.json
```

Conferir os critérios do spec §9 e os casos "seu merda" / "Que barulho é esse?".
