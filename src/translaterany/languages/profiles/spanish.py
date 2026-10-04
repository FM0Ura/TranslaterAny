"""Perfil de regras linguísticas para Espanhol (ES)."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from translaterany.languages.models import LanguageInfo, TreatmentReport

ES_NEGATION = re.compile(r"\b(?:no|nunca|jamás|nadie|nada|ningún|ninguno|ninguna|tampoco)\b", re.IGNORECASE)
ES_PROFANITY = re.compile(
    r"\b(?:mierda|joder|coño|puta|puto|cabrón|cabrona|gilipollas|pendejo|pendeja|hijo de puta|hostia|bastardo)\b",
    re.IGNORECASE,
)
ES_FORMAL_CONNECTIVE = re.compile(
    r"\b(?:no obstante|sin embargo|asimismo|por consiguiente|por ende|en consecuencia|empero)\b",
    re.IGNORECASE,
)
ES_ARCHAIC_PRONOUN = re.compile(r"\b(?:vosotros|vosotras|os|vuestro|vuestra|vuestros|vuestras)\b", re.IGNORECASE)
PT_INTRUSION = re.compile(r"\b(?:não|você|obrigado|muito|agora|então|falar|coisa)\b", re.IGNORECASE)

ES_FUNCTION_WORDS = frozenset(
    {
        "el", "la", "de", "que", "y", "a", "en", "un", "ser", "se", "no", "haber", "por", "con", "su", "para",
        "como", "estar", "tener", "le", "lo", "todo", "pero", "más", "hacer", "o", "poder", "este", "ya",
        "otro", "ese", "si", "me", "primer", "dar", "muy", "bien", "sin",
    }
)

_TU_PATTERN = re.compile(r"\b(?:tú|tu|te|ti|contigo|quieres|puedes|sabes|tienes|vienes|haces|dices)\b", re.IGNORECASE)
_USTED_PATTERN = re.compile(r"\b(?:usted|su|sus|quiere|puede|sabe|tiene|viene|hace|dice)\b", re.IGNORECASE)


@dataclass
class SpanishProfile:
    """Perfil completo para Espanhol."""

    info: LanguageInfo
    negation_pattern: re.Pattern = ES_NEGATION
    profanity_pattern: re.Pattern = ES_PROFANITY
    function_words: frozenset[str] = ES_FUNCTION_WORDS
    foreign_words_pattern: re.Pattern | None = PT_INTRUSION
    dialect_warnings_pattern: re.Pattern | None = None
    formal_connectives_pattern: re.Pattern | None = ES_FORMAL_CONNECTIVE
    archaic_pronouns_pattern: re.Pattern | None = ES_ARCHAIC_PRONOUN

    default_cps: float = 17.0
    default_cpl: int = 42

    def scan_treatment(
        self,
        lines_info: Sequence[dict[str, Any]],
        character_gender: Mapping[str, str],
    ) -> TreatmentReport:
        """Verifica coerência de tú vs usted e concordância de gênero entre personagens."""
        divergences: dict[str, list[str]] = {}

        # Agrupa falas por par (speaker, listener)
        pairs: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for line in lines_info:
            spk = line.get("speaker", "Unknown")
            lis = line.get("listener", "Unknown")
            if spk != "Unknown" and lis != "Unknown" and spk != lis:
                pair_key = (spk, lis) if spk < lis else (lis, spk)
                pairs.setdefault(pair_key, []).append(line)

        for pair_key, group in pairs.items():
            tu_lines = []
            usted_lines = []
            for line in group:
                txt = line.get("text", "")
                if _TU_PATTERN.search(txt):
                    tu_lines.append(line["id"])
                elif _USTED_PATTERN.search(txt):
                    usted_lines.append(line["id"])

            if tu_lines and usted_lines:
                # Há divergência: marca as linhas minoritárias
                minority = tu_lines if len(tu_lines) < len(usted_lines) else usted_lines
                reason = "divergência tú/usted"
                for lid in minority:
                    divergences.setdefault(lid, []).append(reason)

        return TreatmentReport(divergent_reasons=divergences)

    def colloquial_signals(
        self,
        lines: Sequence[Any],
        speaker_of: Mapping[str, str],
        speakers_with_style: set[str],
    ) -> dict[str, list[str]]:
        """Extrai sinais de rigidez formal em espanhol."""
        result: dict[str, list[str]] = {}
        for line in lines:
            txt = getattr(line, "target", "")
            signals: list[str] = []
            if self.formal_connectives_pattern and self.formal_connectives_pattern.search(txt):
                signals.append("formal_connective")
            if self.archaic_pronouns_pattern and self.archaic_pronouns_pattern.search(txt):
                signals.append("archaic_pronoun")
            line_id = getattr(line, "id", None)
            if line_id and signals:
                result[line_id] = signals
        return result
