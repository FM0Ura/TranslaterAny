"""Camada de suporte universal a idiomas do TranslaterAny."""

from translaterany.languages.models import LanguageInfo, TreatmentReport
from translaterany.languages.profile import LanguageProfile, get_profile
from translaterany.languages.registry import LanguageRegistry

__all__ = ["LanguageInfo", "LanguageProfile", "LanguageRegistry", "TreatmentReport", "get_profile"]
