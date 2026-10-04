"""Protocolo base e fábrica para perfis de idioma."""

import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from translaterany.languages.models import LanguageInfo, TreatmentReport
from translaterany.languages.profiles.generic import GenericProfile


class LanguageProfile(Protocol):
    """Contrato de capacidades e regras linguísticas de um idioma."""

    info: LanguageInfo

    negation_pattern: re.Pattern
    profanity_pattern: re.Pattern
    function_words: frozenset[str]
    foreign_words_pattern: re.Pattern | None
    dialect_warnings_pattern: re.Pattern | None
    formal_connectives_pattern: re.Pattern | None
    archaic_pronouns_pattern: re.Pattern | None

    default_cps: float
    default_cpl: int

    def scan_treatment(
        self,
        lines_info: Sequence[dict[str, Any]],
        character_gender: Mapping[str, str],
    ) -> TreatmentReport:
        """Verifica coerência de pronomes de tratamento e flexão de gênero."""
        ...

    def colloquial_signals(
        self,
        lines: Sequence[Any],
        speaker_of: Mapping[str, str],
        speakers_with_style: set[str],
    ) -> dict[str, list[str]]:
        """Extrai sinais de rigidez ou formalidade textual no idioma."""
        ...


# Mapa de construtores de perfis por código ISO 639-1
_PROFILE_REGISTRY: dict[str, Any] = {}


def register_profile(iso639_1: str, factory: Any) -> None:
    """Registra uma classe ou fábrica de perfil para um idioma."""
    _PROFILE_REGISTRY[iso639_1.lower()] = factory


def get_profile(lang: LanguageInfo) -> LanguageProfile:
    """Retorna o LanguageProfile correspondente ao idioma, ou GenericProfile como fallback."""
    iso = lang.iso639_1.lower()
    if iso in _PROFILE_REGISTRY:
        factory = _PROFILE_REGISTRY[iso]
        return factory(lang)
    if iso == "pt":
        from translaterany.languages.profiles.portuguese import PortugueseProfile

        return PortugueseProfile(lang)
    return GenericProfile(lang)
