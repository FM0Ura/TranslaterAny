# M9 — Suporte Universal a Idiomas · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que o TranslaterAny traduza e refine legendas entre quaisquer idiomas de origem (`source_language`) e destino (`target_language`), com catálogo canônico `LanguageRegistry`, arquitetura modular `LanguageProfile` (suporte completo à tríade inicial PT-BR, ES e EN + fallback `GenericProfile`) e parametrização universal de faixas, prompts, LanguageTool e publicação.

**Architecture:** A camada de idiomas reside em `src/translaterany/languages`, provendo a entidade `LanguageInfo`, o catálogo `LanguageRegistry` e a interface `LanguageProfile` com implementações dedicadas para PT-BR, Espanhol, Inglês e Genérico. O `StageContext` carrega os idiomas resolvidos para todas as etapas do pipeline, permitindo que a seleção de faixas (`select_track`), a extração, todos os prompts de IA, a verificação ortográfica (`LanguageTool`) e a publicação (`publish`/`remux`) operem dinamicamente e sem acoplamento rígido a um par específico.

**Tech Stack:** Python 3.14 (`uv`), pydantic 2, pytest, pysubs2, httpx.

**Spec:** [`docs/superpowers/specs/2026-10-04-m9-suporte-universal-idiomas-design.md`](../specs/2026-10-04-m9-suporte-universal-idiomas-design.md)

## Global Constraints

- Python **3.14**; dependências existentes do projeto (`pydantic`, `pysubs2`, `httpx`).
- Identificadores e nomes de código em **inglês**; logs, mensagens ao usuário e corpo dos prompts de instrução em **PT-BR**.
- Padrões inalterados: `source_language = "en"` e `target_language = "pt-BR"`.
- Zero regressão nos 659 testes existentes da suíte (`uv run pytest -q`).
- Testes **somente sintéticos** (`FakeLLM`, mocks de áudio/vídeo/mkv); nunca versionar mídias reais.
- Commits em português no formato convencional: `tipo(escopo): descrição`.

## Review Focus

1. **Tolerância e normalização de idiomas:** Strings como `"pt-BR"`, `"pt_br"`, `"por"`, `"português"`, `"ja"`, `"jpn"`, `"japonês"` devem resolver confiavelmente para a mesma entidade canônica `LanguageInfo`. Testado na Tarefa 1.
2. **Resiliência para códigos não cadastrados:** Informar um idioma arbitrário (ex.: `"sw"` para Swahili ou `"nl"` para Holandês) nunca deve quebrar o programa; o `LanguageRegistry` gera dinamicamente uma `LanguageInfo` válida com `GenericProfile`. Testado na Tarefa 1 e 3.
3. **Precedência estrita de 3 níveis:** A flag da CLI (`--source`/`--target`) deve sobrepor `series.toml`, que deve sobrepor `config.toml`. Testado na Tarefa 2.
4. **Precisão e não-vazamento de prompts:** Todos os prompts parametrizados devem ter suas variáveis `{source}` e `{target}` devidamente interpoladas com os nomes em português dos idiomas, sem deixar chaves não resolvidas. Testado na Tarefa 7.
5. **Prevenção de colisão precisa:** O seletor de faixas (`select_track`) deve checar colisão no idioma `target_language` configurado e relatar o nome correto do idioma na exceção `NoTrack`. Testado na Tarefa 6.

---

## Mapa de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `src/translaterany/languages/models.py` (novo) | Dataclasses `LanguageInfo` e `TreatmentReport` |
| `src/translaterany/languages/registry.py` (novo) | Catálogo central `LanguageRegistry` (normalização, aliases, BCP-47, ISO 639-1/2, matching de faixas) |
| `src/translaterany/languages/profile.py` (novo) | Protocolo base `LanguageProfile` e fábrica `get_profile()` |
| `src/translaterany/languages/profiles/generic.py` (novo) | `GenericProfile` para fallback universal sem falsos positivos |
| `src/translaterany/languages/profiles/portuguese.py` (novo) | `PortugueseProfile` (encapsula regras consolidadas da v1.0.0) |
| `src/translaterany/languages/profiles/spanish.py` (novo) | `SpanishProfile` (regras em espanhol: tú/usted, el/la presidente, negações, profanidades) |
| `src/translaterany/languages/profiles/english.py` (novo) | `EnglishProfile` (regras em inglês: he/she/they, formalidade, contrações, profanidades) |
| `src/translaterany/languages/__init__.py` (novo) | Exportação limpa da camada de idiomas |
| `src/translaterany/config/model.py` (mod.) | Adiciona `source_language` e `target_language` em `AppConfig` e `SeriesConfig` |
| `src/translaterany/pipeline/stage.py` (mod.) | Atributos `source_language`, `target_language` e `target_profile` no `StageContext` |
| `src/translaterany/pipeline/runner.py` (mod.) | Resolução de idiomas e inicialização do contexto com os perfis adequados |
| `src/translaterany/cli/run.py` (mod.) | Flags `--source` / `-s` e `--target` / `-t` no comando `run` |
| `src/translaterany/media/tracks.py` (mod.) | `select_track` filtrando por `source_language` e checando colisão por `target_language` |
| `src/translaterany/stages/select_track.py` (mod.) | Integração de `select_track` com os idiomas do `StageContext` |
| `src/translaterany/stages/extract.py` (mod.) | Heurística `looks_english` condicionada a `source_language == "en"` |
| `src/translaterany/subtitles/translator.py` (mod.) | `SYSTEM_INSTRUCTIONS` parametrizado por idioma de origem e destino |
| `src/translaterany/stages/translate_dialogue.py` (mod.) | Injeção dinâmica de idiomas no prompt de tradução |
| `src/translaterany/stages/translate_signs.py` (mod.) | Injeção dinâmica de idiomas no prompt de placas |
| `src/translaterany/stages/translate_songs.py` (mod.) | Injeção dinâmica de idiomas no prompt de músicas |
| `src/translaterany/stages/review_meaning.py` (mod.) | Injeção dinâmica de idiomas no prompt de revisão |
| `src/translaterany/stages/colloquial.py` (mod.) | Consulta `context.target_profile` para sinais de triagem coloquial |
| `src/translaterany/stages/treatment_consistency.py` (mod.) | Consulta `context.target_profile` para relatório de coerência de tratamento |
| `src/translaterany/stages/final_readthrough.py` (mod.) | Leitura corrida instruída no idioma alvo do contexto |
| `src/translaterany/stages/qa_loop.py` (mod.) | Tags de prompt e blocos de feedback com códigos canônicos dos idiomas |
| `src/translaterany/stages/orthography.py` (mod.) | Passa `target_language.languagetool_code` para o LanguageTool |
| `src/translaterany/util/doctor.py` (mod.) | Checa suporte aos idiomas configurados no LanguageTool |
| `src/translaterany/stages/publish.py` (mod.) | Publica arquivo externo `<stem>.{target_language.code}.ass` |
| `src/translaterany/media/remux.py` (mod.) | Injeta `--language 0:{code}` e nome legível da faixa no mkvmerge |

---

### Task 1: Catálogo e Normalização de Idiomas (`LanguageInfo` e `LanguageRegistry`)

**Files:**
- Create: `src/translaterany/languages/models.py`
- Create: `src/translaterany/languages/registry.py`
- Create: `src/translaterany/languages/__init__.py`
- Test: `tests/languages/test_registry.py`

**Interfaces:**
- Consumes: `dataclasses.dataclass`.
- Produces: `LanguageInfo`, `LanguageRegistry.resolve()`, `LanguageRegistry.matches()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/languages/test_registry.py
import pytest
from translaterany.languages.models import LanguageInfo
from translaterany.languages.registry import LanguageRegistry


def test_resolve_standard_codes() -> None:
    pt = LanguageRegistry.resolve("pt-BR")
    assert pt.code == "pt-BR"
    assert pt.iso639_1 == "pt"
    assert pt.iso639_2 == "por"
    assert "português" in pt.name_pt.lower()

    en = LanguageRegistry.resolve("en")
    assert en.code == "en"
    assert en.iso639_1 == "en"
    assert en.iso639_2 == "eng"
    assert "inglês" in en.name_pt.lower()

    ja = LanguageRegistry.resolve("ja")
    assert ja.code == "ja"
    assert ja.iso639_2 == "jpn"
    assert "japonês" in ja.name_pt.lower()


def test_resolve_flexible_aliases() -> None:
    assert LanguageRegistry.resolve("pt_br").code == "pt-BR"
    assert LanguageRegistry.resolve("PT-br").code == "pt-BR"
    assert LanguageRegistry.resolve("por").code == "pt-BR"
    assert LanguageRegistry.resolve("portugues").code == "pt-BR"
    assert LanguageRegistry.resolve("português").code == "pt-BR"

    assert LanguageRegistry.resolve("jpn").code == "ja"
    assert LanguageRegistry.resolve("japanese").code == "ja"
    assert LanguageRegistry.resolve("japonês").code == "ja"

    assert LanguageRegistry.resolve("spa").code == "es"
    assert LanguageRegistry.resolve("espanhol").code == "es"
    assert LanguageRegistry.resolve("spanish").code == "es"


def test_resolve_unregistered_fallback() -> None:
    sw = LanguageRegistry.resolve("sw")
    assert sw.code == "sw"
    assert sw.iso639_1 == "sw"
    assert sw.iso639_2 == "sw"
    assert sw.languagetool_code == "sw"


def test_matches_mkv_tracks() -> None:
    pt = LanguageRegistry.resolve("pt-BR")
    assert LanguageRegistry.matches("por", pt) is True
    assert LanguageRegistry.matches("pt-BR", pt) is True
    assert LanguageRegistry.matches("pt", pt) is True
    assert LanguageRegistry.matches("eng", pt) is False

    ja = LanguageRegistry.resolve("ja")
    assert LanguageRegistry.matches("jpn", ja) is True
    assert LanguageRegistry.matches("ja", ja) is True
    assert LanguageRegistry.matches("por", ja) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/languages/test_registry.py -v`
Expected: FAIL with ModuleNotFoundError: No module named 'translaterany.languages'

- [ ] **Step 3: Implement `models.py`, `registry.py` and `__init__.py`**

Implementar dataclass `LanguageInfo` em `models.py` e classe `LanguageRegistry` em `registry.py` com dicionário de aliases normalizados (`unicodedata.normalize`), mapa dos principais idiomas de anime e cinema (`pt-BR`, `en`, `ja`, `es`, `fr`, `de`, `it`, `zh`, `ko`, `ru`, `ar`, `hi`, etc.), método `resolve(query)` com tolerância total e método `matches(track_lang, target)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/languages/test_registry.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/languages/ tests/languages/test_registry.py
git commit -m "feat(languages): add LanguageInfo and LanguageRegistry catalog"
```

---

### Task 2: Configuração, Precedência e Inicialização de Contexto

**Files:**
- Modify: `src/translaterany/config/model.py`
- Modify: `src/translaterany/pipeline/stage.py`
- Modify: `src/translaterany/pipeline/runner.py`
- Modify: `src/translaterany/cli/run.py`
- Test: `tests/languages/test_config_languages.py`

**Interfaces:**
- Consumes: `LanguageRegistry.resolve()`.
- Produces: `AppConfig.source_language`, `AppConfig.target_language`, `StageContext.source_language`, `StageContext.target_language`.

- [ ] **Step 1: Write the failing test**

```python
# tests/languages/test_config_languages.py
import pytest
from translaterany.config import load_config_from_str
from translaterany.config.model import AppConfig, ConfigError


def test_default_languages_in_config() -> None:
    cfg = load_config_from_str("")
    assert cfg.source_language == "en"
    assert cfg.target_language == "pt-BR"


def test_custom_languages_in_config() -> None:
    raw = """
    source_language = "ja"
    target_language = "es"
    """
    cfg = load_config_from_str(raw)
    assert cfg.source_language == "ja"
    assert cfg.target_language == "es"


def test_same_languages_raises_config_error() -> None:
    raw = """
    source_language = "pt-BR"
    target_language = "pt-BR"
    """
    with pytest.raises(ValueError, match="não podem ser iguais"):
        load_config_from_str(raw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/languages/test_config_languages.py -v`
Expected: FAIL with AttributeError: 'AppConfig' object has no attribute 'source_language'

- [ ] **Step 3: Implement config fields, validation, CLI flags and context binding**

1. Em `src/translaterany/config/model.py`: adicionar `source_language: str = "en"` e `target_language: str = "pt-BR"` em `AppConfig` e `SeriesConfig`, com `@model_validator(mode="after")` garantindo que não sejam o mesmo idioma.
2. Em `src/translaterany/pipeline/stage.py`: adicionar campos `source_language: LanguageInfo` e `target_language: LanguageInfo` no `StageContext`.
3. Em `src/translaterany/cli/run.py`: adicionar opções `--source` / `-s` e `--target` / `-t` na função `run`.
4. Em `src/translaterany/pipeline/runner.py`: resolver os idiomas com `LanguageRegistry.resolve` respeitando a precedência CLI > SeriesConfig > AppConfig e injetá-los no `StageContext`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/languages/test_config_languages.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/config/model.py src/translaterany/pipeline/stage.py src/translaterany/pipeline/runner.py src/translaterany/cli/run.py tests/languages/test_config_languages.py
git commit -m "feat(config): support source_language and target_language with 3-tier precedence"
```

---

### Task 3: Interface `LanguageProfile` e `GenericProfile`

**Files:**
- Create: `src/translaterany/languages/profile.py`
- Create: `src/translaterany/languages/profiles/generic.py`
- Modify: `src/translaterany/languages/__init__.py`
- Test: `tests/languages/test_profiles_generic.py`

**Interfaces:**
- Consumes: `LanguageInfo`, `TreatmentReport`.
- Produces: `LanguageProfile` protocol, `GenericProfile`, `get_profile(lang: LanguageInfo)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/languages/test_profiles_generic.py
from translaterany.languages.models import LanguageInfo
from translaterany.languages.profile import get_profile
from translaterany.languages.profiles.generic import GenericProfile


def test_generic_profile_fallback() -> None:
    info = LanguageInfo("nl", "nl", "nld", "holandês", "Dutch", "Nederlands", "nl")
    prof = get_profile(info)
    assert isinstance(prof, GenericProfile)
    assert prof.info.code == "nl"
    assert prof.default_cps == 17.0
    assert prof.default_cpl == 42


def test_generic_profile_safe_treatment_and_colloquial() -> None:
    info = LanguageInfo("nl", "nl", "nld", "holandês", "Dutch", "Nederlands", "nl")
    prof = get_profile(info)
    # Generic não emite falsos positivos de tratamento
    report = prof.scan_treatment([{"id": "1", "text": "Hallo"}], {})
    assert len(report.divergent_reasons) == 0

    # Generic não gera sinais de triagem inválidos
    signals = prof.colloquial_signals([], {}, set())
    assert len(signals) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/languages/test_profiles_generic.py -v`
Expected: FAIL with ModuleNotFoundError: No module named 'translaterany.languages.profile'

- [ ] **Step 3: Implement `LanguageProfile` protocol and `GenericProfile`**

1. Em `src/translaterany/languages/models.py`: definir dataclass `TreatmentReport(divergent_reasons: dict[str, list[str]])`.
2. Em `src/translaterany/languages/profile.py`: definir `LanguageProfile(Protocol)` e função `get_profile(lang: LanguageInfo) -> LanguageProfile`.
3. Em `src/translaterany/languages/profiles/generic.py`: implementar `GenericProfile` com expressões regulares neutras e fallbacks seguros.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/languages/test_profiles_generic.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/languages/profile.py src/translaterany/languages/profiles/ tests/languages/test_profiles_generic.py
git commit -m "feat(languages): add LanguageProfile interface and GenericProfile fallback"
```

---

### Task 4: Perfil de Português (`PortugueseProfile`) com 100% de Paridade

**Files:**
- Create: `src/translaterany/languages/profiles/portuguese.py`
- Modify: `src/translaterany/languages/profile.py` (registra `pt` -> `PortugueseProfile`)
- Modify: `src/translaterany/checks/lexicon.py` (reexporta padrões a partir de `PortugueseProfile` ou preserva compatibilidade)
- Test: `tests/languages/test_profile_portuguese.py`

**Interfaces:**
- Consumes: `refine/treatment.py`, `refine/triage.py`, `checks/lexicon.py`.
- Produces: `PortugueseProfile` compatível com `LanguageProfile`.

- [ ] **Step 1: Write the failing test**

```python
# tests/languages/test_profile_portuguese.py
from translaterany.languages.registry import LanguageRegistry
from translaterany.languages.profile import get_profile
from translaterany.languages.profiles.portuguese import PortugueseProfile


def test_get_portuguese_profile() -> None:
    pt_info = LanguageRegistry.resolve("pt-BR")
    prof = get_profile(pt_info)
    assert isinstance(prof, PortugueseProfile)
    assert prof.info.code == "pt-BR"
    assert prof.negation_pattern.search("não")
    assert prof.negation_pattern.search("nunca")
    assert prof.profanity_pattern.search("merda")


def test_portuguese_treatment_scan() -> None:
    pt_info = LanguageRegistry.resolve("pt-BR")
    prof = get_profile(pt_info)
    lines = [
        {"id": "u1", "text": "Você veio aqui?", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
        {"id": "u2", "text": "Tu disseste a verdade?", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
    ]
    report = prof.scan_treatment(lines, {})
    # Deve detectar divergência você/tu
    assert "u2" in report.divergent_reasons or "u1" in report.divergent_reasons
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/languages/test_profile_portuguese.py -v`
Expected: FAIL with ModuleNotFoundError or AssertionError

- [ ] **Step 3: Implement `PortugueseProfile`**

Implementar `src/translaterany/languages/profiles/portuguese.py` consolidando as regras existentes:
1. Léxico: `PT_NEGATION`, `PT_PROFANITY`, `EN_FUNCTION_WORDS`, termos de Portugal (`PT_PT_WORDS`) e espanholismos.
2. Tratamento: encapsular `scan_treatment_consistency` de `refine/treatment.py`.
3. Triagem coloquial: encapsular `colloquial_signals` de `refine/triage.py` (ênclise, conectivos formais, sujeitos redundantes, pronomes arcaicos).
4. Registrar `pt` na fábrica `get_profile`.

- [ ] **Step 4: Run test and regression check to verify it passes**

Run: `uv run pytest tests/languages/test_profile_portuguese.py -v`
Run: `uv run pytest tests/test_treatment_consistency.py tests/test_colloquial.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/languages/profiles/portuguese.py src/translaterany/languages/profile.py tests/languages/test_profile_portuguese.py
git commit -m "feat(languages): implement PortugueseProfile with full parity"
```

---

### Task 5: Perfis de Espanhol e Inglês (`SpanishProfile` e `EnglishProfile`)

**Files:**
- Create: `src/translaterany/languages/profiles/spanish.py`
- Create: `src/translaterany/languages/profiles/english.py`
- Modify: `src/translaterany/languages/profile.py` (registra `es` e `en`)
- Test: `tests/languages/test_profiles_es_en.py`

**Interfaces:**
- Consumes: `LanguageProfile`, `LanguageInfo`, `TreatmentReport`.
- Produces: `SpanishProfile`, `EnglishProfile`.

- [ ] **Step 1: Write the failing test**

```python
# tests/languages/test_profiles_es_en.py
from translaterany.languages.registry import LanguageRegistry
from translaterany.languages.profile import get_profile
from translaterany.languages.profiles.spanish import SpanishProfile
from translaterany.languages.profiles.english import EnglishProfile


def test_spanish_profile_lexicon_and_treatment() -> None:
    es_info = LanguageRegistry.resolve("es")
    prof = get_profile(es_info)
    assert isinstance(prof, SpanishProfile)
    assert prof.negation_pattern.search("jamás")
    assert prof.profanity_pattern.search("mierda")
    assert prof.formal_connectives_pattern.search("no obstante")

    # Scanner tú vs usted
    lines = [
        {"id": "u1", "text": "¿Tú quieres venir?", "speaker": "Carlos", "listener": "Elena", "confidence": "high"},
        {"id": "u2", "text": "Usted sabe que sí.", "speaker": "Carlos", "listener": "Elena", "confidence": "high"},
    ]
    report = prof.scan_treatment(lines, {})
    assert len(report.divergent_reasons) > 0


def test_english_profile_lexicon_and_pronouns() -> None:
    en_info = LanguageRegistry.resolve("en")
    prof = get_profile(en_info)
    assert isinstance(prof, EnglishProfile)
    assert prof.negation_pattern.search("cannot")
    assert prof.profanity_pattern.search("bullshit")
    assert prof.formal_connectives_pattern.search("furthermore")

    # Scanner de pronomes com gênero definido
    lines = [
        {"id": "u1", "text": "He is my best friend.", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
        {"id": "u2", "text": "She went to the market.", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
    ]
    char_gender = {"Bob": "male"}
    report = prof.scan_treatment(lines, char_gender)
    # Se uma fala usa 'she' ao falar diretamente de Bob, reporta divergência
    assert isinstance(report.divergent_reasons, dict)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/languages/test_profiles_es_en.py -v`
Expected: FAIL with ModuleNotFoundError: No module named 'translaterany.languages.profiles.spanish'

- [ ] **Step 3: Implement `SpanishProfile` and `EnglishProfile`**

1. Em `src/translaterany/languages/profiles/spanish.py`:
   - Negações: `\b(?:no|nunca|jamás|nadie|nada|ningún|ninguno|ninguna|tampoco)\b`.
   - Profanidades: `\b(?:mierda|joder|coño|puta|puto|cabrón|cabrona|gilipollas|pendejo|pendeja|hijo de puta|hostia)\b`.
   - Conectivos formais: `\b(?:no obstante|sin embargo|asimismo|por consiguiente|por ende)\b`.
   - Scanner de tratamento: analisa pronomes `tú`/`vos` vs `usted` e concordância de artigos definidos (*el presidente / la presidente*, *el líder / la líder*).
2. Em `src/translaterany/languages/profiles/english.py`:
   - Negações: `\b(?:not|never|no|nobody|nothing|none|neither|nor|without|nowhere|cannot)\b|n't\b`.
   - Profanidades: `\b(?:shit|fuck\w*|damn\w*|bitch\w*|bastard\w*|ass|asshole|crap|bullshit)\b`.
   - Conectivos formais: `\b(?:furthermore|moreover|henceforth|nevertheless|nonetheless)\b`.
   - Scanner de pronomes: consistência de gênero (*he/him* vs *she/her* vs *they/them*).
3. Registrar `es` e `en` na fábrica `get_profile`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/languages/test_profiles_es_en.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/languages/profiles/spanish.py src/translaterany/languages/profiles/english.py src/translaterany/languages/profile.py tests/languages/test_profiles_es_en.py
git commit -m "feat(languages): implement SpanishProfile and EnglishProfile"
```

---

### Task 6: Seleção e Extração de Faixas Multilíngue (`select_track` e `extract`)

**Files:**
- Modify: `src/translaterany/media/tracks.py`
- Modify: `src/translaterany/stages/select_track.py`
- Modify: `src/translaterany/stages/extract.py`
- Test: `tests/media/test_tracks_multilingual.py`

**Interfaces:**
- Consumes: `LanguageRegistry.matches()`, `context.source_language`, `context.target_language`.
- Produces: `select_track(info, source_lang=..., target_lang=..., preferred=..., force=...)`.

- [x] **Step 1: Write the failing test**

```python
# tests/media/test_tracks_multilingual.py
import pytest
from translaterany.languages.registry import LanguageRegistry
from translaterany.media.mkv import MkvInfo, Track
from translaterany.media.tracks import NoTrack, select_track


def test_select_track_by_source_language() -> None:
    tracks = [
        Track(id=0, type="subtitles", codec_id="S_TEXT/ASS", name="Dialog", language="jpn", default=True, forced=False, hearing_impaired=False),
        Track(id=1, type="subtitles", codec_id="S_TEXT/ASS", name="English", language="eng", default=False, forced=False, hearing_impaired=False),
    ]
    info = MkvInfo(tracks=tuple(tracks), attachments=(), duration_ns=None)
    
    # Buscando Japonês como origem
    ja = LanguageRegistry.resolve("ja")
    pt = LanguageRegistry.resolve("pt-BR")
    sel_ja = select_track(info, source_lang=ja, target_lang=pt)
    assert sel_ja.chosen.id == 0

    # Buscando Inglês como origem
    en = LanguageRegistry.resolve("en")
    sel_en = select_track(info, source_lang=en, target_lang=pt)
    assert sel_en.chosen.id == 1


def test_collision_check_with_target_language() -> None:
    tracks = [
        Track(id=0, type="subtitles", codec_id="S_TEXT/ASS", name="English", language="eng", default=True, forced=False, hearing_impaired=False),
        Track(id=1, type="subtitles", codec_id="S_TEXT/ASS", name="Español Latino", language="spa", default=False, forced=False, hearing_impaired=False),
    ]
    info = MkvInfo(tracks=tuple(tracks), attachments=(), duration_ns=None)
    en = LanguageRegistry.resolve("en")
    es = LanguageRegistry.resolve("es")

    # Alvo Espanhol: deve acusar colisão por já existir legenda em espanhol
    with pytest.raises(NoTrack, match="já existe legenda espanhol"):
        select_track(info, source_lang=en, target_lang=es, force=False)

    # Com force=True deve permitir
    sel = select_track(info, source_lang=en, target_lang=es, force=True)
    assert sel.chosen.id == 0
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/media/test_tracks_multilingual.py -v`
Expected: FAIL with TypeError or unexpected arguments in select_track

- [x] **Step 3: Update `tracks.py`, `select_track.py`, and `extract.py`**

1. Em `src/translaterany/media/tracks.py`:
   - Atualizar `select_track` para receber `source_lang: LanguageInfo | None = None` e `target_lang: LanguageInfo | None = None`.
   - Se `None`, usar defaults `en` e `pt-BR`.
   - Colisão: verificar `LanguageRegistry.matches(t.language, target_lang)`.
   - Candidatos: verificar `LanguageRegistry.matches(t.language, source_lang)`.
2. Em `src/translaterany/stages/select_track.py`:
   - Passar `context.source_language` e `context.target_language` para `select_track`.
3. Em `src/translaterany/stages/extract.py`:
   - Só acionar heurística `looks_english` se `context.source_language.iso639_1 == "en"`.

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/media/test_tracks_multilingual.py -v`
Run: `uv run pytest tests/test_select_track.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add src/translaterany/media/tracks.py src/translaterany/stages/select_track.py src/translaterany/stages/extract.py tests/media/test_tracks_multilingual.py
git commit -m "feat(media): make select_track filter by source_lang and check collision by target_lang"
```

---

### Task 7: Parametrização dos Prompts das Etapas de IA e Refinamento

**Files:**
- Modify: `src/translaterany/subtitles/translator.py`
- Modify: `src/translaterany/stages/translate_dialogue.py`
- Modify: `src/translaterany/stages/translate_signs.py`
- Modify: `src/translaterany/stages/translate_songs.py`
- Modify: `src/translaterany/stages/review_meaning.py`
- Modify: `src/translaterany/stages/colloquial.py`
- Modify: `src/translaterany/stages/treatment_consistency.py`
- Modify: `src/translaterany/stages/final_readthrough.py`
- Modify: `src/translaterany/stages/qa_loop.py`
- Test: `tests/stages/test_prompts_multilingual.py`

**Interfaces:**
- Consumes: `context.source_language`, `context.target_language`, `context.target_profile`.
- Produces: Prompts gerados dinamicamente com os idiomas corretos.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/test_prompts_multilingual.py
from translaterany.languages.registry import LanguageRegistry
from translaterany.subtitles.translator import render_system_instructions
from translaterany.stages.review_meaning import ReviewMeaningStage
from translaterany.pipeline.stage import StageContext


def test_system_instructions_dynamic_languages() -> None:
    ja = LanguageRegistry.resolve("ja")
    es = LanguageRegistry.resolve("es")
    instructions = render_system_instructions(source=ja, target=es)
    assert "japonês para espanhol" in instructions.lower()
    assert "fansubs de alta qualidade em espanhol" in instructions.lower()


def test_review_meaning_prompt_dynamic_languages() -> None:
    ja = LanguageRegistry.resolve("ja")
    es = LanguageRegistry.resolve("es")
    stage = ReviewMeaningStage()
    ctx = StageContext(
        stage_names=["review_meaning"],
        stage_index=0,
        source_language=ja,
        target_language=es,
    )
    instr = stage.get_instructions(ctx)
    assert "japonês -> espanhol" in instr.lower()
    assert "espanhol" in instr.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_prompts_multilingual.py -v`
Expected: FAIL with ImportError or AttributeError

- [ ] **Step 3: Parametrize all AI stage prompt templates**

1. Em `src/translaterany/subtitles/translator.py`:
   - Criar `render_system_instructions(source: LanguageInfo, target: LanguageInfo) -> str`.
2. Em `src/translaterany/stages/translate_dialogue.py`, `translate_signs.py`, `translate_songs.py`:
   - Usar `render_system_instructions(context.source_language, context.target_language)`.
3. Em `src/translaterany/stages/review_meaning.py`:
   - Parametrizar template com `{source.name_pt}` e `{target.name_pt}`.
4. Em `src/translaterany/stages/colloquial.py` e `treatment_consistency.py`:
   - Usar `context.target_profile` para extrair regras e formatar instruções.
5. Em `src/translaterany/stages/final_readthrough.py`:
   - Instruir a leitura no idioma `{target.name_pt}`.
6. Em `src/translaterany/stages/qa_loop.py`:
   - Usar `context.source_language.code` e `context.target_language.code` nos rótulos de prompt.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_prompts_multilingual.py -v`
Run: `uv run pytest tests/test_translate_dialogue.py tests/test_qa_loop.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/translator.py src/translaterany/stages/ tests/stages/test_prompts_multilingual.py
git commit -m "feat(stages): dynamically inject source and target languages into AI prompts"
```

---

### Task 8: LanguageTool, Publicação e Remux Parametrizados

**Files:**
- Modify: `src/translaterany/stages/orthography.py`
- Modify: `src/translaterany/orthography/client.py`
- Modify: `src/translaterany/util/doctor.py`
- Modify: `src/translaterany/stages/publish.py`
- Modify: `src/translaterany/media/remux.py`
- Test: `tests/stages/test_publish_remux_multilingual.py`

**Interfaces:**
- Consumes: `context.target_language.languagetool_code`, `context.target_language.code`.
- Produces: `.ass` gravado com `<stem>.{code}.ass`, flags mkvmerge com código e nome do idioma.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/test_publish_remux_multilingual.py
from pathlib import Path
from translaterany.languages.registry import LanguageRegistry
from translaterany.media.remux import build_remux_command
from translaterany.stages.publish import get_output_ass_path


def test_publish_output_path_uses_target_language() -> None:
    mkv_path = Path("/media/anime/Charlotte S01E01.mkv")
    es = LanguageRegistry.resolve("es")
    out_es = get_output_ass_path(mkv_path, target_lang=es)
    assert out_es.name == "Charlotte S01E01.es.ass"

    pt = LanguageRegistry.resolve("pt-BR")
    out_pt = get_output_ass_path(mkv_path, target_lang=pt)
    assert out_pt.name == "Charlotte S01E01.pt-BR.ass"


def test_remux_command_uses_target_language() -> None:
    es = LanguageRegistry.resolve("es")
    cmd = build_remux_command(Path("video.mkv"), Path("video.es.ass"), target_lang=es)
    cmd_str = " ".join(cmd)
    assert "--language 0:es" in cmd_str or "--language 0:spa" in cmd_str
    assert "Espanhol — TranslaterAny" in cmd_str
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_publish_remux_multilingual.py -v`
Expected: FAIL with TypeError or unexpected arguments

- [ ] **Step 3: Update `orthography.py`, `publish.py`, and `remux.py`**

1. Em `src/translaterany/stages/orthography.py`:
   - Passar `context.target_language.languagetool_code` para o `LanguageToolClient`.
2. Em `src/translaterany/stages/publish.py`:
   - Atualizar `get_output_ass_path(video_path, target_lang)` para gerar `<stem>.{target_lang.code}.ass`.
3. Em `src/translaterany/media/remux.py`:
   - Atualizar `remux` e `build_remux_command` para usar `--language 0:{target_lang.code}` e nome `"{target_lang.name_pt} — TranslaterAny"`.
4. Em `src/translaterany/util/doctor.py`:
   - Verificar idiomas no `/v2/languages` do LanguageTool.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_publish_remux_multilingual.py -v`
Run: `uv run pytest tests/test_publish.py tests/test_remux.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/orthography.py src/translaterany/orthography/client.py src/translaterany/util/doctor.py src/translaterany/stages/publish.py src/translaterany/media/remux.py tests/stages/test_publish_remux_multilingual.py
git commit -m "feat(pipeline): parameterize LanguageTool, publish and remux with target language"
```

---

### Task 9: Integração E2E Multilíngue, Verificação Completa e Documentação

**Files:**
- Create: `tests/pipeline/test_multilingual_e2e.py`
- Modify: `STATE.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: Pipeline completo com `ja` → `es` e `en` → `pt-BR`.
- Produces: Execução E2E sintética validada e documentação atualizada.

- [ ] **Step 1: Write E2E integration test**

```python
# tests/pipeline/test_multilingual_e2e.py
from pathlib import Path
from translaterany.config import load_config_from_str
from translaterany.languages.registry import LanguageRegistry
from translaterany.pipeline.runner import Runner


def test_multilingual_pipeline_run_ja_to_es(tmp_path: Path) -> None:
    raw_cfg = """
    source_language = "ja"
    target_language = "es"
    [llm]
    provider = "fake"
    """
    cfg = load_config_from_str(raw_cfg)
    assert cfg.source_language == "ja"
    assert cfg.target_language == "es"
    
    # Valida que o Runner inicializa com o par e perfis corretos
    runner = Runner(cfg)
    assert runner.source_language.code == "ja"
    assert runner.target_language.code == "es"
    assert runner.target_profile.info.code == "es"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/pipeline/test_multilingual_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite and linters**

Run: `uv run pytest -q`
Expected: > 700 testes passando sem falhas (zero regressões).
Run: `uv run ruff check`
Run: `uv run ruff format --check`
Expected: Limpo sem erros.

- [ ] **Step 4: Update `STATE.md` and `ROADMAP.md`**

Registrar no `STATE.md` e `ROADMAP.md` a conclusão do M9 e o avanço da v1.1.

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_multilingual_e2e.py STATE.md ROADMAP.md
git commit -m "feat(e2e): add multilingual integration tests and update project state"
```
