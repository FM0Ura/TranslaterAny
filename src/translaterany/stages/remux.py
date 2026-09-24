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
