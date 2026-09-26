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
        assert ctx.episode is not None
        dest = Path(art.path)
        if dest != external_ptbr_path(ctx.episode):  # vídeo renomeado ou movido
            return False
        return dest.is_file() and file_sha256(dest) == art.sha256
