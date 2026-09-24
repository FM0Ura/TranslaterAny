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
