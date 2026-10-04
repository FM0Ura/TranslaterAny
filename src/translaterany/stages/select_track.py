"""Etapa select_track: escolhe a faixa de legenda em inglês que serve de base."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from translaterany.languages.models import LanguageInfo
from translaterany.languages.registry import LanguageRegistry
from translaterany.media.mkv import MediaError, probe, tool_available
from translaterany.media.tracks import NoTrack, is_own, select_track
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
    foreign_accepted: bool = False  # PT-BR de terceiros aceito com --force (lembrado nas próximas execuções)


SUBTITLE_EXTENSIONS = (".ass", ".ssa", ".srt", ".vtt", ".sub")
PORTUGUESE_TAGS = (".pt-br", ".pt", ".por", ".pob")


def external_ptbr_path(episode: Episode) -> Path:
    """Destino da publicação: <vídeo>.pt-BR.ass."""
    return episode.source.with_name(episode.source.stem + ".pt-BR.ass")


def foreign_subtitle_files(episode: Episode, target_lang: LanguageInfo | None = None) -> list[Path]:
    """Legendas externas no idioma alvo ao lado do vídeo que não foram feitas pela app."""
    stem = episode.source.stem
    tags = (
        PORTUGUESE_TAGS
        if (target_lang is None or target_lang.code == "pt-BR")
        else (
            f".{target_lang.code.lower()}",
            f".{target_lang.iso639_1.lower()}",
            f".{target_lang.iso639_2.lower()}",
        )
    )
    found = []
    for candidate in episode.source.parent.iterdir():
        name = candidate.name
        if not candidate.is_file() or not name.startswith(stem + "."):
            continue
        rest = name[len(stem) :].lower()
        if not rest.endswith(SUBTITLE_EXTENSIONS):
            continue
        tag = rest[: -len(candidate.suffix)]
        if tag in tags and not has_marker(candidate.read_bytes()):
            found.append(candidate)
    return sorted(found)


def foreign_portuguese_files(episode: Episode) -> list[Path]:
    """Legendas externas em português ao lado do vídeo que não foram feitas pela app."""
    return foreign_subtitle_files(episode, None)


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
        accepted = ctx.force or _previously_accepted(ctx.previous_output)
        foreign = foreign_subtitle_files(ctx.episode, ctx.target_language)
        if foreign and not accepted:
            raise SkipEpisode(f"já existe {foreign[0].name} de outra fonte (use --force para sobrescrever)")
        info = probe(ctx.episode.source)
        foreign_tracks = any(
            LanguageRegistry.matches(t.language, ctx.target_language) and not is_own(t) for t in info.subtitles
        )
        try:
            sel = select_track(
                info,
                ctx.series.config.track,
                force=accepted,
                source_lang=ctx.source_language,
                target_lang=ctx.target_language,
            )
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
                foreign_accepted=accepted and bool(foreign or foreign_tracks),
            )
        )

    def doctor_checks(self, cfg: object = None) -> list[Check]:
        return [_tool_check("mkvmerge")]


def _previously_accepted(previous: Path | None) -> bool:
    if previous is None or not previous.is_file():
        return False
    try:
        return SelectTrackArtifact.model_validate_json(previous.read_text(encoding="utf-8")).foreign_accepted
    except ValueError:
        return False


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
