# M1 — Mídia e legendas · Plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** extrair a legenda certa de cada MKV, entender sua estrutura (unidades de texto único, tipos de linha, cenas) e regravá-la idêntica byte a byte; publicar ao lado do vídeo e reinserir no MKV com segurança **quando houver tradução** (a partir do M2).

**Architecture:** novos pacotes `library` (descoberta), `subtitles` (parser `.ass` próprio, segmentação, normalização, classificação), `media` (mkvmerge/mkvextract e remux) e sete etapas em `stages`. O núcleo do M0 ganha entradas por instância, `translates`, `verify_cached`, `previous_output`, `force` e `cache_payload`. Nada vai para a biblioteca sem a marca `; TranslaterAny`, que só a gravação de uma tradução insere.

**Tech Stack:** Python 3.14 · uv · pydantic 2 · typer · pysubs2 (só SRT→ASS) · charset-normalizer · MKVToolNix (mkvmerge/mkvextract) · pytest · ruff.

**Spec:** [`docs/superpowers/specs/2026-09-24-m1-midia-legendas-design.md`](../specs/2026-09-24-m1-midia-legendas-design.md)

> Todo o código deste plano foi executado num protótipo antes de ser escrito aqui: as tarefas foram aplicadas em sequência sobre o `master`, com os testes falhando antes e passando depois de cada implementação, `ruff` limpo, e o resultado final conferido arquivo por arquivo contra o protótipo. O protótipo também passou pelo aceite real (Tarefa 11): 79 episódios, faixas corretas, `write.ass` idêntico em 79/79, `temporada-teste/` intacta. As saídas "Expected" são as reais da simulação.

## Pré-requisitos

- MKVToolNix no PATH (`mkvmerge --version` ≥ 102; instalado via Homebrew). Os testes de integração são pulados sem ele — **não** devem ser pulados nesta execução.
- Branch próprio: `git switch -c m1-midia-legendas`.
- Todos os comandos na raiz do repositório.

## Global Constraints

- `requires-python = ">=3.14"`; ambiente com `uv`.
- Dependências novas do M1: somente `pysubs2` (uso exclusivo: SRT→ASS) e `charset-normalizer`.
- Código em inglês; mensagens ao usuário em PT-BR.
- **Nada** é escrito dentro da biblioteca sem tradução: `publish` e `remux` só agem se `write.ass` contiver a linha `; TranslaterAny`.
- A gravação do `.ass` altera **somente** o campo de texto dos eventos; todo o resto sai byte a byte.
- Metadados de MKV só via `mkvmerge -J`; ferramentas externas rodam com `LC_ALL=C.UTF-8` e decodificação UTF-8.
- Remux: temporário oculto na mesma pasta (`.<nome>.translaterany-tmp.mkv`), verificação antes da troca, `os.replace`, sem backup por padrão.
- Testes sem conteúdo real de legenda: MKVs sintéticos gerados com `mkvmerge`, textos inventados.
- **Nunca** versionar nem alterar nada em `temporada-teste/`.
- Mensagens de commit terminam com:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
  ```

## Desvios conscientes do spec (já incorporados ao spec)

| # | Desvio | Motivo |
|---|---|---|
| 1 | Gancho `Stage.cache_payload()` no núcleo | o `series.toml` fica fora do diretório de dados; sem isso, editá-lo não invalidaria `select_track`/`classify` |
| 2 | `Stage.enabled_by_default` e `StageConfig.enabled = None` | com `enabled = True` por padrão, um config só com `[stages.remux.options]` ligaria o remux sem querer |
| 3 | Cenas calculadas no `classify` (opção `scene_gap_ms` lá) | agrupar cenas exige saber o que é diálogo; no `normalize`, as milhares de placas quadro a quadro virariam uma cena só |
| 4 | Ferramentas com `LC_ALL=C.UTF-8` (não `C`) | com `C`, o `mkvmerge` corrompe o JSON de nomes não ASCII ("Português (Brasil) — TranslaterAny") |
| 5 | Legenda portuguesa de terceiros detectada em qualquer extensão/marca (`.pt-BR`, `.pt`, `.por`, `.pob` × `.ass/.ssa/.srt/.vtt/.sub`) | senão o Jellyfin mostraria duas legendas PT |
| 6 | `run` numa pasta `Season N`/`Specials` processa a série-mãe restrita àquela pasta | é um uso natural; antes virava uma série chamada "Season 1" |
| 7 | `run` numa pasta sem séries: "Nenhuma série encontrada" (código 0) | a pasta vazia não é uma série |
| 8 | Especiais do *D×D* com CBM: 6 episódios (S00E11–14, 16, 17); S00E15 só tem uma faixa | medido; a tabela do spec foi corrigida |

## Review Focus

1. **SSA legado com a coluna `Marked`** (rips antigos) → lido e regravado idêntico — Tarefa 3 (`test_legacy_ssa_format_with_marked`).
2. **Legenda em português de terceiros com outra extensão ou marca** (`.pt-BR.srt`, `.pt.ass`, `.por.ass`, maiúsculas) → episódio pulado; outro idioma (`.es.srt`) não atrapalha — Tarefa 7 (`test_foreign_portuguese_external_subtitle_skips`, `test_other_language_external_subtitle_is_fine`).
3. **`run` apontado para uma pasta de temporada** → mesma série (mesma chave) que a pasta-mãe, só com os episódios daquela pasta — Tarefa 1 (`test_season_folder_belongs_to_parent_series`).
4. **Ctrl+C no meio do remux** → original intacto e nenhum temporário na biblioteca — Tarefa 9 (`test_ctrl_c_during_remux_leaves_original_and_no_temp`).
5. **`mkvmerge` terminando com avisos (código 1)** → remux aceito — Tarefa 9 (`test_mkvmerge_warnings_are_accepted`).

## Estrutura de arquivos

| Arquivo | Responsabilidade |
|---|---|
| `library/episodes.py` | `SxxEyy` / `S01E01-02` |
| `library/nfo.py` | identidade da série pelo `tvshow.nfo` |
| `library/series_config.py` | leitura e validação do `series.toml` |
| `library/discovery.py` | série × biblioteca × temporada, ignorados, duplicados |
| `subtitles/ass.py` | parser/gravação `.ass` preservando bytes; marca de autoria |
| `subtitles/segments.py` | prefixo · texto com `⟦n⟧` · sufixo; desenho |
| `subtitles/normalize.py` | eventos segmentados e unidades de texto único |
| `subtitles/classify.py` | tipos de linha, estilo principal, cenas |
| `subtitles/texts.py` | contrato `UnitTexts` |
| `subtitles/srt.py`, `subtitles/language.py` | SRT→ASS; "parece inglês?" |
| `media/mkv.py` | `mkvmerge -J`, `mkvextract` |
| `media/tracks.py` | regra de escolha da faixa |
| `media/remux.py` | remux com verificação |
| `stages/{select_track,extract,normalize,classify,write,publish,remux}.py` | etapas do pipeline |
| `tests/mkvtools.py`, `tests/pipeline_helpers.py` | MKVs sintéticos; rodar etapas em testes |

---

### Task 1: Descoberta da biblioteca (série, episódios, identidade, series.toml)

Substitui a descoberta provisória do M0 pelo pacote `library` (spec §6): episódios `SxxEyy`/`S01E01-02`, `.MKV`, ocultos, duplicados e arquivos recentes ignorados, identidade da série pelo `tvshow.nfo`, `series.toml` e **pasta de temporada tratada como parte da série-mãe**. `Series` ganha `config` (conteúdo do `series.toml`).

**Files:**
- Modify (substituir): `src/translaterany/util/fs.py`
- Modify (substituir): `src/translaterany/pipeline/units.py`
- Create: `src/translaterany/library/episodes.py`
- Create: `src/translaterany/library/nfo.py`
- Create: `src/translaterany/library/series_config.py`
- Create: `src/translaterany/library/discovery.py`
- Create: `src/translaterany/library/__init__.py`
- Modify: `src/translaterany/cli/run.py` (import)
- Modify: `src/translaterany/cli/status.py` (import)
- Modify: `src/translaterany/cli/retry.py` (import)
- Test: `tests/test_library.py`
- Modify: `tests/test_runner.py` (import)
- Modify: `tests/test_reset_status.py` (import)
- Modify: `tests/test_inventory.py` (import)
- Delete: `tests/test_units.py`

**Interfaces:**
- Consumes: `slugify` (M0), `Series`/`Episode` (M0).
- Produces:
  - `slug_base(name) -> str` em `util/fs.py` (a parte legível do slug)
  - `LINE_TYPES`, `SeriesConfig(track: str | None, styles: dict[str, str])` e `Series.config` em `pipeline/units.py`; `pipeline.units.discover` **deixa de existir**
  - `parse_episode(filename) -> EpisodeId | None`; `EpisodeId(season, first, last).key` → `S01E04`/`S01E01-02`
  - `series_identity(root) -> str | None` (`tvdb:…`/`tmdb:…`/`imdb:…`)
  - `load_series_config(root) -> SeriesConfig`; `SeriesConfigError`
  - `scan_library(path, *, min_file_age=0.0, now=None) -> list[SeriesScan]`; `scan_series(path, *, min_file_age=0.0, now=None, only=None) -> SeriesScan`; `SeriesScan(series, episodes, ignored: list[Ignored], warnings: list[str], error: str | None)`; `Ignored(path, reason)`; `is_series_dir(path)`; `discover(path) -> (Series, list[Episode])` (atalho sem filtro de idade)

- [ ] **Step 1: Remover o teste da descoberta provisória**

```bash
git rm -q tests/test_units.py
```

- [ ] **Step 2: Escrever os testes (devem falhar): `tests/test_library.py`**

```python
import os
import time
from pathlib import Path

import pytest

from translaterany.library import (
    SeriesConfigError,
    discover,
    is_series_dir,
    load_series_config,
    parse_episode,
    scan_library,
    scan_series,
)


def _touch(path: Path, text: str = "x", age: float = 3600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    old = time.time() - age
    os.utime(path, (old, old))
    return path


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("S01E04 - Moment of Earnest Bluray-1080p.mkv", "S01E04"),
        ("Show - s1e2.mkv", "S01E02"),
        ("S00E02 - Special.mkv", "S00E02"),
        ("S01E01-02 - Double.mkv", "S01E01-02"),
        ("S02E100 - Long.mkv", "S02E100"),
    ],
)
def test_parse_episode(name: str, key: str) -> None:
    episode = parse_episode(name)
    assert episode is not None and episode.key == key


def test_parse_episode_without_pattern() -> None:
    assert parse_episode("Movie (2020).mkv") is None
    assert parse_episode("HS01E01X.mkv") is None  # colado a letras não conta


def test_scan_series_keys_order_and_case(tmp_path: Path) -> None:
    root = tmp_path / "Minha Série (2020)"
    _touch(root / "Season 1" / "S01E02 - B.mkv")
    _touch(root / "Season 1" / "S01E01 - A.MKV")
    _touch(root / "Specials" / "S00E01 - Sp.mkv")
    _touch(root / "Season 1" / "S01E01 - A.nfo")
    scan = scan_series(root)
    assert [e.key for e in scan.episodes] == ["S00E01", "S01E01", "S01E02"]
    assert scan.episodes[1].source.name == "S01E01 - A.MKV"
    assert scan.ignored == [] and scan.warnings == []


def test_hidden_files_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01.mkv")
    _touch(root / ".S01E01.translaterany-tmp.mkv")
    assert [e.key for e in scan_series(root).episodes] == ["S01E01"]


def test_duplicates_are_ignored_with_reason(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01 - A HDTV.mkv")
    _touch(root / "S01E01 - A Bluray.mkv")
    _touch(root / "S01E02.mkv")
    scan = scan_series(root)
    assert [e.key for e in scan.episodes] == ["S01E02"]
    assert len(scan.ignored) == 2 and "duplicado" in scan.ignored[0].reason


def test_recent_files_are_ignored(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01.mkv")
    _touch(root / "S01E02.mkv", age=5)
    scan = scan_series(root, min_file_age=120)
    assert [e.key for e in scan.episodes] == ["S01E01"]
    assert "download" in scan.ignored[0].reason


def test_file_without_pattern_gets_slug_key_and_warning(tmp_path: Path) -> None:
    root = tmp_path / "Filme"
    _touch(root / "Filme (2020).mkv")
    scan = scan_series(root)
    assert scan.episodes[0].key.startswith("filme-2020-")
    assert "sem SxxEyy" in scan.warnings[0]


def test_identity_from_nfo_is_stable_across_moves(tmp_path: Path) -> None:
    nfo = "<tvshow><title>X</title><tvdbid>289679</tvdbid><tmdbid>63145</tmdbid></tvshow>"
    for place in ("a", "b"):
        _touch(tmp_path / place / "Charlotte (2015)" / "tvshow.nfo", nfo)
    key_a = scan_series(tmp_path / "a" / "Charlotte (2015)").series.key
    key_b = scan_series(tmp_path / "b" / "Charlotte (2015)").series.key
    assert key_a == key_b and key_a.startswith("charlotte-2015-")


def test_identity_without_nfo_depends_on_path(tmp_path: Path) -> None:
    for place in ("a", "b"):
        _touch(tmp_path / place / "Serie" / "S01E01.mkv")
    assert scan_series(tmp_path / "a" / "Serie").series.key != scan_series(tmp_path / "b" / "Serie").series.key


def test_broken_nfo_falls_back_to_path(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "tvshow.nfo", "<tvshow><tvdbid>1</tvdb")
    _touch(root / "S01E01.mkv")
    assert scan_series(root).series.key.startswith("serie-")


def test_unicode_series_name(tmp_path: Path) -> None:
    root = tmp_path / "High School D×D (2012)"
    _touch(root / "Specials" / "S00E14 - Levia and So ☆.mkv")
    scan = scan_series(root)
    assert scan.series.key.startswith("high-school-d-d-2012-")
    assert scan.episodes[0].source.name == "S00E14 - Levia and So ☆.mkv"


def test_series_or_library_detection(tmp_path: Path) -> None:
    lib = tmp_path / "Anime"
    _touch(lib / "Serie A" / "Season 1" / "S01E01.mkv")
    _touch(lib / "Serie B" / "tvshow.nfo", "<tvshow/>")
    _touch(lib / "Serie B" / "S01E01.mkv")
    (lib / "Vazia").mkdir()
    assert not is_series_dir(lib)
    assert [s.series.name for s in scan_library(lib)] == ["Serie A", "Serie B"]
    assert [s.series.name for s in scan_library(lib / "Serie A")] == ["Serie A"]


def test_scan_rejects_file(tmp_path: Path) -> None:
    f = _touch(tmp_path / "S01E01.mkv")
    with pytest.raises(NotADirectoryError):
        scan_library(f)


def test_discover_shortcut(tmp_path: Path) -> None:
    root = tmp_path / "Serie"
    _touch(root / "S01E01.mkv", age=0)  # o atalho não filtra por idade
    series, episodes = discover(root)
    assert series.name == "Serie" and [e.key for e in episodes] == ["S01E01"]


def test_series_config_valid(tmp_path: Path) -> None:
    _touch(tmp_path / "series.toml", '[subtitles]\ntrack = "ADZ"\n[styles]\n"Mirror" = "sign"\n')
    config = load_series_config(tmp_path)
    assert config.track == "ADZ" and config.styles == {"Mirror": "sign"}
    assert scan_series(tmp_path).series.config.track == "ADZ"


def test_series_config_absent(tmp_path: Path) -> None:
    config = load_series_config(tmp_path)
    assert config.track is None and config.styles == {}


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("[subtitles\n", "arquivo inválido"),
        ("[metadata]\nx = 1\n", "seção desconhecida"),
        ('[subtitles]\nlang = "en"\n', "apenas 'track'"),
        ('[styles]\n"Mirror" = "placa"\n', "use um de"),
    ],
)
def test_series_config_invalid(tmp_path: Path, text: str, match: str) -> None:
    _touch(tmp_path / "series.toml", text)
    with pytest.raises(SeriesConfigError, match=match):
        load_series_config(tmp_path)


def test_scan_series_reports_broken_series_toml(tmp_path: Path) -> None:
    _touch(tmp_path / "Serie" / "S01E01.mkv")
    _touch(tmp_path / "Serie" / "series.toml", "[subtitles\n")
    scan = scan_series(tmp_path / "Serie")
    assert scan.episodes == [] and scan.error is not None and "series.toml" in scan.error


def test_season_folder_belongs_to_parent_series(tmp_path: Path) -> None:
    root = tmp_path / "Charlotte (2015)"
    _touch(root / "tvshow.nfo", "<tvshow><tvdbid>289679</tvdbid></tvshow>")
    _touch(root / "Season 1" / "S01E01.mkv")
    _touch(root / "Specials" / "S00E02.mkv")
    scans = scan_library(root / "Season 1")
    assert [s.series.name for s in scans] == ["Charlotte (2015)"]
    assert [e.key for e in scans[0].episodes] == ["S01E01"]
    assert scans[0].series.key == scan_series(root).series.key
```

- [ ] **Step 3: Trocar o import da descoberta nos testes existentes**

Em `tests/test_runner.py`, `tests/test_reset_status.py`, `tests/test_inventory.py`, troque a linha

```python
from translaterany.pipeline.units import discover
```

por

```python
from translaterany.library import discover
```

```bash
sed -i 's/from translaterany.pipeline.units import discover/from translaterany.library import discover/' tests/test_runner.py tests/test_reset_status.py tests/test_inventory.py
```

- [ ] **Step 4: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_library.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.library'`

- [ ] **Step 5: Implementar `src/translaterany/util/fs.py`** — **substitui o arquivo inteiro**

```python
"""Utilitários de sistema de arquivos: escrita atômica, slugs e hashing."""

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

TMP_MARKER = ".tmp-"
_MIB = 1024 * 1024
_NON_ALNUM = re.compile(r"[\W_]+")


def slug_base(name: str) -> str:
    """Parte legível do slug: minúsculas, não alfanuméricos viram `-`."""
    return _NON_ALNUM.sub("-", name.lower()).strip("-") or "x"


def slugify(name: str) -> str:
    """Slug estável e seguro para nomes de diretório, com sufixo de hash contra colisões."""
    suffix = hashlib.sha256(name.encode("utf-8")).hexdigest()[:6]
    return f"{slug_base(name)}-{suffix}"


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_MIB), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def fingerprint(path: Path) -> str:
    """Impressão digital barata de arquivos grandes: tamanho + primeiro MiB + último MiB."""
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as fh:
        digest.update(fh.read(_MIB))
        if size > _MIB:
            fh.seek(max(size - _MIB, _MIB))
            digest.update(fh.read(_MIB))
    return "sha256:" + digest.hexdigest()


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    """Grava num temporário no mesmo diretório e renomeia: o arquivo final nunca fica parcial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}{TMP_MARKER}{os.getpid()}")
    with tmp.open("wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write(path, text.encode("utf-8"))


def cleanup_tmp(directory: Path) -> int:
    """Remove temporários deixados por execuções interrompidas. Retorna quantos removeu."""
    if not directory.exists():
        return 0
    removed = 0
    for tmp in directory.rglob(f"*{TMP_MARKER}*"):
        if tmp.is_file():
            tmp.unlink()
            removed += 1
    return removed
```

- [ ] **Step 6: Implementar `src/translaterany/pipeline/units.py`** — **substitui o arquivo inteiro**

```python
"""Unidades de trabalho: série e episódio."""

from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

LINE_TYPES = ("dialogue", "sign", "song", "romaji", "karaoke", "drawing", "comment")


class SeriesConfig(BaseModel):
    """Conteúdo validado do `series.toml` opcional da pasta da série."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    track: str | None = None  # parte do nome da faixa preferida
    styles: dict[str, str] = Field(default_factory=dict)  # estilo -> tipo de linha


@dataclass(frozen=True)
class Series:
    key: str
    name: str
    root: Path
    config: SeriesConfig = field(default_factory=SeriesConfig, compare=False)


@dataclass(frozen=True)
class Episode:
    series: Series
    key: str
    source: Path
```

- [ ] **Step 7: Implementar `src/translaterany/library/episodes.py`**

```python
"""Identificação de episódios pelo nome do arquivo (padrão Sonarr: S01E04, S01E01-02)."""

import re
from dataclasses import dataclass

_PATTERN = re.compile(r"(?<![a-z0-9])s(\d{1,2})e(\d{1,3})(?:-(\d{1,3}))?(?![0-9])", re.IGNORECASE)


@dataclass(frozen=True)
class EpisodeId:
    season: int
    first: int
    last: int | None = None  # episódio múltiplo: S01E01-02

    @property
    def key(self) -> str:
        key = f"S{self.season:02d}E{self.first:02d}"
        return f"{key}-{self.last:02d}" if self.last is not None else key


def parse_episode(filename: str) -> EpisodeId | None:
    """Primeira ocorrência de SxxEyy (ou SxxEyy-zz) no nome; None se não houver."""
    match = _PATTERN.search(filename)
    if match is None:
        return None
    last = int(match.group(3)) if match.group(3) else None
    return EpisodeId(season=int(match.group(1)), first=int(match.group(2)), last=last)
```

- [ ] **Step 8: Implementar `src/translaterany/library/nfo.py`**

```python
"""Identidade estável da série a partir do tvshow.nfo (Jellyfin/Kodi/Sonarr)."""

import xml.etree.ElementTree as ET
from pathlib import Path

_ID_TAGS = (("tvdb", "tvdbid"), ("tmdb", "tmdbid"), ("imdb", "imdb_id"))


def series_identity(root: Path) -> str | None:
    """`tvdb:<id>` (ou tmdb/imdb) do tvshow.nfo; None se ausente ou ilegível."""
    nfo = root / "tvshow.nfo"
    if not nfo.is_file():
        return None
    try:
        tree = ET.parse(nfo)
    except ET.ParseError, OSError:
        return None
    for prefix, tag in _ID_TAGS:
        element = tree.getroot().find(tag)
        if element is not None and element.text and element.text.strip():
            return f"{prefix}:{element.text.strip()}"
    return None
```

- [ ] **Step 9: Implementar `src/translaterany/library/series_config.py`**

```python
"""Leitura do series.toml opcional (a app só lê; o usuário cria)."""

import tomllib
from pathlib import Path

from pydantic import ValidationError

from translaterany.pipeline.units import LINE_TYPES, SeriesConfig

FILENAME = "series.toml"


class SeriesConfigError(Exception):
    """series.toml inválido. Mensagem pronta para o usuário."""


def load_series_config(root: Path) -> SeriesConfig:
    path = root / FILENAME
    if not path.is_file():
        return SeriesConfig()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, OSError) as exc:
        raise SeriesConfigError(f"{path}: arquivo inválido — {exc}") from exc
    unknown = set(raw) - {"subtitles", "styles"}
    if unknown:
        raise SeriesConfigError(f"{path}: seção desconhecida {sorted(unknown)} (use [subtitles] e [styles])")
    subtitles = raw.get("subtitles", {})
    styles = raw.get("styles", {})
    if not isinstance(subtitles, dict) or set(subtitles) - {"track"}:
        raise SeriesConfigError(f"{path}: [subtitles] aceita apenas 'track'")
    for style, kind in styles.items() if isinstance(styles, dict) else []:
        if kind not in LINE_TYPES:
            raise SeriesConfigError(f'{path}: [styles] "{style}" = "{kind}"; use um de {", ".join(LINE_TYPES)}')
    try:
        return SeriesConfig(track=subtitles.get("track"), styles=styles)
    except ValidationError as exc:
        raise SeriesConfigError(f"{path}: {exc.errors()[0]['msg']}") from exc
```

- [ ] **Step 10: Implementar `src/translaterany/library/discovery.py`**

```python
"""Descoberta de séries e episódios numa pasta (uma série ou uma biblioteca)."""

import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from translaterany.library.episodes import parse_episode
from translaterany.library.nfo import series_identity
from translaterany.library.series_config import SeriesConfigError, load_series_config
from translaterany.pipeline.units import Episode, Series
from translaterany.util.fs import slug_base, slugify

_SEASON_DIR = re.compile(r"^(season\s*\d+|specials)$", re.IGNORECASE)


@dataclass(frozen=True)
class Ignored:
    path: Path
    reason: str


@dataclass
class SeriesScan:
    series: Series
    episodes: list[Episode]
    ignored: list[Ignored] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None  # series.toml inválido: a série não é processada


def is_series_dir(path: Path) -> bool:
    if (path / "tvshow.nfo").is_file():
        return True
    for child in path.iterdir():
        if child.is_dir() and _SEASON_DIR.match(child.name):
            return True
        if child.is_file() and _is_video(child):
            return True
    return False


def scan_library(path: Path, *, min_file_age: float = 0.0, now: float | None = None) -> list[SeriesScan]:
    """A pasta é uma série, ou uma biblioteca cujas subpastas (um nível) são séries."""
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"não é uma pasta: {path}")
    if _SEASON_DIR.match(root.name) and is_series_dir(root.parent):  # pasta de temporada: série = pasta-mãe
        return [scan_series(root.parent, min_file_age=min_file_age, now=now, only=root)]
    if is_series_dir(root):
        return [scan_series(root, min_file_age=min_file_age, now=now)]
    children = sorted(c for c in root.iterdir() if c.is_dir() and not c.name.startswith(".") and is_series_dir(c))
    return [scan_series(c, min_file_age=min_file_age, now=now) for c in children]


def scan_series(
    path: Path, *, min_file_age: float = 0.0, now: float | None = None, only: Path | None = None
) -> SeriesScan:
    """Lê o series.toml e lista os episódios. series.toml inválido vira `error` (a série não roda)."""
    root = path.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"não é uma pasta: {path}")
    identity = series_identity(root) or f"path:{root}"
    key = f"{slug_base(root.name)}-{hashlib.sha256(identity.encode()).hexdigest()[:6]}"
    try:
        config = load_series_config(root)
    except SeriesConfigError as exc:
        return SeriesScan(series=Series(key=key, name=root.name, root=root), episodes=[], error=str(exc))
    series = Series(key=key, name=root.name, root=root, config=config)
    scan = SeriesScan(series=series, episodes=[])
    current = time.time() if now is None else now

    by_key: dict[str, list[Path]] = defaultdict(list)
    base = only.resolve() if only is not None else root
    for video in sorted(p for p in base.rglob("*") if p.is_file() and _is_video(p)):
        if any(part.startswith(".") for part in video.relative_to(root).parts):
            continue  # ocultos (inclui temporários da própria app)
        if current - video.stat().st_mtime < min_file_age:
            scan.ignored.append(Ignored(video, "modificado há pouco (possível download em andamento)"))
            continue
        episode_id = parse_episode(video.name)
        if episode_id is None:
            scan.warnings.append(f"sem SxxEyy no nome: {video.name}")
            by_key[slugify(video.stem)].append(video)
        else:
            by_key[episode_id.key].append(video)

    for ep_key, videos in by_key.items():
        if len(videos) > 1:
            names = " e ".join(v.name for v in videos)
            scan.ignored.extend(Ignored(v, f"episódio duplicado ({ep_key}): {names}") for v in videos)
            continue
        scan.episodes.append(Episode(series=series, key=ep_key, source=videos[0]))
    scan.episodes.sort(key=lambda e: e.key)
    return scan


def discover(path: Path) -> tuple[Series, list[Episode]]:
    """Atalho para uma única série, sem filtro de idade (usado por retry/status e nos testes)."""
    scan = scan_series(path)
    return scan.series, scan.episodes


def _is_video(path: Path) -> bool:
    return path.suffix.lower() == ".mkv"
```

- [ ] **Step 11: Implementar `src/translaterany/library/__init__.py`**

```python
from translaterany.library.discovery import (
    Ignored,
    SeriesScan,
    discover,
    is_series_dir,
    scan_library,
    scan_series,
)
from translaterany.library.episodes import EpisodeId, parse_episode
from translaterany.library.series_config import SeriesConfigError, load_series_config

__all__ = [
    "EpisodeId",
    "Ignored",
    "SeriesConfigError",
    "SeriesScan",
    "discover",
    "is_series_dir",
    "load_series_config",
    "parse_episode",
    "scan_library",
    "scan_series",
]
```

- [ ] **Step 12: Trocar o import da descoberta na CLI**

```bash
sed -i 's/from translaterany.pipeline.units import discover/from translaterany.library import discover/' src/translaterany/cli/run.py src/translaterany/cli/status.py src/translaterany/cli/retry.py
# só depois de o pacote library existir, para o ruff reconhecê-lo como do projeto:
uv run ruff check --fix --select I src tests
```

- [ ] **Step 13: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_library.py
```

Expected: PASS — `26 passed`

- [ ] **Step 14: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `133 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 15: Commit**

```bash
git add -A src/translaterany/cli/retry.py src/translaterany/cli/run.py src/translaterany/cli/status.py src/translaterany/library/__init__.py src/translaterany/library/discovery.py src/translaterany/library/episodes.py src/translaterany/library/nfo.py src/translaterany/library/series_config.py src/translaterany/pipeline/units.py src/translaterany/util/fs.py tests/test_inventory.py tests/test_library.py tests/test_reset_status.py tests/test_runner.py tests/test_units.py
git commit -F - <<'EOF'
feat(library): descoberta de séries e episódios com identidade estável e series.toml

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 2: Mudanças no núcleo: entradas por instância, translates, verify_cached, previous_output, force, cache_payload

Implementa o spec §5 no núcleo do M0, mais dois ajustes que surgiram ao prototipar (ver "Desvios"): o gancho `cache_payload()` (para o `series.toml` entrar na chave de cache) e `enabled_by_default` com `StageConfig.enabled = None` (para `[stages.remux.options]` não ligar o remux sem querer). Também acrescenta `[discovery] min_file_age` ao config.

**Files:**
- Modify (substituir): `src/translaterany/pipeline/stage.py`
- Modify (substituir): `src/translaterany/pipeline/cache.py`
- Modify (substituir): `src/translaterany/pipeline/runner.py`
- Modify (substituir): `src/translaterany/config/model.py`
- Modify (substituir): `src/translaterany/config/loader.py`
- Test: `tests/test_core_m1.py`

**Interfaces:**
- Consumes: Tarefa 1 (`discover` em `translaterany.library`).
- Produces:
  - `Stage.inputs` passa a ser atributo comum (pode ser definido no `__init__` a partir das opções)
  - `Stage.translates: ClassVar[bool] = False`, `Stage.enabled_by_default: ClassVar[bool] = True`
  - `Stage.cache_payload(series, episode) -> Any` (padrão `None`) — entra na chave como `extra`
  - `Stage.verify_cached(ctx, artifact_path) -> bool` (padrão `True`) — chamado num cache hit
  - `StageContext.previous_output: Path | None`, `StageContext.force: bool`
  - `Runner.run(series, episodes, *, force=False)` — `force` reabre `skipped`
  - `compute_key(stage, input_hashes, source_fingerprint, episode_set=None, extra=None)`
  - `StageConfig.enabled: bool | None`; `DiscoveryConfig(min_file_age=120)`; `ResolvedConfig.min_file_age`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_core_m1.py`**

```python
"""Mudanças no núcleo para o M1: entradas por instância, verify_cached, previous_output, force."""

from pathlib import Path

import pytest
from fake_stages import SourceStage, Text, UpperStage
from pydantic import BaseModel

from translaterany.config.loader import ConfigError, load_config
from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import StageRegistry
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class PickOptions(BaseModel):
    source: str = "t_source"


class PickStage(Stage):
    """Lê a etapa indicada nas opções (entradas definidas pela instância)."""

    name = "t_pick"
    version = "1"
    scope = StageScope.EPISODE
    Options = PickOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.inputs = (self.options.source,)

    def run(self, ctx: StageContext) -> None:
        ctx.output.json(Text(text="pick:" + ctx.inputs.json(self.options.source, Text).text))


class ExternalStage(Stage):
    """Simula uma etapa com efeito fora do diretório de dados."""

    name = "t_external"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_source",)
    external_ok = True
    calls: list[str] = []
    seen_previous: list[Path | None] = []
    seen_force: list[bool] = []

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        type(self).seen_previous.append(ctx.previous_output)
        type(self).seen_force.append(ctx.force)
        ctx.output.json(Text(text="ok"))

    def verify_cached(self, ctx: StageContext, artifact_path: Path) -> bool:
        return type(self).external_ok


@pytest.fixture(autouse=True)
def _reset_external() -> None:
    ExternalStage.calls = []
    ExternalStage.seen_previous = []
    ExternalStage.seen_force = []
    ExternalStage.external_ok = True


def _run(data_dir: Path, series_dir: Path, stages: list[Stage], force: bool = False):
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    return Runner(stages, store, FakeLLM()).run(series, episodes, force=force), store, series, episodes


def test_instance_inputs_are_used_by_runner(data_dir: Path, series_dir: Path) -> None:
    summary, store, series, episodes = _run(
        data_dir, series_dir, [SourceStage(), UpperStage(), PickStage(PickOptions(source="t_upper"))]
    )
    assert summary.stages["t_pick"].done == 3
    art = store.artifact_dir(series.key, episodes[0].key) / "t_pick.json"
    assert Text.model_validate_json(art.read_text()).text == "pick:EPISODIO 1"


def test_runner_validates_instance_inputs() -> None:
    with pytest.raises(ValueError, match="t_upper"):
        Runner([SourceStage(), PickStage(PickOptions(source="t_upper"))], ArtifactStore(Path("/x")), FakeLLM())


def test_config_validates_instance_inputs(tmp_path: Path, registry: StageRegistry) -> None:
    registry.register(PickStage)
    cfg = tmp_path / "config.toml"
    cfg.write_text('[pipeline]\nstages = ["t_source", "t_pick"]\n[stages.t_pick.options]\nsource = "t_upper"\n')
    with pytest.raises(ConfigError, match="depende de 't_upper'"):
        load_config(cfg, registry=registry, env={})


def test_translates_defaults_to_false() -> None:
    assert SourceStage.translates is False


def test_verify_cached_false_forces_rerun(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert len(ExternalStage.calls) == 3
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_external"].cached == 3
    ExternalStage.external_ok = False
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_external"].done == 3


def test_previous_output_is_offered_on_rerun(data_dir: Path, series_dir: Path) -> None:
    _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert ExternalStage.seen_previous == [None, None, None]
    ExternalStage.external_ok = False
    _, store, series, episodes = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    expected = store.artifact_dir(series.key, episodes[0].key) / "t_external.json"
    assert ExternalStage.seen_previous[3] == expected


def test_force_reopens_skipped_and_reaches_context(data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("SKIP", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_source"].skipped == 1
    (series_dir / "Season 1" / "S01E01.mkv").write_text("liberado", encoding="utf-8")
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()])
    assert summary.stages["t_source"].done == 0  # continua pulado sem --force
    summary, *_ = _run(data_dir, series_dir, [SourceStage(), ExternalStage()], force=True)
    assert summary.stages["t_source"].done == 1
    assert ExternalStage.seen_force[-1] is True
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_core_m1.py
```

Expected: FAIL — `6 failed, 1 passed`

- [ ] **Step 3: Implementar `src/translaterany/pipeline/stage.py`** — **substitui o arquivo inteiro**

```python
"""Interface de etapa. Toda etapa do pipeline implementa `Stage`."""

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.llm.client import LLMClient
from translaterany.pipeline.artifacts import InputReader, OutputWriter
from translaterany.pipeline.units import Episode, Series
from translaterany.util.doctor import Check


class StageScope(StrEnum):
    EPISODE = "episode"
    SERIES = "series"


class NoOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SkipEpisode(Exception):  # noqa: N818 — é um sinal, não um erro
    """Lançada por uma etapa para pular o episódio (ex.: legenda em imagem)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class StageContext:
    series: Series
    episode: Episode | None  # None quando a etapa é de escopo série
    episodes: Sequence[Episode]  # todos os episódios da série
    inputs: InputReader
    output: OutputWriter
    llm: LLMClient
    log: logging.Logger
    previous_output: Path | None = None  # artefato anterior desta etapa para a unidade, se houver
    force: bool = False  # `run --force`: permite sobrescrever PT-BR de terceiros


class Stage(ABC):
    name: ClassVar[str]
    version: ClassVar[str]  # mudar invalida o cache (lógica ou prompt mudou)
    scope: ClassVar[StageScope]
    inputs: tuple[str, ...] = ()  # pode ser redefinido por instância (a partir das opções)
    reads_source: ClassVar[bool] = False  # lê o arquivo de origem diretamente
    translates: ClassVar[bool] = False  # produz texto traduzido (libera publish/remux)
    enabled_by_default: ClassVar[bool] = True  # sem [stages.X] no config, a etapa roda?
    Options: ClassVar[type[BaseModel]] = NoOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        self.options = options if options is not None else self.Options()

    @abstractmethod
    def run(self, ctx: StageContext) -> None:
        """Lê entradas via ctx.inputs e grava exatamente um artefato via ctx.output."""

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        """Dados extras (JSON) que entram na chave de cache — ex.: a parte do series.toml que a etapa usa."""
        return None

    def verify_cached(self, ctx: StageContext, artifact_path: Path) -> bool:
        """Chamado num cache hit. Etapas com efeitos fora do diretório de dados conferem se eles
        ainda estão como registrados; False força a reexecução."""
        return True

    def doctor_checks(self) -> list[Check]:
        return []
```

- [ ] **Step 4: Implementar `src/translaterany/pipeline/cache.py`** — **substitui o arquivo inteiro**

```python
"""Chave de cache de uma etapa para uma unidade."""

from collections.abc import Mapping, Sequence
from typing import Any

from translaterany.pipeline.stage import Stage
from translaterany.util.fs import canonical_json, sha256_bytes


def compute_key(
    stage: Stage,
    input_hashes: Mapping[str, str],
    source_fingerprint: str | None,
    episode_set: Sequence[str] | None = None,
    extra: Any = None,
) -> str:
    """`episode_set`: chaves dos episódios da série (só para etapas de série, que veem `ctx.episodes`)."""
    payload = {
        "stage": stage.name,
        "version": stage.version,
        "options": stage.options.model_dump(mode="json"),
        "inputs": dict(sorted(input_hashes.items())),
        "source": source_fingerprint,
        "episodes": sorted(episode_set) if episode_set is not None else None,
        "extra": extra,  # Stage.cache_payload(): dados de fora do diretório de dados (ex.: series.toml)
    }
    return sha256_bytes(canonical_json(payload))


def combine_hashes(pairs: Mapping[str, str]) -> str:
    """Hash de um conjunto (episódio -> hash), usado quando uma etapa de série lê etapas por episódio."""
    return sha256_bytes(canonical_json(sorted(pairs.items())))
```

- [ ] **Step 5: Implementar `src/translaterany/pipeline/runner.py`** — **substitui o arquivo inteiro**

```python
"""Runner: executa as etapas por etapa (todas as unidades passam pela etapa N antes da N+1)."""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from translaterany.llm.client import LLMClient
from translaterany.pipeline.artifacts import (
    ArtifactStore,
    InputError,
    InputReader,
    ManifestSet,
    OutputWriter,
)
from translaterany.pipeline.cache import combine_hashes, compute_key
from translaterany.pipeline.lock import SeriesLock
from translaterany.pipeline.manifest import StageRecord
from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.util.fs import cleanup_tmp, file_sha256, fingerprint

type Outcome = Literal["done", "cached", "failed", "skipped"]
type ProgressFn = Callable[[str, int, int], None]


@dataclass
class StageCounts:
    done: int = 0
    cached: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass
class RunSummary:
    stages: dict[str, StageCounts] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return any(c.failed for c in self.stages.values())


class Runner:
    def __init__(
        self,
        stages: Sequence[Stage],
        store: ArtifactStore,
        llm: LLMClient,
        log: logging.Logger | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.stages = list(stages)
        self.store = store
        self.llm = llm
        self.log = log or logging.getLogger("translaterany.runner")
        self.on_progress = on_progress
        self._scopes: dict[str, StageScope] = {}
        for stage in self.stages:
            if stage.reads_source and stage.scope is StageScope.SERIES:
                raise ValueError(f"etapa '{stage.name}': reads_source não é suportado em etapas de série")
            for name in stage.inputs:
                if name not in self._scopes:
                    raise ValueError(f"etapa '{stage.name}' depende de '{name}', que não vem antes dela")
            self._scopes[stage.name] = stage.scope

    def run(self, series: Series, episodes: Sequence[Episode], *, force: bool = False) -> RunSummary:
        with SeriesLock(self.store.lock_path(series.key)):
            cleanup_tmp(self.store.series_dir(series.key))
            self.store.write_series_info(series)
            manifests = ManifestSet(self.store, series, episodes)
            for manifest in [manifests.series, *manifests.episodes.values()]:
                if manifest.status == "failed":  # falhas anteriores tentam de novo
                    manifest.status = "ok"
                elif force and manifest.status == "skipped":  # --force reabre os pulados
                    manifest.status = "ok"
                    manifest.skip_reason = None
            summary = RunSummary({s.name: StageCounts() for s in self.stages})
            fingerprints: dict[str, str] = {}

            for stage in self.stages:
                if manifests.series.status != "ok":
                    break
                units: list[Episode | None]
                if stage.scope is StageScope.SERIES:
                    units = [None]
                else:
                    units = [ep for ep in episodes if manifests.get(ep).status == "ok"]
                counts = summary.stages[stage.name]
                for index, unit in enumerate(units, start=1):
                    outcome = self._run_unit(stage, series, unit, episodes, manifests, fingerprints, force)
                    setattr(counts, outcome, getattr(counts, outcome) + 1)
                    if self.on_progress:
                        self.on_progress(stage.name, index, len(units))
            return summary

    def _input_hashes(
        self,
        stage: Stage,
        episode: Episode | None,
        episodes: Sequence[Episode],
        manifests: ManifestSet,
    ) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for name in stage.inputs:
            if self._scopes[name] is StageScope.SERIES:
                hashes[name] = _done_hash(manifests.series.stages.get(name), name)
            elif episode is not None:
                hashes[name] = _done_hash(manifests.get(episode).stages.get(name), name)
            else:
                pairs = {
                    ep.key: _done_hash(manifests.get(ep).stages.get(name), name)
                    for ep in episodes
                    if manifests.get(ep).status == "ok"
                }
                hashes[name] = combine_hashes(pairs)
        return hashes

    def _run_unit(
        self,
        stage: Stage,
        series: Series,
        episode: Episode | None,
        episodes: Sequence[Episode],
        manifests: ManifestSet,
        fingerprints: dict[str, str],
        force: bool = False,
    ) -> Outcome:
        manifest = manifests.get(episode)
        unit_name = episode.key if episode else series.key
        directory = self.store.artifact_dir(series.key, episode.key if episode else None)
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        try:  # origem ilegível ou artefato inacessível falham só esta unidade
            source_fp = None
            if stage.reads_source and episode is not None:
                if episode.key not in fingerprints:
                    fingerprints[episode.key] = fingerprint(episode.source)
                source_fp = fingerprints[episode.key]
            episode_set = [ep.key for ep in episodes] if episode is None else None
            key = compute_key(
                stage,
                self._input_hashes(stage, episode, episodes, manifests),
                source_fp,
                episode_set,
                stage.cache_payload(series, episode),
            )
            record = manifest.stages.get(stage.name)
            previous = None
            if record is not None and record.status == "done" and record.artifact is not None:
                candidate = directory / record.artifact
                previous = candidate if candidate.exists() else None
            writer = OutputWriter(directory, stage.name)
            ctx = self._context(stage, series, episode, episodes, manifests, writer, previous, force)
            if (
                previous is not None
                and record is not None
                and record.key == key
                and file_sha256(previous) == record.artifact_hash
                and stage.verify_cached(ctx, previous)
            ):
                self.log.debug("%s: %s em cache", stage.name, unit_name)
                return "cached"
        except Exception as exc:
            return self._fail(stage, manifests, episode, unit_name, exc, started, t0)

        error: Exception | None = None
        digest = ""
        try:
            stage.run(ctx)
            if writer.path is None:
                raise RuntimeError(f"a etapa '{stage.name}' terminou sem gravar artefato")
            digest = file_sha256(writer.path)
        except SkipEpisode as exc:
            if episode is None:
                error = RuntimeError(f"SkipEpisode não é permitido em etapa de série: {exc.reason}")
            else:
                manifest.status = "skipped"
                manifest.skip_reason = exc.reason
                manifests.save(episode)
                self.log.info("%s: %s pulado — %s", stage.name, unit_name, exc.reason)
                return "skipped"
        except Exception as exc:  # KeyboardInterrupt não é Exception: propaga
            error = exc
        return self._finish(stage, manifests, episode, unit_name, error, digest, key, writer, started, t0)

    def _context(
        self,
        stage: Stage,
        series: Series,
        episode: Episode | None,
        episodes: Sequence[Episode],
        manifests: ManifestSet,
        writer: OutputWriter,
        previous: Path | None,
        force: bool,
    ) -> StageContext:
        return StageContext(
            series=series,
            episode=episode,
            episodes=episodes,
            inputs=InputReader(
                self.store,
                series,
                episode,
                episodes,
                stage.inputs,
                {n: self._scopes[n].value for n in stage.inputs},
                manifests,
            ),
            output=writer,
            llm=self.llm,
            log=self.log.getChild(stage.name),
            previous_output=previous,
            force=force,
        )

    def _finish(
        self,
        stage: Stage,
        manifests: ManifestSet,
        episode: Episode | None,
        unit_name: str,
        error: Exception | None,
        digest: str,
        key: str,
        writer: OutputWriter,
        started: datetime,
        t0: float,
    ) -> Outcome:
        manifest = manifests.get(episode)

        if error is not None:
            return self._fail(stage, manifests, episode, unit_name, error, started, t0)

        assert writer.written is not None
        manifest.stages[stage.name] = StageRecord(
            status="done",
            key=key,
            artifact=writer.written,
            artifact_hash=digest,
            started_at=started,
            finished_at=datetime.now(UTC),
            duration_s=round(time.perf_counter() - t0, 3),
        )
        manifests.save(episode)
        return "done"

    def _fail(
        self,
        stage: Stage,
        manifests: ManifestSet,
        episode: Episode | None,
        unit_name: str,
        error: Exception,
        started: datetime,
        t0: float,
    ) -> Outcome:
        self.log.error("%s: falha em %s — %s: %s", stage.name, unit_name, type(error).__name__, error)
        self.log.debug("traceback da falha em %s", unit_name, exc_info=error)  # arquivo de log / --verbose
        manifest = manifests.get(episode)
        manifest.stages[stage.name] = StageRecord(
            status="failed",
            started_at=started,
            finished_at=datetime.now(UTC),
            duration_s=round(time.perf_counter() - t0, 3),
            error=f"{type(error).__name__}: {error}",
        )
        manifest.status = "failed"
        manifests.save(episode)
        return "failed"


def _done_hash(record: StageRecord | None, name: str) -> str:
    if record is None or record.status != "done" or record.artifact_hash is None:
        raise InputError(f"entrada '{name}' ainda não foi produzida")
    return record.artifact_hash
```

- [ ] **Step 6: Implementar `src/translaterany/config/model.py`** — **substitui o arquivo inteiro**

```python
"""Formato do arquivo de configuração (config.toml)."""

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class GeneralConfig(_Strict):
    data_dir: Path | None = None
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"


class DiscoveryConfig(_Strict):
    min_file_age: float = 120  # segundos; arquivos mais novos são ignorados (download em andamento)


class PipelineConfig(_Strict):
    stages: list[str]


class StageConfig(_Strict):
    enabled: bool | None = None  # None: usa o padrão da etapa (enabled_by_default)
    options: dict[str, Any] = Field(default_factory=dict)


class AppConfig(_Strict):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    pipeline: PipelineConfig | None = None  # ausente = pipeline padrão
    stages: dict[str, StageConfig] = Field(default_factory=dict)
```

- [ ] **Step 7: Implementar `src/translaterany/config/loader.py`** — **substitui o arquivo inteiro**

```python
"""Localiza, lê e valida a configuração, e instancia as etapas habilitadas."""

import os
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from translaterany.config.model import AppConfig, PipelineConfig
from translaterany.pipeline.registry import REGISTRY, StageRegistry
from translaterany.pipeline.stage import Stage, StageScope

CONFIG_ENV = "TRANSLATERANY_CONFIG"


class ConfigError(Exception):
    """Configuração inválida. A mensagem já vem pronta para o usuário (PT-BR)."""


@dataclass(frozen=True)
class ResolvedConfig:
    source: Path | None  # arquivo lido, ou None se usou o padrão embutido
    data_dir: Path
    log_level: str
    stages: tuple[Stage, ...]  # habilitadas, na ordem, já instanciadas
    min_file_age: float = 120


def default_config_path(env: Mapping[str, str] = os.environ) -> Path:
    base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else Path.home() / ".config"
    return base / "translaterany" / "config.toml"


def default_data_dir(env: Mapping[str, str] = os.environ) -> Path:
    base = Path(env["XDG_DATA_HOME"]) if env.get("XDG_DATA_HOME") else Path.home() / ".local" / "share"
    return base / "translaterany"


def find_config(explicit: Path | None, env: Mapping[str, str] = os.environ) -> Path | None:
    """Ordem: --config > $TRANSLATERANY_CONFIG > XDG (se existir) > None (padrão embutido)."""
    if explicit is not None:
        if not explicit.exists():
            raise ConfigError(f"arquivo de configuração não encontrado: {explicit}")
        return explicit
    if env.get(CONFIG_ENV):
        path = Path(env[CONFIG_ENV])
        if not path.exists():
            raise ConfigError(f"{CONFIG_ENV} aponta para arquivo inexistente: {path}")
        return path
    path = default_config_path(env)
    return path if path.exists() else None


def load_config(
    explicit: Path | None = None,
    data_dir_override: Path | None = None,
    *,
    registry: StageRegistry = REGISTRY,
    default_pipeline: Sequence[str] | None = None,
    env: Mapping[str, str] = os.environ,
) -> ResolvedConfig:
    if default_pipeline is None:
        from translaterany.stages import DEFAULT_PIPELINE  # registra as etapas embutidas

        default_pipeline = DEFAULT_PIPELINE
    path = find_config(explicit, env)
    raw: dict[str, Any] = {"pipeline": {"stages": list(default_pipeline)}}
    if path is not None:
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Erro no config ({path}): TOML inválido — {exc}") from exc
    where = str(path) if path else "config padrão"

    try:
        config = AppConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_format_errors(where, exc)) from exc

    if config.pipeline is None:
        config.pipeline = PipelineConfig(stages=list(default_pipeline))
    stages = _build_stages(config, registry, where)
    data_dir = data_dir_override or config.general.data_dir or default_data_dir(env)
    return ResolvedConfig(
        source=path,
        data_dir=Path(data_dir).expanduser(),
        log_level=config.general.log_level,
        stages=tuple(stages),
        min_file_age=config.discovery.min_file_age,
    )


def _build_stages(config: AppConfig, registry: StageRegistry, where: str) -> list[Stage]:
    errors: list[str] = []
    order = config.pipeline.stages

    seen: set[str] = set()
    for name in order:
        if name not in registry:
            errors.append(f"pipeline.stages: etapa desconhecida '{name}' (disponíveis: {', '.join(registry.names())})")
        if name in seen:
            errors.append(f"pipeline.stages: etapa '{name}' aparece mais de uma vez")
        seen.add(name)
    for name in config.stages:
        if name not in order:
            errors.append(f"stages.{name}: seção para etapa que não está em pipeline.stages")
    if errors:
        raise ConfigError(_format(where, errors))

    enabled: list[str] = [n for n in order if _is_enabled(config, registry, n)]
    stages: list[Stage] = []
    available: set[str] = set()
    for name in order:
        cls = registry.get(name)
        stage_cfg = config.stages.get(name)
        options_raw = stage_cfg.options if stage_cfg else {}
        try:
            options = cls.Options.model_validate(options_raw)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"])
                errors.append(f"stages.{name}.options.{loc}: {err['msg']}")
            continue
        if name not in enabled:
            continue
        if cls.reads_source and cls.scope is StageScope.SERIES:
            errors.append(f"stages.{name}: reads_source não é suportado em etapas de série")
        stage = cls(options)  # as entradas podem depender das opções (ex.: write.text_source)
        for dep in stage.inputs:
            if dep not in available:
                if dep not in order:
                    reason = "não está no pipeline"
                elif dep not in enabled:
                    reason = "está desabilitada"
                else:
                    reason = "não vem antes dela no pipeline"
                errors.append(f"stages.{name}: depende de '{dep}', que {reason}")
        stages.append(stage)
        available.add(name)
    if errors:
        raise ConfigError(_format(where, errors))
    return stages


def _is_enabled(config: AppConfig, registry: StageRegistry, name: str) -> bool:
    section = config.stages.get(name)
    if section is not None and section.enabled is not None:
        return section.enabled
    return registry.get(name).enabled_by_default


def _format_errors(where: str, exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "(raiz)"
        lines.append(f"{loc}: {err['msg']}")
    return _format(where, lines)


def _format(where: str, errors: Sequence[str]) -> str:
    return f"Erro no config ({where}):\n" + "\n".join(f"  {e}" for e in errors)
```

- [ ] **Step 8: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_core_m1.py
```

Expected: PASS — `7 passed`

- [ ] **Step 9: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `140 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 10: Commit**

```bash
git add -A src/translaterany/config/loader.py src/translaterany/config/model.py src/translaterany/pipeline/cache.py src/translaterany/pipeline/runner.py src/translaterany/pipeline/stage.py tests/test_core_m1.py
git commit -F - <<'EOF'
feat(core): entradas por instância, verify_cached, previous_output, force e cache_payload

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 3: Parser e gravação de .ass (abordagem A)

Parser próprio orientado a linhas (spec §9): guarda o arquivo como está e troca **só** o campo de texto dos eventos alterados. Inclui a marca de autoria `; TranslaterAny` (D10/D11).

**Files:**
- Create: `src/translaterany/subtitles/ass.py`
- Test: `tests/test_ass.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `AssError`; `MARKER = "; TranslaterAny"`
  - `AssEvent(index, line_no, kind, fields, text, text_offset)` com `.field(name)`, `.start_ms`, `.end_ms`
  - `AssDocument(lines, bom, newline, format, events)`
  - `parse_ass(data: bytes) -> AssDocument`; `render_ass(doc, new_texts: Mapping[int, str], *, marker=False) -> bytes`; `has_marker(data: bytes) -> bool`; `ass_time_to_ms(value) -> int`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_ass.py`**

```python
import pytest

from translaterany.subtitles.ass import AssError, ass_time_to_ms, has_marker, parse_ass, render_ass

HEADER = "[Script Info]\n; Script generated by Aegisub\nTitle: teste\nPlayResX: 1920\n\n"
STYLES = "[V4+ Styles]\nFormat: Name, Fontname\nStyle: Default,Arial\n\n"
EVENTS = (
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    "Comment: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,nota do typesetter\n"
    "Dialogue: 0,0:00:01.50,0:00:03.00,Default,Ana,0,0,0,,Olá, tudo bem, amigo?\n"
    "Dialogue: 1,0:01:02.25,0:01:04.00,Sign,,0,0,0,,{\\pos(10,20)}Placa\n"
)
EXTRA = "\n[Aegisub Extradata]\nData: 1,x,y\n"
SAMPLE = (HEADER + STYLES + EVENTS + EXTRA).encode("utf-8")


def test_roundtrip_is_byte_identical() -> None:
    assert render_ass(parse_ass(SAMPLE), {}) == SAMPLE


def test_events_and_commas_in_text() -> None:
    doc = parse_ass(SAMPLE)
    assert [e.kind for e in doc.events] == ["comment", "dialogue", "dialogue"]
    ev = doc.events[1]
    assert ev.text == "Olá, tudo bem, amigo?"
    assert ev.field("style") == "Default" and ev.field("Name") == "Ana"
    assert (ev.start_ms, ev.end_ms) == (1500, 3000)
    assert doc.events[2].start_ms == 62250


def test_crlf_and_bom_are_preserved() -> None:
    data = ("﻿" + (HEADER + STYLES + EVENTS).replace("\n", "\r\n")).encode("utf-8")
    doc = parse_ass(data)
    assert doc.bom and doc.newline == "\r\n"
    assert render_ass(doc, {}) == data
    changed = render_ass(doc, {1: "Oi"})
    assert b"Default,Ana,0,0,0,,Oi\r\n" in changed
    assert changed.startswith("﻿".encode())


def test_render_changes_only_the_text_field() -> None:
    doc = parse_ass(SAMPLE)
    out = render_ass(doc, {1: "Oi, tudo?"}).decode()
    assert "Dialogue: 0,0:00:01.50,0:00:03.00,Default,Ana,0,0,0,,Oi, tudo?\n" in out
    assert out.replace("Oi, tudo?", "Olá, tudo bem, amigo?") == SAMPLE.decode()


def test_custom_format_order() -> None:
    data = b"[Script Info]\n\n[Events]\nFormat: Start, End, Style, Text\nDialogue: 0:00:00.00,0:00:01.00,Default,a, b\n"
    doc = parse_ass(data)
    assert doc.events[0].text == "a, b" and doc.events[0].field("Style") == "Default"
    assert render_ass(doc, {}) == data


def test_marker_inserted_once_after_script_info() -> None:
    doc = parse_ass(SAMPLE)
    out = render_ass(doc, {}, marker=True)
    assert out.decode().startswith("[Script Info]\n; TranslaterAny\n")
    assert has_marker(out) and not has_marker(SAMPLE)
    again = render_ass(parse_ass(out), {}, marker=True)
    assert again.decode().count("; TranslaterAny") == 1


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (b"[Script Info]\nTitle: x\n", r"\[Events\] ausente"),
        (b"[Events]\nDialogue: 0,0:00:00.00,0:00:01.00,D,,0,0,0,,x\n", "antes da linha Format"),
        (b"[Events]\nFormat: Layer, Text, Start\n", "Text precisa ser a última"),
        (b"[Events]\nFormat: Layer, Start, End, Text\nDialogue: 0,0:00:01.00\n", "campos a menos"),
        (b"[Events]\n", "Format ausente"),
        ("[Events]\nFormat: Text\nDialogue: é\n".encode("latin-1"), "não é UTF-8"),
    ],
)
def test_malformed(data: bytes, match: str) -> None:
    with pytest.raises(AssError, match=match):
        parse_ass(data)


def test_time_parsing() -> None:
    assert ass_time_to_ms("1:02:03.45") == 3723450
    with pytest.raises(AssError):
        ass_time_to_ms("abc")


def test_legacy_ssa_format_with_marked() -> None:
    data = (
        b"[Script Info]\nScriptType: v4.00\n\n[Events]\n"
        b"Format: Marked, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        b"Dialogue: Marked=0,0:00:01.00,0:00:02.00,Default,,0000,0000,0000,,Old, style\n"
    )
    doc = parse_ass(data)
    assert doc.events[0].text == "Old, style" and doc.events[0].start_ms == 1000
    assert render_ass(doc, {}) == data
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_ass.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.subtitles.ass'`

- [ ] **Step 3: Implementar `src/translaterany/subtitles/ass.py`**

```python
"""Parser e gravação de .ass orientados a linhas: tudo que não é texto de evento sai byte a byte."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal

BOM = "﻿"
MARKER = "; TranslaterAny"
_EVENT_KINDS = {"dialogue": "dialogue", "comment": "comment"}


class AssError(Exception):
    """Arquivo .ass malformado. Mensagem pronta para o usuário."""


@dataclass(frozen=True)
class AssEvent:
    index: int  # ordem entre os eventos
    line_no: int  # linha no arquivo (0-based)
    kind: Literal["dialogue", "comment"]
    fields: dict[str, str]  # colunas do Format, exceto Text
    text: str
    text_offset: int  # posição, na linha, onde começa o campo de texto

    def field(self, name: str) -> str:
        """Valor de uma coluna sem diferenciar maiúsculas (ex.: 'style')."""
        for key, value in self.fields.items():
            if key.lower() == name.lower():
                return value
        return ""

    @property
    def start_ms(self) -> int:
        return ass_time_to_ms(self.field("Start"))

    @property
    def end_ms(self) -> int:
        return ass_time_to_ms(self.field("End"))


@dataclass
class AssDocument:
    lines: list[str]  # linhas decodificadas, com terminadores
    bom: bool
    newline: str
    format: list[str]
    events: list[AssEvent] = field(default_factory=list)


def ass_time_to_ms(value: str) -> int:
    """'H:MM:SS.cc' -> milissegundos."""
    try:
        hours, minutes, seconds = value.strip().split(":")
        return round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    except ValueError as exc:
        raise AssError(f"tempo inválido: {value!r}") from exc


def parse_ass(data: bytes) -> AssDocument:
    bom = data.startswith(BOM.encode("utf-8"))
    try:
        text = data.decode("utf-8-sig" if bom else "utf-8")
    except UnicodeDecodeError as exc:
        raise AssError("ASS malformado: não é UTF-8") from exc
    lines = text.splitlines(keepends=True)
    newline = "\r\n" if sum(line.endswith("\r\n") for line in lines) * 2 > len(lines) else "\n"
    doc = AssDocument(lines=lines, bom=bom, newline=newline, format=[])

    section = ""
    seen_events = False
    for line_no, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            seen_events = seen_events or section == "events"
            continue
        if section != "events" or ":" not in stripped:
            continue
        label, _, value = line.partition(":")
        label = label.strip().lower()
        if label == "format":
            doc.format = [col.strip() for col in value.split(",")]
            if not doc.format or doc.format[-1].lower() != "text":
                raise AssError(f"ASS malformado: a coluna Text precisa ser a última do Format (linha {line_no + 1})")
            continue
        if label not in _EVENT_KINDS:
            continue
        if not doc.format:
            raise AssError(f"ASS malformado: evento antes da linha Format (linha {line_no + 1})")
        doc.events.append(_parse_event(line, line_no, _EVENT_KINDS[label], doc.format, len(doc.events)))

    if not seen_events:
        raise AssError("ASS malformado: seção [Events] ausente")
    if not doc.format:
        raise AssError("ASS malformado: linha Format ausente em [Events]")
    return doc


def _parse_event(line: str, line_no: int, kind: str, fmt: list[str], index: int) -> AssEvent:
    body = line.rstrip("\r\n")
    head_end = body.index(":") + 1
    offset = head_end
    values: list[str] = []
    for _ in range(len(fmt) - 1):
        comma = body.find(",", offset)
        if comma < 0:
            raise AssError(f"ASS malformado: evento com campos a menos (linha {line_no + 1})")
        values.append(body[offset:comma].strip())
        offset = comma + 1
    fields = dict(zip(fmt[:-1], values, strict=True))
    return AssEvent(index=index, line_no=line_no, kind=kind, fields=fields, text=body[offset:], text_offset=offset)  # type: ignore[arg-type]


def render_ass(doc: AssDocument, new_texts: Mapping[int, str], *, marker: bool = False) -> bytes:
    """Troca só o campo de texto dos eventos indicados; `marker` insere a marca de autoria."""
    lines = list(doc.lines)
    for index, new_text in new_texts.items():
        event = doc.events[index]
        if new_text == event.text:
            continue
        original = lines[event.line_no]
        terminator = original[len(original.rstrip("\r\n")) :]
        lines[event.line_no] = original[: event.text_offset] + new_text + terminator
    if marker and not any(line.strip() == MARKER for line in lines):
        at = next((i + 1 for i, line in enumerate(lines) if line.strip().lower() == "[script info]"), 0)
        lines.insert(at, MARKER + doc.newline)
    return ((BOM if doc.bom else "") + "".join(lines)).encode("utf-8")


def has_marker(data: bytes) -> bool:
    """O .ass foi produzido pela app a partir de uma tradução (marca D10)?"""
    text = data.decode("utf-8", errors="replace")
    return any(line.strip() == MARKER for line in text.splitlines())
```

- [ ] **Step 4: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_ass.py
```

Expected: PASS — `14 passed`

- [ ] **Step 5: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `154 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 6: Commit**

```bash
git add -A src/translaterany/subtitles/ass.py tests/test_ass.py
git commit -F - <<'EOF'
feat(subtitles): parser e gravação de .ass que preservam o arquivo byte a byte

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 4: Segmentação de texto e normalização em unidades

Separa cada evento em prefixo de tags, texto com marcadores `⟦n⟧` e sufixo (spec §10.1), detecta desenho vetorial e agrupa cópias do mesmo texto em **unidades** (spec §10.2).

**Files:**
- Create: `src/translaterany/subtitles/segments.py`
- Create: `src/translaterany/subtitles/normalize.py`
- Test: `tests/test_segments.py`
- Test: `tests/test_normalize.py`

**Interfaces:**
- Consumes: `parse_ass`, `AssDocument` (Tarefa 3).
- Produces:
  - `segment(raw) -> Segmented(prefix, text, markers, suffix, drawing)`; `SegmentError`
  - `fill(text, markers) -> str`; `marker_ids(text) -> list[int]`; `MARKER_RE`
  - `normalize(doc) -> NormalizedDoc(encoding, format, events: list[EventInfo], units: list[Unit])`; `EventInfo(index, line_no, kind, style, start_ms, end_ms, layer, name, prefix, text, markers, suffix, drawing, unit)`; `Unit(id, style, text, markers, events)`; `NormalizeError`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_segments.py`**

```python
import pytest

from translaterany.subtitles.segments import SegmentError, fill, marker_ids, segment


def _roundtrip(raw: str) -> None:
    seg = segment(raw)
    assert seg.prefix + fill(seg.text, seg.markers) + seg.suffix == raw


def test_prefix_inline_and_suffix() -> None:
    raw = "{\\an8\\pos(960,80)}Olá {\\i1}mundo{\\i0}!{\\fad(0,200)}"
    seg = segment(raw)
    assert seg.prefix == "{\\an8\\pos(960,80)}"
    assert seg.text == "Olá ⟦1⟧mundo⟦2⟧!"
    assert seg.markers == ("{\\i1}", "{\\i0}")
    assert seg.suffix == "{\\fad(0,200)}"
    assert not seg.drawing
    _roundtrip(raw)


def test_plain_text_and_line_breaks() -> None:
    seg = segment("Primeira linha\\NSegunda\\hlinha")
    assert seg.prefix == seg.suffix == "" and seg.markers == ()
    assert seg.text == "Primeira linha\\NSegunda\\hlinha"


def test_adjacent_tags_become_one_marker() -> None:
    seg = segment("a{\\i1}{\\b1}b")
    assert seg.markers == ("{\\i1}{\\b1}",) and seg.text == "a⟦1⟧b"


def test_drawing_only() -> None:
    raw = "{\\p1\\pos(10,10)}m 0 0 l 100 0 100 100 0 100{\\p0}"
    seg = segment(raw)
    assert seg.drawing and seg.text == "" and seg.prefix == raw
    _roundtrip(raw)


def test_pos_is_not_drawing() -> None:
    assert not segment("{\\pos(1,2)}Texto").drawing


def test_drawing_then_text() -> None:
    raw = "{\\p1}m 0 0 l 5 5{\\p0}Legenda"
    seg = segment(raw)
    assert seg.drawing and seg.text == "Legenda"
    _roundtrip(raw)


def test_karaoke_syllables_become_markers() -> None:
    raw = "{\\k20}ka{\\k30}ra{\\k25}o{\\k40}ke"
    seg = segment(raw)
    assert seg.prefix == "{\\k20}" and seg.text == "ka⟦1⟧ra⟦2⟧o⟦3⟧ke"
    _roundtrip(raw)


def test_only_tags() -> None:
    seg = segment("{\\fad(100,100)}")
    assert seg.text == "" and seg.prefix == "{\\fad(100,100)}"


def test_reserved_characters_are_rejected() -> None:
    with pytest.raises(SegmentError):
        segment("texto com ⟦1⟧ literal")


def test_marker_ids() -> None:
    assert marker_ids("a⟦1⟧b⟦2⟧c⟦1⟧") == [1, 2, 1]
```

- [ ] **Step 2: Escrever os testes (devem falhar): `tests/test_normalize.py`**

```python
from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.normalize import normalize


def _doc(*events: str) -> bytes:
    head = (
        "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return (head + "".join(e + "\n" for e in events)).encode("utf-8")


def _ev(start: str, style: str, text: str, kind: str = "Dialogue", end: str | None = None) -> str:
    return f"{kind}: 0,0:00:{start},0:00:{end or start},{style},,0,0,0,,{text}"


def test_frame_by_frame_copies_share_one_unit() -> None:
    data = _doc(
        _ev("01.00", "Sign", "{\\pos(10,10)}Rua Principal"),
        _ev("01.04", "Sign", "{\\pos(11,10)}Rua Principal"),
        _ev("01.08", "Sign", "{\\pos(12,10)}Rua  Principal "),
    )
    nd = normalize(parse_ass(data))
    assert len(nd.units) == 1 and nd.units[0].events == [0, 1, 2]
    assert {e.unit for e in nd.events} == {"u1"}


def test_units_split_by_style_and_marker_count() -> None:
    nd = normalize(
        parse_ass(
            _doc(
                _ev("01.00", "Default", "Oi"),
                _ev("02.00", "Sign", "Oi"),
                _ev("03.00", "Default", "O{\\i1}i"),
            )
        )
    )
    assert [u.id for u in nd.units] == ["u1", "u2", "u3"]


def test_comments_empty_and_drawings_have_no_unit() -> None:
    nd = normalize(
        parse_ass(
            _doc(
                _ev("01.00", "Default", "nota", kind="Comment"),
                _ev("02.00", "Default", "{\\fad(1,1)}"),
                _ev("03.00", "Default", "{\\p1}m 0 0 l 1 1{\\p0}"),
                _ev("04.00", "Default", "Fala"),
            )
        )
    )
    assert [e.unit for e in nd.events] == [None, None, None, "u1"]
    assert nd.events[2].drawing
```

- [ ] **Step 3: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_segments.py tests/test_normalize.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.subtitles.segments'`

- [ ] **Step 4: Implementar `src/translaterany/subtitles/segments.py`**

```python
"""Separação do texto de um evento em prefixo de tags, texto com marcadores e sufixo de tags."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

_BLOCK = re.compile(r"(\{[^}]*\})")
_DRAWING = re.compile(r"\\p(\d+)")
MARKER_RE = re.compile(r"⟦(\d+)⟧")


class SegmentError(Exception):
    """O texto não pode ser segmentado sem ambiguidade."""


@dataclass(frozen=True)
class Segmented:
    prefix: str  # tags antes do primeiro texto
    text: str  # texto com marcadores ⟦n⟧ no lugar das tags internas
    markers: tuple[str, ...]  # tags internas, na ordem
    suffix: str  # tags depois do último texto
    drawing: bool  # continha desenho vetorial (\p1…)


def segment(raw: str) -> Segmented:
    if "⟦" in raw or "⟧" in raw:
        raise SegmentError("o texto original contém os caracteres reservados ⟦ ⟧")
    items: list[tuple[str, str]] = []  # ("tag" | "text", conteúdo)
    drawing_mode = False
    had_drawing = False
    for token in _BLOCK.split(raw):
        if not token:
            continue
        if token.startswith("{") and token.endswith("}"):
            for level in _DRAWING.findall(token):
                drawing_mode = int(level) > 0
            items.append(("tag", token))
        elif drawing_mode:
            had_drawing = True
            items.append(("tag", token))  # comandos vetoriais: nunca são texto
        else:
            items.append(("text", token))

    merged: list[tuple[str, str]] = []
    for kind, content in items:
        if merged and merged[-1][0] == kind:
            merged[-1] = (kind, merged[-1][1] + content)
        else:
            merged.append((kind, content))

    text_positions = [i for i, (kind, _) in enumerate(merged) if kind == "text"]
    if not text_positions:
        return Segmented(prefix=raw, text="", markers=(), suffix="", drawing=had_drawing)
    first, last = text_positions[0], text_positions[-1]
    prefix = "".join(content for _, content in merged[:first])
    suffix = "".join(content for _, content in merged[last + 1 :])
    markers: list[str] = []
    parts: list[str] = []
    for kind, content in merged[first : last + 1]:
        if kind == "text":
            parts.append(content)
        else:
            markers.append(content)
            parts.append(f"⟦{len(markers)}⟧")
    return Segmented(prefix=prefix, text="".join(parts), markers=tuple(markers), suffix=suffix, drawing=had_drawing)


def fill(text: str, markers: Sequence[str]) -> str:
    """Devolve as tags internas no lugar dos marcadores ⟦n⟧."""
    return MARKER_RE.sub(lambda m: markers[int(m.group(1)) - 1], text)


def marker_ids(text: str) -> list[int]:
    return [int(m) for m in MARKER_RE.findall(text)]
```

- [ ] **Step 5: Implementar `src/translaterany/subtitles/normalize.py`**

```python
"""Documento normalizado: eventos segmentados e unidades de texto único."""

import re
from typing import Literal

from pydantic import BaseModel

from translaterany.subtitles.ass import AssDocument
from translaterany.subtitles.segments import fill, segment

_SPACES = re.compile(r"\s+")


class NormalizeError(Exception):
    """Invariante de segmentação violado (bug do parser): nada é gravado."""


class EventInfo(BaseModel):
    index: int
    line_no: int
    kind: Literal["dialogue", "comment"]
    style: str
    start_ms: int
    end_ms: int
    layer: int
    name: str
    prefix: str
    text: str
    markers: list[str]
    suffix: str
    drawing: bool
    unit: str | None  # None: comentário, vazio ou só desenho (nunca traduzido)


class Unit(BaseModel):
    id: str
    style: str
    text: str  # texto da 1ª ocorrência, com marcadores
    markers: int
    events: list[int]


class Encoding(BaseModel):
    bom: bool
    newline: str


class NormalizedDoc(BaseModel):
    encoding: Encoding
    format: list[str]
    events: list[EventInfo]
    units: list[Unit]


def normalize(doc: AssDocument) -> NormalizedDoc:
    events: list[EventInfo] = []
    units: dict[tuple[str, str, int], Unit] = {}
    for ev in doc.events:
        seg = segment(ev.text)
        if seg.prefix + fill(seg.text, seg.markers) + seg.suffix != ev.text:
            raise NormalizeError(f"segmentação não reconstrói o evento {ev.index} (linha {ev.line_no + 1})")
        style = ev.field("Style")
        unit_id = None
        clean = _SPACES.sub(" ", seg.text).strip()
        if ev.kind == "dialogue" and clean:
            key = (style, clean, len(seg.markers))
            if key not in units:
                units[key] = Unit(
                    id=f"u{len(units) + 1}", style=style, text=seg.text, markers=len(seg.markers), events=[]
                )
            units[key].events.append(ev.index)
            unit_id = units[key].id
        layer = ev.field("Layer")
        events.append(
            EventInfo(
                index=ev.index,
                line_no=ev.line_no,
                kind=ev.kind,
                style=style,
                start_ms=ev.start_ms,
                end_ms=ev.end_ms,
                layer=int(layer) if layer.lstrip("-").isdigit() else 0,
                name=ev.field("Name") or ev.field("Actor"),
                prefix=seg.prefix,
                text=seg.text,
                markers=list(seg.markers),
                suffix=seg.suffix,
                drawing=seg.drawing,
                unit=unit_id,
            )
        )
    return NormalizedDoc(
        encoding=Encoding(bom=doc.bom, newline=doc.newline),
        format=doc.format,
        events=events,
        units=list(units.values()),
    )
```

- [ ] **Step 6: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_segments.py tests/test_normalize.py
```

Expected: PASS — `13 passed`

- [ ] **Step 7: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `167 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 8: Commit**

```bash
git add -A src/translaterany/subtitles/normalize.py src/translaterany/subtitles/segments.py tests/test_normalize.py tests/test_segments.py
git commit -F - <<'EOF'
feat(subtitles): segmentação texto/tags e unidades de texto único

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 5: Classificação por regras e cenas

Tipos de linha por nome de estilo e tags (spec §11), estilo principal, marca `uncertain`, precedência do `series.toml` e as cenas de diálogo (movidas do `normalize` para cá — ver "Desvios").

**Files:**
- Create: `src/translaterany/subtitles/classify.py`
- Test: `tests/test_classify.py`

**Interfaces:**
- Consumes: `NormalizedDoc`, `EventInfo` (Tarefa 4).
- Produces:
  - `TRANSLATABLE = {'dialogue', 'sign', 'song'}`
  - `style_tokens(style) -> list[str]`; `style_categories(style) -> set[str]`
  - `classify(doc, overrides: Mapping[str, str], scene_gap_ms=5000) -> Classification(main_style, units: dict[str, UnitClass(type, uncertain, rule)], counts, scenes: list[Scene])`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_classify.py`**

```python
import pytest

from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.classify import classify, style_categories, style_tokens
from translaterany.subtitles.normalize import normalize


def _doc(*events: str) -> bytes:
    head = (
        "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    return (head + "".join(e + "\n" for e in events)).encode("utf-8")


def _ev(start: str, style: str, text: str, kind: str = "Dialogue", end: str | None = None) -> str:
    return f"{kind}: 0,0:00:{start},0:00:{end or start},{style},,0,0,0,,{text}"


@pytest.mark.parametrize(
    ("style", "tokens"),
    [
        ("CharlotteEDEnglish", ["charlotte", "ed", "english"]),
        ("OP - Romaji 2", ["op", "romaji", "2"]),
        ("PikminimanSigns", ["pikminiman", "signs"]),
        ("Charlotte-IN01-Eng", ["charlotte", "in", "in01", "01", "eng"]),
    ],
)
def test_style_tokens(style: str, tokens: list[str]) -> None:
    assert style_tokens(style) == tokens


@pytest.mark.parametrize(
    ("style", "cats"),
    [
        ("CharlotteEDRomaji", {"romaji", "song"}),
        ("OP_Rom", {"romaji", "song"}),
        ("ED Ro Blue", {"romaji", "song"}),
        ("CharlotteEDEnglish", {"song"}),
        ("OP_Eng", {"song"}),
        ("Charlotte-IN01-Eng", {"song"}),
        ("Sign-1", {"sign"}),
        ("SIGNS =", {"sign"}),
        ("FyuSigns", {"sign"}),
        ("GJM_Main", set()),
        ("Tensai_Main", set()),
        ("Default", set()),
        ("Mirror", set()),
    ],
)
def test_style_categories(style: str, cats: set[str]) -> None:
    assert style_categories(style) == cats


def _classify(*events: str, overrides: dict[str, str] | None = None):
    nd = normalize(parse_ass(_doc(*events)))
    return nd, classify(nd, overrides or {})


def test_classification_rules() -> None:
    nd, c = _classify(
        _ev("01.00", "GJM_Main", "Fala um", end="02.00"),
        _ev("02.50", "GJM_Main", "Fala dois", end="03.00"),
        _ev("04.00", "CharlotteEDRomaji", "sora no kanata"),
        _ev("05.00", "CharlotteEDEnglish", "Beyond the sky"),
        _ev("06.00", "FyuSigns", "Estação"),
        _ev("07.00", "OP_Rom", "{\\k20}ka{\\k20}ze"),
        _ev("08.00", "Misc", "{\\pos(1,1)}Aviso"),
        _ev("09.00", "OP Sign", "Letreiro"),
    )
    types = {u.text: c.units[u.id] for u in nd.units}
    assert c.main_style == "GJM_Main"
    assert types["Fala um"].type == "dialogue" and not types["Fala um"].uncertain
    assert types["sora no kanata"].type == "romaji"
    assert types["Beyond the sky"].type == "song"
    assert types["Estação"].type == "sign"
    assert types["ka⟦1⟧ze"].type == "karaoke"
    assert types["Aviso"].type == "sign" and types["Aviso"].uncertain
    assert types["Letreiro"].type == "song" and types["Letreiro"].uncertain  # 'op' e 'sign' ao mesmo tempo
    assert c.counts == {"dialogue": 2, "karaoke": 1, "romaji": 1, "sign": 2, "song": 2}


def test_series_overrides_win() -> None:
    nd, c = _classify(_ev("01.00", "Mirror", "Reflexo"), overrides={"Mirror": "sign"})
    assert c.units["u1"].type == "sign" and c.units["u1"].rule == "series.toml"


def test_scenes_split_on_gaps() -> None:
    _, c = _classify(
        _ev("01.00", "Default", "a", end="02.00"),
        _ev("04.00", "Default", "b", end="05.00"),
        _ev("20.00", "Default", "c", end="21.00"),
        _ev("22.00", "Sign-1", "placa", end="23.00"),
    )
    assert [s.events for s in c.scenes] == [[0, 1], [2]]
    assert (c.scenes[0].start_ms, c.scenes[0].end_ms) == (1000, 5000)
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_classify.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.subtitles.classify'`

- [ ] **Step 3: Implementar `src/translaterany/subtitles/classify.py`**

```python
"""Classificação por regras (tipos de linha) e agrupamento do diálogo em cenas."""

import re
from collections import Counter
from collections.abc import Mapping

from pydantic import BaseModel

from translaterany.subtitles.normalize import EventInfo, NormalizedDoc

TRANSLATABLE = frozenset({"dialogue", "sign", "song"})
_TOKENS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+")
_KARAOKE = re.compile(r"\\[kK][fo]?\d")
_POSITION = re.compile(r"\\(pos|move)\(")
_STYLE_RULES: dict[str, frozenset[str]] = {
    "romaji": frozenset({"rom", "romaji", "ro"}),
    "song": frozenset(
        {"op", "ed", "in", "ins", "insert", "song", "songs", "lyric", "lyrics", "opening", "ending", "karaoke"}
    ),
    "sign": frozenset({"sign", "signs", "ts", "typeset", "title", "card", "note", "screen"}),
}
_IN_NUMBER = re.compile(r"^in\d+$")


class UnitClass(BaseModel):
    type: str
    uncertain: bool
    rule: str


class Scene(BaseModel):
    id: str
    start_ms: int
    end_ms: int
    events: list[int]


class Classification(BaseModel):
    main_style: str | None
    units: dict[str, UnitClass]
    counts: dict[str, int]
    scenes: list[Scene]


def style_tokens(style: str) -> list[str]:
    """'CharlotteEDEnglish' -> ['charlotte', 'ed', 'english']; 'OP - Romaji 2' -> ['op', 'romaji', '2']."""
    tokens = [t.lower() for t in _TOKENS.findall(style)]
    joined: list[str] = []
    for token in tokens:  # 'IN' + '01' -> também 'in01'
        if joined and token.isdigit() and joined[-1] == "in":
            joined.append("in" + token)
        joined.append(token)
    return joined


def style_categories(style: str) -> set[str]:
    tokens = set(style_tokens(style))
    found = {cat for cat, words in _STYLE_RULES.items() if tokens & words}
    if any(_IN_NUMBER.match(t) for t in tokens):
        found.add("song")
    return found


def classify(doc: NormalizedDoc, overrides: Mapping[str, str], scene_gap_ms: int = 5000) -> Classification:
    events = {ev.index: ev for ev in doc.events}
    result: dict[str, UnitClass] = {}
    pending: list[str] = []  # sem regra de estilo: diálogo ou placa (decidido pelo estilo principal)

    for unit in doc.units:
        unit_events = [events[i] for i in unit.events]
        if unit.style in overrides:
            result[unit.id] = UnitClass(type=overrides[unit.style], uncertain=False, rule="series.toml")
            continue
        if any(_KARAOKE.search(_raw(ev)) for ev in unit_events):
            result[unit.id] = UnitClass(type="karaoke", uncertain=False, rule="tag \\k")
            continue
        cats = style_categories(unit.style)
        conflicting = cats - ({"song"} if "romaji" in cats else set())
        uncertain = len(conflicting) > 1
        for kind in ("romaji", "song", "sign"):
            if kind in cats:
                result[unit.id] = UnitClass(type=kind, uncertain=uncertain, rule=f"estilo '{unit.style}'")
                break
        else:
            pending.append(unit.id)

    by_id = {u.id: u for u in doc.units}
    style_count = Counter(by_id[uid].style for uid in pending)
    main_style = style_count.most_common(1)[0][0] if style_count else None
    for uid in pending:
        unit = by_id[uid]
        positioned = any(_POSITION.search(ev.prefix + "".join(ev.markers)) for ev in (events[i] for i in unit.events))
        if unit.style != main_style and positioned:
            result[uid] = UnitClass(type="sign", uncertain=True, rule="\\pos/\\move fora do estilo principal")
        else:
            result[uid] = UnitClass(type="dialogue", uncertain=False, rule="padrão")

    counts = Counter(c.type for c in result.values())
    return Classification(
        main_style=main_style,
        units=result,
        counts=dict(sorted(counts.items())),
        scenes=_scenes(doc, result, scene_gap_ms),
    )


def _raw(ev: EventInfo) -> str:
    return ev.prefix + "".join(ev.markers) + ev.suffix


def _scenes(doc: NormalizedDoc, classes: Mapping[str, UnitClass], gap_ms: int) -> list[Scene]:
    dialogue = sorted(
        (ev for ev in doc.events if ev.unit is not None and classes[ev.unit].type == "dialogue"),
        key=lambda ev: (ev.start_ms, ev.index),
    )
    scenes: list[Scene] = []
    for ev in dialogue:
        if scenes and ev.start_ms - scenes[-1].end_ms <= gap_ms:
            scenes[-1].events.append(ev.index)
            scenes[-1].end_ms = max(scenes[-1].end_ms, ev.end_ms)
        else:
            scenes.append(Scene(id=f"s{len(scenes) + 1}", start_ms=ev.start_ms, end_ms=ev.end_ms, events=[ev.index]))
    return scenes
```

- [ ] **Step 4: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_classify.py
```

Expected: PASS — `20 passed`

- [ ] **Step 5: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `187 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 6: Commit**

```bash
git add -A src/translaterany/subtitles/classify.py tests/test_classify.py
git commit -F - <<'EOF'
feat(subtitles): classificação de linhas por regras e agrupamento em cenas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 6: Mídia: leitura do MKV e escolha da faixa

Leitura de metadados só pelo JSON do `mkvmerge -J`, com `LC_ALL=C.UTF-8` (ver "Desvios"), extração com `mkvextract`, e a regra de seleção de faixa (spec §7) como função pura, testada com JSONs que reproduzem os layouts reais.

**Files:**
- Create: `src/translaterany/media/mkv.py`
- Create: `src/translaterany/media/tracks.py`
- Test: `tests/test_tracks.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `MediaError`; `Track(id, type, codec_id, language, name, default, forced, hearing_impaired)`; `Attachment(id, file_name, content_type)`; `MkvInfo(tracks, attachments, duration_ns).subtitles`
  - `parse_identify(data) -> MkvInfo`; `probe(path) -> MkvInfo`; `extract_track(path, track_id, dest)`; `tool_available(name) -> str | None`; `TEXT_CODECS`, `IMAGE_CODECS`
  - `select_track(info, preferred=None, *, force=False) -> Selection(chosen, reason, candidates, sdh_track_ids, own_track_ids, warnings)`; `NoTrack(reason)`; `OWN_TRACK_NAME`; `is_own`, `is_sdh`, `is_signs`, `is_portuguese`, `is_english_or_und`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_tracks.py`**

```python
"""Seleção de faixa sobre JSONs no formato do `mkvmerge -J` (layouts dos casos de teste reais)."""

import pytest

from translaterany.media.mkv import parse_identify
from translaterany.media.tracks import NoTrack, select_track


def _track(tid: int, name: str, lang: str = "en", codec: str = "S_TEXT/ASS", **flags: bool) -> dict:
    props = {"codec_id": codec, "language": "eng", "language_ietf": lang, "track_name": name}
    props["default_track"] = flags.get("default", False)
    props["forced_track"] = flags.get("forced", False)
    if flags.get("hi"):
        props["flag_hearing_impaired"] = True
    return {"id": tid, "type": "subtitles", "properties": props}


def _info(*subs: dict, attachments: int = 0) -> dict:
    video = {"id": 0, "type": "video", "properties": {"codec_id": "V_MPEGH/ISO/HEVC"}}
    atts = [{"id": i + 1, "file_name": f"f{i}.ttf", "content_type": "font/ttf"} for i in range(attachments)]
    return {
        "container": {"recognized": True, "properties": {"duration": 10**9}},
        "tracks": [video, *subs],
        "attachments": atts,
    }


def _select(*subs: dict, preferred: str | None = None, force: bool = False):
    return select_track(parse_identify(_info(*subs)), preferred, force=force)


def test_parse_identify() -> None:
    info = parse_identify(_info(_track(3, "S&S", default=True), attachments=17))
    assert len(info.attachments) == 17 and info.duration_ns == 10**9
    sub = info.subtitles[0]
    assert (sub.id, sub.name, sub.language, sub.default) == (3, "S&S", "en", True)


def test_charlotte_layout() -> None:
    sel = _select(_track(3, "S&S"), _track(4, "Dialog - ENG"))
    assert sel.chosen.id == 4
    assert {c.id: c.kind for c in sel.candidates} == {3: "signs_songs", 4: "full"}


def test_dxd_season_layout() -> None:
    sel = _select(_track(3, "Full Subtitle (FFF/SCY)", default=True), _track(4, "Signs & Songs (FFF/SCY)"))
    assert sel.chosen.name == "Full Subtitle (FFF/SCY)"


def test_dxd_specials_two_full_prefers_default() -> None:
    sel = _select(_track(2, "Full Subtitle (CBM/IK)", default=True), _track(3, "Full Subtitle (ADZ/IK)"))
    assert sel.chosen.name == "Full Subtitle (CBM/IK)"
    assert "default" in sel.reason


def test_signs_default_does_not_win() -> None:  # D×D S00E18
    sel = _select(_track(2, "Full Subtitle (Tensai/IK)"), _track(3, "Signs & Songs (LostYears)", default=True))
    assert sel.chosen.name == "Full Subtitle (Tensai/IK)"


def test_manual_choice_from_series_toml() -> None:
    sel = _select(
        _track(2, "Full Subtitle (CBM/IK)", default=True), _track(3, "Full Subtitle (ADZ/IK)"), preferred="adz"
    )
    assert sel.chosen.id == 3 and "series.toml" in sel.reason


def test_manual_choice_without_match_warns() -> None:
    sel = _select(_track(2, "Full"), preferred="XYZ")
    assert sel.chosen.id == 2 and "XYZ" in sel.warnings[0]


def test_only_signs_is_used() -> None:
    sel = _select(_track(3, "Signs & Songs"))
    assert sel.chosen.id == 3 and "placas" in sel.reason


def test_sdh_is_never_base_and_is_reported() -> None:
    sel = _select(_track(2, "English (SDH)"), _track(3, "Full"), _track(4, "CC", hi=False), _track(5, "Eng", hi=True))
    assert sel.chosen.id == 3
    assert sel.sdh_track_ids == [2, 4, 5]


def test_only_sdh() -> None:
    with pytest.raises(NoTrack, match="só há legenda SDH"):
        _select(_track(2, "English SDH"))


def test_only_image_subtitles() -> None:
    with pytest.raises(NoTrack, match="imagem"):
        _select(_track(2, "English", codec="S_HDMV/PGS"))


def test_no_english() -> None:
    with pytest.raises(NoTrack, match="sem legenda em inglês"):
        _select(_track(2, "Español", lang="es"))


def test_und_is_candidate() -> None:
    assert _select(_track(2, "Track", lang="und")).chosen.id == 2


def test_srt_is_candidate() -> None:
    assert _select(_track(2, "English", codec="S_TEXT/UTF8")).chosen.id == 2


def test_own_track_is_ignored() -> None:
    sel = _select(_track(2, "Full"), _track(5, "Português (Brasil) — TranslaterAny", lang="pt-BR", default=True))
    assert sel.chosen.id == 2 and sel.own_track_ids == [5]


def test_foreign_ptbr_skips_unless_forced() -> None:
    subs = (_track(2, "Full"), _track(3, "Português", lang="pt-BR"))
    with pytest.raises(NoTrack, match="PT-BR de outra fonte"):
        _select(*subs)
    assert _select(*subs, force=True).chosen.id == 2
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_tracks.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.media.mkv'`

- [ ] **Step 3: Implementar `src/translaterany/media/mkv.py`**

```python
"""Leitura de metadados (mkvmerge -J, independente de idioma) e extração de faixas (mkvextract)."""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TEXT_CODECS = frozenset({"S_TEXT/ASS", "S_TEXT/SSA", "S_TEXT/UTF8"})
IMAGE_CODECS = frozenset({"S_HDMV/PGS", "S_VOBSUB"})


class MediaError(Exception):
    """Falha ao ler ou processar um MKV. Mensagem pronta para o usuário."""


@dataclass(frozen=True)
class Track:
    id: int
    type: str  # video | audio | subtitles
    codec_id: str
    language: str  # IETF quando disponível (ex.: "en", "pt-BR"), senão ISO 639-2
    name: str
    default: bool
    forced: bool
    hearing_impaired: bool


@dataclass(frozen=True)
class Attachment:
    id: int
    file_name: str
    content_type: str


@dataclass(frozen=True)
class MkvInfo:
    tracks: tuple[Track, ...]
    attachments: tuple[Attachment, ...]
    duration_ns: int | None

    @property
    def subtitles(self) -> list[Track]:
        return [t for t in self.tracks if t.type == "subtitles"]


def parse_identify(data: dict[str, Any]) -> MkvInfo:
    """Converte a saída JSON do `mkvmerge -J`."""
    tracks = []
    for raw in data.get("tracks", []):
        props = raw.get("properties", {})
        tracks.append(
            Track(
                id=int(raw["id"]),
                type=raw.get("type", ""),
                codec_id=props.get("codec_id", ""),
                language=props.get("language_ietf") or props.get("language", "und"),
                name=props.get("track_name", ""),
                default=bool(props.get("default_track", False)),
                forced=bool(props.get("forced_track", False)),
                hearing_impaired=bool(props.get("flag_hearing_impaired", False)),
            )
        )
    attachments = tuple(
        Attachment(id=int(a["id"]), file_name=a.get("file_name", ""), content_type=a.get("content_type", ""))
        for a in data.get("attachments", [])
    )
    duration = data.get("container", {}).get("properties", {}).get("duration")
    return MkvInfo(tracks=tuple(tracks), attachments=attachments, duration_ns=int(duration) if duration else None)


def probe(path: Path) -> MkvInfo:
    result = _run(["mkvmerge", "-J", str(path)])
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise MediaError(f"MKV ilegível: resposta inesperada do mkvmerge para {path.name}") from exc
    if not data.get("container", {}).get("recognized", False) or data.get("errors"):
        detail = (data.get("errors") or ["formato não reconhecido"])[0]
        raise MediaError(f"MKV ilegível: {detail}")
    return parse_identify(data)


def extract_track(path: Path, track_id: int, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = _run(["mkvextract", str(path), "tracks", f"{track_id}:{dest}"], check=False)
    if result.returncode > 1 or not dest.exists():
        raise MediaError(f"falha ao extrair a faixa {track_id} de {path.name}: {_first_line(result)}")


def tool_available(name: str) -> str | None:
    return shutil.which(name)


def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    if tool_available(cmd[0]) is None:
        raise MediaError(f"{cmd[0]} não encontrado no PATH (instale o MKVToolNix)")
    result = subprocess.run(
        cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C.UTF-8"}, encoding="utf-8"
    )
    if check and result.returncode > 1:
        raise MediaError(f"MKV ilegível: {_first_line(result)}")
    return result


def _first_line(result: subprocess.CompletedProcess[str]) -> str:
    text = (result.stdout or "") + (result.stderr or "")
    return next((line.strip() for line in text.splitlines() if line.strip()), f"código {result.returncode}")
```

- [ ] **Step 4: Implementar `src/translaterany/media/tracks.py`**

```python
"""Escolha da faixa de legenda em inglês que serve de base para a tradução."""

import re
from dataclasses import dataclass, field

from translaterany.media.mkv import IMAGE_CODECS, TEXT_CODECS, MkvInfo, Track

OWN_TRACK_NAME = "Português (Brasil) — TranslaterAny"
_OWN = re.compile(r"translaterany", re.IGNORECASE)
_SDH = re.compile(r"\bsdh\b|\bcc\b|hearing", re.IGNORECASE)
_SIGNS = re.compile(r"sign|song|s&s|forced", re.IGNORECASE)


class NoTrack(Exception):  # noqa: N818 — vira SkipEpisode
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class CandidateInfo:
    id: int
    name: str
    kind: str  # full | signs_songs | sdh | own | image | other_language
    discarded: str | None


@dataclass
class Selection:
    chosen: Track
    reason: str
    candidates: list[CandidateInfo]
    sdh_track_ids: list[int]
    own_track_ids: list[int]
    warnings: list[str] = field(default_factory=list)


def is_own(track: Track) -> bool:
    return bool(_OWN.search(track.name))


def is_sdh(track: Track) -> bool:
    return track.hearing_impaired or bool(_SDH.search(track.name))


def is_signs(track: Track) -> bool:
    return track.forced or bool(_SIGNS.search(track.name))


def is_portuguese(track: Track) -> bool:
    lang = track.language.lower()
    return lang.startswith("pt") or lang == "por"


def is_english_or_und(track: Track) -> bool:
    lang = track.language.lower()
    return lang.startswith("en") or lang in {"eng", "und"}


def select_track(info: MkvInfo, preferred: str | None = None, *, force: bool = False) -> Selection:
    subs = info.subtitles
    own = [t for t in subs if is_own(t)]
    if not force and any(is_portuguese(t) and not is_own(t) for t in subs):
        raise NoTrack("já existe legenda PT-BR de outra fonte (use --force para sobrescrever)")
    sdh = [t for t in subs if not is_own(t) and is_sdh(t)]
    infos: list[CandidateInfo] = []
    candidates: list[Track] = []
    for track in subs:
        if is_own(track):
            infos.append(CandidateInfo(track.id, track.name, "own", "faixa da própria app"))
        elif track.codec_id in IMAGE_CODECS:
            infos.append(CandidateInfo(track.id, track.name, "image", "legenda em imagem"))
        elif track.codec_id not in TEXT_CODECS or not is_english_or_und(track):
            infos.append(CandidateInfo(track.id, track.name, "other_language", "não é legenda de texto em inglês"))
        elif is_sdh(track):
            infos.append(CandidateInfo(track.id, track.name, "sdh", "SDH/CC nunca é usada como base"))
        else:
            candidates.append(track)

    if not candidates:
        english_text = [t for t in subs if t.codec_id in TEXT_CODECS and is_english_or_und(t) and not is_own(t)]
        if english_text and all(is_sdh(t) for t in english_text):
            raise NoTrack("só há legenda SDH em inglês")
        if any(t.codec_id in IMAGE_CODECS for t in subs):
            raise NoTrack("legenda em imagem (OCR fora da v1)")
        raise NoTrack("sem legenda em inglês")

    warnings: list[str] = []
    chosen: Track | None = None
    reason = ""
    if preferred:
        matches = [t for t in candidates if preferred.lower() in t.name.lower()]
        if matches:
            chosen, reason = matches[0], f"escolha manual (series.toml: '{preferred}')"
        else:
            warnings.append(f"series.toml pede faixa com '{preferred}', mas nenhuma candidata corresponde")
    if chosen is None:
        ordered = sorted(candidates, key=lambda t: (is_signs(t), not t.default, t.id))
        chosen = ordered[0]
        full = [t for t in candidates if not is_signs(t)]
        if is_signs(chosen):
            reason = "única opção: faixa de placas e músicas"
        elif len(full) > 1:
            reason = "faixa completa; desempate pela marca default" if chosen.default else "faixa completa; menor ID"
        else:
            reason = "faixa completa (não é de placas/músicas)"
    for track in candidates:
        if track is not chosen:
            why = "preterida: placas/músicas" if is_signs(track) else "preterida no desempate"
            infos.append(CandidateInfo(track.id, track.name, "signs_songs" if is_signs(track) else "full", why))
    infos.append(CandidateInfo(chosen.id, chosen.name, "signs_songs" if is_signs(chosen) else "full", None))
    infos.sort(key=lambda c: c.id)
    return Selection(
        chosen=chosen,
        reason=reason,
        candidates=infos,
        sdh_track_ids=[t.id for t in sdh],
        own_track_ids=[t.id for t in own],
        warnings=warnings,
    )
```

- [ ] **Step 5: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_tracks.py
```

Expected: PASS — `16 passed`

- [ ] **Step 6: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `203 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 7: Commit**

```bash
git add -A src/translaterany/media/mkv.py src/translaterany/media/tracks.py tests/test_tracks.py
git commit -F - <<'EOF'
feat(media): leitura de MKV via JSON e regra de seleção de faixa

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 7: Etapas select_track e extract

Primeiras etapas reais do M1 (spec §7–8), com MKVs sintéticos gerados pelo `mkvmerge` nos testes. Inclui a conversão de SRT, a checagem de faixas `und` e a detecção de legenda em português de terceiros **em qualquer extensão** (`.pt-BR.srt`, `.pt.ass`, `.por.ass`…).

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (dependências)
- Create: `src/translaterany/subtitles/srt.py`
- Create: `src/translaterany/subtitles/language.py`
- Create: `src/translaterany/stages/select_track.py`
- Create: `src/translaterany/stages/extract.py`
- Create: `tests/mkvtools.py`
- Create: `tests/pipeline_helpers.py`
- Modify (substituir): `tests/conftest.py`
- Test: `tests/test_stages_extract.py`

**Interfaces:**
- Consumes: Tarefas 1–3 e 6.
- Produces:
  - `srt_to_ass(data) -> bytes`; `decode_text(data) -> str`; `looks_english(doc) -> bool`
  - `SelectTrackStage` (`select_track`, `reads_source`, `cache_payload` = `series.config.track`); `SelectTrackArtifact(chosen, reason, candidates, sdh_track_ids, own_track_ids, attachments, warnings)`
  - `external_ptbr_path(episode) -> Path`; `foreign_portuguese_files(episode) -> list[Path]`
  - `ExtractStage` (`extract`, entrada `select_track`) → `extract.ass`
  - Testes: `mkvtools.make_mkv`, `Sub`, `FULL_ASS`, `SIGNS_ASS`, `SRT`, `needs_mkvtoolnix`; `pipeline_helpers.run_stages`, `artifact`; fixture `synthetic_series`

- [ ] **Step 1: Criar/atualizar apoio de testes: `tests/mkvtools.py`**

```python
"""Geração de MKVs sintéticos para testes (só mkvmerge; conteúdo inventado)."""

import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

needs_mkvtoolnix = pytest.mark.skipif(
    shutil.which("mkvmerge") is None or shutil.which("mkvextract") is None,
    reason="MKVToolNix ausente",
)

ASS_HEAD = (
    "[Script Info]\n; Script generated by teste\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
    "[V4+ Styles]\nFormat: Name, Fontname, Fontsize\nStyle: Default,Arial,48\nStyle: Sign-1,Arial,40\n\n"
    "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
)
SIGNS_EVENTS = [
    "Dialogue: 0,0:00:01.00,0:00:02.00,Sign-1,,0,0,0,,{\\pos(100,100)}Estação Central",
    "Dialogue: 0,0:00:01.04,0:00:02.00,Sign-1,,0,0,0,,{\\pos(101,100)}Estação Central",
]
DIALOGUE_EVENTS = [
    "Dialogue: 0,0:00:03.00,0:00:05.00,Default,,0,0,0,,Where are we going, friend?",
    "Dialogue: 0,0:00:05.50,0:00:07.00,Default,,0,0,0,,To the {\\i1}old{\\i0} station.",
]


def ass(events: list[str]) -> str:
    return ASS_HEAD + "".join(e + "\n" for e in events)


FULL_ASS = ass(SIGNS_EVENTS + DIALOGUE_EVENTS)
SIGNS_ASS = ass(SIGNS_EVENTS)
SRT = "1\n00:00:01,000 --> 00:00:02,000\nHello there, how are you?\n\n2\n00:00:03,000 --> 00:00:04,000\nI am fine.\n"


@dataclass
class Sub:
    content: str
    name: str
    lang: str = "en"
    ext: str = ".ass"
    default: bool = False
    forced: bool = False
    hearing_impaired: bool = False


def make_mkv(path: Path, subs: list[Sub], fonts: int = 1, age: float = 3600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.parent / f".work-{path.stem}"
    work.mkdir(exist_ok=True)
    cmd = ["mkvmerge", "-q", "-o", str(path)]
    for i, sub in enumerate(subs):
        file = work / f"{i}{sub.ext}"
        file.write_text(sub.content, encoding="utf-8")
        cmd += [
            "--language", f"0:{sub.lang}",
            "--track-name", f"0:{sub.name}",
            "--default-track-flag", f"0:{'yes' if sub.default else 'no'}",
            "--forced-display-flag", f"0:{'yes' if sub.forced else 'no'}",
            "--hearing-impaired-flag", f"0:{'yes' if sub.hearing_impaired else 'no'}",
            str(file),
        ]  # fmt: skip
    for i in range(fonts):
        font = work / f"font{i}.ttf"
        font.write_bytes(b"\x00\x01\x00\x00fake-font")
        cmd += ["--attachment-mime-type", "font/ttf", "--attach-file", str(font)]
    subprocess.run(cmd, check=True, capture_output=True)
    shutil.rmtree(work)
    old = time.time() - age
    os.utime(path, (old, old))
    return path
```

- [ ] **Step 2: Criar/atualizar apoio de testes: `tests/pipeline_helpers.py`**

```python
"""Funções de apoio para rodar etapas reais sobre MKVs sintéticos."""

from pathlib import Path

from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.runner import Runner
from translaterany.pipeline.stage import Stage


def run_stages(data_dir: Path, root: Path, stages: list[Stage], force: bool = False):
    store = ArtifactStore(data_dir)
    series, episodes = discover(root)
    summary = Runner(stages, store, FakeLLM()).run(series, episodes, force=force)
    return summary, store, series, episodes


def artifact(store: ArtifactStore, series, episode, name: str) -> Path:
    return store.artifact_dir(series.key, episode.key) / name
```

- [ ] **Step 3: Criar/atualizar apoio de testes: `tests/conftest.py`** — **substitui o arquivo inteiro**

```python
"""Fixtures compartilhadas pelos testes."""

from pathlib import Path

import pytest
from fake_stages import TEST_STAGES
from mkvtools import FULL_ASS, SIGNS_ASS, Sub, make_mkv

from translaterany.pipeline.registry import REGISTRY, StageRegistry

for _cls in TEST_STAGES:  # disponíveis também no REGISTRY global (usado pela CLI)
    if _cls.name not in REGISTRY:
        REGISTRY.register(_cls)


@pytest.fixture(autouse=True)
def _reset_calls() -> None:
    for cls in TEST_STAGES:
        cls.calls = []


@pytest.fixture
def registry() -> StageRegistry:
    reg = StageRegistry()
    for cls in TEST_STAGES:
        reg.register(cls)
    return reg


@pytest.fixture
def series_dir(tmp_path: Path) -> Path:
    """Série fictícia com 3 'episódios' (arquivos .mkv de texto)."""
    root = tmp_path / "library" / "Minha Série (2020)"
    (root / "Season 1").mkdir(parents=True)
    for i in (1, 2, 3):
        (root / "Season 1" / f"S01E0{i}.mkv").write_text(f"episodio {i}", encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def synthetic_series(tmp_path: Path) -> Path:
    """Série com um MKV real (só legendas): S&S default, Dialog completa, SDH e 2 fontes."""
    root = tmp_path / "lib" / "Serie (2020)"
    make_mkv(
        root / "Season 1" / "S01E01 - A.mkv",
        [
            Sub(SIGNS_ASS, "S&S", default=True),
            Sub(FULL_ASS, "Dialog - ENG"),
            Sub(FULL_ASS, "English SDH", hearing_impaired=True),
        ],
        fonts=2,
    )
    return root
```

- [ ] **Step 4: Escrever os testes (devem falhar): `tests/test_stages_extract.py`**

```python
"""Etapas select_track e extract com MKVs sintéticos (MKVToolNix real, conteúdo inventado)."""

import json
from pathlib import Path

import pytest
from mkvtools import FULL_ASS, SRT, Sub, make_mkv, needs_mkvtoolnix
from pipeline_helpers import artifact, run_stages

from translaterany.pipeline.stage import Stage
from translaterany.stages.extract import ExtractStage
from translaterany.stages.select_track import SelectTrackStage

pytestmark = needs_mkvtoolnix


def _stages() -> list[Stage]:
    return [SelectTrackStage(), ExtractStage()]


def test_selects_full_track_and_records_sdh_and_fonts(data_dir: Path, synthetic_series: Path) -> None:
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages())
    assert not summary.failed
    select = json.loads(artifact(store, s, eps[0], "select_track.json").read_text())
    assert select["chosen"]["name"] == "Dialog - ENG"
    assert select["sdh_track_ids"] == [2] and len(select["attachments"]) == 2  # sem vídeo: IDs começam em 0
    assert b"Where are we going, friend?" in artifact(store, s, eps[0], "extract.ass").read_bytes()


def test_srt_track_is_converted(data_dir: Path, tmp_path: Path) -> None:
    root = tmp_path / "Srt"
    make_mkv(root / "S01E01.mkv", [Sub(SRT, "English", ext=".srt")], fonts=0)
    summary, store, s, eps = run_stages(data_dir, root, _stages())
    assert not summary.failed
    extracted = artifact(store, s, eps[0], "extract.ass").read_text(encoding="utf-8")
    assert "[Events]" in extracted and "Hello there, how are you?" in extracted


def test_und_track_language_check(data_dir: Path, tmp_path: Path) -> None:
    make_mkv(tmp_path / "A" / "S01E01.mkv", [Sub(FULL_ASS, "Track", lang="und")], fonts=0)
    summary, *_ = run_stages(data_dir, tmp_path / "A", _stages())
    assert summary.stages["extract"].done == 1
    other = FULL_ASS.replace("Where are we going, friend?", "Onde vamos, amigo?").replace(
        "To the {\\i1}old{\\i0} station.", "Para a {\\i1}velha{\\i0} estação."
    )
    make_mkv(tmp_path / "B" / "S01E01.mkv", [Sub(other, "Track", lang="und")], fonts=0)
    summary, *_ = run_stages(data_dir, tmp_path / "B", _stages())
    assert summary.stages["extract"].skipped == 1


def test_corrupt_mkv_fails_only_that_episode(data_dir: Path, synthetic_series: Path) -> None:
    (synthetic_series / "Season 1" / "S01E02 - B.mkv").write_bytes(b"lixo")
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages())
    assert summary.stages["select_track"].failed == 1 and summary.stages["select_track"].done == 1
    manifest = json.loads(store.manifest_path(s.key, "S01E02").read_text())
    assert "MKV ilegível" in manifest["stages"]["select_track"]["error"]


def test_series_toml_changes_invalidate_selection(data_dir: Path, synthetic_series: Path) -> None:
    run_stages(data_dir, synthetic_series, _stages())
    (synthetic_series / "series.toml").write_text('[subtitles]\ntrack = "S&S"\n', encoding="utf-8")
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages())
    assert summary.stages["select_track"].done == 1
    assert json.loads(artifact(store, s, eps[0], "select_track.json").read_text())["chosen"]["name"] == "S&S"


@pytest.mark.parametrize(
    "name", ["S01E01 - A.pt-BR.srt", "S01E01 - A.pt.ass", "S01E01 - A.por.ass", "S01E01 - A.PT-BR.vtt"]
)
def test_foreign_portuguese_external_subtitle_skips(data_dir: Path, synthetic_series: Path, name: str) -> None:
    (synthetic_series / "Season 1" / name).write_text("legenda de outra pessoa", encoding="utf-8")
    summary, *_ = run_stages(data_dir, synthetic_series, _stages())
    assert summary.stages["select_track"].skipped == 1


def test_other_language_external_subtitle_is_fine(data_dir: Path, synthetic_series: Path) -> None:
    (synthetic_series / "Season 1" / "S01E01 - A.es.srt").write_text("subtítulo", encoding="utf-8")
    summary, *_ = run_stages(data_dir, synthetic_series, _stages())
    assert summary.stages["select_track"].done == 1
```

- [ ] **Step 5: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_stages_extract.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.stages.extract'`

- [ ] **Step 6: Instalar as dependências novas**

```bash
uv add pysubs2 charset-normalizer
```

- [ ] **Step 7: Implementar `src/translaterany/subtitles/srt.py`**

```python
"""Conversão de SRT (qualquer codificação) para ASS."""

import charset_normalizer
import pysubs2

from translaterany.subtitles.ass import AssError


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        best = charset_normalizer.from_bytes(data).best()
        if best is None:
            raise AssError("legenda com codificação desconhecida") from None
        return str(best)


def srt_to_ass(data: bytes) -> bytes:
    subs = pysubs2.SSAFile.from_string(decode_text(data), format_="srt")
    return subs.to_string("ass").encode("utf-8")
```

- [ ] **Step 8: Implementar `src/translaterany/subtitles/language.py`**

```python
"""Heurística simples: o texto parece inglês?"""

import re

from translaterany.subtitles.ass import AssDocument

_TAGS = re.compile(r"\{[^}]*\}|\\[Nnh]")
_WORDS = re.compile(r"[a-z']+")
COMMON_ENGLISH = frozenset(
    """the be to of and a in that have i it for not on with he as you do at this but his by from they we say her
    she or an will my one all would there their what so up out if about who get which go me when make can like time
    no just him know take people into year your good some could them see other than then now look only come its
    over think also back after use two how our work first well way even new want because any these give day most
    us is are was were am been has had did does don't i'm it's that's you're what's let's here
    yes okay oh hey""".split()
)
THRESHOLD = 0.15


def english_ratio(doc: AssDocument) -> float:
    words = [w for ev in doc.events if ev.kind == "dialogue" for w in _WORDS.findall(_TAGS.sub(" ", ev.text).lower())]
    if not words:
        return 0.0
    return sum(w in COMMON_ENGLISH for w in words) / len(words)


def looks_english(doc: AssDocument) -> bool:
    return english_ratio(doc) >= THRESHOLD
```

- [ ] **Step 9: Implementar `src/translaterany/stages/select_track.py`**

```python
"""Etapa select_track: escolhe a faixa de legenda em inglês que serve de base."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from translaterany.media.mkv import MediaError, probe, tool_available
from translaterany.media.tracks import NoTrack, select_track
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.ass import has_marker
from translaterany.util.doctor import Check, CheckResult, FunctionCheck


class TrackInfo(BaseModel):
    id: int
    codec_id: str
    language: str
    name: str
    default: bool
    forced: bool


class CandidateModel(BaseModel):
    id: int
    name: str
    kind: str
    discarded: str | None


class AttachmentModel(BaseModel):
    id: int
    file_name: str
    content_type: str


class SelectTrackArtifact(BaseModel):
    chosen: TrackInfo
    reason: str
    candidates: list[CandidateModel]
    sdh_track_ids: list[int]
    own_track_ids: list[int]
    attachments: list[AttachmentModel]
    warnings: list[str]


SUBTITLE_EXTENSIONS = (".ass", ".ssa", ".srt", ".vtt", ".sub")
PORTUGUESE_TAGS = (".pt-br", ".pt", ".por", ".pob")


def external_ptbr_path(episode: Episode) -> Path:
    """Destino da publicação: <vídeo>.pt-BR.ass."""
    return episode.source.with_name(episode.source.stem + ".pt-BR.ass")


def foreign_portuguese_files(episode: Episode) -> list[Path]:
    """Legendas externas em português ao lado do vídeo que não foram feitas pela app."""
    stem = episode.source.stem
    found = []
    for candidate in episode.source.parent.iterdir():
        name = candidate.name
        if not candidate.is_file() or not name.startswith(stem + "."):
            continue
        rest = name[len(stem) :].lower()
        if not rest.endswith(SUBTITLE_EXTENSIONS):
            continue
        tag = rest[: -len(candidate.suffix)]
        if tag in PORTUGUESE_TAGS and not has_marker(candidate.read_bytes()):
            found.append(candidate)
    return sorted(found)


@register_stage
class SelectTrackStage(Stage):
    name = "select_track"
    version = "1"
    scope = StageScope.EPISODE
    reads_source = True

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        return {"track": series.config.track}

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        foreign = foreign_portuguese_files(ctx.episode)
        if foreign and not ctx.force:
            raise SkipEpisode(f"já existe {foreign[0].name} de outra fonte (use --force para sobrescrever)")
        info = probe(ctx.episode.source)
        try:
            sel = select_track(info, ctx.series.config.track, force=ctx.force)
        except NoTrack as exc:
            raise SkipEpisode(exc.reason) from exc
        for warning in sel.warnings:
            ctx.log.warning("%s: %s", ctx.episode.key, warning)
        chosen = sel.chosen
        ctx.output.json(
            SelectTrackArtifact(
                chosen=TrackInfo(
                    id=chosen.id,
                    codec_id=chosen.codec_id,
                    language=chosen.language,
                    name=chosen.name,
                    default=chosen.default,
                    forced=chosen.forced,
                ),
                reason=sel.reason,
                candidates=[CandidateModel(**c.__dict__) for c in sel.candidates],
                sdh_track_ids=sel.sdh_track_ids,
                own_track_ids=sel.own_track_ids,
                attachments=[AttachmentModel(**a.__dict__) for a in info.attachments],
                warnings=sel.warnings,
            )
        )

    def doctor_checks(self) -> list[Check]:
        return [_tool_check("mkvmerge")]


def _tool_check(tool: str) -> Check:
    def run() -> CheckResult:
        path = tool_available(tool)
        if path is None:
            return CheckResult("fail", f"{tool} não encontrado no PATH (instale o MKVToolNix)")
        return CheckResult("ok", f"{tool}: {path}")

    return FunctionCheck(tool, run)


__all__ = [
    "MediaError",
    "SelectTrackArtifact",
    "SelectTrackStage",
    "external_ptbr_path",
    "foreign_portuguese_files",
]
```

- [ ] **Step 10: Implementar `src/translaterany/stages/extract.py`**

```python
"""Etapa extract: extrai a faixa escolhida como .ass (SRT é convertido)."""

import tempfile
from pathlib import Path

from translaterany.media.mkv import extract_track
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope
from translaterany.stages.select_track import SelectTrackArtifact, _tool_check
from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.language import looks_english
from translaterany.subtitles.srt import srt_to_ass
from translaterany.util.doctor import Check


@register_stage
class ExtractStage(Stage):
    name = "extract"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("select_track",)
    reads_source = True

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        track = ctx.inputs.json("select_track", SelectTrackArtifact).chosen
        with tempfile.TemporaryDirectory(prefix="translaterany-") as tmp:
            dest = Path(tmp) / "track"
            extract_track(ctx.episode.source, track.id, dest)
            data = dest.read_bytes()
        if track.codec_id == "S_TEXT/UTF8":
            data = srt_to_ass(data)
        if track.language.lower() == "und" and not looks_english(parse_ass(data)):
            raise SkipEpisode("faixa 'und' não parece inglês")
        ctx.output.file(".ass", data)

    def doctor_checks(self) -> list[Check]:
        return [_tool_check("mkvextract")]
```

- [ ] **Step 11: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_stages_extract.py
```

Expected: PASS — `10 passed`

- [ ] **Step 12: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `213 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 13: Commit**

```bash
git add -A pyproject.toml src/translaterany/stages/extract.py src/translaterany/stages/select_track.py src/translaterany/subtitles/language.py src/translaterany/subtitles/srt.py tests/conftest.py tests/mkvtools.py tests/pipeline_helpers.py tests/test_stages_extract.py uv.lock
git commit -F - <<'EOF'
feat(stages): select_track e extract

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 8: Etapas normalize, classify, write e publish

Completa a leitura e a gravação (spec §10–12): o contrato `UnitTexts`, o `write` com `text_source` (entradas definidas pela instância) e o `publish` travado pela marca de autoria. Uma etapa de tradução **falsa** (`t_translate`, só nos testes) exercita a publicação.

**Files:**
- Create: `src/translaterany/subtitles/texts.py`
- Create: `src/translaterany/stages/normalize.py`
- Create: `src/translaterany/stages/classify.py`
- Create: `src/translaterany/stages/write.py`
- Create: `src/translaterany/stages/publish.py`
- Modify (substituir): `tests/fake_stages.py`
- Test: `tests/test_stages_write.py`

**Interfaces:**
- Consumes: Tarefas 2–5 e 7.
- Produces:
  - `UnitTexts(texts: dict[str, str])`
  - `NormalizeStage` (`normalize`), `ClassifyStage` (`classify`, opção `scene_gap_ms`, `cache_payload` = estilos do `series.toml`)
  - `WriteStage` (`write`, opção `text_source`, padrão `normalize`) → `write.ass`; `TextError`
  - `PublishStage` (`publish`) → `publish.json` = `PublishArtifact(published, reason, path, sha256)`
  - Testes: `TranslateStage` (`t_translate`, `translates = True`) em `fake_stages.py`

- [ ] **Step 1: Criar/atualizar apoio de testes: `tests/fake_stages.py`** — **substitui o arquivo inteiro**

```python
"""Etapas fictícias usadas nos testes do pipeline."""

from pydantic import BaseModel

from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope


class Text(BaseModel):
    text: str


class Collected(BaseModel):
    items: dict[str, str]


class SourceStage(Stage):
    """Lê o arquivo de origem e grava o conteúdo como texto."""

    name = "t_source"
    version = "1"
    scope = StageScope.EPISODE
    reads_source = True
    calls: list[str] = []

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        content = ctx.episode.source.read_bytes().decode("utf-8", "replace")
        if "SKIP" in content:
            raise SkipEpisode("marcado para pular")
        if "FAIL" in content:
            raise RuntimeError("falha simulada")
        if "INTERRUPT" in content:
            raise KeyboardInterrupt
        ctx.output.json(Text(text=content))


class UpperOptions(BaseModel):
    suffix: str = ""


class UpperStage(Stage):
    """Maiúsculas do texto da etapa anterior + sufixo configurável."""

    name = "t_upper"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_source",)
    Options = UpperOptions
    calls: list[str] = []

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        text = ctx.inputs.json("t_source", Text).text
        ctx.output.json(Text(text=text.upper() + self.options.suffix))


class LengthStage(Stage):
    """Depende de t_source; grava só o tamanho (muda pouco)."""

    name = "t_length"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_source",)
    calls: list[str] = []

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        ctx.output.json(Text(text=str(len(ctx.inputs.json("t_source", Text).text))))


class CollectStage(Stage):
    """Etapa de série: junta os resultados de t_upper de todos os episódios."""

    name = "t_collect"
    version = "1"
    scope = StageScope.SERIES
    inputs = ("t_upper",)
    calls: list[str] = []

    def run(self, ctx: StageContext) -> None:
        type(self).calls.append(ctx.series.key)
        items = {k: v.text for k, v in ctx.inputs.json_all("t_upper", Text).items()}
        if any("BOOM" in v for v in items.values()):
            raise RuntimeError("falha na etapa de série")
        ctx.output.json(Collected(items=items))


class ReadSeriesStage(Stage):
    """Etapa por episódio que lê o artefato da etapa de série."""

    name = "t_read_series"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("t_collect",)
    calls: list[str] = []

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        collected = ctx.inputs.json("t_collect", Collected)
        ctx.output.json(Text(text=str(len(collected.items))))


TEST_STAGES: list[type[Stage]] = [SourceStage, UpperStage, LengthStage, CollectStage, ReadSeriesStage]


class TranslateStage(Stage):
    """Tradução falsa: põe em maiúsculas as unidades traduzíveis (mantém os marcadores)."""

    name = "t_translate"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("normalize", "classify")
    translates = True
    calls: list[str] = []

    def run(self, ctx: StageContext) -> None:
        from translaterany.subtitles.classify import TRANSLATABLE, Classification
        from translaterany.subtitles.normalize import NormalizedDoc
        from translaterany.subtitles.texts import UnitTexts

        assert ctx.episode is not None
        type(self).calls.append(ctx.episode.key)
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classes = ctx.inputs.json("classify", Classification)
        texts = {u.id: u.text.upper() for u in doc.units if classes.units[u.id].type in TRANSLATABLE}
        ctx.output.json(UnitTexts(texts=texts))


TEST_STAGES.append(TranslateStage)
```

- [ ] **Step 2: Escrever os testes (devem falhar): `tests/test_stages_write.py`**

```python
"""Etapas normalize, classify, write e publish com MKVs sintéticos."""

import json
from pathlib import Path

from mkvtools import needs_mkvtoolnix
from pipeline_helpers import artifact, run_stages

from translaterany.pipeline.stage import Stage
from translaterany.stages.classify import ClassifyStage
from translaterany.stages.extract import ExtractStage
from translaterany.stages.normalize import NormalizeStage
from translaterany.stages.publish import PublishStage
from translaterany.stages.select_track import SelectTrackStage
from translaterany.stages.write import WriteOptions, WriteStage

pytestmark = needs_mkvtoolnix


def _stages(translate: bool = False) -> list[Stage]:
    from fake_stages import TranslateStage

    stages: list[Stage] = [SelectTrackStage(), ExtractStage(), NormalizeStage(), ClassifyStage()]
    if translate:
        stages.append(TranslateStage())
    stages.append(WriteStage(WriteOptions(text_source="t_translate" if translate else "normalize")))
    stages.append(PublishStage())
    return stages


def test_pipeline_without_translation_is_identity(data_dir: Path, synthetic_series: Path) -> None:
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages())
    assert not summary.failed
    extracted = artifact(store, s, eps[0], "extract.ass").read_bytes()
    assert artifact(store, s, eps[0], "write.ass").read_bytes() == extracted
    publish = json.loads(artifact(store, s, eps[0], "publish.json").read_text())
    assert publish == {"published": False, "reason": "pipeline sem tradução", "path": None, "sha256": None}
    assert not list(synthetic_series.rglob("*.pt-BR.ass"))
    classify = json.loads(artifact(store, s, eps[0], "classify.json").read_text())
    assert classify["counts"] == {"dialogue": 2, "sign": 1}


def test_translation_is_published_next_to_video(data_dir: Path, synthetic_series: Path) -> None:
    _, store, s, eps = run_stages(data_dir, synthetic_series, _stages(translate=True))
    published = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    text = published.read_text(encoding="utf-8")
    assert "; TranslaterAny" in text
    assert "WHERE ARE WE GOING, FRIEND?" in text
    assert "TO THE {\\i1}OLD{\\i0} STATION." in text
    assert "{\\pos(101,100)}ESTAÇÃO CENTRAL" in text


def test_deleted_publication_is_restored(data_dir: Path, synthetic_series: Path) -> None:
    run_stages(data_dir, synthetic_series, _stages(translate=True))
    published = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    published.unlink()
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True))
    assert summary.stages["publish"].done == 1 and published.exists()


def test_foreign_ptbr_file_skips_unless_forced(data_dir: Path, synthetic_series: Path) -> None:
    foreign = synthetic_series / "Season 1" / "S01E01 - A.pt-BR.ass"
    foreign.write_text("legenda de outra pessoa", encoding="utf-8")
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True))
    assert summary.stages["select_track"].skipped == 1
    assert foreign.read_text(encoding="utf-8") == "legenda de outra pessoa"
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True), force=True)
    assert summary.stages["publish"].done == 1
    assert "; TranslaterAny" in foreign.read_text(encoding="utf-8")
```

- [ ] **Step 3: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_stages_write.py
```

Expected: FAIL — `ModuleNotFoundError: No module named 'translaterany.stages.classify'`

- [ ] **Step 4: Implementar `src/translaterany/subtitles/texts.py`**

```python
"""Contrato das etapas de texto: {id da unidade: texto com marcadores ⟦n⟧}."""

from pydantic import BaseModel, Field


class UnitTexts(BaseModel):
    texts: dict[str, str] = Field(default_factory=dict)
```

- [ ] **Step 5: Implementar `src/translaterany/stages/normalize.py`**

```python
"""Etapa normalize: segmenta os eventos e agrupa textos únicos."""

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.ass import parse_ass
from translaterany.subtitles.normalize import normalize


@register_stage
class NormalizeStage(Stage):
    name = "normalize"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("extract",)

    def run(self, ctx: StageContext) -> None:
        doc = parse_ass(ctx.inputs.path("extract").read_bytes())
        ctx.output.json(normalize(doc))
```

- [ ] **Step 6: Implementar `src/translaterany/stages/classify.py`**

```python
"""Etapa classify: tipo de cada unidade (regras) e cenas de diálogo."""

from typing import Any

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.subtitles.classify import classify
from translaterany.subtitles.normalize import NormalizedDoc


class ClassifyOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_gap_ms: int = 5000


@register_stage
class ClassifyStage(Stage):
    name = "classify"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("normalize",)
    Options = ClassifyOptions

    def cache_payload(self, series: Series, episode: Episode | None) -> Any:
        return {"styles": dict(sorted(series.config.styles.items()))}

    def run(self, ctx: StageContext) -> None:
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        ctx.output.json(classify(doc, ctx.series.config.styles, self.options.scene_gap_ms))
```

- [ ] **Step 7: Implementar `src/translaterany/stages/write.py`**

```python
"""Etapa write: remonta o .ass com os textos da etapa indicada em text_source."""

from pydantic import BaseModel, ConfigDict

from translaterany.pipeline.registry import REGISTRY, register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.ass import parse_ass, render_ass
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import fill, marker_ids
from translaterany.subtitles.texts import UnitTexts

ORIGINAL = "normalize"


class WriteOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text_source: str = ORIGINAL


class TextError(Exception):
    """Texto de uma etapa de tradução não devolveu os marcadores da unidade."""


@register_stage
class WriteStage(Stage):
    name = "write"
    version = "1"
    scope = StageScope.EPISODE
    Options = WriteOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        source = self.options.text_source
        self.inputs = ("extract", ORIGINAL) if source == ORIGINAL else ("extract", ORIGINAL, source)

    def run(self, ctx: StageContext) -> None:
        source = self.options.text_source
        doc = parse_ass(ctx.inputs.path("extract").read_bytes())
        normalized = ctx.inputs.json(ORIGINAL, NormalizedDoc)
        texts = {} if source == ORIGINAL else ctx.inputs.json(source, UnitTexts).texts
        markers_by_unit = {u.id: u.markers for u in normalized.units}
        new_texts: dict[int, str] = {}
        for ev in normalized.events:
            if ev.unit is None or ev.unit not in texts:
                continue
            text = texts[ev.unit]
            expected = list(range(1, markers_by_unit[ev.unit] + 1))
            if sorted(marker_ids(text)) != expected:
                raise TextError(f"unidade {ev.unit}: o texto precisa conter exatamente os marcadores {expected}")
            new_texts[ev.index] = ev.prefix + fill(text, ev.markers) + ev.suffix
        translates = source in REGISTRY and REGISTRY.get(source).translates
        ctx.output.file(".ass", render_ass(doc, new_texts, marker=translates))
```

- [ ] **Step 8: Implementar `src/translaterany/stages/publish.py`**

```python
"""Etapa publish: copia o .ass traduzido para <vídeo>.pt-BR.ass ao lado do MKV."""

import os
from pathlib import Path

from pydantic import BaseModel

from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope
from translaterany.stages.select_track import external_ptbr_path
from translaterany.subtitles.ass import has_marker
from translaterany.util.fs import file_sha256


class PublishArtifact(BaseModel):
    published: bool
    reason: str
    path: str | None = None
    sha256: str | None = None


@register_stage
class PublishStage(Stage):
    name = "publish"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("write",)

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        source = ctx.inputs.path("write")
        data = source.read_bytes()
        if not has_marker(data):
            ctx.output.json(PublishArtifact(published=False, reason="pipeline sem tradução"))
            return
        dest = external_ptbr_path(ctx.episode)
        if dest.is_file() and not has_marker(dest.read_bytes()) and not ctx.force:
            raise SkipEpisode(f"já existe {dest.name} de outra fonte (use --force para sobrescrever)")
        tmp = dest.with_name(f".{dest.name}.translaterany-tmp")
        try:
            tmp.write_bytes(data)
            os.replace(tmp, dest)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise OSError(f"não foi possível gravar em {dest}; a legenda está em {source}") from exc
        ctx.output.json(PublishArtifact(published=True, reason="publicado", path=str(dest), sha256=file_sha256(dest)))

    def verify_cached(self, ctx: StageContext, artifact_path: Path) -> bool:
        art = PublishArtifact.model_validate_json(artifact_path.read_text(encoding="utf-8"))
        if not art.published or art.path is None:
            return True
        dest = Path(art.path)
        return dest.is_file() and file_sha256(dest) == art.sha256
```

- [ ] **Step 9: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_stages_write.py
```

Expected: PASS — `4 passed`

- [ ] **Step 10: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `217 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 11: Commit**

```bash
git add -A src/translaterany/stages/classify.py src/translaterany/stages/normalize.py src/translaterany/stages/publish.py src/translaterany/stages/write.py src/translaterany/subtitles/texts.py tests/fake_stages.py tests/test_stages_write.py
git commit -F - <<'EOF'
feat(stages): normalize, classify, write e publish

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 9: Remux seguro e idempotente

Reinserção no MKV (spec §13): espaço livre, temporário oculto, verificação, troca atômica, backup opcional e idempotência pela impressão digital registrada (sem laço).

**Files:**
- Create: `src/translaterany/media/remux.py`
- Create: `src/translaterany/stages/remux.py`
- Test: `tests/test_stages_remux.py`

**Interfaces:**
- Consumes: Tarefas 2, 6, 7 e 8.
- Produces:
  - `remux(mkv, ass, *, remove_ids, keep_backup, log) -> Path | None`; `build_command(...)`; `verify(original, result, removed)`; `temp_path(mkv)`
  - `RemuxStage` (`remux`, `enabled_by_default = False`, opções `keep_backup`, `remove_sdh`) → `RemuxArtifact(status, mkv_fingerprint_after, ass_sha256, removed_track_ids, backup)`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_stages_remux.py`**

```python
"""Etapa remux com MKVs sintéticos."""

import json
from pathlib import Path

import pytest
from mkvtools import needs_mkvtoolnix
from pipeline_helpers import artifact, run_stages

from translaterany.media import remux as remux_module
from translaterany.media.mkv import MediaError, probe
from translaterany.pipeline.stage import Stage
from translaterany.stages.classify import ClassifyStage
from translaterany.stages.extract import ExtractStage
from translaterany.stages.normalize import NormalizeStage
from translaterany.stages.publish import PublishStage
from translaterany.stages.remux import RemuxOptions, RemuxStage
from translaterany.stages.select_track import SelectTrackStage
from translaterany.stages.write import WriteOptions, WriteStage
from translaterany.util.fs import fingerprint

pytestmark = needs_mkvtoolnix


def _stages(translate: bool = False, remux: bool = False, keep_backup: bool = False) -> list[Stage]:
    from fake_stages import TranslateStage

    stages: list[Stage] = [SelectTrackStage(), ExtractStage(), NormalizeStage(), ClassifyStage()]
    if translate:
        stages.append(TranslateStage())
    stages.append(WriteStage(WriteOptions(text_source="t_translate" if translate else "normalize")))
    stages.append(PublishStage())
    if remux:
        stages.append(RemuxStage(RemuxOptions(keep_backup=keep_backup)))
    return stages


def test_remux_adds_default_ptbr_and_removes_sdh(data_dir: Path, synthetic_series: Path) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    assert not summary.failed
    info = probe(mkv)
    subs = {t.name: t for t in info.subtitles}
    assert set(subs) == {"S&S", "Dialog - ENG", "Português (Brasil) — TranslaterAny"}
    assert [t.name for t in info.subtitles if t.default] == ["Português (Brasil) — TranslaterAny"]
    assert subs["Português (Brasil) — TranslaterAny"].language == "pt-BR"
    assert len(info.attachments) == 2
    assert not list(mkv.parent.glob(".*translaterany-tmp*"))
    remux = json.loads(artifact(store, s, eps[0], "remux.json").read_text())
    assert remux["status"] == "remuxed" and remux["removed_track_ids"] == [2]


def test_remux_does_not_loop(data_dir: Path, synthetic_series: Path) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    after_first = fingerprint(mkv)
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    assert fingerprint(mkv) == after_first
    assert json.loads(artifact(store, s, eps[0], "remux.json").read_text())["status"] == "up_to_date"
    assert summary.stages["normalize"].cached == 1 and summary.stages["t_translate"].cached == 1
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    assert all(c.done == 0 for c in summary.stages.values())


def test_remux_verification_failure_keeps_original(data_dir: Path, synthetic_series: Path, monkeypatch) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    before = fingerprint(mkv)

    def broken(*args, **kwargs):
        raise MediaError("verificação do remux falhou: simulada")

    monkeypatch.setattr(remux_module, "verify", broken)
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    assert summary.stages["remux"].failed == 1
    assert fingerprint(mkv) == before
    assert not list(mkv.parent.glob(".*translaterany-tmp*"))


def test_remux_keep_backup(data_dir: Path, synthetic_series: Path) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    before = fingerprint(mkv)
    run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True, keep_backup=True))
    backup = mkv.with_name(mkv.name + ".bak")
    assert backup.exists() and fingerprint(backup) == before


def test_remux_without_translation_does_nothing(data_dir: Path, synthetic_series: Path) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    before = fingerprint(mkv)
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages(remux=True))
    assert fingerprint(mkv) == before
    assert json.loads(artifact(store, s, eps[0], "remux.json").read_text())["status"] == "not_translated"


def test_ctrl_c_during_remux_leaves_original_and_no_temp(data_dir: Path, synthetic_series: Path, monkeypatch) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    before = fingerprint(mkv)
    real_run = remux_module.subprocess.run

    def interrupted(cmd, **kwargs):
        real_run(cmd, **kwargs)  # o temporário chega a ser criado
        raise KeyboardInterrupt

    monkeypatch.setattr(remux_module.subprocess, "run", interrupted)
    with pytest.raises(KeyboardInterrupt):
        run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    assert fingerprint(mkv) == before
    assert not list(mkv.parent.glob(".*translaterany-tmp*"))


def test_mkvmerge_warnings_are_accepted(data_dir: Path, synthetic_series: Path, monkeypatch) -> None:
    real_run = remux_module.subprocess.run

    def with_warnings(cmd, **kwargs):
        result = real_run(cmd, **kwargs)
        result.returncode = 1
        return result

    monkeypatch.setattr(remux_module.subprocess, "run", with_warnings)
    summary, *_ = run_stages(data_dir, synthetic_series, _stages(translate=True, remux=True))
    assert summary.stages["remux"].done == 1
```

- [ ] **Step 2: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_stages_remux.py
```

Expected: FAIL — `ImportError: cannot import name 'remux' from 'translaterany.media' (src/translaterany/media/__init__.py)`

- [ ] **Step 3: Implementar `src/translaterany/media/remux.py`**

```python
"""Reinserção da legenda PT-BR no MKV: temporário oculto, verificação e troca atômica."""

import logging
import os
import shutil
import subprocess
from pathlib import Path

from translaterany.media.mkv import MediaError, MkvInfo, probe
from translaterany.media.tracks import OWN_TRACK_NAME, is_own, is_portuguese

SPACE_MARGIN = 1.05
DURATION_TOLERANCE_NS = 1_000_000_000


def temp_path(mkv: Path) -> Path:
    return mkv.with_name(f".{mkv.stem}.translaterany-tmp.mkv")


def build_command(mkv: Path, ass: Path, out: Path, info: MkvInfo, remove_ids: list[int]) -> list[str]:
    cmd = ["mkvmerge", "-o", str(out)]
    if remove_ids:
        cmd += ["--subtitle-tracks", "!" + ",".join(str(i) for i in sorted(remove_ids))]
    for track in info.subtitles:
        if track.id not in remove_ids:
            cmd += ["--default-track-flag", f"{track.id}:no"]
    cmd.append(str(mkv))
    cmd += ["--language", "0:pt-BR", "--track-name", f"0:{OWN_TRACK_NAME}", "--default-track-flag", "0:yes", str(ass)]
    return cmd


def verify(original: MkvInfo, result: MkvInfo, removed: int) -> None:
    expected = len(original.tracks) - removed + 1
    if len(result.tracks) != expected:
        raise MediaError(f"verificação do remux falhou: {len(result.tracks)} faixas, esperado {expected}")
    if original.duration_ns and result.duration_ns:
        if abs(original.duration_ns - result.duration_ns) > DURATION_TOLERANCE_NS:
            raise MediaError("verificação do remux falhou: duração diferente da original")
    if len(result.attachments) != len(original.attachments):
        raise MediaError("verificação do remux falhou: anexos (fontes) perdidos")
    defaults = [t for t in result.subtitles if t.default]
    if len(defaults) != 1 or not (is_own(defaults[0]) and is_portuguese(defaults[0])):
        raise MediaError("verificação do remux falhou: a faixa PT-BR não ficou como a única default")


def remux(
    mkv: Path,
    ass: Path,
    *,
    remove_ids: list[int],
    keep_backup: bool,
    log: logging.Logger,
) -> Path | None:
    """Substitui `mkv` por uma versão com a faixa PT-BR. Devolve o caminho do backup, se houver."""
    size = mkv.stat().st_size
    free = shutil.disk_usage(mkv.parent).free
    if free < size * SPACE_MARGIN:
        need = size * SPACE_MARGIN / 1e9
        raise MediaError(f"sem espaço para o remux: precisa de {need:.1f} GB livres em {mkv.parent}")
    original = probe(mkv)
    tmp = temp_path(mkv)
    try:
        cmd = build_command(mkv, ass, tmp, original, remove_ids)
        result = subprocess.run(
            cmd, capture_output=True, text=True, env={**os.environ, "LC_ALL": "C.UTF-8"}, encoding="utf-8"
        )
        if result.returncode == 1:
            log.warning("mkvmerge terminou com avisos: %s", result.stdout.strip()[-500:])
        elif result.returncode != 0:
            raise MediaError(f"mkvmerge falhou no remux: {result.stdout.strip()[-300:] or result.returncode}")
        verify(original, probe(tmp), len(remove_ids))
        backup = None
        if keep_backup:
            backup = mkv.with_name(mkv.name + ".bak")
            os.replace(mkv, backup)
        os.replace(tmp, mkv)
        return backup
    finally:
        tmp.unlink(missing_ok=True)
```

- [ ] **Step 4: Implementar `src/translaterany/stages/remux.py`**

```python
"""Etapa remux: reinsere a legenda PT-BR no MKV (desligada por padrão)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from translaterany.media.remux import remux
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.stages.select_track import SelectTrackArtifact
from translaterany.subtitles.ass import has_marker
from translaterany.util.fs import file_sha256, fingerprint


class RemuxOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep_backup: bool = False
    remove_sdh: bool = True


class RemuxArtifact(BaseModel):
    status: Literal["not_translated", "remuxed", "up_to_date"]
    mkv_fingerprint_after: str | None = None
    ass_sha256: str | None = None
    removed_track_ids: list[int] = []
    backup: str | None = None


@register_stage
class RemuxStage(Stage):
    name = "remux"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("write", "select_track")
    reads_source = True
    enabled_by_default = False
    Options = RemuxOptions

    def run(self, ctx: StageContext) -> None:
        assert ctx.episode is not None
        ass = ctx.inputs.path("write")
        if not has_marker(ass.read_bytes()):
            ctx.output.json(RemuxArtifact(status="not_translated"))
            return
        mkv = ctx.episode.source
        ass_hash = file_sha256(ass)
        previous = _load(ctx.previous_output)
        if (
            previous is not None
            and previous.status in ("remuxed", "up_to_date")
            and previous.mkv_fingerprint_after == fingerprint(mkv)
            and previous.ass_sha256 == ass_hash
        ):
            ctx.output.json(previous.model_copy(update={"status": "up_to_date"}))
            return
        select = ctx.inputs.json("select_track", SelectTrackArtifact)
        remove = sorted(set(select.own_track_ids) | (set(select.sdh_track_ids) if self.options.remove_sdh else set()))
        backup = remux(mkv, ass, remove_ids=remove, keep_backup=self.options.keep_backup, log=ctx.log)
        ctx.output.json(
            RemuxArtifact(
                status="remuxed",
                mkv_fingerprint_after=fingerprint(mkv),
                ass_sha256=ass_hash,
                removed_track_ids=remove,
                backup=str(backup) if backup else None,
            )
        )

    def verify_cached(self, ctx: StageContext, artifact_path: Path) -> bool:
        art = _load(artifact_path)
        if art is None or art.status == "not_translated":
            return True
        assert ctx.episode is not None
        return ctx.episode.source.is_file() and fingerprint(ctx.episode.source) == art.mkv_fingerprint_after


def _load(path: Path | None) -> RemuxArtifact | None:
    if path is None or not path.is_file():
        return None
    return RemuxArtifact.model_validate_json(path.read_text(encoding="utf-8"))
```

- [ ] **Step 5: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_stages_remux.py
```

Expected: PASS — `7 passed`

- [ ] **Step 6: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `224 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 7: Commit**

```bash
git add -A src/translaterany/media/remux.py src/translaterany/stages/remux.py tests/test_stages_remux.py
git commit -F - <<'EOF'
feat(remux): reinserção da legenda PT-BR com verificação e idempotência

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 10: CLI e pipeline padrão do M1

`run` passa a aceitar uma biblioteca (série a série, com avisos, ignorados, erro de `series.toml` por série e `--force`), `status` mostra a faixa escolhida, "pasta nunca processada" e "(arquivo ausente)", e o pipeline padrão vira o do M1 (com remux desligado).

**Files:**
- Modify (substituir): `src/translaterany/stages/__init__.py`
- Modify (substituir): `src/translaterany/pipeline/status.py`
- Modify (substituir): `src/translaterany/cli/run.py`
- Modify (substituir): `src/translaterany/cli/status.py`
- Test (substituir): `tests/test_cli.py`
- Test (substituir): `tests/test_inventory.py`

**Interfaces:**
- Consumes: todas as tarefas anteriores.
- Produces:
  - `DEFAULT_PIPELINE = ('inventory', 'select_track', 'extract', 'normalize', 'classify', 'write', 'publish', 'remux')`
  - `UnitStatus.missing: bool`
  - `translaterany run <série|biblioteca> [--force]`

- [ ] **Step 1: Escrever os testes (devem falhar): `tests/test_cli.py`** — **substitui o arquivo inteiro**

```python
from pathlib import Path

from mkvtools import FULL_ASS, SIGNS_ASS, Sub, make_mkv, needs_mkvtoolnix
from typer.testing import CliRunner

from translaterany.cli import app

runner = CliRunner()


def _config(tmp_path: Path, data_dir: Path, stages: str = '"t_source", "t_upper"') -> Path:
    path = tmp_path / "config.toml"
    text = f'[general]\ndata_dir = "{data_dir}"\n[discovery]\nmin_file_age = 0\n[pipeline]\nstages = [{stages}]\n'
    path.write_text(text, encoding="utf-8")
    return path


def _invoke(*args: str):
    return runner.invoke(app, list(args), env={"XDG_CONFIG_HOME": "/nao/existe", "TRANSLATERANY_CONFIG": ""})


def test_run_then_cached_then_status(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    first = _invoke("--config", cfg, "run", str(series_dir))
    assert first.exit_code == 0, first.output
    assert "3 episódio(s)" in first.output
    second = _invoke("--config", cfg, "run", str(series_dir))
    assert second.exit_code == 0
    status = _invoke("--config", cfg, "status", str(series_dir))
    assert status.exit_code == 0
    assert "t_upper" in status.output
    all_status = _invoke("--config", cfg, "status")
    assert "Minha Série (2020)" in all_status.output
    assert list((data_dir / "logs").glob("run-*.log"))


def test_run_with_failure_exit_1(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01.mkv").write_text("FAIL", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    assert result.exit_code == 1


def test_run_interrupted_exit_130(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E02.mkv").write_text("INTERRUPT", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    assert result.exit_code == 130
    assert "retomar" in result.output


def test_run_invalid_config_exit_2(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir, '"nope"')), "run", str(series_dir))
    assert result.exit_code == 2
    assert "etapa desconhecida" in result.output


def test_run_not_a_directory_exit_2(tmp_path: Path, data_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(tmp_path / "nao-existe"))
    assert result.exit_code == 2


def test_retry_forces_rerun(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    result = _invoke("--config", cfg, "retry", str(series_dir), "--from", "t_upper")
    assert result.exit_code == 0, result.output
    assert "4 unidade(s)" in result.output  # 3 episódios + a série
    bad = _invoke("--config", cfg, "retry", str(series_dir), "--from", "nope")
    assert bad.exit_code == 2


def test_doctor_ok_and_config_failure(tmp_path: Path, data_dir: Path) -> None:
    ok = _invoke("--config", str(_config(tmp_path, data_dir)), "doctor")
    assert ok.exit_code == 0, ok.output
    assert "configuração válida" in ok.output
    bad = _invoke("--config", str(_config(tmp_path, data_dir, '"nope"')), "doctor")
    assert bad.exit_code == 1


@needs_mkvtoolnix
def test_default_config_runs_m1_pipeline(tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Serie"
    make_mkv(root / "S01E01.mkv", [Sub(SIGNS_ASS, "S&S", default=True), Sub(FULL_ASS, "Dialog - ENG")])
    env = {"XDG_CONFIG_HOME": str(tmp_path / "sem-config"), "TRANSLATERANY_CONFIG": ""}
    result = runner.invoke(app, ["--data-dir", str(tmp_path / "d"), "run", str(root)], env=env)
    assert result.exit_code == 0, result.output
    for stage in ("inventory", "select_track", "extract", "normalize", "classify", "write", "publish"):
        assert stage in result.output
    assert "remux" not in result.output  # desligado por padrão
    status = runner.invoke(app, ["--data-dir", str(tmp_path / "d"), "status", str(root)], env=env)
    assert "Dialog - ENG" in status.output and "publish" in status.output
    assert not list(root.glob("*.pt-BR.ass"))


def test_run_empty_folder(tmp_path: Path, data_dir: Path) -> None:
    empty = tmp_path / "Vazia"
    empty.mkdir()
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(empty))
    assert result.exit_code == 0, result.output
    assert "Nenhuma série encontrada" in result.output


def test_corrupted_manifest_gives_clear_error(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    manifest = next((data_dir / "series").glob("*/episodes/*/manifest.json"))
    manifest.write_text("{corrompido", encoding="utf-8")
    for args in (
        ["run", str(series_dir)],
        ["status", str(series_dir)],
        ["retry", str(series_dir), "--from", "t_upper"],
    ):
        result = _invoke("--config", cfg, *args)
        assert result.exit_code == 1, (args, result.output)
        assert "manifest inválido" in result.output
        assert "Traceback" not in result.output


def test_run_unreadable_source_no_traceback(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    bad = series_dir / "Season 1" / "S01E02.mkv"
    bad.chmod(0)
    try:
        result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    finally:
        bad.chmod(0o644)
    assert result.exit_code == 1, result.output
    assert "Traceback" not in result.output
    assert "Resumo" in result.output


def test_non_utf8_manifest_gives_clear_error(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    manifest = next((data_dir / "series").glob("*/episodes/*/manifest.json"))
    manifest.write_bytes(
        manifest.read_text(encoding="utf-8")
        .replace('"skip_reason": null', '"skip_reason": "episódio"')
        .encode("latin-1")
    )
    for args in (
        ["run", str(series_dir)],
        ["status", str(series_dir)],
        ["retry", str(series_dir), "--from", "t_upper"],
    ):
        result = _invoke("--config", cfg, *args)
        assert result.exit_code == 1, (args, result.output)
        assert "manifest inválido" in result.output
        assert "Traceback" not in result.output


def test_status_with_corrupted_series_json(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    series_json = next((data_dir / "series").glob("*/series.json"))
    series_json.write_text("{", encoding="utf-8")
    result = _invoke("--config", cfg, "status")
    assert result.exit_code == 0, result.output
    assert series_json.parent.name[:12] in result.output
    assert "Traceback" not in result.output


def test_run_unwritable_data_dir_reports_doctor_failure(tmp_path: Path, series_dir: Path) -> None:
    locked = tmp_path / "ro"
    locked.mkdir()
    locked.chmod(0o555)
    try:
        result = _invoke("--config", str(_config(tmp_path, locked / "data")), "run", str(series_dir))
    finally:
        locked.chmod(0o755)
    assert result.exit_code == 2, result.output
    assert "data_dir" in result.output
    assert "Traceback" not in result.output


def test_status_never_processed(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "status", str(series_dir))
    assert result.exit_code == 0 and "Pasta nunca processada" in result.output


def test_status_marks_missing_file(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = str(_config(tmp_path, data_dir))
    _invoke("--config", cfg, "run", str(series_dir))
    (series_dir / "Season 1" / "S01E03.mkv").unlink()
    result = _invoke("--config", cfg, "status", str(series_dir))
    assert "arquivo ausente" in result.output


def test_run_library_with_broken_series_toml(tmp_path: Path, data_dir: Path) -> None:
    lib = tmp_path / "Anime"
    (lib / "Boa" / "Season 1").mkdir(parents=True)
    (lib / "Boa" / "Season 1" / "S01E01.mkv").write_text("episodio", encoding="utf-8")
    (lib / "Ruim" / "Season 1").mkdir(parents=True)
    (lib / "Ruim" / "Season 1" / "S01E01.mkv").write_text("episodio", encoding="utf-8")
    (lib / "Ruim" / "series.toml").write_text("[subtitles\n", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(lib))
    assert result.exit_code == 1, result.output
    assert "Série: Boa" in result.output and "Resumo — Boa" in result.output
    assert "series.toml" in result.output and "Resumo — Ruim" not in result.output


def test_run_lists_ignored_files(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    (series_dir / "Season 1" / "S01E01 - outra versão.mkv").write_text("dup", encoding="utf-8")
    result = _invoke("--config", str(_config(tmp_path, data_dir)), "run", str(series_dir))
    assert result.exit_code == 0, result.output
    assert "ignorado nesta execução" in result.output and "duplicado" in result.output
    assert "2 episódio(s)" in result.output
```

- [ ] **Step 2: Escrever os testes (devem falhar): `tests/test_inventory.py`** — **substitui o arquivo inteiro**

```python
import json
from pathlib import Path

from translaterany.library import discover
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.runner import Runner
from translaterany.stages.inventory import InventoryStage


def test_inventory_records_size_and_fingerprint(data_dir: Path, series_dir: Path) -> None:
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    Runner([InventoryStage()], store, FakeLLM()).run(series, episodes)
    art = json.loads((store.artifact_dir(series.key, episodes[0].key) / "inventory.json").read_text())
    assert art["size"] == len("episodio 1")
    assert art["fingerprint"].startswith("sha256:")
    assert art["source"] == str(episodes[0].source)


def test_inventory_reruns_only_when_file_changes(data_dir: Path, series_dir: Path) -> None:
    store = ArtifactStore(data_dir)
    series, episodes = discover(series_dir)
    Runner([InventoryStage()], store, FakeLLM()).run(series, episodes)
    (series_dir / "Season 1" / "S01E01.mkv").write_bytes(b"x" * 3_000_000)
    summary = Runner([InventoryStage()], store, FakeLLM()).run(series, episodes)
    assert summary.stages["inventory"].done == 1 and summary.stages["inventory"].cached == 2


def test_builtin_stages_registered_and_default_pipeline() -> None:
    from translaterany.stages import DEFAULT_PIPELINE

    assert "inventory" in REGISTRY
    assert DEFAULT_PIPELINE == (
        "inventory",
        "select_track",
        "extract",
        "normalize",
        "classify",
        "write",
        "publish",
        "remux",
    )
    assert REGISTRY.get("remux").enabled_by_default is False
```

- [ ] **Step 3: Rodar os testes e confirmar que falham**

```bash
uv run pytest -q tests/test_cli.py tests/test_inventory.py
```

Expected: FAIL — `7 failed, 14 passed`

- [ ] **Step 4: Implementar `src/translaterany/stages/__init__.py`** — **substitui o arquivo inteiro**

```python
"""Etapas embutidas. Importar este pacote registra todas elas no REGISTRY."""

from translaterany.stages import (  # noqa: F401
    classify,
    extract,
    inventory,
    normalize,
    publish,
    remux,
    select_track,
    write,
)

# Pipeline usado quando não há [pipeline] no config (remux vem desabilitado: enabled_by_default = False).
DEFAULT_PIPELINE: tuple[str, ...] = (
    "inventory",
    "select_track",
    "extract",
    "normalize",
    "classify",
    "write",
    "publish",
    "remux",
)
```

- [ ] **Step 5: Implementar `src/translaterany/pipeline/status.py`** — **substitui o arquivo inteiro**

```python
"""Leitura do estado das unidades a partir dos manifests (comando status)."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from translaterany.pipeline.artifacts import ArtifactStore


@dataclass(frozen=True)
class UnitStatus:
    unit: str  # chave do episódio, ou "(série)"
    status: str  # ok | skipped | failed
    last_done: str | None  # última etapa concluída, na ordem do pipeline
    detail: str | None  # motivo do pulo ou erro da falha
    missing: bool = False  # o arquivo de origem do episódio não existe mais


def series_status(store: ArtifactStore, series_key: str, stage_order: Sequence[str]) -> list[UnitStatus]:
    rows: list[UnitStatus] = []
    units: list[tuple[str, str | None]] = [("(série)", None)]
    units += [(key, key) for key in store.episode_keys(series_key)]
    for label, episode_key in units:
        manifest = store.read_manifest(series_key, episode_key)
        if manifest is None:
            continue
        done = [name for name in stage_order if (r := manifest.stages.get(name)) and r.status == "done"]
        failed = [r for r in manifest.stages.values() if r.status == "failed"]
        detail = manifest.skip_reason
        if manifest.status == "failed" and failed:
            detail = failed[-1].error
        missing = episode_key is not None and bool(manifest.unit.source) and not Path(manifest.unit.source).exists()
        rows.append(UnitStatus(label, manifest.status, done[-1] if done else None, detail, missing))
    return rows
```

- [ ] **Step 6: Implementar `src/translaterany/cli/run.py`** — **substitui o arquivo inteiro**

```python
"""Comando run."""

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.progress import BarColumn, MofNCompleteColumn, Progress, TaskID, TextColumn
from rich.table import Table

from translaterany.cli.app import (
    EXIT_FAILURE,
    EXIT_INTERRUPTED,
    EXIT_OK,
    EXIT_USAGE,
    AppState,
    all_checks,
    app,
    console,
    load_or_exit,
    print_checks,
)
from translaterany.config import ResolvedConfig
from translaterany.library import SeriesScan, scan_library
from translaterany.llm import FakeLLM
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.lock import SeriesLocked
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.runner import Runner, RunSummary
from translaterany.util.doctor import has_failure, run_checks
from translaterany.util.log import LOGGER_NAME, setup_logging


@app.command()
def run(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série ou da biblioteca.")],
    force: Annotated[bool, typer.Option("--force", help="Reabre pulados e sobrescreve PT-BR de terceiros.")] = False,
) -> None:
    """Executa o pipeline numa série ou em todas as séries de uma biblioteca."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    results = run_checks(all_checks(cfg))
    if has_failure(results):
        console.print("[red]Verificação de ambiente falhou:[/red]")
        print_checks(results)
        raise typer.Exit(EXIT_USAGE)
    setup_logging("DEBUG" if state.verbose else cfg.log_level, cfg.data_dir / "logs")

    try:
        scans = scan_library(path, min_file_age=cfg.min_file_age)
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc
    if not scans:
        console.print(f"Nenhuma série encontrada em {path}.")
        raise typer.Exit(EXIT_OK)

    failed = False
    for scan in scans:
        failed |= not _run_series(scan, cfg, force)
    raise typer.Exit(EXIT_FAILURE if failed else EXIT_OK)


def _run_series(scan: SeriesScan, cfg: ResolvedConfig, force: bool) -> bool:
    """Processa uma série; devolve False se algo falhou."""
    series = scan.series
    console.print(f"Série: [bold]{series.name}[/bold] — {len(scan.episodes)} episódio(s)")
    for warning in scan.warnings:
        console.print(f"  [yellow]aviso:[/yellow] {warning}")
    for ignored in scan.ignored:
        console.print(f"  [dim]ignorado nesta execução: {ignored.path.name} — {ignored.reason}[/dim]")
    if scan.error:
        console.print(f"  [red]{scan.error}[/red]")
        return False

    log = logging.getLogger(LOGGER_NAME)
    with Progress(TextColumn("{task.description}"), BarColumn(), MofNCompleteColumn(), console=console) as progress:
        tasks: dict[str, TaskID] = {}

        def on_progress(stage: str, done: int, total: int) -> None:
            if stage not in tasks:
                tasks[stage] = progress.add_task(stage, total=total)
            progress.update(tasks[stage], completed=done)

        runner = Runner(cfg.stages, ArtifactStore(cfg.data_dir), FakeLLM(), log, on_progress)
        try:
            summary = runner.run(series, scan.episodes, force=force)
        except SeriesLocked:
            console.print(f"  [yellow]A série '{series.name}' já está sendo processada por outra execução.[/yellow]")
            return False
        except ManifestError as exc:
            console.print(f"  [red]{exc}[/red]")
            return False
        except OSError as exc:
            log.debug("erro de E/S", exc_info=exc)
            console.print(f"  [red]Erro de leitura/gravação: {exc}[/red]")
            return False
        except KeyboardInterrupt as exc:
            console.print("[yellow]Interrompido. Rode o mesmo comando para retomar.[/yellow]")
            raise typer.Exit(EXIT_INTERRUPTED) from exc

    _print_summary(series.name, summary)
    return not summary.failed


def _print_summary(name: str, summary: RunSummary) -> None:
    table = Table(title=f"Resumo — {name}")
    for column in ("Etapa", "Executadas", "Em cache", "Puladas", "Falhas"):
        table.add_column(column)
    for stage, c in summary.stages.items():
        table.add_row(stage, str(c.done), str(c.cached), str(c.skipped), str(c.failed))
    console.print(table)
```

- [ ] **Step 7: Implementar `src/translaterany/cli/status.py`** — **substitui o arquivo inteiro**

```python
"""Comando status."""

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.status import series_status

_COLORS = {"ok": "green", "skipped": "yellow", "failed": "red"}


def _track_name(store: ArtifactStore, series_key: str, episode_key: str | None) -> str:
    """Nome da faixa escolhida pelo select_track, se já existir."""
    if episode_key is None:
        return ""
    path = store.artifact_dir(series_key, episode_key) / "select_track.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["chosen"]["name"]
    except OSError, ValueError, KeyError:
        return ""


@app.command()
def status(
    ctx: typer.Context,
    path: Annotated[Path | None, typer.Argument(help="Pasta da série (padrão: todas).")] = None,
) -> None:
    """Mostra o estado dos episódios."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    store = ArtifactStore(cfg.data_dir)
    if path is not None:
        try:
            series, _ = discover(path)
        except NotADirectoryError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(EXIT_USAGE) from exc
        if not store.series_dir(series.key).exists():
            console.print(f"Pasta nunca processada: {series.name}")
            return
        targets = [(series.key, series.name)]
    else:
        targets = [(info["key"], info["name"]) for info in store.known_series()]
    if not targets:
        console.print("Nenhuma série processada ainda.")
        return

    order = [s.name for s in cfg.stages]
    for key, name in targets:
        table = Table(title=name)
        for column in ("Unidade", "Status", "Última etapa", "Faixa", "Detalhe"):
            table.add_column(column)
        try:
            rows = series_status(store, key, order)
        except ManifestError as exc:
            console.print(f"[red]{exc}[/red]")
            raise typer.Exit(EXIT_FAILURE) from exc
        for row in rows:
            color = _COLORS.get(row.status, "white")
            unit = row.unit + (" (arquivo ausente)" if row.missing else "")
            track = _track_name(store, key, None if row.unit == "(série)" else row.unit)
            table.add_row(unit, f"[{color}]{row.status}[/{color}]", row.last_done or "—", track, row.detail or "")
        console.print(table)
```

- [ ] **Step 8: Rodar os testes da tarefa**

```bash
uv run pytest -q tests/test_cli.py tests/test_inventory.py
```

Expected: PASS — `21 passed`

- [ ] **Step 9: Suíte completa e lint**

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: `228 passed`; `All checks passed!`; nenhum arquivo a reformatar.

- [ ] **Step 10: Commit**

```bash
git add -A src/translaterany/cli/run.py src/translaterany/cli/status.py src/translaterany/pipeline/status.py src/translaterany/stages/__init__.py tests/test_cli.py tests/test_inventory.py
git commit -F - <<'EOF'
feat(cli): run por biblioteca, --force e status com faixa e arquivos ausentes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```

---

### Task 11: Aceite com os casos reais e atualização do estado

Valida os critérios de pronto do spec (§18) em *Charlotte (2015)* e *High School D×D (2012)*, com um diretório de dados descartável. **Nada** pode mudar em `temporada-teste/`, e os comandos abaixo só imprimem nomes de faixa, contagens e comparações — nunca o texto das legendas.

**Files:**
- Modify: `STATE.md`

**Interfaces:**
- Consumes: CLI completa (Tarefa 10).
- Produces: M1 marcado como ✅.

- [ ] **Step 1: Critério 1 — testes e lint**

```bash
uv run pytest -q && uv run ruff check src tests && uv run ruff format --check src tests
```

Expected: tudo passa, sem testes pulados (`skipped` não aparece no resumo).

- [ ] **Step 2: Retrato da temporada de teste e diretório descartável**

```bash
export TL_DATA="$(mktemp -d)"
find temporada-teste -printf '%P %s %T@\n' | sort > "$TL_DATA/antes.txt"
```

- [ ] **Step 3: Critério 2 — execução completa**

```bash
uv run translaterany --data-dir "$TL_DATA/dados" run temporada-teste; echo "exit=$?"
```

Expected: `Série: Charlotte (2015) — 14 episódio(s)`, `Série: High School D×D (2012) — 65 episódio(s)`, nenhuma falha nos resumos (colunas "Puladas" e "Falhas" em 0; `remux` não aparece) e `exit=0`.

- [ ] **Step 4: Critérios 2, 3 e 4 — faixas, identidade e classificação**

```bash
python3 - "$TL_DATA/dados" <<'EOF'
import json, sys
from collections import Counter
from pathlib import Path
for sdir in sorted((Path(sys.argv[1]) / "series").iterdir()):
    name = json.loads((sdir / "series.json").read_text())["name"]
    chosen, same, total = Counter(), 0, 0
    for ep in sorted((sdir / "episodes").iterdir()):
        sel = json.loads((ep / "select_track.json").read_text())
        chosen[("especiais" if ep.name.startswith("S00") else "temporadas", sel["chosen"]["name"])] += 1
        total += 1
        same += (ep / "write.ass").read_bytes() == (ep / "extract.ass").read_bytes()
        if name.startswith("Charlotte") and ep.name == "S01E01":
            c = json.loads((ep / "classify.json").read_text())
            print("Charlotte S01E01:", c["main_style"], c["counts"])
    print(f"{name}: write==extract {same}/{total}")
    for (group, track), n in sorted(chosen.items()):
        print(f"  {group}: {track} x{n}")
EOF
```

Expected:
```
Charlotte S01E01: GJM_Main {'dialogue': 377, 'romaji': 59, 'sign': 60, 'song': 30}
Charlotte (2015): write==extract 14/14
  especiais: Dialog - ENG x1
  temporadas: Dialog - ENG x13
High School D×D (2012): write==extract 65/65
  especiais: Full Subtitle (CBM/IK) x6
  especiais: Full Subtitle (FFF) x9
  especiais: Full Subtitle (P/FFF) x1
  especiais: Full Subtitle (Tensai/IK) x1
  temporadas: Full Subtitle (FFF) x12
  temporadas: Full Subtitle (FFF/SCY) x24
  temporadas: Full Subtitle (Tensai/IK) x12
```

- [ ] **Step 5: Critério 6 — segunda execução em cache, e pasta de temporada**

```bash
uv run translaterany --data-dir "$TL_DATA/dados" run temporada-teste | grep -E "│ [a-z_]+ "
uv run translaterany --data-dir "$TL_DATA/dados" run "temporada-teste/Charlotte (2015)/Season 1" | grep -E "^Série|│ inventory"
```

Expected: todas as linhas de etapa com `0` executadas (14 ou 65 em cache); a pasta de temporada mostra `Série: Charlotte (2015) — 13 episódio(s)` com `inventory` 13 em cache.

- [ ] **Step 6: Critério 5 — `temporada-teste/` intacta**

```bash
find temporada-teste -printf '%P %s %T@\n' | sort | cmp - "$TL_DATA/antes.txt" && echo "intacta"
git status --short   # nada de temporada-teste/ pode aparecer
```

Expected: `intacta`; `git status` sem arquivos de `temporada-teste/`.

- [ ] **Step 7: Atualizar `STATE.md`**

Na tabela de progresso, troque a linha do M1 por:

```markdown
| M1 — Mídia e legendas | ✅ | [spec](docs/superpowers/specs/2026-09-24-m1-midia-legendas-design.md) | [plano](docs/superpowers/plans/2026-09-24-m1-midia-legendas.md) | concluído |
```

Em "Onde estamos", marque o marco atual como **M2 — Camada de IA e tradução básica** (não iniciado) e a próxima ação como "escrever o spec do M2". Registre no "Registro de decisões" os desvios deste plano que ainda não estiverem lá e o que surgir na execução.

- [ ] **Step 8: Limpar e commitar**

```bash
rm -rf "$TL_DATA"
git add STATE.md
git commit -F - <<'EOF'
docs: conclui o M1 — Mídia e legendas

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01KbjEK4hjffGhWESfY9tcLd
EOF
```
