"""Checagens básicas: markers, untranslated, length_ratio, numbers, negation (M5)."""

from translaterany.checks import CheckEnv, Finding, LineInput, check_names, run_line_checks
from translaterany.checks.registry import CHECKS, line_check
from translaterany.checks.text import plain, visible_lines, words
from translaterany.config.model import ChecksConfig


def line(src: str, tgt: str, *, kind: str = "dialogue", dur: int = 3000) -> LineInput:
    return LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=dur)


def only(findings: list[Finding], check: str) -> list[Finding]:
    return [f for f in findings if f.check == check]


ENV = CheckEnv()


def test_text_helpers_strip_tags_markers_and_breaks() -> None:
    assert visible_lines("Olá⟦1⟧ mundo\\Nsegunda {\\i1}linha") == ["Olá mundo", "segunda linha"]
    assert plain("A\\Nb") == "A b"
    assert words("Don't stop, 42 now") == ["don't", "stop", "now"]


def test_markers_ok_and_missing() -> None:
    assert not only(run_line_checks([line("To the ⟦1⟧old⟦2⟧ station", "Para a ⟦1⟧velha⟦2⟧ estação")], ENV), "markers")
    found = only(run_line_checks([line("To the ⟦1⟧old⟦2⟧ station", "Para a velha⟦2⟧ estação")], ENV), "markers")
    assert [f.severity for f in found] == ["error"]


def test_untranslated_identical_and_english_words() -> None:
    same = only(run_line_checks([line("Where are we going?", "where are we  going?")], ENV), "untranslated")
    assert [f.severity for f in same] == ["error"]
    english = only(run_line_checks([line("What is this?", "What is this thing aqui")], ENV), "untranslated")
    assert english and english[0].severity == "error"
    # interjeição curta idêntica não é erro
    assert not only(run_line_checks([line("Huh?", "Huh?")], ENV), "untranslated")
    assert not only(run_line_checks([line("Where are we going?", "Para onde vamos?")], ENV), "untranslated")


def test_length_ratio_bounds_and_min_chars() -> None:
    long_src = "This is a fairly long sentence to translate."
    assert only(run_line_checks([line(long_src, "Curta.")], ENV), "length_ratio")[0].severity == "warn"
    long_tgt = "Esta é uma frase razoavelmente longa para traduzir."
    assert not only(run_line_checks([line(long_src, long_tgt)], ENV), "length_ratio")
    assert not only(run_line_checks([line("Hi there", "Oi")], ENV), "length_ratio")  # < 10 caracteres


def test_numbers_missing() -> None:
    found = only(run_line_checks([line("I need 3 of them by 10.", "Preciso de três até as 10.")], ENV), "numbers")
    assert len(found) == 1 and "3" in found[0].message
    assert not only(run_line_checks([line("Room 42", "Sala 42")], ENV), "numbers")


def test_negation_dropped() -> None:
    assert only(run_line_checks([line("I don't know.", "Eu sei.")], ENV), "negation")
    assert only(run_line_checks([line("I don’t know.", "Eu sei.")], ENV), "negation")  # apóstrofo curvo
    assert not only(run_line_checks([line("I don't know.", "Eu não sei.")], ENV), "negation")
    assert not only(run_line_checks([line("I know.", "Eu sei.")], ENV), "negation")


def test_line_types_are_respected() -> None:
    assert not only(run_line_checks([line("I don't know.", "Eu sei.", kind="song")], ENV), "negation")


def test_disabled_checks_are_skipped() -> None:
    env = CheckEnv(limits=ChecksConfig(disabled=["negation"]))
    assert not only(run_line_checks([line("I don't know.", "Eu sei.")], env), "negation")


def test_crashing_check_becomes_finding() -> None:
    @line_check("t_boom", {"dialogue"})
    def boom(line: LineInput, env: CheckEnv) -> list[Finding]:
        raise ValueError("quebrou")

    try:
        found = only(run_line_checks([line("a", "b")], ENV), "check_crashed")
        assert found[0].severity == "error" and "t_boom" in found[0].message
    finally:
        CHECKS.pop("t_boom")


def test_check_names_include_episode_checks() -> None:
    assert {"markers", "untranslated", "length_ratio", "numbers", "negation", "font_glyphs"} <= check_names()
