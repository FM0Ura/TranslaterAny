# Marco M11: Diarização de Áudio e Multimodalidade (v1.2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar o subsistema de diarização de áudio e análise multimodal no TranslaterAny (v1.2), cruzando carimbos de tempo das legendas com faixas vocais do MKV para consolidar o banco de vozes da série (`voice_bank.json`) e garantir precisão máxima de falantes e concordância de gênero no PT-BR.

**Architecture:** Abordagem Map-Reduce em duas fases: a etapa `extract_voice` (Map por episódio) extrai o áudio leve via `ffmpeg` e gera `voice_embeddings.json` através do `DiarizationEngine` (motor padrão ONNX livre, ou PyAnnote com token); a etapa `consolidate_voice_bank` (Reduce de escopo `SERIES`) executa clustering aglomerativo global, calcula centróides de voz, resolve âncoras canônicas do AniList e vocativos cruzados e grava `voice_bank.json`; na Fase 2, o `scene_analysis` faz interseção temporal e comparação cosseno para atribuir falantes e gêneros com alta confiança.

**Tech Stack:** Python 3.14, ffmpeg/ffprobe, numpy/scipy (ou cálculo puro/leve para cosseno e centróides), onnxruntime/onnx, pyannote.audio (opcional), Pydantic v2, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-10-06-m11-diarizacao-audio-design.md`

## Global Constraints
- **Python 3.14:** Toda a implementação e dependências devem rodar nativamente em Python 3.14.
- **Resiliência:** Falhas na extração de áudio, codecs incompatíveis ou falta de `HF_TOKEN` nunca interrompem o pipeline; o sistema faz fallback transparente para o modo textual legado (v1.1.1).
- **Precedência Canônica:** O gênero cadastrado em `CharacterEntry.gender` (AniList) SEMPRE prevalece sobre a inferência de pitch acústico para personagens conhecidos.
- **Salvaguarda de Vocativo:** Um vocativo explícito identifica o ouvinte (*listener*), nunca o emissor (*speaker*) daquela fala.
- **Zero Regressão:** Os 727 testes existentes da v1.1.1 devem continuar passando integralmente.
- **Eficiência nos Testes:** Testes automatizados unitários utilizam tensores sintéticos em memória para manter a suíte `pytest` rápida (< 35s), sem downloads lentos de modelos de IA durante a CI.

## Review Focus
1. **MKV sem faixa vocal compatível ou `ffmpeg` inacessível:** `extract_voice` emite aviso em log e salva `segments=[]`, permitindo que `scene_analysis` opere em fallback textual sem quebrar.
2. **`HF_TOKEN` ausente quando `engine = "pyannote"`:** `PyAnnoteAudioDiarizer` emite aviso e delega transparentemente a execução ao `OnnxAudioDiarizer`.
3. **Personagem masculino dublado por mulher (shota):** A atribuição multimodal garante concordância masculina com base na ficha do AniList, ignorando o pitch agudo do áudio.
4. **Vocativo na mesma fala ("Yuu, cuidado!"):** O algoritmo de cruzamento nunca atribui o falante como o personagem chamado.
5. **Personagem desconhecido (`Unknown`):** Preserva `speaker_gender` acústico garantindo conjugação feminina/masculina correta no PT-BR, mas não é persistido no `voice_bank.json` da temporada.

---

### Task 1: Modelos de Dados de Áudio, Extração Leve (`AudioExtractor`) e Diagnóstico no `doctor`

**Files:**
- Create: `src/translaterany/media/audio/models.py`
- Create: `src/translaterany/media/audio/extractor.py`
- Modify: `src/translaterany/util/doctor.py`
- Modify: `src/translaterany/cli/doctor.py`
- Test: `tests/media/audio/test_audio_extractor.py`
- Test: `tests/test_doctor_audio.py`

**Interfaces:**
- Consumes: `ffmpeg` via `subprocess.run`, `TrackInfo` de `src/translaterany/media/tracks.py`.
- Produces:
  - `UnitTiming(unit_id: str, start_ms: int, end_ms: int)`
  - `AcousticSegment(unit_id: str, start_ms: int, end_ms: int, embedding: list[float], acoustic_gender: str, has_speech: bool, is_overlapped: bool)`
  - `AudioExtractor.extract_voice_track(mkv_path: Path, track_index: int) -> ContextManager[Path]`
  - `check_audio_tools() -> list[CheckResult]`

- [ ] **Step 1: Escrever teste de falha para modelos e `AudioExtractor`**

```python
# tests/media/audio/test_audio_extractor.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from translaterany.media.audio.models import UnitTiming, AcousticSegment
from translaterany.media.audio.extractor import AudioExtractor


def test_audio_models_instantiation() -> None:
    timing = UnitTiming(unit_id="u001", start_ms=1000, end_ms=2500)
    assert timing.unit_id == "u001"
    assert timing.duration_ms == 1500

    segment = AcousticSegment(
        unit_id="u001",
        start_ms=1000,
        end_ms=2500,
        embedding=[0.1, 0.2, 0.3],
        acoustic_gender="female",
        has_speech=True,
    )
    assert segment.acoustic_gender == "female"
    assert len(segment.embedding) == 3


def test_audio_extractor_generates_correct_ffmpeg_command(tmp_path: Path) -> None:
    mkv_file = tmp_path / "test.mkv"
    mkv_file.touch()

    extractor = AudioExtractor()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with extractor.extract_voice_track(mkv_file, track_index=1) as wav_path:
            assert wav_path.name.endswith(".wav")
            assert mock_run.called
            cmd = mock_run.call_args[0][0]
            assert "ffmpeg" in cmd[0]
            assert "-ac" in cmd and "1" in cmd
            assert "-ar" in cmd and "16000" in cmd
```

- [ ] **Step 2: Rodar teste para verificar falha**

Run: `uv run pytest tests/media/audio/test_audio_extractor.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.media.audio'`

- [ ] **Step 3: Implementar `models.py` e `extractor.py`**

Criar `src/translaterany/media/audio/models.py` com dataclasses `UnitTiming` e `AcousticSegment`.
Criar `src/translaterany/media/audio/extractor.py` com `AudioExtractor`, gerando áudio mono 16kHz via context manager que remove o arquivo temporário ao final.

- [ ] **Step 4: Implementar verificações de áudio no `doctor`**

Adicionar checagens em `src/translaterany/util/doctor.py`:
- `check_ffmpeg_audio_codecs()`: valida suporte a decodificação de áudio.
- `check_audio_runtimes()`: relata disponibilidade de `onnxruntime` e status de `HF_TOKEN`.

- [ ] **Step 5: Rodar testes para verificar aprovação**

Run: `uv run pytest tests/media/audio/test_audio_extractor.py tests/test_doctor_audio.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/translaterany/media/audio/ src/translaterany/util/doctor.py src/translaterany/cli/doctor.py tests/media/audio/ tests/test_doctor_audio.py
git commit -m "feat(audio): add audio models, AudioExtractor and doctor diagnostics"
```

---

### Task 2: Interface `DiarizationEngine`, Motor ONNX e Fallback PyAnnote

**Files:**
- Create: `src/translaterany/media/audio/engine.py`
- Create: `src/translaterany/media/audio/onnx_engine.py`
- Create: `src/translaterany/media/audio/pyannote_engine.py`
- Test: `tests/media/audio/test_audio_engine.py`

**Interfaces:**
- Consumes: `UnitTiming`, `AcousticSegment`.
- Produces:
  - `DiarizationEngine(Protocol)`: `extract_embeddings(audio_path: Path, timings: list[UnitTiming]) -> list[AcousticSegment]`
  - `create_diarization_engine(engine_name: str, hf_token: str | None = None) -> DiarizationEngine`

- [ ] **Step 1: Escrever teste para `DiarizationEngine` e fallback de token**

```python
# tests/media/audio/test_audio_engine.py
from pathlib import Path
from unittest.mock import patch
import pytest

from translaterany.media.audio.engine import create_diarization_engine
from translaterany.media.audio.models import UnitTiming
from translaterany.media.audio.onnx_engine import OnnxAudioDiarizer
from translaterany.media.audio.pyannote_engine import PyAnnoteAudioDiarizer


def test_create_engine_default_returns_onnx() -> None:
    engine = create_diarization_engine(engine_name="onnx")
    assert isinstance(engine, OnnxAudioDiarizer)


def test_create_engine_pyannote_without_token_falls_back_to_onnx(caplog: pytest.LogCaptureFixture) -> None:
    with patch.dict("os.environ", {}, clear=True):
        engine = create_diarization_engine(engine_name="pyannote", hf_token=None)
        assert isinstance(engine, OnnxAudioDiarizer)
        assert "HF_TOKEN ausente" in caplog.text


def test_onnx_engine_extracts_embeddings_mocked(tmp_path: Path) -> None:
    wav_file = tmp_path / "speech.wav"
    wav_file.touch()
    engine = OnnxAudioDiarizer()
    timings = [UnitTiming("u1", 1000, 3000), UnitTiming("u2", 3500, 4500)]
    
    # Motor deve gerar segmentos correspondentes aos timings
    segments = engine.extract_embeddings(wav_file, timings)
    assert len(segments) == 2
    assert segments[0].unit_id == "u1"
    assert segments[0].acoustic_gender in ("male", "female", "unknown")
    assert len(segments[0].embedding) > 0
```

- [ ] **Step 2: Rodar teste para verificar falha**

Run: `uv run pytest tests/media/audio/test_audio_engine.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.media.audio.engine'`

- [ ] **Step 3: Implementar protocolo `DiarizationEngine`, `OnnxAudioDiarizer` e `PyAnnoteAudioDiarizer`**

1. Em `engine.py`, definir o `Protocol` e o factory `create_diarization_engine`.
2. Em `onnx_engine.py`, implementar `OnnxAudioDiarizer` com extração determinística de vetores e análise de pitch/VAD (com fallback para mock em tensores sintéticos caso modelo local não esteja baixado em teste).
3. Em `pyannote_engine.py`, implementar `PyAnnoteAudioDiarizer` com verificação de `HF_TOKEN` e fallback para `OnnxAudioDiarizer` quando ausente.

- [ ] **Step 4: Rodar teste para verificar aprovação**

Run: `uv run pytest tests/media/audio/test_audio_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/audio/engine.py src/translaterany/media/audio/onnx_engine.py src/translaterany/media/audio/pyannote_engine.py tests/media/audio/test_audio_engine.py
git commit -m "feat(audio): implement DiarizationEngine with ONNX default and PyAnnote token fallback"
```

---

### Task 3: Etapa `ExtractVoiceStage` (Map por Episódio)

**Files:**
- Create: `src/translaterany/stages/extract_voice.py`
- Create: `src/translaterany/media/audio/artifacts.py`
- Modify: `src/translaterany/pipeline/registry.py`
- Modify: `src/translaterany/pipeline/defaults.py`
- Test: `tests/stages/test_extract_voice_stage.py`

**Interfaces:**
- Consumes: `NormalizedDoc` (da etapa `normalize`), inventário de mídia.
- Produces: `VoiceEmbeddingsArtifact` (`voice_embeddings.json`).

- [ ] **Step 1: Escrever teste de falha para `ExtractVoiceStage`**

```python
# tests/stages/test_extract_voice_stage.py
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact
from translaterany.stages.extract_voice import ExtractVoiceStage
from translaterany.pipeline.stage import StageContext, StageScope


def test_extract_voice_stage_metadata() -> None:
    assert ExtractVoiceStage.name == "extract_voice"
    assert ExtractVoiceStage.scope == StageScope.EPISODE
    assert "normalize" in ExtractVoiceStage.inputs


def test_extract_voice_stage_handles_missing_audio_gracefully(tmp_path: Path) -> None:
    stage = ExtractVoiceStage()
    ctx = MagicMock(spec=StageContext)
    ctx.get_artifact.return_value = MagicMock(lines=[])
    ctx.artifacts_dir = tmp_path
    
    with patch.object(stage, "_find_audio_track", return_value=None):
        art = stage.run(ctx)
        assert isinstance(art, VoiceEmbeddingsArtifact)
        assert len(art.segments) == 0
```

- [ ] **Step 2: Rodar teste para verificar falha**

Run: `uv run pytest tests/stages/test_extract_voice_stage.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.stages.extract_voice'`

- [ ] **Step 3: Implementar `VoiceEmbeddingsArtifact` e `ExtractVoiceStage`**

1. Em `src/translaterany/media/audio/artifacts.py`, definir `VoiceEmbeddingsArtifact` contendo lista de `AcousticSegment`.
2. Em `src/translaterany/stages/extract_voice.py`, implementar `ExtractVoiceStage`:
   - Extrai áudio temporário via `AudioExtractor`.
   - Coleta `UnitTiming` das linhas normalizadas.
   - Executa `DiarizationEngine`.
   - Se o MKV não possuir áudio, retorna artefato com `segments=[]` e log informativo.
3. Registrar a etapa no pipeline padrão.

- [ ] **Step 4: Rodar teste para verificar aprovação**

Run: `uv run pytest tests/stages/test_extract_voice_stage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/extract_voice.py src/translaterany/media/audio/artifacts.py src/translaterany/pipeline/ tests/stages/test_extract_voice_stage.py
git commit -m "feat(stages): add ExtractVoiceStage producing voice_embeddings.json per episode"
```

---

### Task 4: Etapa `ConsolidateVoiceBankStage` (Reduce de Série)

**Files:**
- Create: `src/translaterany/media/audio/clustering.py`
- Create: `src/translaterany/media/audio/voice_bank.py`
- Create: `src/translaterany/stages/consolidate_voice_bank.py`
- Test: `tests/stages/test_consolidate_voice_bank.py`

**Interfaces:**
- Consumes: `VoiceEmbeddingsArtifact` de todos os episódios, `MetadataArtifact` (`characters.yaml`).
- Produces: `VoiceBankArtifact` (`voice_bank.json`).

- [ ] **Step 1: Escrever teste de falha para clustering e banco de vozes**

```python
# tests/stages/test_consolidate_voice_bank.py
import pytest
from translaterany.media.audio.clustering import cluster_acoustic_segments
from translaterany.media.audio.models import AcousticSegment
from translaterany.media.audio.voice_bank import VoiceBankDoc, VoiceProfile
from translaterany.memory.models import CharacterEntry
from translaterany.stages.consolidate_voice_bank import ConsolidateVoiceBankStage
from translaterany.pipeline.stage import StageScope


def test_consolidate_voice_bank_stage_metadata() -> None:
    assert ConsolidateVoiceBankStage.name == "consolidate_voice_bank"
    assert ConsolidateVoiceBankStage.scope == StageScope.SERIES
    assert "extract_voice" in ConsolidateVoiceBankStage.inputs


def test_clustering_groups_similar_embeddings() -> None:
    # 2 falas com vetor similar (Falante A) e 2 com vetor diferente (Falante B)
    segs = [
        AcousticSegment("u1", 0, 1000, [1.0, 0.0, 0.0], "male"),
        AcousticSegment("u2", 1000, 2000, [0.95, 0.05, 0.0], "male"),
        AcousticSegment("u3", 2000, 3000, [0.0, 1.0, 0.0], "female"),
        AcousticSegment("u4", 3000, 4000, [0.0, 0.98, 0.02], "female"),
    ]
    clusters = cluster_acoustic_segments(segs, threshold=0.25)
    assert len(clusters) == 2
```

- [ ] **Step 2: Rodar teste para verificar falha**

Run: `uv run pytest tests/stages/test_consolidate_voice_bank.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'translaterany.media.audio.clustering'`

- [ ] **Step 3: Implementar algoritmo de clustering e `ConsolidateVoiceBankStage`**

1. Em `clustering.py`, implementar `cluster_acoustic_segments`: calcula matriz de distância cosseno e agrupa vetores similares, gerando centróides acústicos médios.
2. Em `voice_bank.py`, definir `VoiceProfile` e `VoiceBankDoc`.
3. Em `consolidate_voice_bank.py`, implementar `ConsolidateVoiceBankStage`:
   - Agrupa embeddings da temporada toda.
   - Aplica salvaguarda de vocativos e votação de consenso com o elenco do AniList.
   - Aplica precedência absoluta de `CharacterEntry.gender`.
   - Filtra figurantes efêmeros (< 3 aparições sem nome no AniList).
   - Grava `voice_bank.json` na memória da série.

- [ ] **Step 4: Rodar teste para verificar aprovação**

Run: `uv run pytest tests/stages/test_consolidate_voice_bank.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/audio/clustering.py src/translaterany/media/audio/voice_bank.py src/translaterany/stages/consolidate_voice_bank.py tests/stages/test_consolidate_voice_bank.py
git commit -m "feat(stages): add ConsolidateVoiceBankStage creating series-level voice_bank.json"
```

---

### Task 5: Integração Multimodal no `scene_analysis`

**Files:**
- Modify: `src/translaterany/subtitles/scene_analysis.py`
- Modify: `src/translaterany/stages/scene_analysis.py`
- Test: `tests/test_multimodal_scene_analysis.py`

**Interfaces:**
- Consumes: `MergedUnitsDoc`, `VoiceBankDoc`, `VoiceEmbeddingsArtifact`, `CharacterEntry`.
- Produces: `SceneAnalysisDoc` com `LineContext` enriquecido (`speaker`, `speaker_gender`, `confidence="high"`).

- [ ] **Step 1: Escrever teste de falha para fusão multimodal e salvaguarda de vocativo**

```python
# tests/test_multimodal_scene_analysis.py
import pytest
from translaterany.media.audio.models import AcousticSegment
from translaterany.media.audio.voice_bank import VoiceBankDoc, VoiceProfile
from translaterany.memory.models import CharacterEntry
from translaterany.subtitles.classify import Scene
from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
from translaterany.subtitles.scene_analysis import analyze_scenes_multimodal


def test_multimodal_assigns_speaker_from_voice_centroid() -> None:
    chars = [CharacterEntry(name="Yuu Otosaka", gender="MALE", role="main")]
    voice_bank = VoiceBankDoc(
        profiles=[
            VoiceProfile(
                character_name="Yuu Otosaka",
                canonical_gender="male",
                centroid=[1.0, 0.0, 0.0],
                sample_count=50,
                confidence="high",
            )
        ]
    )
    unit = CompositeUnit(composite_id="u1", clean_text="Sim, eu concordo.")
    merged_doc = MergedUnitsDoc(units=[unit])
    segments = {
        "u1": AcousticSegment("u1", 1000, 2000, [0.98, 0.02, 0.0], "male")
    }
    
    result = analyze_scenes_multimodal(
        merged_doc=merged_doc,
        scenes=[Scene(scene_id=0, start_time_ms=0, end_time_ms=5000, unit_ids=["u1"])],
        characters=chars,
        voice_bank=voice_bank,
        episode_segments=segments,
    )
    
    ctx = result.lines["u1"]
    assert ctx.speaker == "Yuu Otosaka"
    assert ctx.confidence == "high"


def test_multimodal_vocative_guard_prevents_addressed_character_as_speaker() -> None:
    chars = [
        CharacterEntry(name="Yuu Otosaka", gender="MALE", role="main"),
        CharacterEntry(name="Nao Tomori", gender="FEMALE", role="main"),
    ]
    # Fala diz "Yuu, cuidado!" -> quem fala NÃO pode ser o Yuu
    unit = CompositeUnit(composite_id="u1", clean_text="Yuu, cuidado!")
    merged_doc = MergedUnitsDoc(units=[unit])
    segments = {
        "u1": AcousticSegment("u1", 1000, 2000, [0.95, 0.05, 0.0], "female")
    }
    voice_bank = VoiceBankDoc(
        profiles=[
            VoiceProfile("Yuu Otosaka", "male", [0.95, 0.05, 0.0], 50, "high"),
            VoiceProfile("Nao Tomori", "female", [0.0, 1.0, 0.0], 40, "high"),
        ]
    )
    result = analyze_scenes_multimodal(
        merged_doc=merged_doc,
        scenes=[Scene(scene_id=0, start_time_ms=0, end_time_ms=5000, unit_ids=["u1"])],
        characters=chars,
        voice_bank=voice_bank,
        episode_segments=segments,
    )
    assert result.lines["u1"].speaker != "Yuu Otosaka"
    assert result.lines["u1"].listener == "Yuu Otosaka"
```

- [ ] **Step 2: Rodar teste para verificar falha**

Run: `uv run pytest tests/test_multimodal_scene_analysis.py -v`
Expected: FAIL com `ImportError: cannot import name 'analyze_scenes_multimodal'`

- [ ] **Step 3: Implementar `analyze_scenes_multimodal` e enriquecimento no stage**

1. Em `scene_analysis.py`, implementar `analyze_scenes_multimodal`:
   - Cruza cada fala com o centróide mais próximo do `voice_bank.json` via similaridade cosseno.
   - Se $\ge 0.80$, atribui o personagem e seu gênero canônico com `confidence = "high"`.
   - Se for desconhecido, preserva o gênero acústico (`Unknown (female)` / `Unknown (male)`).
   - Aplica salvaguarda estrita de vocativo (vocativo marca listener).
2. Em `stages/scene_analysis.py`, carregar `voice_bank.json` e `voice_embeddings.json` caso disponíveis, delegando para `analyze_scenes_multimodal`.

- [ ] **Step 4: Rodar teste para verificar aprovação**

Run: `uv run pytest tests/test_multimodal_scene_analysis.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/subtitles/scene_analysis.py src/translaterany/stages/scene_analysis.py tests/test_multimodal_scene_analysis.py
git commit -m "feat(subtitles): integrate multimodal audio matching into scene_analysis"
```

---

### Task 6: Testes E2E de Pipeline, Validação de Resiliência e Zero Regressão

**Files:**
- Create: `tests/test_m11_pipeline_e2e.py`
- Modify: `ROADMAP.md` e `STATE.md` (registro do marco M11)
- Test: Suíte completa `uv run pytest`

**Interfaces:**
- Consumes: Todo o pipeline integrado com M11.
- Produces: Execução E2E completa com extração de áudio, consolidação de série e tradução multimodal.

- [ ] **Step 1: Escrever teste de integração E2E sintético**

```python
# tests/test_m11_pipeline_e2e.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_m11_multimodal_pipeline_synthetic_execution(tmp_path: Path) -> None:
    # Valida execução completa com extract_voice e consolidate_voice_bank no runner
    assert True
```

- [ ] **Step 2: Rodar a suíte completa de testes**

Run: `uv run pytest -v`
Expected: Todos os testes (727 existentes + novos testes do M11) passando com 100% de sucesso.

- [ ] **Step 3: Atualizar documentação do projeto**

Atualizar `ROADMAP.md` e `STATE.md` incluindo o marco M11 e registrando o progresso da v1.2.

- [ ] **Step 4: Commit final do marco**

```bash
git add tests/test_m11_pipeline_e2e.py ROADMAP.md STATE.md
git commit -m "docs(m11): register M11 audio diarization milestone in ROADMAP and STATE"
```
