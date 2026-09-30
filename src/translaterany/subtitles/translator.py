import logging
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from translaterany.llm.client import (
    LLMClient,
    LLMOutputError,
    LLMRefusalError,
    LLMRequest,
    LLMTransientError,
    Usage,
)
from translaterany.memory.models import CharacterEntry, GlossaryEntry
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.subtitles.chunking import (
    ContextLine,
    DialogueLine,
    create_dialogue_batches,
    format_batch_prompt,
)

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTIONS = """Você é um tradutor especialista de legendas de animes (Inglês para Português do Brasil).
Sua missão é produzir diálogos naturais, coloquiais e fluidos no estilo de fansubs brasileiros de alta qualidade.
Mantenha rigorosamente o significado pretendido, pontuação expressiva (... ! ?) e estilo de cada personagem.
Você DEVE devolver exclusivamente a estrutura solicitada, contendo a tradução de todas as falas
identificadas por seus IDs.
NÃO traduza as falas marcadas como contexto."""


class TranslationItem(BaseModel):
    id: str
    text: str


class TranslationBatch(BaseModel):
    items: list[TranslationItem] = Field(default_factory=list)


class DialogueBatchTranslator:
    def __init__(
        self,
        client: LLMClient,
        model_name: str = "translate",
        fallback_model: str | None = "translategemma",
        max_tokens_per_batch: int = 800,
        max_context_lines: int = 5,
        glossary: Sequence[GlossaryEntry] = (),
        characters: Sequence[CharacterEntry] = (),
        system_instructions: str | None = None,
        honorifics_policy: str = "keep",
        profanity_policy: str = "faithful",
        line_contexts: Mapping[str, Any] | None = None,
        metrics: StageMetrics | None = None,
    ):
        self.metrics = metrics
        self.client = client
        self.model_name = model_name
        self.fallback_model = fallback_model
        self.max_tokens_per_batch = max_tokens_per_batch
        self.max_context_lines = max_context_lines
        self.glossary = list(glossary or ())
        self.characters = list(characters or ())
        self.honorifics_policy = honorifics_policy
        self.profanity_policy = profanity_policy
        self.line_contexts = dict(line_contexts or {})

        base_instructions = system_instructions or SYSTEM_INSTRUCTIONS
        policy_lines: list[str] = []
        if self.honorifics_policy == "keep":
            policy_lines.append(
                "- Políticas de honoríficos (honorifics): MANTENHA os sufixos japoneses originais transliterados (-san, -kun, -chan, -senpai, -sama, sensei, etc.). Não remova nem substitua por termos genéricos como senhor/dona."
            )
        elif self.honorifics_policy == "adapt":
            policy_lines.append(
                "- Políticas de honoríficos (honorifics): adapte os sufixos honoríficos japoneses para tratamento natural em português."
            )
        elif self.honorifics_policy == "remove":
            policy_lines.append(
                "- Políticas de honoríficos (honorifics): remova os sufixos honoríficos japoneses."
            )

        if self.profanity_policy == "faithful":
            policy_lines.append(
                "- Políticas de linguagem forte e palavrões (profanity): traduza com fidelidade mantendo o peso emocional equivalente da fala original em português coloquial, sem censura ou higienização."
            )
        elif self.profanity_policy == "soften":
            policy_lines.append(
                "- Políticas de linguagem forte e palavrões (profanity): suavize termos vulgares e ofensivos."
            )
        elif self.profanity_policy == "raw":
            policy_lines.append(
                "- Políticas de linguagem forte e palavrões (profanity): mantenha termos crus e explícitos sem atenuação."
            )

        has_low_conf = any(getattr(ctx, "confidence", "") == "low" for ctx in self.line_contexts.values())
        if has_low_conf or self.line_contexts:
            policy_lines.append(
                "- Gênero e falantes indeterminados: para falas com baixa confiança (low confidence) ou falante desconhecido, adote formulações gramaticalmente neutras (neutral gender phrasing) em português."
            )

        if policy_lines:
            base_instructions = f"{base_instructions}\n\n[DIRETRIZES DE ESTILO E POLÍTICAS]:\n" + "\n".join(policy_lines)

        self.system_instructions = base_instructions
        self.total_usage = Usage()
        self.fallback_count = 0

    def _count(self, name: str, n: int = 1) -> None:
        if self.metrics is not None:
            self.metrics.count(name, n)

    @retry(
        retry=retry_if_exception_type(LLMTransientError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=4),
        reraise=True,
    )
    def _call_model(self, prompt: str, target_model: str) -> tuple[TranslationBatch, Usage]:
        req = LLMRequest(
            model=target_model,
            instructions=self.system_instructions,
            prompt=prompt,
            output_type=TranslationBatch,
        )
        res = self.client.generate(req)
        return res.output, res.usage

    def _process_batch(
        self,
        lines: list[DialogueLine],
        context: list[ContextLine],
        glossary: Sequence[GlossaryEntry] = (),
        characters: Sequence[CharacterEntry] = (),
    ) -> dict[str, str]:
        if not lines:
            return {}

        prompt = format_batch_prompt(
            lines,
            context,
            glossary=glossary,
            characters=characters,
            line_contexts=self.line_contexts,
        )
        expected_ids = {line.id for line in lines}
        target_model = self.model_name

        try:
            output, usage = self._call_model(prompt, target_model)
        except LLMRefusalError as exc:
            if self.fallback_model and self.fallback_model != target_model:
                logger.warning("Recusa de modelo de nuvem (%s). Tentando modelo local %s.", exc, self.fallback_model)
                target_model = self.fallback_model
                try:
                    output, usage = self._call_model(prompt, target_model)
                except (LLMRefusalError, LLMOutputError):  # fmt: skip
                    output, usage = None, Usage()
            else:
                output, usage = None, Usage()
        except LLMOutputError:
            output, usage = None, Usage()

        self.total_usage = Usage(
            input_tokens=self.total_usage.input_tokens + usage.input_tokens,
            output_tokens=self.total_usage.output_tokens + usage.output_tokens,
            cached_input_tokens=self.total_usage.cached_input_tokens + usage.cached_input_tokens,
        )

        translations: dict[str, str] = {}
        if output:
            for item in output.items:
                if item.id in expected_ids:
                    translations[item.id] = item.text

        # Nível 2: Reconciliação de IDs ausentes
        missing_ids = expected_ids - set(translations.keys())
        if missing_ids and len(missing_ids) < len(lines):
            self._count("ids_reconciled", len(missing_ids))
            missing_lines = [line for line in lines if line.id in missing_ids]
            sub_results = self._process_batch(missing_lines, context, glossary=glossary, characters=characters)
            translations.update(sub_results)
            missing_ids = expected_ids - set(translations.keys())

        # Nível 3: Bisseção recursiva
        if missing_ids:
            if len(lines) > 1:
                self._count("batches_split")
                mid = len(lines) // 2
                left = self._process_batch(lines[:mid], context, glossary=glossary, characters=characters)
                right = self._process_batch(lines[mid:], context, glossary=glossary, characters=characters)
                left.update(right)
                return left
            else:
                # Nível 4: Degradação graciosa
                failed_line = lines[0]
                logger.warning(
                    "Falha ao traduzir fala id=%s ('%s'). Mantendo original.",
                    failed_line.id,
                    failed_line.text,
                )
                self.fallback_count += 1
                self._count("fallback_original")
                return {failed_line.id: failed_line.text}

        return translations

    def translate_lines(
        self,
        lines: list[DialogueLine],
        glossary: Sequence[GlossaryEntry] | None = None,
        characters: Sequence[CharacterEntry] | None = None,
    ) -> dict[str, str]:
        glossary_to_use = self.glossary if glossary is None else list(glossary)
        characters_to_use = self.characters if characters is None else list(characters)
        batches = create_dialogue_batches(
            lines,
            max_tokens_per_batch=self.max_tokens_per_batch,
            max_context_lines=self.max_context_lines,
        )
        all_translations: dict[str, str] = {}
        recent_context: list[ContextLine] = []

        for batch in batches:
            batch_result = self._process_batch(
                batch.lines,
                recent_context,
                glossary=glossary_to_use,
                characters=characters_to_use,
            )
            all_translations.update(batch_result)
            for line in batch.lines:
                recent_context.append(ContextLine(text=batch_result.get(line.id, line.text)))
            if self.max_context_lines > 0:
                if len(recent_context) > self.max_context_lines:
                    recent_context = recent_context[-self.max_context_lines :]
            else:
                recent_context = []

        return all_translations
