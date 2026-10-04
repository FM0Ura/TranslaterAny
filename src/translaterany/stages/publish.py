"""Etapa publish: copia o .ass traduzido para <vídeo>.pt-BR.ass ao lado do MKV."""

import os
from pathlib import Path

from pydantic import BaseModel

from translaterany.languages.models import LanguageInfo
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode
from translaterany.subtitles.ass import has_marker
from translaterany.util.fs import file_sha256


class PublishArtifact(BaseModel):
    published: bool
    reason: str
    path: str | None = None
    sha256: str | None = None


def get_output_ass_path(video_path: Path, target_lang: LanguageInfo | None = None) -> Path:
    """Destino da publicação: <vídeo>.<idioma>.ass."""
    code = target_lang.code if target_lang is not None else "pt-BR"
    return video_path.with_name(f"{video_path.stem}.{code}.ass")


def external_ptbr_path(episode: Episode) -> Path:
    """Destino da publicação para PT-BR (retrocompatibilidade): <vídeo>.pt-BR.ass."""
    return get_output_ass_path(episode.source, None)


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
        dest = get_output_ass_path(ctx.episode.source, getattr(ctx, "target_language", None))
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
        assert ctx.episode is not None
        dest = Path(art.path)
        expected = get_output_ass_path(ctx.episode.source, getattr(ctx, "target_language", None))
        if dest != expected:  # vídeo renomeado ou movido
            return False
        return dest.is_file() and file_sha256(dest) == art.sha256
