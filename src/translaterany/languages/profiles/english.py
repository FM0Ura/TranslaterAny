"""Perfil de regras linguísticas para Inglês (EN)."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from translaterany.checks.lexicon import EN_FUNCTION_WORDS, EN_NEGATION
from translaterany.languages.models import LanguageInfo, TreatmentReport

EN_PROFANITY = re.compile(
    r"\b(?:shit|fuck\w*|damn\w*|bitch\w*|bastard\w*|ass|asshole|crap|bullshit|idiot\w*|moron\w*|jerk\w*|hell|"
    r"dumbass|screw\w*|piss\w*|dick\w*|stupid|fool\w*|dumb\w*|loser\w*|pervert\w*)\b",
    re.IGNORECASE,
)
EN_FORMAL_CONNECTIVE = re.compile(
    r"\b(?:furthermore|moreover|henceforth|nevertheless|nonetheless|consequently|heretofore)\b",
    re.IGNORECASE,
)
EN_ARCHAIC_PRONOUN = re.compile(r"\b(?:thou|thee|thy|thine|ye|whilst)\b", re.IGNORECASE)

_HE_PRONOUNS = re.compile(r"\b(?:he|him|his|himself)\b", re.IGNORECASE)
_SHE_PRONOUNS = re.compile(r"\b(?:she|her|hers|herself)\b", re.IGNORECASE)


@dataclass
class EnglishProfile:
    """Perfil completo para Inglês."""

    info: LanguageInfo
    negation_pattern: re.Pattern = EN_NEGATION
    profanity_pattern: re.Pattern = EN_PROFANITY
    function_words: frozenset[str] = EN_FUNCTION_WORDS
    foreign_words_pattern: re.Pattern | None = None
    dialect_warnings_pattern: re.Pattern | None = None
    formal_connectives_pattern: re.Pattern | None = EN_FORMAL_CONNECTIVE
    archaic_pronouns_pattern: re.Pattern | None = EN_ARCHAIC_PRONOUN

    default_cps: float = 17.0
    default_cpl: int = 42

    def scan_treatment(
        self,
        lines_info: Sequence[dict[str, Any]],
        character_gender: Mapping[str, str],
    ) -> TreatmentReport:
        """Verifica coerência de pronomes de gênero he/she/they em relação a personagens."""
        divergences: dict[str, list[str]] = {}
        for line in lines_info:
            txt = line.get("text", "")
            listener = line.get("listener", "Unknown")
            if listener in character_gender:
                gender = character_gender[listener].lower()
                if gender in ("male", "masculine", "homem"):
                    if _SHE_PRONOUNS.search(txt) and not _HE_PRONOUNS.search(txt):
                        divergences.setdefault(line["id"], []).append("pronome feminino referindo a homem")
                elif gender in ("female", "feminine", "mulher"):
                    if _HE_PRONOUNS.search(txt) and not _SHE_PRONOUNS.search(txt):
                        divergences.setdefault(line["id"], []).append("pronome masculino referindo a mulher")

        return TreatmentReport(divergent_reasons=divergences)

    def colloquial_signals(
        self,
        lines: Sequence[Any],
        speaker_of: Mapping[str, str],
        speakers_with_style: set[str],
    ) -> dict[str, list[str]]:
        """Extrai sinais de rigidez formal em inglês."""
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
