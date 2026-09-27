# Marco 4: Tradução Contextual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o Marco 4 (Tradução Contextual), adicionando memória de tradução para reuso de linhas idênticas na série (OP/ED, prévias, placas recorrentes), fusão e redistribuição inteligente de frases partidas, análise de cena com falantes/ouvintes/confiança, etapas especializadas de tradução para placas (`signs`) e músicas (`songs`), tradução de diálogo contextualizada com políticas globais de honoríficos e palavrões, e desambiguação por IA para classificação incerta.

**Architecture:** O pipeline linear é estendido com etapas modulares na Fase 2: `classify` (com desambiguação opcional por IA) → `translation_memory` (busca correspondências exatas em `translation_memory.yaml`) → `merge_sentences` (une frases partidas consecutivas em unidades compostas) → `scene_analysis` (infere falantes, clima e desafios por cena) → etapas especializadas de tradução (`translate_dialogue`, `translate_signs`, `translate_songs`) → `redistribute_sentences` (divide frases unidas proporcionalmente à duração dos eventos originais, alimenta a TM com novas linhas recorrentes e consolida o `UnitTexts` final para a etapa `write`).

**Tech Stack:** Python 3.14, `uv`, `pydantic` v2, `ruamel.yaml`, `pydantic-ai-slim`, `pytest`.

**Spec:** [`docs/superpowers/specs/2026-09-27-m4-traducao-contextual-design.md`](../specs/2026-09-27-m4-traducao-contextual-design.md)

## Global Constraints

- `requires-python = ">=3.14"`; gerenciamento exclusivo de dependências via uv.
- Código, classes, métodos e identificadores em inglês; mensagens ao usuário, logs e documentação em PT-BR.
- Política padrão de honoríficos: `"keep"` (preservar sufixos `-san`, `-kun`, `-chan`, `-senpai`, `sensei`, etc.).
- Política padrão de palavrões: `"faithful"` (fidelidade de peso emocional equivalente sem censura nem vulgarização).
- Memória de tradução em YAML por pasta de série (`<data_dir>/series/<series_key>/memory/translation_memory.yaml`).
- Precedência de dados na TM: `user > auto`. Edições manuais no YAML nunca são sobrescritas.
- Karaokê (tags `\k`, `\kf`, `\ko`) e estilos romaji permanecem estritamente intocados.
- Resiliência: falha individual de IA reverte para o texto original com aviso no log; o pipeline nunca é abortado por uma linha isolada.
- Testes automatizados da suíte (`pytest`) devem ser 100% sintéticos, rápidos e determinísticos, sem rede externa ou dependência de Ollama ativo.

## Review Focus

1. **Preservação de marcadores inline (`⟦1⟧`, etc.) em frases compostas e redistribuídas:** A etapa `merge_sentences` remapeia ou concatena marcadores e `redistribute_sentences` deve garantir que os marcadores originais retornem exatamente às unidades originais correspondentes.
2. **Isolamento de Karaokê e Romaji:** Linhas de karaokê (`\k`) ou com estilos contendo `romaji` nunca devem ser traduzidas ou alteradas pela etapa `translate_songs`.
3. **Precedência na Memória de Tradução:** Entradas marcadas como `source: "user"` em `translation_memory.yaml` nunca podem ser sobrescritas por atualizações automáticas (`source: "auto"`).
4. **Proteção contra reaproveitamento de diálogos curtos na TM:** Linhas de diálogo curtas e monossilábicas (ex.: "Yes.", "Sure.") não podem ser registradas automaticamente na TM para evitar contaminação de contexto entre cenas distintas.
5. **Divisão proporcional sem partir palavras:** `redistribute_sentences` deve dividir frases em limites de pontuação ou espaços de palavras, nunca no meio de uma palavra em português.

---

### Task 1: Configuração Global de Tradução (`config/model.py`, `config/loader.py`)

**Files:**
- Modify: `src/translaterany/config/model.py`
- Modify: `src/translaterany/config/loader.py`
- Test: `tests/test_config_m4.py`

**Interfaces:**
- Produces: `TranslationConfig` (com campos `honorifics: Literal["keep", "adapt", "remove"] = "keep"` e `profanity: Literal["faithful", "soften", "raw"] = "faithful"`).
- Produces: `AppConfig.translation: TranslationConfig`.

- [ ] **Step 1: Escrever teste com falha para `TranslationConfig`**

```python
# tests/test_config_m4.py
from translaterany.config.loader import load_config
from translaterany.config.model import AppConfig, TranslationConfig


def test_translation_config_defaults():
    cfg = TranslationConfig()
    assert cfg.honorifics == "keep"
    assert cfg.profanity == "faithful"


def test_translation_config_in_app_config():
    app_cfg = AppConfig()
    assert hasattr(app_cfg, "translation")
    assert app_cfg.translation.honorifics == "keep"
    assert app_cfg.translation.profanity == "faithful"


def test_load_config_with_translation_section(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(
        """
[translation]
honorifics = "adapt"
profanity = "soften"
""",
        encoding="utf-8",
    )
    resolved = load_config(cfg_file)
    assert resolved.app.translation.honorifics == "adapt"
    assert resolved.app.translation.profanity == "soften"
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_config_m4.py -v`
Expected: FAIL com `ImportError` ou `AttributeError: 'AppConfig' object has no attribute 'translation'`.

- [ ] **Step 3: Implementar `TranslationConfig` em `config/model.py`**

Adicionar `TranslationConfig` e campo `translation` em `AppConfig`:

```python
# Em src/translaterany/config/model.py:
class TranslationConfig(_Strict):
    honorifics: Literal["keep", "adapt", "remove"] = "keep"
    profanity: Literal["faithful", "soften", "raw"] = "faithful"


# Em AppConfig:
class AppConfig(_Strict):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    translation: TranslationConfig = Field(default_factory=TranslationConfig)
    pipeline: PipelineConfig | None = None
    stages: dict[str, StageConfig] = Field(default_factory=dict)
```

- [ ] **Step 4: Executar testes de configuração**

Run: `pytest tests/test_config_m4.py tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/config/model.py tests/test_config_m4.py
git commit -m "feat(config): adiciona configuracao global de traducao (honorificos e palavrao)"
```

---

### Task 2: Desambiguação na Etapa Classify (`subtitles/classify.py`, `stages/classify.py`)

**Files:**
- Modify: `src/translaterany/subtitles/classify.py`
- Modify: `src/translaterany/stages/classify.py`
- Test: `tests/test_classify_ai.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `Classification`, `LLMClient`
- Produces: `ClassifyOptions.ai_disambiguate: bool = False`, desambiguação de unidades incertas atualizando `UnitClass(type=..., uncertain=False, rule="ai_disambiguate")`.

- [ ] **Step 1: Escrever teste com falha para desambiguação por IA na classificação**

```python
# tests/test_classify_ai.py
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.stage import StageContext
from translaterany.stages.classify import ClassifyOptions, ClassifyStage
from translaterany.subtitles.classify import UnitClass
from translaterany.subtitles.normalize import EventInfo, NormalizedDoc, UnitInfo


def test_classify_stage_disambiguates_with_ai(tmp_path):
    # Doc com uma linha com pos fora do estilo principal (marcada como incerta pelas regras do M1)
    ev = EventInfo(index=0, unit="u1", prefix=r"{\pos(100,200)}", markers=["⟦1⟧"], suffix="", start_ms=0, end_ms=2000)
    unit = UnitInfo(id="u1", text="Chapter 1: The Beginning", markers=1, style="TitleStyle", events=[0])
    doc = NormalizedDoc(events=[ev], units=[unit])

    fake_llm = FakeLLM(
        responses=[
            '{"units": [{"id": "u1", "line_type": "sign", "reason": "chapter title screen"}]}'
        ]
    )

    stage = ClassifyStage(ClassifyOptions(ai_disambiguate=True))
    stage.client = fake_llm

    # Execução isolada ou via função helper
    from translaterany.subtitles.classify import classify, disambiguate_uncertain_units
    initial_cls = classify(doc, overrides={})
    assert initial_cls.units["u1"].uncertain is True

    updated_cls = disambiguate_uncertain_units(doc, initial_cls, fake_llm)
    assert updated_cls.units["u1"].uncertain is False
    assert updated_cls.units["u1"].type == "sign"
    assert updated_cls.units["u1"].rule == "ai_disambiguate"
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_classify_ai.py -v`
Expected: FAIL com `ImportError: cannot import name 'disambiguate_uncertain_units'`.

- [ ] **Step 3: Implementar `disambiguate_uncertain_units` e atualizar `ClassifyStage`**

Em `src/translaterany/subtitles/classify.py`:
- Adicionar modelo Pydantic para saída de desambiguação:
  ```python
  class DisambiguatedUnit(BaseModel):
      id: str
      line_type: str
      reason: str = ""

  class DisambiguateOutput(BaseModel):
      units: list[DisambiguatedUnit]
  ```
- Implementar função `disambiguate_uncertain_units(doc: NormalizedDoc, cls: Classification, client: LLMClient | None) -> Classification`.
- Se `client` for nulo ou falhar, mantém a classificação original com `uncertain=True`.
- Em `src/translaterany/stages/classify.py`:
  - Adicionar `ai_disambiguate: bool = False` em `ClassifyOptions`.
  - Em `run(ctx)`: se `self.options.ai_disambiguate` e existirem unidades incertas, chama `disambiguate_uncertain_units`.

- [ ] **Step 4: Executar testes de classificação**

Run: `pytest tests/test_classify_ai.py tests/test_classify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/classify.py src/translaterany/stages/classify.py tests/test_classify_ai.py
git commit -m "feat(classify): adiciona desambiguacao de unidades incertas por IA"
```

---

### Task 3: Memória de Tradução da Série (`memory/tm.py`, `stages/translation_memory.py`)

**Files:**
- Create: `src/translaterany/memory/tm.py`
- Create: `src/translaterany/stages/translation_memory.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_translation_memory.py`

**Interfaces:**
- Produces: `TMEntrySource`, `TMEntry`, `TranslationMemoryDoc`, `TranslationMemoryStore`.
- Produces: `TranslationMemoryArtifact` (contendo `matched_units: dict[str, str]`, `matched_keys: list[str]`).
- Produces: `TranslationMemoryStage` (inputs `("normalize", "classify")`).

- [ ] **Step 1: Escrever testes com falha para `TranslationMemoryStore` e `TranslationMemoryStage`**

```python
# tests/test_translation_memory.py
from translaterany.memory.tm import TMEntry, TMEntrySource, TranslationMemoryDoc, TranslationMemoryStore
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import EventInfo, NormalizedDoc, UnitInfo


def test_tm_store_save_and_load(tmp_path):
    tm_file = tmp_path / "translation_memory.yaml"
    store = TranslationMemoryStore(tm_file)
    doc = TranslationMemoryDoc(
        entries={
            "brave shine": TMEntry(
                clean_text="Brave Shine",
                translation="Brilho Corajoso",
                category="song",
                source=TMEntrySource.AUTO,
                occurrences=1,
                episodes=["S01E01"],
            )
        }
    )
    store.save(doc)

    loaded = store.load()
    assert "brave shine" in loaded.entries
    assert loaded.entries["brave shine"].translation == "Brilho Corajoso"


def test_tm_precedence_user_over_auto(tmp_path):
    tm_file = tmp_path / "translation_memory.yaml"
    store = TranslationMemoryStore(tm_file)
    doc = TranslationMemoryDoc(
        entries={
            "op song": TMEntry(
                clean_text="OP Song",
                translation="Tradução Manual do Usuário",
                category="song",
                source=TMEntrySource.USER,
            )
        }
    )
    store.save(doc)

    # Tentativa de atualizar com auto
    store.record_translation("OP Song", "Tradução Automática Nova", "song", "S01E02")
    loaded = store.load()
    assert loaded.entries["op song"].translation == "Tradução Manual do Usuário"
    assert loaded.entries["op song"].source == TMEntrySource.USER
    assert loaded.entries["op song"].occurrences == 2
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_translation_memory.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.memory.tm'`.

- [ ] **Step 3: Implementar `translaterany/memory/tm.py` e `stages/translation_memory.py`**

- Criar `src/translaterany/memory/tm.py`:
  - `TMEntrySource` (`"user"`, `"auto"`).
  - `TMEntry` (`clean_text`, `translation`, `category`, `source`, `occurrences`, `episodes`).
  - `TranslationMemoryDoc` (`entries: dict[str, TMEntry]`).
  - `TranslationMemoryStore`:
    - `load()`: lê arquivo YAML via `ruamel.yaml`; se não existir, devolve doc vazio; se corrompido, emite warning e devolve vazio.
    - `save(doc)`: grava via `ruamel.yaml` atômico (`.tmp` + rename).
    - `record_translation(clean_text, translation, category, episode_key)`: atualiza ou insere, respeitando precedência `user`.
- Criar `src/translaterany/stages/translation_memory.py`:
  - `TranslationMemoryArtifact(BaseModel): matched_units: dict[str, str], matched_keys: list[str]`.
  - `TranslationMemoryOptions(BaseModel): enabled: bool = True, min_dialogue_chars: int = 15`.
  - `TranslationMemoryStage(Stage)`:
    - `name = "translation_memory"`, `scope = StageScope.EPISODE`, `inputs = ("normalize", "classify")`.
    - Consulta `translation_memory.yaml`. Para `song`/`sign`, casa texto limpo; para `dialogue`, casa se `source == "user"` ou se $\text{len} \ge \text{min\_dialogue\_chars}$.
    - Para unidades casadas, formata os marcadores `⟦n⟧` corretos da unidade.
    - Grava `translation_memory.json`.
- Registrar etapa em `src/translaterany/stages/__init__.py`.

- [ ] **Step 4: Executar testes de TM**

Run: `pytest tests/test_translation_memory.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/memory/tm.py src/translaterany/stages/translation_memory.py src/translaterany/stages/__init__.py tests/test_translation_memory.py
git commit -m "feat(memory): adiciona subsistema de memoria de traducao (TM)"
```

---

### Task 4: Fusão de Frases Partidas (`subtitles/merge.py`, `stages/merge_sentences.py`)

**Files:**
- Create: `src/translaterany/subtitles/merge.py`
- Create: `src/translaterany/stages/merge_sentences.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_merge_sentences.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `Classification`, `TranslationMemoryArtifact`
- Produces: `CompositeUnit`, `MergedUnitsDoc`.
- Produces: `MergeSentencesStage` (inputs `("normalize", "classify", "translation_memory")`).

- [ ] **Step 1: Escrever testes com falha para fusão de frases**

```python
# tests/test_merge_sentences.py
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc, merge_dialogue_units
from translaterany.subtitles.normalize import EventInfo, NormalizedDoc, UnitInfo


def test_merge_dialogue_units_with_ellipsis():
    ev1 = EventInfo(index=0, unit="u1", prefix="", markers=["⟦1⟧"], suffix="", start_ms=1000, end_ms=2000)
    u1 = UnitInfo(id="u1", text="Even if you say that...", markers=1, style="Default", events=[0])

    ev2 = EventInfo(index=1, unit="u2", prefix="", markers=["⟦1⟧"], suffix="", start_ms=2200, end_ms=3500)
    u2 = UnitInfo(id="u2", text="...I can't believe it.", markers=1, style="Default", events=[1])

    doc = NormalizedDoc(events=[ev1, ev2], units=[u1, u2])
    classes = {"u1": UnitClass(type="dialogue", uncertain=False, rule=""), "u2": UnitClass(type="dialogue", uncertain=False, rule="")}

    merged = merge_dialogue_units(doc, classes, tm_resolved_ids=set(), max_gap_ms=1500)
    assert len(merged.units) == 1
    comp = merged.units[0]
    assert comp.composite_id == "u1+u2"
    assert comp.unit_ids == ["u1", "u2"]
    assert comp.durations_ms == [1000, 1300]
    assert "Even if you say that..." in comp.clean_text
    assert "I can't believe it." in comp.clean_text


def test_merge_dialogue_skips_tm_resolved():
    ev1 = EventInfo(index=0, unit="u1", prefix="", markers=["⟦1⟧"], suffix="", start_ms=1000, end_ms=2000)
    u1 = UnitInfo(id="u1", text="Wait...", markers=1, style="Default", events=[0])
    ev2 = EventInfo(index=1, unit="u2", prefix="", markers=["⟦1⟧"], suffix="", start_ms=2200, end_ms=3500)
    u2 = UnitInfo(id="u2", text="for me.", markers=1, style="Default", events=[1])
    doc = NormalizedDoc(events=[ev1, ev2], units=[u1, u2])
    classes = {"u1": UnitClass(type="dialogue", uncertain=False, rule=""), "u2": UnitClass(type="dialogue", uncertain=False, rule="")}

    # u1 já foi resolvida pela TM
    merged = merge_dialogue_units(doc, classes, tm_resolved_ids={"u1"}, max_gap_ms=1500)
    assert len(merged.units) == 2
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_merge_sentences.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.subtitles.merge'`.

- [ ] **Step 3: Implementar `merge.py` e `MergeSentencesStage`**

- Criar `src/translaterany/subtitles/merge.py`:
  - Modelos `CompositeUnit` e `MergedUnitsDoc`.
  - Função `merge_dialogue_units(doc: NormalizedDoc, classes: dict[str, UnitClass], tm_resolved_ids: set[str], max_gap_ms: int = 1500) -> MergedUnitsDoc`.
  - Critérios de união:
    - Intervalo $\le \text{max\_gap\_ms}$;
    - Mesma cena/estilo de diálogo;
    - Pontuação aberta (`...`, `,`, `-`, `--` ou sem pontuação final) ou início com minúscula/reticências;
    - Nenhuma das unidades pertencente a `tm_resolved_ids`.
- Criar `src/translaterany/stages/merge_sentences.py`:
  - `MergeSentencesOptions(BaseModel): max_gap_ms: int = 1500`.
  - `MergeSentencesStage(Stage)`:
    - `name = "merge_sentences"`, `scope = StageScope.EPISODE`, `inputs = ("normalize", "classify", "translation_memory")`.
    - Produz `merge_sentences.json` (`MergedUnitsDoc`).
- Registrar etapa em `src/translaterany/stages/__init__.py`.

- [ ] **Step 4: Executar testes de união de frases**

Run: `pytest tests/test_merge_sentences.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/merge.py src/translaterany/stages/merge_sentences.py src/translaterany/stages/__init__.py tests/test_merge_sentences.py
git commit -m "feat(subtitles): adiciona etapa merge_sentences para fusao de frases partidas"
```

---

### Task 5: Análise Contextual de Cena (`subtitles/scene_analysis.py`, `stages/scene_analysis.py`)

**Files:**
- Create: `src/translaterany/subtitles/scene_analysis.py`
- Create: `src/translaterany/stages/scene_analysis.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_scene_analysis.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `Classification`, `ConsolidatedMemoryArtifact`, `MergedUnitsDoc`, `LLMClient`
- Produces: `LineContext`, `SceneAnalysisDoc`, `SceneAnalysisStage` (inputs `("normalize", "classify", "consolidate_memory", "merge_sentences")`).

- [ ] **Step 1: Escrever teste com falha para análise de cena**

```python
# tests/test_scene_analysis.py
from translaterany.llm.fake import FakeLLM
from translaterany.memory.models import CharacterEntry, CharacterRole, Gender
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import LineContext, SceneAnalysisDoc, analyze_scenes


def test_analyze_scenes_with_fake_llm():
    units = [
        CompositeUnit(
            composite_id="u1",
            unit_ids=["u1"],
            durations_ms=[2000],
            clean_text="Who are you?",
            text_with_markers="Who are you?",
            speaker="Unknown",
        )
    ]
    merged_doc = MergedUnitsDoc(units=units, merged_count=0)
    scenes = [Scene(id="s1", start_ms=0, end_ms=5000, events=[0])]
    characters = [CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN)]

    fake_llm = FakeLLM(
        responses=[
            '{"lines": {"u1": {"speaker": "Yuu Otosaka", "listener": "Nao Tomori", "confidence": "high", "tone": "suspicious", "challenges": []}}}'
        ]
    )

    doc = analyze_scenes(merged_doc, scenes, characters, "Synopsis", fake_llm)
    assert "u1" in doc.lines
    assert doc.lines["u1"].speaker == "Yuu Otosaka"
    assert doc.lines["u1"].confidence == "high"
    assert doc.lines["u1"].tone == "suspicious"


def test_analyze_scenes_fallback_on_llm_failure():
    units = [
        CompositeUnit(
            composite_id="u1",
            unit_ids=["u1"],
            durations_ms=[2000],
            clean_text="Hello.",
            text_with_markers="Hello.",
            speaker="Unknown",
        )
    ]
    merged_doc = MergedUnitsDoc(units=units, merged_count=0)
    fake_llm = FakeLLM(responses=["INVALID JSON {"])

    doc = analyze_scenes(merged_doc, [], [], "Synopsis", fake_llm)
    assert "u1" in doc.lines
    assert doc.lines["u1"].confidence == "low"
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_scene_analysis.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.subtitles.scene_analysis'`.

- [ ] **Step 3: Implementar `scene_analysis.py` e `SceneAnalysisStage`**

- Criar `src/translaterany/subtitles/scene_analysis.py`:
  - Modelos `LineContext` (`speaker`, `listener`, `confidence: Literal["high", "medium", "low"]`, `tone`, `relationship`, `challenges: list[str]`).
  - Modelo `SceneAnalysisDoc(lines: dict[str, LineContext])`.
  - Função `analyze_scenes(...) -> SceneAnalysisDoc`:
    - Envia lote de falas com personagens cadastrados em `characters.yaml` e sinopse da série.
    - Em caso de falha da IA, preenche `confidence = "low"` como fallback.
- Criar `src/translaterany/stages/scene_analysis.py`:
  - `SceneAnalysisOptions(BaseModel): model: str = "review"`.
  - `SceneAnalysisStage(Stage)`:
    - `name = "scene_analysis"`, `scope = StageScope.EPISODE`, `inputs = ("normalize", "classify", "consolidate_memory", "merge_sentences")`.
    - Produz `scene_analysis.json` (`SceneAnalysisDoc`).
- Registrar etapa em `src/translaterany/stages/__init__.py`.

- [ ] **Step 4: Executar testes de análise de cena**

Run: `pytest tests/test_scene_analysis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/scene_analysis.py src/translaterany/stages/scene_analysis.py src/translaterany/stages/__init__.py tests/test_scene_analysis.py
git commit -m "feat(subtitles): adiciona etapa scene_analysis para deteccao contextual de falantes e tom"
```

---

### Task 6: Tradução de Placas e Músicas (`subtitles/signs.py`, `subtitles/songs.py`, `stages/translate_signs.py`, `stages/translate_songs.py`)

**Files:**
- Create: `src/translaterany/subtitles/signs.py`
- Create: `src/translaterany/subtitles/songs.py`
- Create: `src/translaterany/stages/translate_signs.py`
- Create: `src/translaterany/stages/translate_songs.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_translate_signs_songs.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `Classification`, `TranslationMemoryArtifact`
- Produces: `TranslateSignsStage` e `TranslateSongsStage`, ambas gerando `UnitTexts`.

- [ ] **Step 1: Escrever testes com falha para placas e músicas**

```python
# tests/test_translate_signs_songs.py
from translaterany.llm.fake import FakeLLM
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import EventInfo, NormalizedDoc, UnitInfo
from translaterany.subtitles.signs import translate_signs
from translaterany.subtitles.songs import translate_songs


def test_translate_signs_conciseness():
    unit = UnitInfo(id="s1", text="Student Council Room", markers=0, style="Sign", events=[0])
    doc = NormalizedDoc(events=[], units=[unit])
    classes = {"s1": UnitClass(type="sign", uncertain=False, rule="")}
    fake_llm = FakeLLM(responses=['{"translations": [{"id": "s1", "text": "Sala do Conselho Estudantil"}]}'])

    res = translate_signs(doc, classes, tm_resolved={}, client=fake_llm)
    assert res.texts["s1"] == "Sala do Conselho Estudantil"


def test_translate_songs_preserves_karaoke_and_romaji():
    # Linha romaji/karaoke não deve ser traduzida
    u_rom = UnitInfo(id="m1", text=r"{\k20}demo {\k30}zutto", markers=0, style="Romaji", events=[0])
    # Linha de tradução da letra em inglês deve ser traduzida
    u_eng = UnitInfo(id="m2", text="Brave shine in the dark", markers=0, style="Song_EN", events=[1])

    doc = NormalizedDoc(events=[], units=[u_rom, u_eng])
    classes = {
        "m1": UnitClass(type="karaoke", uncertain=False, rule=""),
        "m2": UnitClass(type="song", uncertain=False, rule=""),
    }
    fake_llm = FakeLLM(responses=['{"translations": [{"id": "m2", "text": "Brilho corajoso na escuridão"}]}'])

    res = translate_songs(doc, classes, tm_resolved={}, client=fake_llm)
    assert "m1" not in res.texts  # Romaji/karaokê nunca traduz
    assert res.texts["m2"] == "Brilho corajoso na escuridão"
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_translate_signs_songs.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.subtitles.signs'`.

- [ ] **Step 3: Implementar `signs.py`, `songs.py`, `TranslateSignsStage` e `TranslateSongsStage`**

- Criar `src/translaterany/subtitles/signs.py` e `src/translaterany/stages/translate_signs.py`:
  - Traduz unidades com `type == "sign"` fora da TM.
  - Prompt especializado com foco em concisão e preservação de marcadores visuais.
  - Grava `translate_signs.json` (`UnitTexts`).
- Criar `src/translaterany/subtitles/songs.py` e `src/translaterany/stages/translate_songs.py`:
  - Traduz unidades com `type == "song"` fora da TM.
  - Ignora unidades com tags `\k` ou classificadas como `romaji`.
  - Prompt especializado com tom lírico/poético.
  - Grava `translate_songs.json` (`UnitTexts`).
- Registrar ambas em `src/translaterany/stages/__init__.py`.

- [ ] **Step 4: Executar testes de placas e músicas**

Run: `pytest tests/test_translate_signs_songs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/signs.py src/translaterany/subtitles/songs.py src/translaterany/stages/translate_signs.py src/translaterany/stages/translate_songs.py src/translaterany/stages/__init__.py tests/test_translate_signs_songs.py
git commit -m "feat(stages): adiciona etapas translate_signs e translate_songs"
```

---

### Task 7: Tradução de Diálogos Contextualizada (`subtitles/translator.py`, `stages/translate_dialogue.py`)

**Files:**
- Modify: `src/translaterany/subtitles/translator.py`
- Modify: `src/translaterany/stages/translate_dialogue.py`
- Test: `tests/test_translate_dialogue_contextual.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `Classification`, `ConsolidatedMemoryArtifact`, `TranslationMemoryArtifact`, `MergedUnitsDoc`, `SceneAnalysisDoc`.
- Produces: `translate_dialogue.json` (`UnitTexts`) respeitando políticas de honoríficos, palavrões, construções neutras quando confiança for baixa e unidades compostas de `merge_sentences`.

- [ ] **Step 1: Escrever testes com falha para tradução contextualizada com políticas**

```python
# tests/test_translate_dialogue_contextual.py
from translaterany.llm.fake import FakeLLM
from translaterany.memory.models import CharacterEntry, CharacterRole, Gender
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.scene_analysis import LineContext
from translaterany.subtitles.translator import DialogueBatchTranslator


def test_translator_injects_honorifics_and_profanity_policies():
    fake_llm = FakeLLM(responses=['{"translations": [{"id": "u1", "text": "Tadokoro-senpai, que droga!"}]}'])
    translator = DialogueBatchTranslator(
        client=fake_llm,
        model_name="translate",
        honorifics_policy="keep",
        profanity_policy="faithful",
    )
    lines = [DialogueLine(id="u1", text="Tadokoro-senpai, damn it!")]
    res = translator.translate_lines(lines)
    assert res["u1"] == "Tadokoro-senpai, que droga!"

    # Verifica que as políticas foram instruídas no system prompt
    assert "honorific" in fake_llm.last_prompt.lower()
    assert "profanity" in fake_llm.last_prompt.lower()


def test_translator_instructs_neutral_gender_on_low_confidence():
    fake_llm = FakeLLM(responses=['{"translations": [{"id": "u1", "text": "Tenho certeza disso."}]}'])
    line_ctx = {"u1": LineContext(speaker="Unknown", confidence="low")}
    translator = DialogueBatchTranslator(
        client=fake_llm,
        model_name="translate",
        line_contexts=line_ctx,
    )
    lines = [DialogueLine(id="u1", text="I am certain of this.")]
    res = translator.translate_lines(lines)
    assert res["u1"] == "Tenho certeza disso."
    assert "neutral" in fake_llm.last_prompt.lower()
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_translate_dialogue_contextual.py -v`
Expected: FAIL com `TypeError` (argumentos inesperados `honorifics_policy`, `profanity_policy`, `line_contexts`).

- [ ] **Step 3: Implementar enriquecimento contextual no tradutor e na etapa**

- Em `src/translaterany/subtitles/translator.py`:
  - Adicionar parâmetros `honorifics_policy: str = "keep"`, `profanity_policy: str = "faithful"`, `line_contexts: dict[str, LineContext] | None = None`.
  - Injetar no prompt as instruções de honoríficos (`keep`: manter sufixos japoneses originais romanizados) e palavrões (`faithful`: intensidade equivalente).
  - Para linhas com `confidence == "low"`, instruir o modelo a adotar construções neutras de gênero.
- Em `src/translaterany/stages/translate_dialogue.py`:
  - Atualizar inputs: `("normalize", "classify", "consolidate_memory", "translation_memory", "merge_sentences", "scene_analysis")`.
  - Pular unidades já resolvidas na `translation_memory`.
  - Consumir as unidades de `merge_sentences` (traduzindo frases inteiras e compostas).
  - Passar as políticas lidas de `ctx.series.config` (ou default `AppConfig.translation`).

- [ ] **Step 4: Executar testes de tradução contextual**

Run: `pytest tests/test_translate_dialogue_contextual.py tests/test_stages_translate_dialogue.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/translator.py src/translaterany/stages/translate_dialogue.py tests/test_translate_dialogue_contextual.py
git commit -m "feat(translate): integra contexto de cena, politicas de honorificos e palavrao"
```

---

### Task 8: Redistribuição de Frases e Consolidação Final (`subtitles/redistribute.py`, `stages/redistribute_sentences.py`, `stages/write.py`, `stages/__init__.py`)

**Files:**
- Create: `src/translaterany/subtitles/redistribute.py`
- Create: `src/translaterany/stages/redistribute_sentences.py`
- Modify: `src/translaterany/stages/write.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_redistribute_sentences.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `Classification`, `TranslationMemoryArtifact`, `MergedUnitsDoc`, outputs de `translate_dialogue`, `translate_signs`, `translate_songs`.
- Produces: `RedistributeSentencesStage`, gerando o artefato consolidado `UnitTexts` em `redistribute_sentences.json`.
- Modifies: `write.py` para usar `redistribute_sentences` como fonte padrão de textos (`DEFAULT_SOURCE = "redistribute_sentences"`).
- Modifies: `DEFAULT_PIPELINE` em `stages/__init__.py` com a ordem completa do M4.

- [ ] **Step 1: Escrever testes com falha para divisão proporcional e consolidação**

```python
# tests/test_redistribute_sentences.py
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.normalize import EventInfo, NormalizedDoc, UnitInfo
from translaterany.subtitles.redistribute import redistribute_composite_unit


def test_redistribute_splits_at_natural_comma():
    # Frase composta: dur1 = 2000ms, dur2 = 2000ms (50% / 50%)
    comp = CompositeUnit(
        composite_id="u1+u2",
        unit_ids=["u1", "u2"],
        durations_ms=[2000, 2000],
        clean_text="Even if you say that, I cannot believe it.",
        text_with_markers="Even if you say that, I cannot believe it.",
    )
    translated_text = "Mesmo que você diga isso, não posso acreditar."
    split_texts = redistribute_composite_unit(comp, translated_text)
    assert len(split_texts) == 2
    assert split_texts["u1"] == "Mesmo que você diga isso,"
    assert split_texts["u2"] == "não posso acreditar."


def test_redistribute_preserves_inline_markers():
    comp = CompositeUnit(
        composite_id="u1+u2",
        unit_ids=["u1", "u2"],
        durations_ms=[2000, 2000],
        clean_text="Word1 Word2",
        text_with_markers="⟦1⟧Word1⟦2⟧ ⟦3⟧Word2⟦4⟧",
    )
    # Supondo marcadores ⟦1⟧ e ⟦2⟧ na u1 e ⟦3⟧ e ⟦4⟧ na u2
    translated_text = "⟦1⟧Palavra1⟦2⟧ ⟦3⟧Palavra2⟦4⟧"
    split_texts = redistribute_composite_unit(comp, translated_text)
    assert "⟦1⟧" in split_texts["u1"]
    assert "⟦2⟧" in split_texts["u1"]
    assert "⟦3⟧" in split_texts["u2"]
    assert "⟦4⟧" in split_texts["u2"]
```

- [ ] **Step 2: Executar teste para verificar falha**

Run: `pytest tests/test_redistribute_sentences.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.subtitles.redistribute'`.

- [ ] **Step 3: Implementar `redistribute.py` e `RedistributeSentencesStage`**

- Criar `src/translaterany/subtitles/redistribute.py`:
  - `redistribute_composite_unit(comp: CompositeUnit, translated_text: str) -> dict[str, str]`:
    - Calcula proporção por duração.
    - Localiza ponto de divisão ideal (preferência: pontuação `,`, `;`, `-`, `...`; fallback: espaço entre palavras).
    - Preserva marcadores de tags ASS correspondentes a cada unidade.
- Criar `src/translaterany/stages/redistribute_sentences.py`:
  - `RedistributeSentencesOptions(BaseModel): auto_feed_tm: bool = True`.
  - `RedistributeSentencesStage(Stage)`:
    - Inputs: `("normalize", "classify", "translation_memory", "merge_sentences", "translate_dialogue", "translate_signs", "translate_songs")`.
    - Agrega textos de todas as fontes de tradução e TM.
    - Divide unidades compostas de volta para seus IDs originais.
    - Se `auto_feed_tm == True`, registra novas músicas e placas traduzidas em `translation_memory.yaml`.
    - Grava `redistribute_sentences.json` (`UnitTexts`).
- Em `src/translaterany/stages/write.py`:
  - Atualizar `DEFAULT_SOURCE = "redistribute_sentences"`.
- Em `src/translaterany/stages/__init__.py`:
  - Atualizar `DEFAULT_PIPELINE`:
    ```python
    DEFAULT_PIPELINE: tuple[str, ...] = (
        "inventory",
        "metadata",
        "select_track",
        "extract",
        "normalize",
        "classify",
        "extract_terms",
        "consolidate_memory",
        "translation_memory",
        "merge_sentences",
        "scene_analysis",
        "translate_dialogue",
        "translate_signs",
        "translate_songs",
        "redistribute_sentences",
        "write",
        "publish",
        "remux",
    )
    ```

- [ ] **Step 4: Executar testes de redistribuição e escrita**

Run: `pytest tests/test_redistribute_sentences.py tests/test_stages_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/redistribute.py src/translaterany/stages/redistribute_sentences.py src/translaterany/stages/write.py src/translaterany/stages/__init__.py tests/test_redistribute_sentences.py
git commit -m "feat(stages): adiciona redistribute_sentences e atualiza DEFAULT_PIPELINE do Marco 4"
```

---

### Task 9: Teste E2E e Integração Completa do Marco 4 (`tests/test_m4_e2e.py`)

**Files:**
- Create: `tests/test_m4_e2e.py`
- Modify: `STATE.md`

**Interfaces:**
- Validates: Execução ponta a ponta em 2 episódios sintéticos completos com o pipeline completo do M4. Verifica que no Ep 2 a abertura traduzida do Ep 1 é aproveitada da memória de tradução com 0 chamadas de IA para a música, que frases partidas são unidas e redistribuídas, que placas são traduzidas concisas e que o `.ass` gerado é válido.

- [ ] **Step 1: Escrever teste E2E do Marco 4**

```python
# tests/test_m4_e2e.py
from pathlib import Path
from translaterany.config.loader import load_config
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.units import Episode, Series
from translaterany.stages import DEFAULT_PIPELINE
from translaterany.subtitles.ass import parse_ass


def test_m4_e2e_pipeline_two_episodes(tmp_path):
    # Configuração com pipeline M4 completo
    series_dir = tmp_path / "Test Anime (2025)"
    series_dir.mkdir()
    season_dir = series_dir / "Season 1"
    season_dir.mkdir()

    ep1_mkv = season_dir / "Test Anime - S01E01.mkv"
    ep2_mkv = season_dir / "Test Anime - S01E02.mkv"
    ep1_mkv.touch()
    ep2_mkv.touch()

    # Cria ASS sintético para os 2 episódios com OP, Placa e Diálogo com reticências
    ass_content = """[Script Info]
Title: Test
ScriptType: v4.00+

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,2,10,10,10,1
Style: Sign,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,8,10,10,10,1
Style: Song_EN,Arial,20,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,1,8,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:01:00.00,0:01:30.00,Song_EN,,0,0,0,,Brave shine in the night
Dialogue: 0,0:02:00.00,0:02:05.00,Sign,,0,0,0,,Student Council
Dialogue: 0,0:03:00.00,0:03:02.00,Default,,0,0,0,,Wait for me...
Dialogue: 0,0:03:02.20,0:03:04.00,Default,,0,0,0,,...I am coming!
"""

    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(path=series_dir, key="test-anime")
    episodes = [
        Episode(series=series, path=ep1_mkv, key="S01E01", number=1, season=1),
        Episode(series=series, path=ep2_mkv, key="S01E02", number=2, season=1),
    ]

    # Prepara mock de extração para os testes sintéticos
    for ep in episodes:
        store.write_extracted_ass(series.key, ep.key, ass_content.encode("utf-8"))

    # FakeLLM com respostas previsíveis
    fake_llm = FakeLLM(
        responses=[
            # Ep 1: metadata, extract_terms, consolidate_memory
            '{"terms": []}',
            '{"glossary": [], "characters": []}',
            # Ep 1: scene analysis
            '{"lines": {}}',
            # Ep 1: signs translation
            '{"translations": [{"id": "u2", "text": "Conselho Estudantil"}]}',
            # Ep 1: songs translation
            '{"translations": [{"id": "u1", "text": "Brilho corajoso na noite"}]}',
            # Ep 1: dialogue translation
            '{"translations": [{"id": "u3+u4", "text": "Espere por mim... já estou chegando!"}]}',
            # Ep 2: scene analysis
            '{"lines": {}}',
            # Ep 2: signs translation (se não casar na TM)
            '{"translations": [{"id": "u2", "text": "Conselho Estudantil"}]}',
            # Ep 2: dialogue translation
            '{"translations": [{"id": "u3+u4", "text": "Espere por mim... já estou chegando!"}]}',
        ]
    )

    stages_instances = [REGISTRY.get(name)() for name in DEFAULT_PIPELINE if name not in ("inventory", "select_track", "extract", "remux", "publish")]
    runner = Runner(stages=stages_instances, store=store, llm=fake_llm)
    summary = runner.run(series, episodes)

    assert summary.status == "success"

    # Verifica arquivo gravado do Ep 1 e Ep 2
    ep1_ass = parse_ass(store.stage_artifact_path(series.key, episodes[0].key, "write", ".ass").read_bytes())
    assert any("Brilho corajoso na noite" in ev.text for ev in ep1_ass.events)
    assert any("Conselho Estudantil" in ev.text for ev in ep1_ass.events)
    assert any("Espere por mim" in ev.text for ev in ep1_ass.events)

    # Verifica que translation_memory.yaml foi alimentado e Ep 2 reutilizou a música
    tm_path = store.series_dir(series.key) / "memory" / "translation_memory.yaml"
    assert tm_path.exists()
    content = tm_path.read_text(encoding="utf-8")
    assert "brave shine in the night" in content.lower()
```

- [ ] **Step 2: Executar teste E2E**

Run: `pytest tests/test_m4_e2e.py -v`
Expected: PASS.

- [ ] **Step 3: Atualizar `STATE.md` com status de implementação do Marco 4**

- Atualizar tabela de marcos em `STATE.md` marcando M4 como concluído com a contagem total de testes.
- Atualizar "Onde estamos" e "Registro de decisões".

- [ ] **Step 4: Executar suíte completa de testes**

Run: `pytest -v`
Expected: Todos os testes passando sem erros.

- [ ] **Step 5: Commit**

```bash
git add tests/test_m4_e2e.py STATE.md
git commit -m "test(e2e): valida integracao ponta a ponta do Marco 4 e atualiza STATE.md"
```
