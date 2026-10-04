from translaterany.languages.registry import LanguageRegistry


def test_resolve_standard_codes() -> None:
    pt = LanguageRegistry.resolve("pt-BR")
    assert pt.code == "pt-BR"
    assert pt.iso639_1 == "pt"
    assert pt.iso639_2 == "por"
    assert "português" in pt.name_pt.lower()

    en = LanguageRegistry.resolve("en")
    assert en.code == "en"
    assert en.iso639_1 == "en"
    assert en.iso639_2 == "eng"
    assert "inglês" in en.name_pt.lower()

    ja = LanguageRegistry.resolve("ja")
    assert ja.code == "ja"
    assert ja.iso639_2 == "jpn"
    assert "japonês" in ja.name_pt.lower()


def test_resolve_flexible_aliases() -> None:
    assert LanguageRegistry.resolve("pt_br").code == "pt-BR"
    assert LanguageRegistry.resolve("PT-br").code == "pt-BR"
    assert LanguageRegistry.resolve("por").code == "pt-BR"
    assert LanguageRegistry.resolve("portugues").code == "pt-BR"
    assert LanguageRegistry.resolve("português").code == "pt-BR"

    assert LanguageRegistry.resolve("jpn").code == "ja"
    assert LanguageRegistry.resolve("japanese").code == "ja"
    assert LanguageRegistry.resolve("japonês").code == "ja"

    assert LanguageRegistry.resolve("spa").code == "es"
    assert LanguageRegistry.resolve("espanhol").code == "es"
    assert LanguageRegistry.resolve("spanish").code == "es"


def test_resolve_unregistered_fallback() -> None:
    sw = LanguageRegistry.resolve("sw")
    assert sw.code == "sw"
    assert sw.iso639_1 == "sw"
    assert sw.iso639_2 == "sw"
    assert sw.languagetool_code == "sw"


def test_matches_mkv_tracks() -> None:
    pt = LanguageRegistry.resolve("pt-BR")
    assert LanguageRegistry.matches("por", pt) is True
    assert LanguageRegistry.matches("pt-BR", pt) is True
    assert LanguageRegistry.matches("pt", pt) is True
    assert LanguageRegistry.matches("eng", pt) is False

    ja = LanguageRegistry.resolve("ja")
    assert LanguageRegistry.matches("jpn", ja) is True
    assert LanguageRegistry.matches("ja", ja) is True
    assert LanguageRegistry.matches("por", ja) is False
