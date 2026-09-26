import logging
import re
from typing import TYPE_CHECKING, ClassVar

from pydantic import BaseModel

from translaterany.config.model import ProviderConfig
from translaterany.llm.client import LLMClient
from translaterany.memory.artifacts import ConsolidatedMemoryArtifact
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.classify import Classification, ClassifiedUnit, ClassifiedUnitCollection
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import DialogueBatchTranslator
from translaterany.util.doctor import Check, ollama_check, ollama_models_check

if TYPE_CHECKING:
    from translaterany.config.loader import ResolvedConfig

logger = logging.getLogger(__name__)


def _matches_term(term: str, text: str) -> bool:
    if not term:
        return False
    prefix = r"\b" if re.match(r"^\w", term) else ""
    suffix = r"\b" if re.search(r"\w$", term) else ""
    pattern = rf"{prefix}{re.escape(term)}{suffix}"
    return bool(re.search(pattern, text, re.IGNORECASE))


class TranslateDialogueOptions(BaseModel):
    model: str = "translate"
    fallback_model: str | None = "translategemma"
    max_tokens_per_batch: int = 800
    max_context_lines: int = 5


@register_stage
class StageTranslateDialogue(Stage):
    name: ClassVar[str] = "translate_dialogue"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    inputs: ClassVar[tuple[str, ...]] = ("normalize", "classify", "consolidate_memory")
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
            max_context_lines=self.options.max_context_lines,
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

        series = getattr(ctx, "series", None)
        if series is not None and store is not None:
            mem_dir = store.series_dir(series.key) / "memory"
            if mem_dir.exists():
                mem_store = MemoryStore(mem_dir)
                all_characters = mem_store.load_characters()
                glossary = mem_store.load_glossary()
                full_text = "\n".join(u.text for u in dialogue_units)
                for entry in glossary.values():
                    terms_to_check = [entry.term, *entry.aliases]
                    if any(_matches_term(t, full_text) for t in terms_to_check):
                        matched_glossary.append(entry)
                        used_terms_dict[entry.term] = entry.content_hash()

                for char in all_characters:
                    names_to_check = [char.name, *char.aliases]
                    if any(_matches_term(n, full_text) for n in names_to_check):
                        matched_characters.append(char)

        lines = [DialogueLine(id=u.id, text=u.text) for u in dialogue_units]
        translator = DialogueBatchTranslator(
            client=client,
            model_name=self.options.model,
            fallback_model=self.options.fallback_model,
            max_tokens_per_batch=self.options.max_tokens_per_batch,
            max_context_lines=self.options.max_context_lines,
            glossary=matched_glossary,
            characters=matched_characters,
        )
        translated_texts = translator.translate_lines(lines)

        final_texts: dict[str, str] = {}
        for u in dialogue_units:
            tr = translated_texts.get(u.id, u.text)
            if u.markers > 0:
                expected = list(range(1, u.markers + 1))
                if sorted(marker_ids(tr)) != expected:
                    logger.warning(
                        "Unidade %s: tradução perdeu marcadores %s (obtido %s). Fazendo fallback para texto original.",
                        u.id,
                        expected,
                        marker_ids(tr),
                    )
                    tr = u.text
            final_texts[u.id] = tr

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
