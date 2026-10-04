"""Perfil de regras linguísticas para Português do Brasil (PT-BR)."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from translaterany.checks.lexicon import EN_FUNCTION_WORDS, PT_NEGATION, PT_PROFANITY, PT_PT_WORDS, SPANISH
from translaterany.languages.models import LanguageInfo, TreatmentReport
from translaterany.refine.lexicon import ARCHAIC_PRONOUN, FORMAL_CONNECTIVE
from translaterany.refine.treatment import scan_treatment_consistency
from translaterany.refine.triage import colloquial_signals


@dataclass
class PortugueseProfile:
    """Perfil completo para Português do Brasil."""

    info: LanguageInfo
    negation_pattern: re.Pattern = PT_NEGATION
    profanity_pattern: re.Pattern = PT_PROFANITY
    function_words: frozenset[str] = EN_FUNCTION_WORDS
    foreign_words_pattern: re.Pattern | None = SPANISH
    dialect_warnings_pattern: re.Pattern | None = PT_PT_WORDS
    formal_connectives_pattern: re.Pattern | None = FORMAL_CONNECTIVE
    archaic_pronouns_pattern: re.Pattern | None = ARCHAIC_PRONOUN

    default_cps: float = 17.0
    default_cpl: int = 42

    def scan_treatment(
        self,
        lines_info: Sequence[dict[str, Any]],
        character_gender: Mapping[str, str],
    ) -> TreatmentReport:
        """Executa scanner de tratamento e consistência de pronomes/artigos em PT-BR."""
        raw_report = scan_treatment_consistency(lines_info, character_gender)
        # Converte o report de refine/treatment para TreatmentReport
        divergences: dict[str, list[str]] = {}
        for pair_report in raw_report.values():
            for lid, reasons in pair_report.divergent_reasons.items():
                divergences.setdefault(lid, []).extend(reasons)
        return TreatmentReport(divergent_reasons=divergences)

    def colloquial_signals(
        self,
        lines: Sequence[Any],
        speaker_of: Mapping[str, str],
        speakers_with_style: set[str],
    ) -> dict[str, list[str]]:
        """Extrai sinais de ênclise, conectivos e rigidez coloquial em PT-BR."""
        return colloquial_signals(lines, speaker_of, speakers_with_style)
