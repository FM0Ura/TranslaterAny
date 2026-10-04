from translaterany.languages.profile import get_profile
from translaterany.languages.profiles.portuguese import PortugueseProfile
from translaterany.languages.registry import LanguageRegistry


def test_get_portuguese_profile() -> None:
    pt_info = LanguageRegistry.resolve("pt-BR")
    prof = get_profile(pt_info)
    assert isinstance(prof, PortugueseProfile)
    assert prof.info.code == "pt-BR"
    assert prof.negation_pattern.search("não")
    assert prof.negation_pattern.search("nunca")
    assert prof.profanity_pattern.search("merda")


def test_portuguese_treatment_scan() -> None:
    pt_info = LanguageRegistry.resolve("pt-BR")
    prof = get_profile(pt_info)
    lines = [
        {"id": "u1", "text": "Você veio aqui?", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
        {"id": "u2", "text": "Tu disseste a verdade?", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
    ]
    report = prof.scan_treatment(lines, {})
    # Deve detectar divergência você/tu
    assert "u2" in report.divergent_reasons or "u1" in report.divergent_reasons
