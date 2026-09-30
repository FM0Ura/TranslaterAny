import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

from translaterany.config.model import AppConfig, ProviderConfig
from translaterany.llm.client import LLMClient
from translaterany.memory.artifacts import ConsolidatedMemoryArtifact
from translaterany.memory.matching import select_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import StageMetrics, count
from translaterany.pipeline.units import Episode, Series
from translaterany.stages.translation_memory import TranslationMemoryArtifact
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import Classification, ClassifiedUnit, ClassifiedUnitCollection
from translaterany.subtitles.linebreak import char_budget, flatten_breaks
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.scene_analysis import SceneAnalysisDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import DialogueBatchTranslator
from translaterany.util.doctor import Check, ollama_check, ollama_models_check

if TYPE_CHECKING:
    from translaterany.config.loader import ResolvedConfig

logger = logging.getLogger(__name__)


class TranslateDialogueOptions(BaseModel):
    model: str = "translate"
    fallback_model: str | None = "translategemma"
    max_tokens_per_batch: int = 800
    max_lines_per_batch: int | None = 1  # uma fala por chamada: evita desalinhamento de IDs
    max_context_lines: int = 5
    honorifics: str = "keep"
    profanity: str = "faithful"


@register_stage
class StageTranslateDialogue(Stage):
    name: ClassVar[str] = "translate_dialogue"
    version: ClassVar[str] = "2"  # 2: frase sem \N para o modelo + orçamento de caracteres
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    produces_texts: ClassVar[bool] = True
    produces_dialogue: ClassVar[bool] = True
    inputs: ClassVar[tuple[str, ...]] = (
        "normalize",
        "classify",
        "consolidate_memory",
        "translation_memory",
        "merge_sentences",
        "scene_analysis",
    )
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = TranslateDialogueOptions

    def __init__(
        self,
        client: LLMClient | BaseModel | None = None,
        options: BaseModel | None = None,
        inputs: tuple[str, ...] | None = None,
    ) -> None:
        if isinstance(client, BaseModel) and options is None:
            options = client
            client = None
        if options is None:
            options = TranslateDialogueOptions()
        elif not isinstance(options, TranslateDialogueOptions):
            options = TranslateDialogueOptions.model_validate(options)
        super().__init__(options)
        self.options: TranslateDialogueOptions = options
        self.client = client
        if inputs is not None:
            self.inputs = inputs
        self.max_cps, self.max_cpl = 17.0, 42  # padrão Netflix; o loader aplica o [checks] via bind_pipeline

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        if app is not None:
            self.max_cps, self.max_cpl = app.checks.max_cps, app.checks.max_cpl

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        return {"max_cps": self.max_cps, "max_cpl": self.max_cpl}

    def translate_collection(self, collection: ClassifiedUnitCollection) -> ClassifiedUnitCollection:
        dialogue_units = [u for u in collection.units if u.line_type == "dialogue"]
        if not dialogue_units or not self.client:
            return collection

        lines = [DialogueLine(id=u.id, text=u.clean_text) for u in dialogue_units]
        translator = DialogueBatchTranslator(
            client=self.client,
            model_name=self.options.model,
            fallback_model=self.options.fallback_model,
            max_tokens_per_batch=self.options.max_tokens_per_batch,
            max_lines_per_batch=self.options.max_lines_per_batch,
            max_context_lines=self.options.max_context_lines,
            honorifics_policy=self.options.honorifics,
            profanity_policy=self.options.profanity,
        )
        translations = translator.translate_lines(lines)

        new_units: list[ClassifiedUnit] = []
        for u in collection.units:
            if u.id in translations:
                tr_text = translations[u.id]
                new_raw = f"{u.prefix}{tr_text}{u.suffix}"
                new_units.append(u.model_copy(update={"clean_text": tr_text, "raw_text": new_raw}))
            else:
                new_units.append(u)

        return ClassifiedUnitCollection(units=new_units)

    def run(self, ctx: StageContext) -> None:
        client = self.client or ctx.llm
        normalized = ctx.inputs.json("normalize", NormalizedDoc)
        classification = ctx.inputs.json("classify", Classification)

        dialogue_units = [
            u
            for u in normalized.units
            if classification.units.get(u.id) and classification.units[u.id].type == "dialogue"
        ]

        if not dialogue_units or not client:
            ctx.output.json(UnitTexts(texts={}, used_terms={}))
            return

        # Carrega artefatos opcionais do M4
        tm_resolved: dict[str, str] = {}
        try:
            tm_artifact = ctx.inputs.json("translation_memory", TranslationMemoryArtifact)
            tm_resolved = tm_artifact.matched_units
        except Exception:
            pass

        merged_doc: MergedUnitsDoc | None = None
        try:
            merged_doc = ctx.inputs.json("merge_sentences", MergedUnitsDoc)
        except Exception:
            pass

        scene_doc: SceneAnalysisDoc | None = None
        try:
            scene_doc = ctx.inputs.json("scene_analysis", SceneAnalysisDoc)
        except Exception:
            pass

        line_contexts = scene_doc.lines if scene_doc else {}

        # Políticas de tradução
        honorifics = self.options.honorifics
        profanity = self.options.profanity
        app_cfg = getattr(ctx, "config", None)
        if app_cfg and hasattr(app_cfg, "translation"):
            honorifics = app_cfg.translation.honorifics
            profanity = app_cfg.translation.profanity
        series = getattr(ctx, "series", None)
        if series and hasattr(series, "config") and series.config and hasattr(series.config, "translation"):
            honorifics = series.config.translation.honorifics
            profanity = series.config.translation.profanity

        # Carrega artefato consolidate_memory se disponível
        try:
            _ = ctx.inputs.json("consolidate_memory", ConsolidatedMemoryArtifact)
        except Exception:
            pass

        # Carrega glossário e personagens da memória da série
        store = getattr(ctx, "store", None)
        if store is None:
            store = getattr(getattr(ctx, "inputs", None), "_store", None)
        if store is None:
            from translaterany.config.loader import default_data_dir

            store = ArtifactStore(default_data_dir())

        matched_glossary: list[GlossaryEntry] = []
        matched_characters: list[CharacterEntry] = []
        used_terms_dict: dict[str, str] = {}

        if series is not None and store is not None:
            mem_dir = store.series_dir(series.key) / "memory"
            if mem_dir.exists():
                mem_store = MemoryStore(mem_dir)
                all_characters = mem_store.load_characters()
                glossary = mem_store.load_glossary()
                full_text = "\n".join(u.text for u in dialogue_units)
                matched_glossary, matched_characters = select_for_text(glossary.values(), all_characters, full_text)
                used_terms_dict = {entry.term: entry.content_hash() for entry in matched_glossary}

        # Monta linhas a traduzir (respeitando merge_sentences e TM)
        lines: list[DialogueLine] = []
        final_texts: dict[str, str] = {}
        units_to_verify: dict[str, str] = {}
        durations: dict[str, int] = {}
        event_counts: dict[str, int] = {}

        if merged_doc and merged_doc.units:
            for comp in merged_doc.units:
                if len(comp.unit_ids) == 1 and comp.composite_id in tm_resolved:
                    final_texts[comp.composite_id] = tm_resolved[comp.composite_id]
                else:
                    lines.append(DialogueLine(id=comp.composite_id, text=flatten_breaks(comp.text_with_markers)))
                    durations[comp.composite_id] = sum(comp.durations_ms)
                    event_counts[comp.composite_id] = len(comp.unit_ids)
                    units_to_verify[comp.composite_id] = comp.text_with_markers
        else:
            for u in dialogue_units:
                if u.id in tm_resolved:
                    final_texts[u.id] = tm_resolved[u.id]
                else:
                    lines.append(DialogueLine(id=u.id, text=flatten_breaks(u.text)))
                    units_to_verify[u.id] = u.text

        if lines:
            count(ctx, "lines", len(lines))
            events = {e.index: e for e in normalized.events}
            for u in dialogue_units:
                spans = [events[i].end_ms - events[i].start_ms for i in u.events if i in events]
                durations.setdefault(u.id, min(spans) if spans else 0)
            budgets = {
                line.id: b
                for line in lines
                if (
                    b := char_budget(
                        durations.get(line.id, 0),
                        max_cps=self.max_cps,
                        max_cpl=self.max_cpl,
                        events=event_counts.get(line.id, 1),
                    )
                )
            }
            translator = DialogueBatchTranslator(
                client=client,
                model_name=self.options.model,
                fallback_model=self.options.fallback_model,
                max_tokens_per_batch=self.options.max_tokens_per_batch,
                max_lines_per_batch=self.options.max_lines_per_batch,
                char_budgets=budgets,
                max_context_lines=self.options.max_context_lines,
                glossary=matched_glossary,
                characters=matched_characters,
                honorifics_policy=honorifics,
                profanity_policy=profanity,
                line_contexts=line_contexts,
                metrics=ctx.metrics if isinstance(getattr(ctx, "metrics", None), StageMetrics) else None,
            )
            translated_texts = translator.translate_lines(lines)

            for line_id, orig_text in units_to_verify.items():
                tr = translated_texts.get(line_id, orig_text)
                expected = marker_ids(orig_text)
                if expected:
                    if sorted(marker_ids(tr)) != sorted(expected):
                        logger.warning(
                            "Unidade %s: tradução perdeu marcadores %s (obtido %s). Fazendo fallback para texto original.",
                            line_id,
                            expected,
                            marker_ids(tr),
                        )
                        tr = orig_text
                        count(ctx, "markers_lost")
                final_texts[line_id] = tr

        ctx.output.json(UnitTexts(texts=final_texts, used_terms=used_terms_dict))

    def doctor_checks(self, cfg: ResolvedConfig | None = None) -> list[Check]:
        if cfg is None:
            return []

        prof = cfg.llm.profiles.get(cfg.llm.profile)
        req_models: list[str] = []
        uses_ollama = False
        if prof:
            for key in (prof.translate, prof.review):
                m_cfg = cfg.llm.models.get(key)
                if m_cfg and m_cfg.provider == "ollama":
                    uses_ollama = True
                    req_models.append(m_cfg.model)
        elif cfg.llm.profile in ("local", "hibrido"):
            uses_ollama = True

        if not uses_ollama:
            return []

        if not req_models:
            req_models = ["translategemma:12b", "gemma4:12b"]
        req_models = list(dict.fromkeys(req_models))

        ollama_provider = cfg.llm.providers.get("ollama", ProviderConfig())
        ollama_url = ollama_provider.base_url or "http://localhost:11434"

        return [
            ollama_check(ollama_url),
            ollama_models_check(ollama_url, req_models),
        ]
