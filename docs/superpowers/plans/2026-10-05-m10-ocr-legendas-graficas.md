# Marco M10: OCR para Legendas Gráficas (PGS / VobSub) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar suporte nativo a legendas em imagem (PGS `.sup` e VobSub `.sub`/`.idx`) no TranslaterAny via extração leve com `mkvextract`, decodificação de bitmaps com `Pillow`, OCR paralelo com Tesseract, inferência de estilos/posições e integração transparente ao pipeline existente.

**Architecture:** O `select_track` passa a selecionar faixas completas de imagem quando não houver texto completo; `extract` extrai o arquivo gráfico bruto (`.sup` ou `.sub`); a nova etapa `ocr` decodifica os pacotes em `SubtitleDisplaySet`, desduplica quadros por hash, executa o Tesseract em paralelo gerando um `.ass` estruturado com itálicos e posicionamento (`Top`, `Sign`, `Default`); `normalize` consome o `.ass` gerado transparentemente.

**Tech Stack:** Python 3.14, Pillow, Tesseract OCR (binário via sistema/Homebrew), pysubs2, Pydantic v2, Typer, pytest.

**Spec:** `docs/superpowers/specs/2026-10-05-m10-ocr-legendas-graficas-design.md`

## Global Constraints
- Dependências Python: apenas `pillow` (zero frameworks pesados de visão computacional como OpenCV).
- Compatibilidade: 100% compatível com Python 3.14.
- Regressão: os 686 testes existentes devem continuar passando com zero falhas.
- Formatação e lint: `ruff check` e `ruff format` limpos em todos os módulos.
- TDD estrito: Red -> Green -> Refactor -> Commit para cada tarefa.

## Review Focus
1. **Vídeo com apenas faixa PGS de diálogo e faixa de texto parcial (Signs/Songs):** O `select_track` deve escolher obrigatoriamente a faixa PGS completa e nunca a parcial de texto.
2. **Faixa nativa de texto existente no MKV:** A etapa `ocr` deve fazer bypass instantâneo sem executar subprocessos nem overhead.
3. **Quadro PGS sem texto (somente limpeza/erase):** O parser não deve enviar quadros vazios ao Tesseract e deve usar o timestamp para fechar a fala anterior.
4. **Ausência do binário `tesseract` no sistema:** O comando `doctor` e a etapa `ocr` devem falhar com mensagem explicativa e amigável em PT-BR sem traceback poluído.
5. **Legendas em itálico no PGS:** O output hOCR do Tesseract deve preservar o itálico transpondo para tags `{\i1}...{\i0}` no ASS.

---

### Task 1: Dependência `pillow` e Diagnóstico do Tesseract no `doctor`

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/translaterany/util/doctor.py`
- Modify: `src/translaterany/cli/doctor.py`
- Test: `tests/test_doctor_tesseract.py`

**Interfaces:**
- Consumes: `shutil.which`, `subprocess.run(["tesseract", "--version"])`.
- Produces: `check_tesseract_installed(source_lang: str | None = None) -> CheckResult`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_doctor_tesseract.py
from unittest.mock import patch, MagicMock
from translaterany.util.doctor import check_tesseract_installed


def test_tesseract_check_ok_when_installed() -> None:
    with patch("shutil.which", return_value="/usr/bin/tesseract"), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="tesseract 5.5.0\n", stderr="")
        res = check_tesseract_installed("eng")
        assert res.status == "ok"
        assert "tesseract" in res.message.lower()


def test_tesseract_check_warn_or_fail_when_missing() -> None:
    with patch("shutil.which", return_value=None):
        res = check_tesseract_installed("eng")
        assert res.status in ("warn", "fail")
        assert "brew install tesseract" in res.message or "não encontrado" in res.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_doctor_tesseract.py -v`
Expected: FAIL with `ImportError: cannot import name 'check_tesseract_installed'`

- [ ] **Step 3: Implement `check_tesseract_installed` and add `pillow` dependency**

1. Adicionar `pillow>=11.0.0` em `pyproject.toml`.
2. Em `src/translaterany/util/doctor.py`, implementar `check_tesseract_installed(source_lang: str | None = None) -> CheckResult`.
3. Em `src/translaterany/cli/doctor.py`, registrar a checagem no comando `doctor`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_doctor_tesseract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml src/translaterany/util/doctor.py src/translaterany/cli/doctor.py tests/test_doctor_tesseract.py
git commit -m "feat(doctor): add Tesseract OCR installation and language pack check"
```

---

### Task 2: Priorização Inteligente de Faixas Gráficas em `select_track`

**Files:**
- Modify: `src/translaterany/media/tracks.py`
- Test: `tests/media/test_tracks_image_priority.py`

**Interfaces:**
- Consumes: `MkvInfo`, `Track`, `IMAGE_CODECS`, `LanguageRegistry`.
- Produces: `select_track(...) -> Selection` que prioriza faixas completas de imagem sobre faixas parciais de texto.

- [ ] **Step 1: Write the failing test**

```python
# tests/media/test_tracks_image_priority.py
from translaterany.media.mkv import MkvInfo, Track
from translaterany.media.tracks import select_track
from translaterany.languages.registry import LanguageRegistry


def test_select_track_prefers_full_pgs_over_signs_text() -> None:
    # Cenário comum: faixa de texto com apenas placas/músicas, e faixa PGS completa
    text_signs = Track(id=1, name="English Signs & Songs", language="eng", codec_id="S_TEXT/ASS", forced=True)
    pgs_full = Track(id=2, name="English Subtitles", language="eng", codec_id="S_HDMV/PGS", default=True)
    info = MkvInfo(tracks=[text_signs, pgs_full], duration_ns=1000)

    sel = select_track(info, source_lang=LanguageRegistry.resolve("en"))
    assert sel.chosen.id == 2
    assert sel.chosen.codec_id == "S_HDMV/PGS"


def test_select_track_prefers_full_text_over_full_pgs() -> None:
    # Cenário de desempate: ambas são completas, texto tem prioridade sobre OCR
    text_full = Track(id=1, name="English Full", language="eng", codec_id="S_TEXT/ASS")
    pgs_full = Track(id=2, name="English PGS", language="eng", codec_id="S_HDMV/PGS")
    info = MkvInfo(tracks=[text_full, pgs_full], duration_ns=1000)

    sel = select_track(info, source_lang=LanguageRegistry.resolve("en"))
    assert sel.chosen.id == 1
    assert sel.chosen.codec_id == "S_TEXT/ASS"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/media/test_tracks_image_priority.py -v`
Expected: FAIL with `NoTrack: legenda em imagem (OCR fora da v1)` ou escolha errada

- [ ] **Step 3: Update `select_track` in `src/translaterany/media/tracks.py`**

1. Permitir `IMAGE_CODECS` entre os candidatos válidos se o idioma for compatível.
2. Definir a chave de ordenação: `(is_signs(t), t.codec_id in IMAGE_CODECS, not t.default, t.id)`.
3. Atualizar a mensagem de erro quando não houver legendas.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/media/test_tracks_image_priority.py tests/test_tracks.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/tracks.py tests/media/test_tracks_image_priority.py
git commit -m "feat(media): prioritize full image tracks over partial text tracks in select_track"
```

---

### Task 3: Extração de Faixas Gráficas em `extract` e `mkvextract`

**Files:**
- Modify: `src/translaterany/media/extract.py`
- Modify: `src/translaterany/stages/extract.py`
- Test: `tests/media/test_extract_graphical.py`

**Interfaces:**
- Consumes: `mkv: Path`, `track_id: int`, `codec_id: str`.
- Produces: `extract_track(mkv, track_id, codec, out_dir) -> Path` suportando `.sup` e `.sub`.

- [ ] **Step 1: Write the failing test**

```python
# tests/media/test_extract_graphical.py
from pathlib import Path
from unittest.mock import patch, MagicMock
from translaterany.media.extract import extract_track


def test_extract_track_extracts_sup_for_pgs(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        out_path = extract_track(tmp_path / "video.mkv", track_id=3, codec_id="S_HDMV/PGS", out_dir=tmp_path)
        assert out_path.suffix == ".sup"
        assert "3:" in mock_run.call_args[0][0][3]


def test_extract_track_extracts_sub_for_vobsub(tmp_path: Path) -> None:
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        out_path = extract_track(tmp_path / "video.mkv", track_id=2, codec_id="S_VOBSUB", out_dir=tmp_path)
        assert out_path.suffix == ".sub"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/media/test_extract_graphical.py -v`
Expected: FAIL with `MediaError` ou formato não reconhecido

- [ ] **Step 3: Update `extract_track` and `ExtractStage`**

1. Em `src/translaterany/media/extract.py`: mapear `S_HDMV/PGS` para extensão `.sup` e `S_VOBSUB` para `.sub`.
2. Em `src/translaterany/stages/extract.py`: salvar o formato correto em `ExtractArtifact(format="sup"|"sub")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/media/test_extract_graphical.py tests/test_stages_extract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/extract.py src/translaterany/stages/extract.py tests/media/test_extract_graphical.py
git commit -m "feat(media): support mkvextract extraction for PGS (.sup) and VobSub (.sub) tracks"
```

---

### Task 4: Modelos e Parser de Bitmaps PGS (`.sup`)

**Files:**
- Create: `src/translaterany/media/ocr/models.py`
- Create: `src/translaterany/media/ocr/pgs.py`
- Test: `tests/media/ocr/test_pgs_parser.py`

**Interfaces:**
- Consumes: Arquivo `.sup` contendo fluxos de pacotes Blu-ray.
- Produces: `parse_pgs(sup_path: Path) -> list[SubtitleDisplaySet]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/media/ocr/test_pgs_parser.py
from pathlib import Path
from PIL import Image
from translaterany.media.ocr.models import SubtitleDisplaySet
from translaterany.media.ocr.pgs import parse_pgs, decode_rle


def test_decode_rle_simple_line() -> None:
    # Bytes de exemplo de linha RLE padrão PGS
    raw = bytes([0x00, 0x85, 0x01])  # Exemplo de run de 5 pixels da cor 1
    pixels = decode_rle(raw, width=5)
    assert len(pixels) == 5
    assert pixels == [1, 1, 1, 1, 1]


def test_parse_pgs_synthetic_packets(tmp_path: Path) -> None:
    sup_file = tmp_path / "test.sup"
    # Monta pacotes sintéticos mínimos PCS + PDS + ODS + EDS
    from tests.ocr_helpers import make_synthetic_sup
    make_synthetic_sup(sup_file, width=100, height=30, text_color=1)
    
    displays = parse_pgs(sup_file)
    assert len(displays) == 1
    assert isinstance(displays[0], SubtitleDisplaySet)
    assert displays[0].width == 100
    assert displays[0].image.size == (100, 30)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/media/ocr/test_pgs_parser.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'translaterany.media.ocr'`

- [ ] **Step 3: Implement `models.py` and `pgs.py`**

1. Criar `src/translaterany/media/ocr/models.py` com `SubtitleDisplaySet`.
2. Criar `src/translaterany/media/ocr/pgs.py` com parser binário de pacotes PG (`0x14` PDS, `0x15` ODS, `0x16` PCS, `0x17` WDS) e decodificador RLE.
3. Usar `Pillow` para binarizar e produzir a imagem `Image.Image` em modo `L`.
4. Criar helper `tests/ocr_helpers.py` para gerar `.sup` sintéticos válidos para testes.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/media/ocr/test_pgs_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/ocr/ tests/media/ocr/test_pgs_parser.py tests/ocr_helpers.py
git commit -m "feat(ocr): implement Blu-ray PGS (.sup) packet parser and RLE decoder"
```

---

### Task 5: Parser e Decodificador VobSub (`.sub` + `.idx`)

**Files:**
- Create: `src/translaterany/media/ocr/vobsub.py`
- Test: `tests/media/ocr/test_vobsub_parser.py`

**Interfaces:**
- Consumes: Arquivos `.sub` e `.idx`.
- Produces: `parse_vobsub(sub_path: Path, idx_path: Path) -> list[SubtitleDisplaySet]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/media/ocr/test_vobsub_parser.py
from pathlib import Path
from translaterany.media.ocr.models import SubtitleDisplaySet
from translaterany.media.ocr.vobsub import parse_vobsub


def test_parse_vobsub_synthetic(tmp_path: Path) -> None:
    from tests.ocr_helpers import make_synthetic_vobsub
    sub_path = tmp_path / "test.sub"
    idx_path = tmp_path / "test.idx"
    make_synthetic_vobsub(sub_path, idx_path)

    items = parse_vobsub(sub_path, idx_path)
    assert len(items) == 1
    assert isinstance(items[0], SubtitleDisplaySet)
    assert items[0].start_ms == 1000
    assert items[0].end_ms == 3000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/media/ocr/test_vobsub_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `vobsub.py`**

1. Em `src/translaterany/media/ocr/vobsub.py`, implementar parser do índice `.idx` (timestamps, offsets, paleta).
2. Extrair e decodificar os pacotes de subpicture MPEG-2 do arquivo `.sub`.
3. Emitir lista padronizada de `SubtitleDisplaySet`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/media/ocr/test_vobsub_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/ocr/vobsub.py tests/media/ocr/test_vobsub_parser.py
git commit -m "feat(ocr): implement DVD VobSub (.sub/.idx) parser and decoder"
```

---

### Task 6: Motor de OCR com Tesseract, Binarização e Paralelismo

**Files:**
- Create: `src/translaterany/media/ocr/engine.py`
- Test: `tests/media/ocr/test_ocr_engine.py`

**Interfaces:**
- Consumes: `list[SubtitleDisplaySet]`, `lang: str`, `max_workers: int`.
- Produces: `run_ocr(displays: list[SubtitleDisplaySet], lang: str) -> list[OCRResultLine]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/media/ocr/test_ocr_engine.py
from unittest.mock import patch
from PIL import Image
from translaterany.media.ocr.models import SubtitleDisplaySet
from translaterany.media.ocr.engine import run_ocr, OCRResultLine


def test_ocr_engine_detects_italics_from_hocr() -> None:
    sample_hocr = """
    <div class='ocr_page'>
      <span class='ocr_line'><em>Hello</em> world</span>
    </div>
    """
    img = Image.new("L", (100, 30), color=255)
    ds = SubtitleDisplaySet(1000, 2000, 0, 900, 100, 30, 1920, 1080, img)
    
    with patch("translaterany.media.ocr.engine._call_tesseract_hocr", return_value=sample_hocr):
        results = run_ocr([ds], lang="eng", max_workers=1)
        assert len(results) == 1
        assert results[0].text == "{\\i1}Hello{\\i0} world"


def test_ocr_engine_deduplicates_identical_consecutive_frames() -> None:
    img = Image.new("L", (100, 30), color=255)
    ds1 = SubtitleDisplaySet(1000, 2000, 0, 900, 100, 30, 1920, 1080, img)
    ds2 = SubtitleDisplaySet(2000, 3000, 0, 900, 100, 30, 1920, 1080, img)
    
    with patch("translaterany.media.ocr.engine._call_tesseract_hocr", return_value="<span>Test</span>") as mock_tess:
        results = run_ocr([ds1, ds2], lang="eng", max_workers=1)
        assert len(results) == 1
        assert results[0].start_ms == 1000
        assert results[0].end_ms == 3000
        assert mock_tess.call_count == 1  # Evitou segunda chamada por hash idêntico
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/media/ocr/test_ocr_engine.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement `engine.py`**

1. Invocação de `tesseract` com `--psm 6 --oem 1 -l <lang> hocr`.
2. Parser de tags hOCR (`<em>`, `<i>` $\rightarrow$ `{\i1}...{\i0}`).
3. Desduplicação inteligente por hash de imagem SHA-256.
4. Execução concorrente com `concurrent.futures.ThreadPoolExecutor`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/media/ocr/test_ocr_engine.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/media/ocr/engine.py tests/media/ocr/test_ocr_engine.py
git commit -m "feat(ocr): implement parallel Tesseract OCR engine with hOCR italics and deduplication"
```

---

### Task 7: Etapa `OCRStage` e Reconstrução do `ocr.ass`

**Files:**
- Create: `src/translaterany/stages/ocr.py`
- Test: `tests/stages/test_ocr_stage.py`

**Interfaces:**
- Consumes: `ctx.inputs.path("extract")`, `ctx.source_language`.
- Produces: `OCRArtifact(bypassed: bool, path: str, lines_count: int, ...)` e arquivo `ocr.ass`.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/test_ocr_stage.py
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from translaterany.stages.ocr import OCRStage, OCRArtifact


def test_ocr_stage_bypasses_text_track(tmp_path: Path) -> None:
    ass_file = tmp_path / "track.ass"
    ass_file.write_text("[Events]\nDialogue: ...", encoding="utf-8")
    
    stage = OCRStage()
    mock_inputs = SimpleNamespace(path=lambda name: ass_file)
    mock_output = MagicMock()
    ctx = SimpleNamespace(
        inputs=mock_inputs,
        output=mock_output,
        episode=SimpleNamespace(source=Path("video.mkv")),
        log=MagicMock(),
    )
    
    stage.run(ctx)
    art = mock_output.json.call_args[0][0]
    assert isinstance(art, OCRArtifact)
    assert art.bypassed is True
    assert art.path == str(ass_file)


def test_ocr_stage_infers_position_styles(tmp_path: Path) -> None:
    # Valida que linha Y < 25% vira estilo Top / \an8 e Y > 65% vira Default
    from translaterany.stages.ocr import _build_ass_event
    from translaterany.media.ocr.engine import OCRResultLine
    
    top_line = OCRResultLine(start_ms=1000, end_ms=2000, x=100, y=50, w=200, h=40, video_w=1920, video_h=1080, text="Top Title")
    ev_top = _build_ass_event(top_line)
    assert "\\an8" in ev_top.text or ev_top.style == "Top"
    
    bottom_line = OCRResultLine(start_ms=3000, end_ms=4000, x=100, y=900, w=200, h=40, video_w=1920, video_h=1080, text="Dialogue")
    ev_bottom = _build_ass_event(bottom_line)
    assert ev_bottom.style == "Default"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_ocr_stage.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'translaterany.stages.ocr'`

- [ ] **Step 3: Implement `OCRStage` in `src/translaterany/stages/ocr.py`**

1. Registrar etapa `@register_stage` com nome `"ocr"`.
2. Se entrada for `.ass` ou `.srt`, emitir `OCRArtifact(bypassed=True, path=...)`.
3. Se entrada for `.sup` ou `.sub`, executar parser + OCR, inferir posições verticais e salvar `.ocr.ass`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_ocr_stage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/ocr.py tests/stages/test_ocr_stage.py
git commit -m "feat(stages): add OCRStage with text bypass and ASS positioning inference"
```

---

### Task 8: Integração com `NormalizeStage` e Pipeline Completo

**Files:**
- Modify: `src/translaterany/stages/normalize.py`
- Modify: `src/translaterany/config/model.py`
- Modify: `src/translaterany/pipeline/runner.py`
- Test: `tests/stages/test_normalize_with_ocr.py`

**Interfaces:**
- Consumes: `OCRStage` output em `NormalizeStage`.
- Produces: `DEFAULT_PIPELINE` contendo `"ocr"` entre `"extract"` e `"normalize"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/stages/test_normalize_with_ocr.py
from pathlib import Path
from types import SimpleNamespace
from translaterany.stages.normalize import NormalizeStage
from translaterany.stages.ocr import OCRStage


def test_normalize_binds_to_ocr_when_present() -> None:
    ocr = OCRStage()
    norm = NormalizeStage()
    norm.bind_pipeline([ocr], app=None)
    assert "ocr" in norm.inputs


def test_normalize_binds_to_extract_when_ocr_absent() -> None:
    from translaterany.stages.extract import ExtractStage
    ext = ExtractStage()
    norm = NormalizeStage()
    norm.bind_pipeline([ext], app=None)
    assert "extract" in norm.inputs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/stages/test_normalize_with_ocr.py -v`
Expected: FAIL

- [ ] **Step 3: Update `NormalizeStage`, `config/model.py`, and `pipeline/runner.py`**

1. Em `src/translaterany/stages/normalize.py`, atualizar `bind_pipeline` para conectar em `ocr` ou `extract`.
2. Em `src/translaterany/config/model.py`, incluir `"ocr"` na sequência de `DEFAULT_PIPELINE` entre `extract` e `normalize`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/stages/test_normalize_with_ocr.py tests/test_stages_normalize.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/translaterany/stages/normalize.py src/translaterany/config/model.py src/translaterany/pipeline/runner.py tests/stages/test_normalize_with_ocr.py
git commit -m "feat(pipeline): wire OCR stage into DEFAULT_PIPELINE and bind NormalizeStage"
```

---

### Task 9: Integração E2E, Verificação com Animes de Teste e Documentação

**Files:**
- Create: `tests/pipeline/test_ocr_e2e.py`
- Modify: `STATE.md`
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: Pipeline completo executando com MKVs sintéticos PGS e com arquivos reais de `temporada-teste/`.
- Produces: Confirmação de 100% dos testes passando e documentação do Marco M10 finalizada.

- [ ] **Step 1: Write E2E integration test with synthetic PGS**

```python
# tests/pipeline/test_ocr_e2e.py
from pathlib import Path
from unittest.mock import patch
from mkvtools import create_synthetic_mkv, Sub, needs_mkvtoolnix
from translaterany.config import load_config_from_str
from translaterany.pipeline.runner import PipelineRunner
from translaterany.llm.fake import FakeLLM


@needs_mkvtoolnix
def test_pipeline_runs_pgs_end_to_end(tmp_path: Path) -> None:
    # Gera MKV sintético com faixa PGS e valida fluxo completo até publicação .ass
    from tests.ocr_helpers import make_synthetic_sup
    sup_file = tmp_path / "test.sup"
    make_synthetic_sup(sup_file, width=200, height=50)
    
    video = tmp_path / "Season 1" / "Anime S01E01.mkv"
    create_synthetic_mkv(video, subs=[Sub(content=sup_file.read_text(errors="ignore"), name="PGS", ext=".sup")])
    
    cfg = load_config_from_str("")
    fake_llm = FakeLLM(responses={"Hello world": "Olá mundo"})
    
    with patch("translaterany.media.ocr.engine._call_tesseract_hocr", return_value="<span>Hello world</span>"):
        runner = PipelineRunner(config=cfg, client=fake_llm)
        res = runner.run_series(tmp_path)
        assert res.status == "success"
        
        ass_files = list(tmp_path.glob("**/*.pt-BR.ass"))
        assert len(ass_files) == 1
        assert "Olá mundo" in ass_files[0].read_text(encoding="utf-8")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/pipeline/test_ocr_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite and linters**

Run: `uv run pytest -q`
Expected: > 700 testes passando sem falhas (zero regressões).
Run: `uv run ruff check`
Run: `uv run ruff format --check`
Expected: Limpo sem erros.

- [ ] **Step 4: Update `STATE.md` and `ROADMAP.md`**

Registrar a conclusão do Marco M10 e da versão 1.1 em `STATE.md` e `ROADMAP.md`.

- [ ] **Step 5: Commit**

```bash
git add tests/pipeline/test_ocr_e2e.py STATE.md ROADMAP.md
git commit -m "feat(e2e): add end-to-end OCR integration tests and mark M10 complete"
```
