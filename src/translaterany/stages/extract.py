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
        from translaterany.languages.registry import LanguageRegistry

        source_lang = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
        if (
            track.language.lower() == "und"
            and source_lang.iso639_1 == "en"
            and not looks_english(parse_ass(data))
        ):
            raise SkipEpisode("faixa 'und' não parece inglês")
        ctx.output.file(".ass", data)

    def doctor_checks(self, cfg: object = None) -> list[Check]:
        return [_tool_check("mkvextract")]
