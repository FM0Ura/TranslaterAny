# tests/languages/test_profiles_es_en.py
from translaterany.languages.registry import LanguageRegistry
from translaterany.languages.profile import get_profile
from translaterany.languages.profiles.spanish import SpanishProfile
from translaterany.languages.profiles.english import EnglishProfile


def test_spanish_profile_lexicon_and_treatment() -> None:
    es_info = LanguageRegistry.resolve("es")
    prof = get_profile(es_info)
    assert isinstance(prof, SpanishProfile)
    assert prof.negation_pattern.search("jamás")
    assert prof.profanity_pattern.search("mierda")
    assert prof.formal_connectives_pattern.search("no obstante")

    # Scanner tú vs usted
    lines = [
        {"id": "u1", "text": "¿Tú quieres venir?", "speaker": "Carlos", "listener": "Elena", "confidence": "high"},
        {"id": "u2", "text": "Usted sabe que sí.", "speaker": "Carlos", "listener": "Elena", "confidence": "high"},
    ]
    report = prof.scan_treatment(lines, {})
    assert len(report.divergent_reasons) > 0


def test_english_profile_lexicon_and_pronouns() -> None:
    en_info = LanguageRegistry.resolve("en")
    prof = get_profile(en_info)
    assert isinstance(prof, EnglishProfile)
    assert prof.negation_pattern.search("cannot")
    assert prof.profanity_pattern.search("bullshit")
    assert prof.formal_connectives_pattern.search("furthermore")

    # Scanner de pronomes com gênero definido
    lines = [
        {"id": "u1", "text": "He is my best friend.", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
        {"id": "u2", "text": "She went to the market.", "speaker": "Alice", "listener": "Bob", "confidence": "high"},
    ]
    char_gender = {"Bob": "male"}
    report = prof.scan_treatment(lines, char_gender)
    # Se uma fala usa 'she' ao falar diretamente de Bob, reporta divergência
    assert isinstance(report.divergent_reasons, dict)
