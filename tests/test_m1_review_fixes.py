"""Correções da revisão final do M1 (cada teste reproduz um achado)."""

import json
import os
import stat
from pathlib import Path

import pytest
from mkvtools import FULL_ASS, SIGNS_ASS, Sub, make_mkv, needs_mkvtoolnix
from pipeline_helpers import artifact, run_stages
from typer.testing import CliRunner

from translaterany.cli import app
from translaterany.media.mkv import parse_identify, probe
from translaterany.media.tracks import select_track
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.stages.classify import ClassifyStage
from translaterany.stages.extract import ExtractStage
from translaterany.stages.normalize import NormalizeStage
from translaterany.stages.publish import PublishStage
from translaterany.stages.remux import RemuxOptions, RemuxStage
from translaterany.stages.select_track import SelectTrackStage
from translaterany.stages.write import WriteOptions, WriteStage
from translaterany.subtitles.ass import parse_ass, render_ass
from translaterany.subtitles.texts import UnitTexts
from translaterany.util.fs import fingerprint


def _stages(translate: str | None = "t_translate", remux: bool = False, keep_backup: bool = False) -> list[Stage]:
    from fake_stages import TranslateStage

    stages: list[Stage] = [SelectTrackStage(), ExtractStage(), NormalizeStage(), ClassifyStage()]
    if translate == "t_translate":
        stages.append(TranslateStage())
    elif translate == "t_empty":
        stages.append(EmptyTranslateStage())
    stages.append(WriteStage(WriteOptions(text_source=translate or "normalize")))
    stages.append(PublishStage())
    if remux:
        stages.append(RemuxStage(RemuxOptions(keep_backup=keep_backup)))
    return stages


class EmptyTranslateStage(Stage):
    """Tradução que não produziu nada (ex.: todas as chamadas falharam)."""

    name = "t_empty"
    version = "1"
    scope = StageScope.EPISODE
    inputs = ("normalize",)
    translates = True

    def run(self, ctx: StageContext) -> None:
        ctx.output.json(UnitTexts())


@pytest.fixture(autouse=True)
def _register_empty() -> None:
    from translaterany.pipeline.registry import REGISTRY

    if "t_empty" not in REGISTRY:
        REGISTRY.register(EmptyTranslateStage)


# 2 — separadores Unicode dentro do texto não quebram linha
def test_unicode_separators_stay_inside_event_text() -> None:
    head = (
        "[Script Info]\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    data = (head + "Dialogue: 0,0:00:01.00,0:00:02.00,Default,,0,0,0,,Hello wor\x0cld\x1cok\n").encode()
    doc = parse_ass(data)
    assert doc.events[0].text == "Hello wor\x0cld\x1cok"
    assert render_ass(doc, {}) == data
    out = render_ass(doc, {0: "OLÁ MUNDO"}).decode()
    assert out.endswith(",,OLÁ MUNDO\n")


def test_lone_cr_line_endings_still_split() -> None:
    data = b"[Events]\rFormat: Start, End, Text\rDialogue: 0:00:01.00,0:00:02.00,Oi\r"
    doc = parse_ass(data)
    assert doc.events[0].text == "Oi"
    assert render_ass(doc, {}) == data


# 7 — escolha manual prefere a faixa completa entre as que casam
def test_manual_choice_prefers_full_over_signs() -> None:
    def track(tid: int, name: str) -> dict:
        props = {"codec_id": "S_TEXT/ASS", "language_ietf": "en", "track_name": name}
        return {"id": tid, "type": "subtitles", "properties": props}

    info = parse_identify({"tracks": [track(2, "ADZ Signs & Songs"), track(3, "ADZ Full")]})
    assert select_track(info, "ADZ").chosen.id == 3


# promovido — sem texto novo, nada de marca de tradução
@needs_mkvtoolnix
def test_empty_translation_is_not_marked_or_published(data_dir: Path, synthetic_series: Path) -> None:
    summary, store, s, eps = run_stages(data_dir, synthetic_series, _stages(translate="t_empty"))
    assert not summary.failed
    written = artifact(store, s, eps[0], "write.ass").read_bytes()
    assert written == artifact(store, s, eps[0], "extract.ass").read_bytes()
    assert not list(synthetic_series.rglob("*.pt-BR.ass"))


# 8 — vídeo renomeado recebe a legenda no novo nome
@needs_mkvtoolnix
def test_renamed_video_gets_its_publication(data_dir: Path, synthetic_series: Path) -> None:
    run_stages(data_dir, synthetic_series, _stages())
    season = synthetic_series / "Season 1"
    (season / "S01E01 - A.mkv").rename(season / "S01E01 - Novo Nome.mkv")
    run_stages(data_dir, synthetic_series, _stages())
    assert (season / "S01E01 - Novo Nome.pt-BR.ass").exists()


# 4 — remux preserva permissões
@needs_mkvtoolnix
def test_remux_keeps_file_mode(data_dir: Path, synthetic_series: Path) -> None:
    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    mkv.chmod(0o664)
    run_stages(data_dir, synthetic_series, _stages(remux=True))
    assert stat.S_IMODE(mkv.stat().st_mode) == 0o664


# 5 — backup guarda sempre o original e nunca é sobrescrito
@needs_mkvtoolnix
def test_backup_keeps_the_pristine_original(data_dir: Path, synthetic_series: Path, monkeypatch) -> None:
    from fake_stages import TranslateStage

    mkv = synthetic_series / "Season 1" / "S01E01 - A.mkv"
    pristine = fingerprint(mkv)
    run_stages(data_dir, synthetic_series, _stages(remux=True, keep_backup=True))
    first_remux = fingerprint(mkv)
    original_run = TranslateStage.run

    def louder(self, ctx):  # tradução diferente: força um segundo remux de verdade
        original_run(self, ctx)
        path = ctx.output.path
        texts = UnitTexts.model_validate_json(path.read_text())
        path.write_text(UnitTexts(texts={k: v + "!" for k, v in texts.texts.items()}).model_dump_json())

    monkeypatch.setattr(TranslateStage, "run", louder)
    monkeypatch.setattr(TranslateStage, "version", "2")
    run_stages(data_dir, synthetic_series, _stages(remux=True, keep_backup=True))
    assert fingerprint(mkv) != first_remux  # houve um segundo remux
    assert fingerprint(mkv.with_name(mkv.name + ".bak")) == pristine


# 3 — --force é lembrado nas execuções seguintes
@needs_mkvtoolnix
def test_forced_episode_is_not_skipped_later(data_dir: Path, tmp_path: Path) -> None:
    root = tmp_path / "lib" / "Serie"
    make_mkv(root / "S01E01.mkv", [Sub(FULL_ASS, "Full"), Sub(SIGNS_ASS, "Português", lang="pt-BR")])
    summary, *_ = run_stages(data_dir, root, _stages(remux=True))
    assert summary.stages["select_track"].skipped == 1
    summary, *_ = run_stages(data_dir, root, _stages(remux=True), force=True)
    assert summary.stages["remux"].done == 1
    summary, store, s, eps = run_stages(data_dir, root, _stages(remux=True))
    assert summary.stages["select_track"].skipped == 0 and not summary.failed
    assert json.loads(artifact(store, s, eps[0], "remux.json").read_text())["status"] == "up_to_date"
    assert "Português" in {t.name for t in probe(root / "S01E01.mkv").subtitles}


# 6 — status e retry numa pasta de temporada usam a série-mãe
def test_status_and_retry_on_season_folder(tmp_path: Path, data_dir: Path, series_dir: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        f'[general]\ndata_dir = "{data_dir}"\n[discovery]\nmin_file_age = 0\n[pipeline]\nstages = ["t_source"]\n',
        encoding="utf-8",
    )
    runner = CliRunner()
    env = {"XDG_CONFIG_HOME": "/nao/existe", "TRANSLATERANY_CONFIG": ""}
    season = str(series_dir / "Season 1")
    assert runner.invoke(app, ["--config", str(cfg), "run", season], env=env).exit_code == 0
    status = runner.invoke(app, ["--config", str(cfg), "status", season], env=env)
    assert "nunca processada" not in status.output and "S01E01" in status.output
    retry = runner.invoke(app, ["--config", str(cfg), "retry", season, "--from", "t_source"], env=env)
    assert retry.exit_code == 0
    assert len(os.listdir(data_dir / "series")) == 1  # nenhuma série órfã "season-1-…"
