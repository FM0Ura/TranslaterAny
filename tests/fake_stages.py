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
