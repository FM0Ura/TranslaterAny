"""Perfil genérico com fallbacks seguros para qualquer idioma."""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from translaterany.languages.models import LanguageInfo, TreatmentReport

_EMPTY_RE = re.compile(r"(?!)")  # Expressão que nunca dá match


@dataclass
class GenericProfile:
    """Perfil neutro para idiomas sem implementação especializada."""

    info: LanguageInfo
    negation_pattern: re.Pattern = _EMPTY_RE
    profanity_pattern: re.Pattern = _EMPTY_RE
    function_words: frozenset[str] = frozenset()
    foreign_words_pattern: re.Pattern | None = None
    dialect_warnings_pattern: re.Pattern | None = None
    formal_connectives_pattern: re.Pattern | None = None
    archaic_pronouns_pattern: re.Pattern | None = None

    default_cps: float = 17.0
    default_cpl: int = 42

    def scan_treatment(
        self,
        lines_info: Sequence[dict[str, Any]],
        character_gender: Mapping[str, str],
    ) -> TreatmentReport:
        """Generic não gera falsos positivos de tratamento."""
        return TreatmentReport(divergent_reasons={})

    def colloquial_signals(
        self,
        lines: Sequence[Any],
        speaker_of: Mapping[str, str],
        speakers_with_style: set[str],
    ) -> dict[str, list[str]]:
        """Generic não emite sinais inválidos de coloquialidade."""
        return {}
