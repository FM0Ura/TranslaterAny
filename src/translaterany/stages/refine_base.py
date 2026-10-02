"""Base das etapas de refinamento do diálogo (M6): blocos por cena, resposta só com edições validadas."""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from translaterany.checks import CheckEnv, LineInput
from translaterany.checks.snapshots import LineSource, build_sources, composite_members, lines_for
from translaterany.config.model import AppConfig, ChecksConfig
from translaterany.llm.client import LLMRequest
from translaterany.memory.matching import load_memory_for_text
from translaterany.memory.models import CharacterEntry
from translaterany.pipeline.gates import StageGate
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.refine.blocks import ReviewLine, build_blocks, render_block_prompt
from translaterany.refine.edits import REJECT_REASONS, EditsResponse, LineEdit, apply_edits
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.linebreak import char_budget
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.scene_analysis import SceneAnalysisDoc
from translaterany.subtitles.scenes import scene_index_of
from translaterany.subtitles.texts import UnitTexts

logger = logging.getLogger(__name__)

_OPTIONAL = ("merge_sentences", "scene_analysis", "consolidate_memory", "translation_memory")
CONTEXT_WINDOW = 3  # falas de contexto por lado de cada alvo


class EditOutcomeDict(dict[str, str]):
    def __init__(
        self,
        texts: Mapping[str, str],
        applied: dict[str, str] | None = None,
        rejected: dict[str, int] | None = None,
    ) -> None:
        super().__init__(texts)
        self.applied = applied or {}
        self.rejected = rejected or dict.fromkeys(REJECT_REASONS, 0)

    @property
    def texts(self) -> dict[str, str]:
        return dict(self)


def apply_edits_with_gate(
    texts: Mapping[str, str],
    edits: Iterable[LineEdit],
    gate: StageGate | None = None,
    editable: set[str] | None = None,
    sources: Mapping[str, LineSource] | None = None,
    env: CheckEnv | None = None,
    forbidden: Mapping[str, str] | None = None,
    targets: set[str] | None = None,
) -> EditOutcomeDict:

    if gate is None:
        gate = StageGate()
    if targets is None:
        targets = editable if editable is not None else set(texts.keys())
    if sources is None:
        sources = {
            uid: LineSource(source=txt, duration_ms=2000, line_type="dialogue", style="") for uid, txt in texts.items()
        }
    if env is None:
        env = CheckEnv()

    outcome = apply_edits(texts, edits, targets, sources, env, forbidden=forbidden)
    if not gate.enabled:
        return EditOutcomeDict(outcome.texts, applied=outcome.applied, rejected=outcome.rejected)

    for item in list(outcome.applied.keys()):
        new_text = outcome.texts[item]
        src = sources[item]
        new_line = LineInput(
            id=item,
            source=src.source,
            target=new_text,
            line_type=src.line_type,
            style=src.style,
            duration_ms=src.duration_ms,
            composite=src.composite,
        )
        decision = gate.evaluate([new_line], env)
        orig_line = LineInput(
            id=item,
            source=src.source,
            target=texts[item],
            line_type=src.line_type,
            style=src.style,
            duration_ms=src.duration_ms,
            composite=src.composite,
        )
        orig_decision = gate.evaluate([orig_line], env)
        best_text, _ = gate.never_worsen(texts[item], orig_decision.findings, new_text, decision.findings)

        if decision.blocking or best_text != new_text or gate.is_oscillating(item, new_text):
            logger.info(
                "StageGate rejeitou edição de %s: introduz achados bloqueantes (%s). Mantendo original.",
                item,
                decision.blocking,
            )
            outcome.texts[item] = texts[item]
            outcome.applied.pop(item, None)
            outcome.rejected["worse"] += 1

    return EditOutcomeDict(outcome.texts, applied=outcome.applied, rejected=outcome.rejected)


class RefineOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = "review"
    max_lines_per_block: int = 30


@dataclass
class RefineData:
    """O que as subclasses usam para escolher alvos."""

    sources: dict[str, LineSource]
    lines: list[LineInput]
    env: CheckEnv
    speaker_of: dict[str, str]
    characters: list[CharacterEntry] = field(default_factory=list)
    listener_of: dict[str, str] = field(default_factory=dict)
    confidence_of: dict[str, str] = field(default_factory=dict)


class DialogueRefineStage(Stage):
    scope: ClassVar[StageScope] = StageScope.EPISODE
    produces_texts: ClassVar[bool] = True
    produces_dialogue: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = RefineOptions
    default_dialogue_input: ClassVar[str] = "translate_dialogue"

    def __init__(self, options: BaseModel | None = None) -> None:
        super().__init__(options)
        self.dialogue_input = self.default_dialogue_input
        self.max_cps, self.max_cpl = 17.0, 42
        self.limits = ChecksConfig()
        self.gate = StageGate()
        self.inputs = ("normalize", "classify", *_OPTIONAL, *self._extra_inputs(), self.dialogue_input)

    # --- a sobrescrever -------------------------------------------------------------------------
    def instructions(self) -> str:
        raise NotImplementedError

    def select_targets(self, ids: Sequence[str], data: RefineData) -> dict[str, list[str]]:
        raise NotImplementedError

    def forbidden_texts(self, ctx: StageContext, texts: Mapping[str, str]) -> dict[str, str] | None:
        return None

    def _extra_inputs(self) -> tuple[str, ...]:
        return ()

    # --- pipeline ------------------------------------------------------------------------------
    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        names = [s.name for s in previous]
        dialogue = [s.name for s in previous if s.produces_dialogue]
        if dialogue:
            self.dialogue_input = dialogue[-1]
        if app is not None:
            self.limits = app.checks
            self.max_cps, self.max_cpl = app.checks.max_cps, app.checks.max_cpl
            if hasattr(app, "gates"):
                self.gate = StageGate(config=app.gates)
        self._bind_extra(previous)
        optional = tuple(n for n in _OPTIONAL if n in names)
        self.inputs = ("normalize", "classify", *optional, *self._extra_inputs(), self.dialogue_input)

    def _bind_extra(self, previous: Sequence[Stage]) -> None:
        return None

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        return {"input": self.dialogue_input, "limits": self.limits.model_dump(mode="json")}

    def render_prompt(self, review: Sequence[ReviewLine]) -> str:
        return render_block_prompt(review)

    # --- execução ------------------------------------------------------------------------------
    def run(self, ctx: StageContext) -> None:
        self.gate.reset()
        dialogue = ctx.inputs.json(self.dialogue_input, UnitTexts)
        texts = dict(dialogue.texts)
        if not texts:
            ctx.output.json(UnitTexts(texts={}, used_terms=dialogue.used_terms))
            return
        doc = ctx.inputs.json("normalize", NormalizedDoc)
        classes = ctx.inputs.json("classify", Classification)
        merged = ctx.inputs.json("merge_sentences", MergedUnitsDoc) if "merge_sentences" in self.inputs else None
        scene_doc = ctx.inputs.json("scene_analysis", SceneAnalysisDoc) if "scene_analysis" in self.inputs else None
        sources = build_sources(doc, classes, merged)
        ids = [i for i in texts if i in sources]
        glossary, characters = load_memory_for_text(
            getattr(ctx, "store", None), ctx.series.key, "\n".join(sources[i].source for i in ids)
        )
        env = CheckEnv(glossary=glossary, names=[[c.name, *c.aliases] for c in characters], limits=self.limits)
        contexts = scene_doc.lines if scene_doc else {}
        speaker_of = {i: contexts[i].speaker for i in ids if i in contexts}
        listener_of = {i: contexts[i].listener for i in ids if i in contexts}
        confidence_of = {i: contexts[i].confidence for i in ids if i in contexts}
        lines, _ = lines_for({i: texts[i] for i in ids}, sources)
        data = RefineData(
            sources=sources,
            lines=lines,
            env=env,
            speaker_of=speaker_of,
            characters=characters,
            listener_of=listener_of,
            confidence_of=confidence_of,
        )
        targets = self.select_targets(ids, data)
        if "translation_memory" in self.inputs:  # falas resolvidas pela memória de tradução não são revisadas
            tm = ctx.inputs.json("translation_memory", TranslationMemoryArtifact)
            targets = {i: s for i, s in targets.items() if i not in tm.matched_units}
        count(ctx, "lines_read", len(ids))
        count(ctx, "lines_targeted", len(targets))
        members = composite_members(merged)
        scene_of = scene_index_of(ids, members, {u.id: u.events for u in doc.units}, classes.scenes)
        forbidden = self.forbidden_texts(ctx, texts)
        for block in build_blocks(
            ids, set(targets), scene_of, self.options.max_lines_per_block, context_window=CONTEXT_WINDOW
        ):
            count(ctx, "blocks")
            review = [
                ReviewLine(
                    id=i,
                    source=sources[i].source,
                    target=texts[i],
                    speaker=contexts[i].speaker if i in contexts else "Unknown",
                    tone=contexts[i].tone if i in contexts else "neutral",
                    budget=char_budget(
                        sources[i].duration_ms,
                        max_cps=self.max_cps,
                        max_cpl=self.max_cpl,
                        events=len(members.get(i, [i])),
                    ),
                    signals=targets.get(i, []),
                    editable=i in targets,
                )
                for i in block
            ]
            try:
                response = ctx.llm.generate(
                    LLMRequest(
                        model=self.options.model,
                        instructions=self.instructions(),
                        prompt=self.render_prompt(review),
                        output_type=EditsResponse,
                        tag=self.name,
                    )
                ).output
            except Exception as exc:  # bloco com falha passa sem mudanças
                logger.warning("%s: bloco a partir de %s falhou (%s); mantendo o texto.", self.name, block[0], exc)
                count(ctx, "blocks_failed")
                continue
            count(ctx, "edits_proposed", len(response.edits))
            editable = {i for i in block if i in targets}
            gate = getattr(self, "gate", None) or StageGate()
            outcome = apply_edits_with_gate(
                texts,
                response.edits,
                gate=gate,
                editable=editable,
                sources=sources,
                env=env,
                forbidden=forbidden,
            )
            texts = outcome.texts
            count(ctx, "edits_applied", len(outcome.applied))

            for reason in REJECT_REASONS:
                if outcome.rejected[reason]:
                    count(ctx, f"rejected_{reason}", outcome.rejected[reason])
            if forbidden is not None and outcome.rejected["reversal"]:
                count(ctx, "reversals", outcome.rejected["reversal"])
        ctx.output.json(UnitTexts(texts=texts, used_terms=dialogue.used_terms))
