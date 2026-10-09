"""Detecção de letras bilíngues 'romaji / inglês' e de estilos de tradução de letra (dados sintéticos)."""

import pytest

from translaterany.subtitles.classify import is_lyric_translation_style
from translaterany.subtitles.lyrics import is_romaji_word, split_bilingual_lyric


@pytest.mark.parametrize(
    "word",
    ["kimi", "taiyo", "mimamotte", "furikaeranai", "konna", "tsukara", "sakebe", "shinda", "gakkou", "ōkii", "wo", "n"],
)
def test_romaji_words(word: str) -> None:
    assert is_romaji_word(word)


@pytest.mark.parametrize("word", ["the", "hello", "they", "my", "world", "strong", "cat", "dad", "what", "s", ""])
def test_english_words_are_not_romaji(word: str) -> None:
    assert not is_romaji_word(word)


def test_split_backslash_n_pair() -> None:
    got = split_bilingual_lyric("Kimi to taiyo ga shinda hi\\NThe day you and the sun died")
    assert got is not None
    assert (got.romaji, got.separator, got.gloss) == (
        "Kimi to taiyo ga shinda hi",
        "\\N",
        "The day you and the sun died",
    )
    assert got.strong


def test_split_slash_pair() -> None:
    got = split_bilingual_lyric("Koe wo karashite sakebe / Shout yourself hoarse into the sky")
    assert got is not None
    assert got.separator == " / " and got.gloss == "Shout yourself hoarse into the sky"


def test_two_word_romaji_is_weak() -> None:
    got = split_bilingual_lyric("Mimamotte ite\\NAnd watch over me")
    assert got is not None and not got.strong


@pytest.mark.parametrize(
    "text",
    [
        "Hello?\\NDad?!",  # diálogo comum
        "Take this!\\NDad! Can't you hear my voice?",
        "Rei!\\NRe...",
        "Yes!\\NHirano!",
        "Takashi Komuro\\NWhat are you doing here with them?",  # nome em duas palavras maiúsculas
        "Kenji Takashi Hisashi\\NHurry up and get out of there now",  # só nomes próprios
        "Koe wo karashite sakebe",  # sem glosa
        "Koe wo karashite sakebe\\NOk",  # glosa curta demais
        "Koe wo karashite sakebe\\Nkono sekai wo kowashite",  # as duas metades são romaji
        "We're going to escape from\\Nthe management building!",
        "Line one is plain english here\\NLine two is plain english too",
        "Kimi 12 to taiyo\\NThe day you and the sun died",
        "Kimi to taiyo ga\\Nshinda hi\\NThe day you and the sun died",  # três linhas: ambíguo
        "",
    ],
)
def test_normal_dialogue_is_not_bilingual_lyric(text: str) -> None:
    assert split_bilingual_lyric(text) is None


def test_markers_do_not_confuse_the_split() -> None:
    got = split_bilingual_lyric("⟦1⟧Kimi to taiyo ga shinda hi⟦2⟧\\N⟦3⟧The day you and the sun died⟦4⟧")
    assert got is not None
    assert got.romaji == "⟦1⟧Kimi to taiyo ga shinda hi⟦2⟧"
    assert got.gloss == "⟦3⟧The day you and the sun died⟦4⟧"


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("op trans", True),
        ("ed trans", True),
        ("OP_Translation", True),
        ("EDTranslation", True),
        ("OP TL", True),
        ("op kara", False),
        ("OP_Romaji", False),
        ("Default", False),
        ("Sign Translated", True),
        ("Transport", False),  # 'trans' só como palavra inteira do nome do estilo
    ],
)
def test_lyric_translation_style(style: str, expected: bool) -> None:
    assert is_lyric_translation_style(style) is expected
