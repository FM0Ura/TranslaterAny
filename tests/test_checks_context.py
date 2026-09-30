# tests/test_checks_context.py
"""Checagens de contexto: names, glossary, foreign_markers, reading_speed (M5)."""

import pytest

from translaterany.checks import CheckEnv, Finding, LineInput, run_line_checks
from translaterany.checks.rules_context import measure
from translaterany.memory.matching import matches_term, select_for_text
from translaterany.memory.models import CharacterEntry, GlossaryEntry


def line(src: str, tgt: str, *, kind: str = "dialogue", dur: int = 3000) -> LineInput:
    return LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=dur)


def only(findings: list[Finding], check: str) -> list[Finding]:
    return [f for f in findings if f.check == check]


def test_matches_term_word_boundaries() -> None:
    assert matches_term("Yu", "Yu, wait!")
    assert not matches_term("Yu", "Yuusuke")
    assert matches_term("Dr. Kim", "Hello Dr. Kim")
    assert not matches_term("", "x")


def test_select_for_text_filters_by_presence() -> None:
    glossary = [GlossaryEntry(term="Ability", translation="Habilidade"), GlossaryEntry(term="Zero", translation="Zero")]
    chars = [CharacterEntry(name="Yu Otosaka", aliases=["Yu"]), CharacterEntry(name="Nao")]
    g, c = select_for_text(glossary, chars, "Yu used his Ability.")
    assert [e.term for e in g] == ["Ability"]
    assert [x.name for x in c] == ["Yu Otosaka"]


def test_names_missing_in_translation() -> None:
    env = CheckEnv(names=[["Yu Otosaka", "Yu"]])
    assert only(run_line_checks([line("Yu, wait!", "Espera!")], env), "names")
    assert not only(run_line_checks([line("Yu, wait!", "Yu, espera!")], env), "names")


def test_glossary_expected_form() -> None:
    env = CheckEnv(
        glossary=[
            GlossaryEntry(term="Student Council", translation="Conselho Estudantil"),
            GlossaryEntry(term="Hoshinoumi", translation="", keep_original=True),
        ]
    )
    assert only(run_line_checks([line("The Student Council is here.", "O grêmio chegou.")], env), "glossary")
    assert not only(
        run_line_checks([line("The Student Council is here.", "O Conselho Estudantil chegou.")], env), "glossary"
    )
    assert not only(run_line_checks([line("Hoshinoumi Academy", "Academia Hoshinoumi")], env), "glossary")


def test_foreign_markers() -> None:
    env = CheckEnv()
    assert only(run_line_checks([line("I'm on the bus.", "Estou no autocarro.")], env), "foreign_markers")
    assert only(run_line_checks([line("I'm eating.", "Estou a comer.")], env), "foreign_markers")
    assert only(run_line_checks([line("But why?", "¿Pero por qué?")], env), "foreign_markers")
    assert not only(run_line_checks([line("I'm eating.", "Estou comendo.")], env), "foreign_markers")


def test_measure_counts_visible_chars() -> None:
    m = measure("{\\i1}Olá⟦1⟧ mundo\\N  tudo bem? ", 1000)
    assert m.lines == 2
    assert m.max_cpl == len("Olá mundo")
    assert m.cps == pytest.approx(len("Olá mundo") + len("tudo bem?"))


def test_reading_speed_cps_limit_exact() -> None:
    env = CheckEnv()
    ok = run_line_checks([line("x", "a" * 17, dur=1000)], env)  # 17,0 CPS passa
    assert not [f for f in only(ok, "reading_speed") if f.message.startswith("CPS")]
    bad = run_line_checks([line("x", "a" * 171, dur=10_000)], env)  # 17,1 CPS falha
    cps = [f for f in only(bad, "reading_speed") if f.message.startswith("CPS")]
    assert cps and cps[0].severity == "error" and cps[0].value == pytest.approx(17.1)


def test_reading_speed_cpl_and_lines() -> None:
    env = CheckEnv()
    ok = only(run_line_checks([line("x", "a" * 42, dur=10_000)], env), "reading_speed")
    assert not ok
    cpl = only(run_line_checks([line("x", "a" * 43, dur=10_000)], env), "reading_speed")
    assert [f.message.split()[0] for f in cpl] == ["CPL"]
    three = only(run_line_checks([line("x", "a\\Nb\\Nc", dur=10_000)], env), "reading_speed")
    assert [f.message.split()[0] for f in three] == ["linhas:"]


def test_reading_speed_zero_duration_skips_cps() -> None:
    found = only(run_line_checks([line("x", "a" * 30, dur=0)], CheckEnv()), "reading_speed")
    assert found == []
    assert measure("abc", 0).cps is None
