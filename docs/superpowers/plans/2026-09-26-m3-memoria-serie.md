# Marco 3: Memória da Série Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o subsistema de memória da série (`translaterany.memory`) com AniList (GraphQL), Jikan (REST), etapas de extração e consolidação de termos em YAML (`characters.yaml`, `glossary.yaml`, `story.yaml`), injeção dinâmica de glossário na tradução e rastreamento de staleness com `retry --stale`.

**Architecture:** A Fase 1 do pipeline executa as etapas `metadata` (AniList/Jikan em escopo `series`), `extract_terms` (map por episódio com IA) e `consolidate_memory` (reduce por série com IA) gerando arquivos YAML editáveis com precedência estrita (`user` > `metadata` > `extracted`). A Fase 2 (`translate_dialogue`) filtra os termos que ocorrem no episódio, injeta glossário e personagens no prompt e registra `used_terms` no artefato para detecção de staleness e reprocessamento com `retry --stale`.

**Tech Stack:** Python 3.14, `uv`, `pydantic` v2, `ruamel.yaml`, `httpx`, `tenacity`, `pydantic-ai-slim`, `typer`, `rich`, `pytest`.

**Spec:** [`docs/superpowers/specs/2026-09-26-m3-memoria-serie-design.md`](../specs/2026-09-26-m3-memoria-serie-design.md)

## Global Constraints

- requires-python = ">=3.14"; gerenciamento exclusivo de dependências via uv.
- Código, classes, métodos e identificadores em inglês; mensagens exibidas ao usuário, logs e documentação em PT-BR.
- Nova dependência: `ruamel.yaml>=0.18.0`.
- Memória unificada por pasta de série (`data_dir/series/<series_key>/memory/`).
- Precedência de dados: `user` > `metadata` > `extracted`. Edições manuais no YAML nunca são sobrescritas.
- Testes automatizados da suíte (`pytest`) devem ser 100% sintéticos, rápidos e determinísticos, sem rede externa ou dependência de Ollama ativo.

## Review Focus

1. **Falha de rede ou timeout nas APIs externas (AniList/Jikan):** A etapa `metadata` deve degradar graciosamente (`matched=False`), permitindo que a série continue a execução normalmente sem metadados externos.
2. **Preservação de comentários e edições manuais em arquivos YAML:** O leitor/escritor `ruamel.yaml` deve manter comentários existentes e garantir que termos com `source: user` nunca sejam alterados por novas extrações.
3. **Colisão de chaves de episódios em múltiplas temporadas:** Sinopses de episódios em `StoryMemory` devem ser indexadas pela chave canônica do episódio (`ep.key`, ex: `"S01E01"`), evitando colisões em séries multi-temporada.
4. **Filtragem de glossário com termos compostos e case-insensitive:** A filtragem por episódio deve casar termos e aliases sem sensibilidade a maiúsculas/minúsculas e respeitar limites de palavras (evitando falsos positivos parciais).
5. **Comando `retry --stale`:** Deve resetar especificamente os episódios que consumiram termos que sofreram alteração no hash de conteúdo, tornando `--from` opcional quando `--stale` é fornecido.

---

### Task 1: Dependências e Modelos de Memória (`pyproject.toml`, `memory/models.py`, `memory/artifacts.py`)

**Files:**
- Modify: `pyproject.toml`
- Create: `src/translaterany/memory/models.py`
- Create: `src/translaterany/memory/artifacts.py`
- Modify: `src/translaterany/memory/__init__.py`
- Test: `tests/test_memory_models.py`

**Interfaces:**
- Produces: `CharacterEntry`, `GlossaryEntry`, `StoryMemory`, `EpisodeSynopsis`, `MetadataArtifact`, `ExtractTermsArtifact`, `ConsolidatedMemoryArtifact`.

- [ ] **Step 1: Adicionar dependência `ruamel.yaml` via uv**

Run: `uv add "ruamel.yaml>=0.18.0"`

- [ ] **Step 2: Escrever testes com falha para os modelos de memória**

```python
# tests/test_memory_models.py
from translaterany.memory.models import (
    CharacterEntry,
    CharacterRole,
    EntrySource,
    Gender,
    GlossaryCategory,
    GlossaryEntry,
    StoryMemory,
    EpisodeSynopsis,
)
from translaterany.memory.artifacts import (
    MetadataArtifact,
    ExtractTermsArtifact,
    ConsolidatedMemoryArtifact,
)


def test_glossary_entry_content_hash():
    entry1 = GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)
    entry2 = GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)
    assert entry1.content_hash() == entry2.content_hash()

    entry3 = GlossaryEntry(term="Plunder", translation="Pilhar", category=GlossaryCategory.TECHNIQUE)
    assert entry1.content_hash() != entry3.content_hash()


def test_character_entry_defaults():
    char = CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE, role=CharacterRole.MAIN)
    assert char.source == EntrySource.EXTRACTED
    assert char.aliases == []


def test_story_memory_episode_key():
    story = StoryMemory(title="Charlotte", year=2015)
    story.episodes["S01E01"] = EpisodeSynopsis(episode_key="S01E01", number=1, synopsis="Primeiro ep")
    assert "S01E01" in story.episodes
    assert story.episodes["S01E01"].number == 1


def test_artifacts_serialization():
    meta = MetadataArtifact(matched=True, anilist_id=20954, title="Charlotte")
    data = meta.model_dump_json()
    loaded = MetadataArtifact.model_validate_json(data)
    assert loaded.anilist_id == 20954
    assert loaded.matched is True

    consolidated = ConsolidatedMemoryArtifact(
        series_name="Charlotte",
        characters_count=4,
        glossary_count=12,
        characters_hash="abc",
        glossary_hash="def",
        story_hash="123",
        glossary_terms=["Plunder", "Collapse"],
    )
    c_data = consolidated.model_dump_json()
    assert ConsolidatedMemoryArtifact.model_validate_json(c_data).glossary_count == 12
```

- [ ] **Step 3: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_memory_models.py -v`
Expected: FAIL (módulos não definidos)

- [ ] **Step 4: Implementar `models.py` e `artifacts.py`**

Implementar conforme especificação em `src/translaterany/memory/models.py` e `src/translaterany/memory/artifacts.py`. Exportar modelos em `src/translaterany/memory/__init__.py`.

- [ ] **Step 5: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_memory_models.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock src/translaterany/memory/ tests/test_memory_models.py
git commit -m "feat(memory): modelos de dados e artefatos da memória da série"
```

---

### Task 2: Armazenamento e Precedência YAML com `ruamel.yaml` (`memory/store.py`)

**Files:**
- Create: `src/translaterany/memory/store.py`
- Test: `tests/test_memory_yaml.py`

**Interfaces:**
- Consumes: `CharacterEntry`, `GlossaryEntry`, `StoryMemory` from `translaterany.memory.models`.
- Produces: `MemoryStore(dir: Path)` com métodos:
  - `load_characters() -> list[CharacterEntry]`
  - `save_characters(characters: list[CharacterEntry]) -> str` (retorna sha256)
  - `merge_characters(incoming: list[CharacterEntry]) -> list[CharacterEntry]`
  - `load_glossary() -> dict[str, GlossaryEntry]` (indexado por `term`)
  - `save_glossary(entries: list[GlossaryEntry]) -> str` (retorna sha256)
  - `merge_glossary(incoming: list[GlossaryEntry]) -> list[GlossaryEntry]`
  - `load_story() -> StoryMemory | None`
  - `save_story(story: StoryMemory) -> str` (retorna sha256)

- [ ] **Step 1: Escrever testes com falha para `MemoryStore`**

```python
# tests/test_memory_yaml.py
from pathlib import Path
from translaterany.memory.models import (
    CharacterEntry,
    CharacterRole,
    EntrySource,
    Gender,
    GlossaryCategory,
    GlossaryEntry,
    StoryMemory,
)
from translaterany.memory.store import MemoryStore


def test_yaml_roundtrip_glossary(tmp_path: Path):
    store = MemoryStore(tmp_path)
    entries = [
        GlossaryEntry(term="Academy", translation="Academia", category=GlossaryCategory.PLACE),
        GlossaryEntry(term="Power", translation="Poder", category=GlossaryCategory.GENERAL),
    ]
    h1 = store.save_glossary(entries)
    assert len(h1) == 64
    loaded = store.load_glossary()
    assert len(loaded) == 2
    assert loaded["Academy"].translation == "Academia"


def test_user_precedence_is_preserved_on_merge(tmp_path: Path):
    store = MemoryStore(tmp_path)
    user_entry = GlossaryEntry(
        term="Academy",
        translation="Colégio Especial",
        category=GlossaryCategory.PLACE,
        source=EntrySource.USER,
        notes="Decisão do fansub",
    )
    store.save_glossary([user_entry])

    ai_entry = GlossaryEntry(
        term="Academy",
        translation="Academia",
        category=GlossaryCategory.PLACE,
        source=EntrySource.EXTRACTED,
    )
    store.merge_glossary([ai_entry])

    reloaded = store.load_glossary()
    assert reloaded["Academy"].translation == "Colégio Especial"
    assert reloaded["Academy"].source == EntrySource.USER
    assert reloaded["Academy"].notes == "Decisão do fansub"


def test_character_merge_preserves_user_fields(tmp_path: Path):
    store = MemoryStore(tmp_path)
    c_user = CharacterEntry(name="Yuu", gender=Gender.MALE, role=CharacterRole.MAIN, source=EntrySource.USER)
    store.save_characters([c_user])

    c_meta = CharacterEntry(
        name="Yuu", gender=Gender.UNKNOWN, role=CharacterRole.SUPPORTING, source=EntrySource.METADATA
    )
    merged = store.merge_characters([c_meta])
    assert len(merged) == 1
    assert merged[0].role == CharacterRole.MAIN
    assert merged[0].gender == Gender.MALE
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_memory_yaml.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar `MemoryStore` em `src/translaterany/memory/store.py`**

Utilizar `ruamel.yaml.YAML(typ="rt")` para leitura e gravação preservando ordem e formatação. Implementar `merge_glossary` e `merge_characters` respeitando precedência `user` > `metadata` > `extracted`.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_memory_yaml.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/memory/store.py tests/test_memory_yaml.py
git commit -m "feat(memory): persistência de glossário e fichas em YAML com ruamel"
```

---

### Task 3: Clientes AniList (GraphQL) e Jikan (REST) com Cache em Disco (`memory/anilist.py`, `memory/jikan.py`)

**Files:**
- Create: `src/translaterany/memory/anilist.py`
- Create: `src/translaterany/memory/jikan.py`
- Test: `tests/test_anilist_client.py`
- Test: `tests/test_jikan_client.py`

**Interfaces:**
- Produces: `AniListMatch(anilist_id: int, mal_id: int | None, title: str, romaji: str, year: int | None, genres: list[str], characters: list[CharacterEntry])`
- Produces: `AniListClient(cache_dir: Path)` com `search_anime(title: str, year: int | None = None) -> AniListMatch | None`
- Produces: `JikanClient(cache_dir: Path)` com `get_episode_synopses(mal_id: int) -> dict[int, EpisodeSynopsis]`

- [ ] **Step 1: Escrever testes com falha para clientes de API**

```python
# tests/test_anilist_client.py
from pathlib import Path
import httpx
from translaterany.memory.anilist import AniListClient


def test_anilist_search_anime_success(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    mock_payload = {
        "data": {
            "Media": {
                "id": 20954,
                "idMal": 28999,
                "title": {"romaji": "Charlotte", "english": "Charlotte", "native": "シャーロット"},
                "seasonYear": 2015,
                "episodes": 13,
                "genres": ["Drama", "Supernatural"],
                "characters": {
                    "edges": [
                        {
                            "role": "MAIN",
                            "node": {
                                "name": {"full": "Yuu Otosaka", "native": "乙坂 有宇"},
                                "gender": "Male",
                            },
                        }
                    ]
                },
            }
        }
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, json=mock_payload))
    res = client.search_anime("Charlotte", 2015)
    assert res is not None
    assert res.anilist_id == 20954
    assert res.mal_id == 28999
    assert len(res.characters) == 1
    assert res.characters[0].name == "Yuu Otosaka"
    assert (tmp_path / "cache" / "anilist").exists()


def test_anilist_offline_returns_none(tmp_path: Path, monkeypatch):
    client = AniListClient(cache_dir=tmp_path / "cache")

    def mock_post(*a, **kw):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "post", mock_post)
    res = client.search_anime("Charlotte", 2015)
    assert res is None
```

```python
# tests/test_jikan_client.py
from pathlib import Path
import httpx
from translaterany.memory.jikan import JikanClient


def test_jikan_get_episode_synopses_success(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")
    mock_payload = {
        "data": [
            {
                "mal_id": 1,
                "title": "I Think About Others",
                "synopsis": "Yuu Otosaka uses his ability to cheat on tests.",
            }
        ]
    }
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json=mock_payload))
    eps = client.get_episode_synopses(28999)
    assert 1 in eps
    assert "cheat" in eps[1].synopsis
    assert eps[1].title == "I Think About Others"


def test_jikan_offline_returns_empty_dict(tmp_path: Path, monkeypatch):
    client = JikanClient(cache_dir=tmp_path / "cache")

    def mock_get(*a, **kw):
        raise httpx.ConnectError("Offline")

    monkeypatch.setattr(httpx, "get", mock_get)
    eps = client.get_episode_synopses(28999)
    assert eps == {}
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_anilist_client.py tests/test_jikan_client.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar `AniListClient` e `JikanClient`**

Implementar consultas HTTP com `httpx`, armazenamento em cache JSON por hash de consulta em `cache_dir / "anilist"` e `cache_dir / "jikan"`, rate-limiting com `tenacity` e tratamento de erros de conexão e rate-limit (429) com fallback silencioso para `None` / `{}`.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_anilist_client.py tests/test_jikan_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/memory/anilist.py src/translaterany/memory/jikan.py tests/test_anilist_client.py tests/test_jikan_client.py
git commit -m "feat(memory): clientes AniList e Jikan com cache persistente"
```

---

### Task 4: Etapa de Pipeline `MetadataStage` e Override em `series.toml` (`stages/metadata.py`, `library/series_config.py`, `pipeline/units.py`, `stages/__init__.py`)

**Files:**
- Create: `src/translaterany/stages/metadata.py`
- Modify: `src/translaterany/library/series_config.py`
- Modify: `src/translaterany/pipeline/units.py`
- Modify: `src/translaterany/stages/__init__.py`
- Test: `tests/test_stage_metadata.py`

**Interfaces:**
- Consumes: `AniListClient`, `JikanClient`, `SeriesConfig` (com `metadata.anilist_id`).
- Produces: `MetadataStage` (escopo `series`, inputs `("inventory",)`), grava `metadata.json` (`MetadataArtifact`).
- Registers: `MetadataStage` em `translaterany.pipeline.registry`.

- [ ] **Step 1: Escrever testes com falha para `MetadataStage` e suporte a `[metadata]` no `series.toml`**

```python
# tests/test_stage_metadata.py
from pathlib import Path
from types import SimpleNamespace
from translaterany.library.series_config import load_series_config
from translaterany.pipeline.units import Episode, Series
from translaterany.stages.metadata import MetadataStage
from translaterany.memory.artifacts import MetadataArtifact
from translaterany.memory.anilist import AniListMatch
from translaterany.memory.models import CharacterEntry, Gender


def test_series_toml_with_metadata(tmp_path: Path):
    toml_file = tmp_path / "series.toml"
    toml_file.write_text("[metadata]\nanilist_id = 20954\n", encoding="utf-8")
    cfg = load_series_config(tmp_path)
    assert cfg.metadata.anilist_id == 20954


def test_metadata_stage_runs_and_writes_artifact(tmp_path: Path):
    captured: MetadataArtifact | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    class MockAniList:
        def search_anime(self, title, year):
            return AniListMatch(
                anilist_id=20954,
                mal_id=28999,
                title="Charlotte",
                romaji="Charlotte",
                year=2015,
                genres=["Drama"],
                characters=[CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE)],
            )

    class MockJikan:
        def get_episode_synopses(self, mal_id):
            return {}

    stage = MetadataStage(anilist_client=MockAniList(), jikan_client=MockJikan())
    series = Series(name="Charlotte (2015)", path=tmp_path)
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        output=MockOutput(),
        inputs=SimpleNamespace(json=lambda *a: None),
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.matched is True
    assert captured.anilist_id == 20954
    assert len(captured.characters) == 1


def test_metadata_stage_offline_fallback(tmp_path: Path):
    captured: MetadataArtifact | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    class MockAniListOffline:
        def search_anime(self, title, year):
            return None

    stage = MetadataStage(anilist_client=MockAniListOffline(), jikan_client=None)
    series = Series(name="Serie Desconhecida", path=tmp_path)
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        output=MockOutput(),
        inputs=SimpleNamespace(json=lambda *a: None),
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.matched is False
    assert captured.anilist_id is None
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_stage_metadata.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar `MetadataStage` e suporte no `series_config.py`**

Adicionar modelo `SeriesMetadataConfig(anilist_id: int | None = None)` em `pipeline/units.py` e carregar seção `[metadata]` no `series_config.py`. Implementar `MetadataStage` com extração de título/ano a partir do nome da série (ex.: `"Charlotte (2015)"` -> title `"Charlotte"`, year `2015`). Importar e registrar em `stages/__init__.py`.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_stage_metadata.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/metadata.py src/translaterany/library/series_config.py src/translaterany/pipeline/units.py src/translaterany/stages/__init__.py tests/test_stage_metadata.py
git commit -m "feat(stages): etapa metadata e suporte a anilist_id no series.toml"
```

---

### Task 5: Etapas de Extração e Consolidação com IA (`stages/extract_terms.py`, `stages/consolidate_memory.py`, `llm/fake.py`, `stages/__init__.py`, `tests/test_inventory.py`)

**Files:**
- Create: `src/translaterany/stages/extract_terms.py`
- Create: `src/translaterany/stages/consolidate_memory.py`
- Modify: `src/translaterany/llm/fake.py`
- Modify: `src/translaterany/stages/__init__.py`
- Modify: `tests/test_inventory.py`
- Test: `tests/test_stage_extract_terms.py`
- Test: `tests/test_stage_consolidate_memory.py`

**Interfaces:**
- Produces: `ExtractTermsStage` (escopo `episode`, inputs `("metadata", "normalize")`, grava `extract_terms.json` via `ExtractTermsArtifact`).
- Produces: `ConsolidateMemoryStage` (escopo `series`, inputs `("metadata", "extract_terms")`, grava `consolidate_memory.json` via `ConsolidatedMemoryArtifact` e grava `characters.yaml`, `glossary.yaml`, `story.yaml`).
- Updates: `DEFAULT_PIPELINE` em `stages/__init__.py` e assert em `tests/test_inventory.py`.

- [ ] **Step 1: Atualizar `FakeLLM` em `src/translaterany/llm/fake.py` para suportar `output_type` genérico**

Ajustar `FakeLLM.generate` para que, ao receber um `request.output_type` que não seja `TranslationBatch`, devolva uma instância válida do modelo requisitado (ou execute script customizado se fornecido).

- [ ] **Step 2: Escrever testes com falha para `ExtractTermsStage` e `ConsolidateMemoryStage`**

```python
# tests/test_stage_extract_terms.py
from pathlib import Path
from types import SimpleNamespace
from translaterany.llm.fake import FakeLLM
from translaterany.stages.extract_terms import ExtractTermsStage, ExtractTermsResponse
from translaterany.memory.artifacts import ExtractTermsArtifact, MetadataArtifact
from translaterany.subtitles.normalize import NormalizedDoc, Unit, Encoding
from translaterany.pipeline.units import Episode


def test_extract_terms_stage_executes_and_outputs_artifact(tmp_path: Path):
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[
            Unit(id="0", style="Default", text="Welcome to Hoshinoumi Academy!", markers=0, events=[0]),
            Unit(id="1", style="Default", text="Use your Plunder ability.", markers=0, events=[1]),
        ],
    )
    meta = MetadataArtifact(matched=True, anilist_id=20954, title="Charlotte")

    captured: ExtractTermsArtifact | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name, model):
            if name == "normalize":
                return doc
            if name == "metadata":
                return meta
            raise ValueError(name)

    fake_response = ExtractTermsResponse(
        terms=[
            {"term": "Hoshinoumi Academy", "translation": "Academia Hoshinoumi", "category": "place"},
            {"term": "Plunder", "translation": "Saque", "category": "technique"},
        ],
        character_mentions=["Yuu"],
    )
    fake_llm = FakeLLM([fake_response])
    stage = ExtractTermsStage(client=fake_llm)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)
    ctx = SimpleNamespace(
        episode=ep,
        inputs=MockInputs(),
        output=MockOutput(),
        llm=fake_llm,
    )
    stage.run(ctx)
    assert captured is not None
    assert len(captured.terms) == 2
    assert captured.terms[0].term == "Hoshinoumi Academy"
    assert captured.character_mentions == ["Yuu"]
```

```python
# tests/test_stage_consolidate_memory.py
from pathlib import Path
from types import SimpleNamespace
from translaterany.stages.consolidate_memory import ConsolidateMemoryStage
from translaterany.memory.artifacts import ConsolidatedMemoryArtifact, ExtractTermsArtifact, MetadataArtifact
from translaterany.memory.models import GlossaryCategory, GlossaryEntry, CharacterEntry, Gender
from translaterany.pipeline.units import Series, Episode
from translaterany.pipeline.artifacts import ArtifactStore


def test_consolidate_memory_stage_produces_yamls_and_artifact(tmp_path: Path):
    meta = MetadataArtifact(
        matched=True,
        anilist_id=20954,
        title="Charlotte",
        characters=[CharacterEntry(name="Yuu Otosaka", gender=Gender.MALE)],
    )
    ep1_terms = ExtractTermsArtifact(
        episode_key="S01E01",
        terms=[GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)],
        character_mentions=["Yuu"],
    )

    captured: ConsolidatedMemoryArtifact | None = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name, model):
            if name == "metadata":
                return meta
            raise ValueError(name)

        def json_all(self, name, model):
            if name == "extract_terms":
                return {"S01E01": ep1_terms}
            raise ValueError(name)

    series = Series(name="Charlotte (2015)", path=tmp_path)
    store = ArtifactStore(tmp_path / "data")
    stage = ConsolidateMemoryStage()
    ctx = SimpleNamespace(
        series=series,
        episode=None,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=None,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.glossary_count == 1
    assert captured.characters_count == 1
    assert "Plunder" in captured.glossary_terms
    # Verifica que os arquivos YAML foram gravados em data_dir/series/<key>/memory/
    mem_dir = store.series_dir(series.key) / "memory"
    assert (mem_dir / "glossary.yaml").exists()
    assert (mem_dir / "characters.yaml").exists()
```

- [ ] **Step 3: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_stage_extract_terms.py tests/test_stage_consolidate_memory.py -v`
Expected: FAIL

- [ ] **Step 4: Implementar `ExtractTermsStage` e `ConsolidateMemoryStage`**

Implementar extração de termos com modelo Pydantic `ExtractTermsResponse`. Implementar consolidação por série integrando com `MemoryStore`.
Atualizar `DEFAULT_PIPELINE` em `src/translaterany/stages/__init__.py` para incluir `metadata`, `extract_terms` e `consolidate_memory`.
Atualizar a tupla de teste em `tests/test_inventory.py`.

- [ ] **Step 5: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_stage_extract_terms.py tests/test_stage_consolidate_memory.py tests/test_inventory.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/translaterany/stages/extract_terms.py src/translaterany/stages/consolidate_memory.py src/translaterany/llm/fake.py src/translaterany/stages/__init__.py tests/test_stage_extract_terms.py tests/test_stage_consolidate_memory.py tests/test_inventory.py
git commit -m "feat(stages): etapas extract_terms e consolidate_memory com suporte a DEFAULT_PIPELINE"
```

---

### Task 6: Injeção de Glossário na Tradução e Rastreamento de Staleness (`subtitles/chunking.py`, `subtitles/translator.py`, `stages/translate_dialogue.py`, `subtitles/texts.py`, `pipeline/reset.py`, `pipeline/status.py`, `cli/status.py`, `cli/retry.py`)

**Files:**
- Modify: `src/translaterany/subtitles/chunking.py`
- Modify: `src/translaterany/subtitles/translator.py`
- Modify: `src/translaterany/subtitles/texts.py`
- Modify: `src/translaterany/stages/translate_dialogue.py`
- Modify: `src/translaterany/pipeline/reset.py`
- Modify: `src/translaterany/pipeline/status.py`
- Modify: `src/translaterany/cli/status.py`
- Modify: `src/translaterany/cli/retry.py`
- Test: `tests/test_translate_with_glossary.py`
- Test: `tests/test_stale_invalidation.py`

**Interfaces:**
- `UnitTexts`: adiciona campo `used_terms: dict[str, str] = Field(default_factory=dict)`.
- `format_batch_prompt`: aceita `glossary: list[GlossaryEntry] = ()` e `characters: list[CharacterEntry] = ()`, formatando blocos `[GLOSSÁRIO OBRIGATÓRIO]` e `[PERSONAGENS]`.
- `DialogueBatchTranslator`: aceita `glossary` e `characters`.
- `StageTranslateDialogue`: lê `consolidate_memory`, filtra termos do episódio, passa para o tradutor e preenche `UnitTexts.used_terms`.
- `reset_stale(...)` em `pipeline/reset.py` e suporte a `--stale` em `cli/retry.py`.

- [ ] **Step 1: Escrever testes com falha para injeção de glossário e invalidação por staleness**

```python
# tests/test_translate_with_glossary.py
from pathlib import Path
from types import SimpleNamespace
from translaterany.subtitles.chunking import DialogueLine, format_batch_prompt
from translaterany.memory.models import GlossaryCategory, GlossaryEntry, CharacterEntry, Gender
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.subtitles.normalize import NormalizedDoc, Unit, Encoding
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.memory.artifacts import ConsolidatedMemoryArtifact
from translaterany.pipeline.units import Series, Episode
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.llm.fake import FakeLLM


def test_format_batch_prompt_includes_glossary_and_characters():
    lines = [DialogueLine(id="1", text="Hello from Hoshinoumi Academy!")]
    glossary = [
        GlossaryEntry(term="Hoshinoumi Academy", translation="Academia Hoshinoumi", category=GlossaryCategory.PLACE)
    ]
    characters = [CharacterEntry(name="Yuu", gender=Gender.MALE, role="main", speech_style="informal")]

    prompt = format_batch_prompt(lines, [], glossary=glossary, characters=characters)
    assert "[GLOSSÁRIO OBRIGATÓRIO]" in prompt
    assert "Hoshinoumi Academy -> Academia Hoshinoumi" in prompt
    assert "[PERSONAGENS]" in prompt
    assert "Yuu (male): informal" in prompt


def test_translate_dialogue_filters_terms_and_populates_used_terms(tmp_path: Path):
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="0", style="Default", text="Welcome to Hoshinoumi Academy!", markers=0, events=[0])],
    )
    classification = Classification(
        main_style="Default",
        units={"0": UnitClass(type="dialogue", uncertain=False, rule="test")},
        counts={"dialogue": 1},
        scenes=[],
    )
    cons_art = ConsolidatedMemoryArtifact(
        series_name="Charlotte",
        characters_count=1,
        glossary_count=2,
        characters_hash="h1",
        glossary_hash="h2",
        story_hash="h3",
        glossary_terms=["Hoshinoumi Academy", "Plunder"],
    )
    # Grava glossary.yaml
    store = ArtifactStore(tmp_path / "data")
    series = Series(name="Charlotte (2015)", path=tmp_path)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    g_entry = GlossaryEntry(term="Hoshinoumi Academy", translation="Academia Hoshinoumi")
    from translaterany.memory.store import MemoryStore

    MemoryStore(mem_dir).save_glossary([g_entry, GlossaryEntry(term="Plunder", translation="Saque")])

    captured = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured
            captured = obj

    class MockInputs:
        def json(self, name, model):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name == "consolidate_memory":
                return cons_art
            raise ValueError(name)

    fake_llm = FakeLLM(responses={"Welcome to Hoshinoumi Academy!": "Bem-vindo à Academia Hoshinoumi!"})
    stage = StageTranslateDialogue(client=fake_llm)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)
    ctx = SimpleNamespace(
        series=series,
        episode=ep,
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        llm=fake_llm,
    )
    stage.run(ctx)
    assert captured is not None
    assert captured.texts["0"] == "Bem-vindo à Academia Hoshinoumi!"
    assert "Hoshinoumi Academy" in captured.used_terms
    assert "Plunder" not in captured.used_terms  # Plunder não foi mencionada no episódio
```

```python
# tests/test_stale_invalidation.py
from pathlib import Path
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import EpisodeManifest, ManifestSet
from translaterany.pipeline.units import Series, Episode
from translaterany.subtitles.texts import UnitTexts
from translaterany.memory.models import GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.reset import reset_stale


def test_stale_detection_and_reset(tmp_path: Path):
    store = ArtifactStore(tmp_path / "data")
    series = Series(name="Charlotte (2015)", path=tmp_path)
    ep = Episode(key="S01E01", source=tmp_path / "S01E01.mkv", number=1, season=1)

    # 1. Salva glossary inicial
    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)
    entry = GlossaryEntry(term="Plunder", translation="Pilhar")
    mem_store.save_glossary([entry])
    initial_hash = entry.content_hash()

    # 2. Grava artefato translate_dialogue com initial_hash
    art_dir = store.artifact_dir(series.key, ep.key)
    art_dir.mkdir(parents=True, exist_ok=True)
    texts = UnitTexts(texts={"0": "Pilhar"}, used_terms={"Plunder": initial_hash})
    (art_dir / "translate_dialogue.json").write_text(texts.model_dump_json(), encoding="utf-8")

    # 3. Cria manifest com status done
    manifests = ManifestSet(store, series, [ep])
    manifests.episodes[ep.key].stages["translate_dialogue"] = SimpleNamespace(
        status="done", key="k", artifact="translate_dialogue.json", artifact_hash="h"
    )
    manifests.save(ep)

    # 4. Modifica termo no glossary.yaml
    updated_entry = GlossaryEntry(term="Plunder", translation="Saque")
    mem_store.save_glossary([updated_entry])

    # 5. Executa reset_stale
    reset_count = reset_stale(store, series, [ep])
    assert reset_count == 1

    # 6. Verifica que manifest teve translate_dialogue removido/resetado
    reloaded_manifest = store.load_manifest(series.key, ep.key)
    assert "translate_dialogue" not in reloaded_manifest.stages
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_translate_with_glossary.py tests/test_stale_invalidation.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar injeção de glossário e reset de staleness**

- Estender `UnitTexts` com `used_terms: dict[str, str] = Field(default_factory=dict)`.
- Atualizar `format_batch_prompt` em `chunking.py` e `DialogueBatchTranslator` em `translator.py`.
- Atualizar `StageTranslateDialogue.run` para filtrar termos do episódio e popular `used_terms`.
- Implementar `reset_stale(store, series, episodes)` em `src/translaterany/pipeline/reset.py`.
- Atualizar `src/translaterany/pipeline/status.py` e `src/translaterany/cli/status.py` para exibir aviso quando houver termos stale.
- Atualizar `src/translaterany/cli/retry.py` para aceitar `--stale` tornando `--from` opcional.

- [ ] **Step 4: Executar testes para verificar aprovação**

Run: `uv run pytest tests/test_translate_with_glossary.py tests/test_stale_invalidation.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/chunking.py src/translaterany/subtitles/translator.py src/translaterany/subtitles/texts.py src/translaterany/stages/translate_dialogue.py src/translaterany/pipeline/reset.py src/translaterany/pipeline/status.py src/translaterany/cli/status.py src/translaterany/cli/retry.py tests/test_translate_with_glossary.py tests/test_stale_invalidation.py
git commit -m "feat(translate): injeção de glossário na tradução e reset seletivo por staleness"
```

---

### Task 7: Comando CLI `memory`, Testes Ponta a Ponta do M3 e Conclusão (`cli/memory.py`, `cli/app.py`, `tests/test_cli_memory.py`, `tests/test_m3_e2e.py`, `STATE.md`)

**Files:**
- Create: `src/translaterany/cli/memory.py`
- Modify: `src/translaterany/cli/app.py`
- Modify: `src/translaterany/cli/__init__.py`
- Create: `tests/test_cli_memory.py`
- Create: `tests/test_m3_e2e.py`
- Modify: `STATE.md`

**Interfaces:**
- Produces: Comando `translaterany memory <path> [--export <dir>] [--import <file>] [--refresh]` registrado no app Typer.
- Produces: Teste de integração E2E do M3 com pipeline completo de 11 etapas (`inventory` → `metadata` → `select_track` → `extract` → `normalize` → `classify` → `extract_terms` → `consolidate_memory` → `translate_dialogue` → `write` → `publish`).

- [ ] **Step 1: Escrever testes com falha para o comando `memory` e teste E2E do M3**

```python
# tests/test_cli_memory.py
from pathlib import Path
from typer.testing import CliRunner
from translaterany.cli.app import app
from translaterany.memory.models import GlossaryCategory, GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.units import Series

runner = CliRunner()


def test_memory_command_help():
    result = runner.invoke(app, ["memory", "--help"])
    assert result.exit_code == 0
    assert "memória da série" in result.output.lower()


def test_memory_command_displays_glossary_table(tmp_path: Path):
    series_dir = tmp_path / "Charlotte (2015)"
    series_dir.mkdir()
    data_dir = tmp_path / "data"
    store = ArtifactStore(data_dir)
    series = Series(name="Charlotte (2015)", path=series_dir)
    mem_dir = store.series_dir(series.key) / "memory"
    mem_dir.mkdir(parents=True, exist_ok=True)
    MemoryStore(mem_dir).save_glossary(
        [GlossaryEntry(term="Plunder", translation="Saque", category=GlossaryCategory.TECHNIQUE)]
    )

    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text(f'[general]\ndata_dir = "{data_dir}"\n', encoding="utf-8")

    result = runner.invoke(app, ["--config", str(cfg_file), "memory", str(series_dir)])
    assert result.exit_code == 0
    assert "Plunder" in result.output
    assert "Saque" in result.output
```

```python
# tests/test_m3_e2e.py
from pathlib import Path
import httpx
from translaterany.config.loader import load_config_from_str
from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.runner import PipelineRunner
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.stages.extract_terms import ExtractTermsResponse
from tests.mkvtools import create_synthetic_mkv, make_mkv, Sub, FULL_ASS


def test_m3_pipeline_end_to_end_with_memory(tmp_path: Path, monkeypatch):
    # 1. Mock de APIs externas
    mock_anilist = {
        "data": {
            "Media": {
                "id": 20954,
                "idMal": 28999,
                "title": {"romaji": "Charlotte", "english": "Charlotte", "native": "シャーロット"},
                "seasonYear": 2015,
                "episodes": 1,
                "genres": ["Supernatural"],
                "characters": {"edges": []},
            }
        }
    }
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: httpx.Response(200, json=mock_anilist))
    monkeypatch.setattr(httpx, "get", lambda *a, **kw: httpx.Response(200, json={"data": []}))

    # 2. Criação do MKV sintético com termo especial
    series_dir = tmp_path / "Charlotte (2015)"
    video_path = series_dir / "Season 1" / "S01E01.mkv"
    create_synthetic_mkv(
        video_path,
        dialogues=[
            ("00:00:01.000", "00:00:03.000", "Welcome to Hoshinoumi Academy!"),
            ("00:00:04.000", "00:00:06.000", "He has the Plunder ability."),
        ],
    )

    # 3. FakeLLM respondendo à extração e à tradução com o termo do glossário
    fake_extract = ExtractTermsResponse(
        terms=[
            {"term": "Hoshinoumi Academy", "translation": "Academia Hoshinoumi", "category": "place"},
            {"term": "Plunder", "translation": "Saque", "category": "technique"},
        ]
    )
    fake_llm = FakeLLM(
        script=[fake_extract],
        responses={
            "Welcome to Hoshinoumi Academy!": "Bem-vindo à Academia Hoshinoumi!",
            "He has the Plunder ability.": "Ele tem a habilidade Saque.",
        },
    )

    data_dir = tmp_path / "data"
    config = load_config_from_str(f'[general]\ndata_dir = "{data_dir}"\n')
    runner = PipelineRunner(config=config, client=fake_llm, store=ArtifactStore(data_dir))
    summary = runner.run_series(series_dir)
    assert not summary.failed

    # 4. Verifica geração dos arquivos YAML de memória
    store = ArtifactStore(data_dir)
    series_key = "charlotte-2015"
    mem_dir = store.series_dir(series_key) / "memory"
    assert (mem_dir / "glossary.yaml").exists()
    assert (mem_dir / "story.yaml").exists()
    assert (mem_dir / "characters.yaml").exists()

    # 5. Verifica arquivo .pt-BR.ass gerado com a tradução padronizada
    ass_files = list(series_dir.glob("**/*.pt-BR.ass"))
    assert len(ass_files) == 1
    content = ass_files[0].read_text(encoding="utf-8")
    assert "; TranslaterAny" in content
    assert "Academia Hoshinoumi" in content
    assert "Saque" in content
```

- [ ] **Step 2: Executar testes para confirmar falha**

Run: `uv run pytest tests/test_cli_memory.py tests/test_m3_e2e.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar comando CLI `memory` e registrar no `app.py`**

Criar `src/translaterany/cli/memory.py` com renderização em tabela Rich, `--export`, `--import`, `--refresh`. Atualizar `STATE.md` marcando M3 como concluído (`✅`).

- [ ] **Step 4: Executar suíte completa de testes do projeto**

Run: `uv run pytest`
Expected: Todos os testes passando (293 existentes + novos testes do M3).

- [ ] **Step 5: Executar linter e formatador**

Run: `uv run ruff check .`
Expected: Limpo sem erros.

- [ ] **Step 6: Commit**

```bash
git add src/translaterany/cli/memory.py src/translaterany/cli/app.py src/translaterany/cli/__init__.py tests/test_cli_memory.py tests/test_m3_e2e.py STATE.md
git commit -m "feat(cli): comando memory, testes E2E do Marco 3 e conclusão no STATE.md"
```
