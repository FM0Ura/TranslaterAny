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
