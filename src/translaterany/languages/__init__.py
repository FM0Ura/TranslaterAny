"""Camada de suporte universal a idiomas do TranslaterAny."""

from translaterany.languages.models import LanguageInfo, TreatmentReport
from translaterany.languages.registry import LanguageRegistry

__all__ = ["LanguageInfo", "LanguageRegistry", "TreatmentReport"]
