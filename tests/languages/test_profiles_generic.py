# tests/languages/test_profiles_generic.py
from translaterany.languages.models import LanguageInfo
from translaterany.languages.profile import get_profile
from translaterany.languages.profiles.generic import GenericProfile


def test_generic_profile_fallback() -> None:
    info = LanguageInfo("nl", "nl", "nld", "holandês", "Dutch", "Nederlands", "nl")
    prof = get_profile(info)
    assert isinstance(prof, GenericProfile)
    assert prof.info.code == "nl"
    assert prof.default_cps == 17.0
    assert prof.default_cpl == 42


def test_generic_profile_safe_treatment_and_colloquial() -> None:
    info = LanguageInfo("nl", "nl", "nld", "holandês", "Dutch", "Nederlands", "nl")
    prof = get_profile(info)
    # Generic não emite falsos positivos de tratamento
    report = prof.scan_treatment([{"id": "1", "text": "Hallo"}], {})
    assert len(report.divergent_reasons) == 0

    # Generic não gera sinais de triagem inválidos
    signals = prof.colloquial_signals([], {}, set())
    assert len(signals) == 0
