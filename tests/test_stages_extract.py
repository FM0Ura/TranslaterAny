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
