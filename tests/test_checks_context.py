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


def test_glossary_ignores_alias_that_is_a_character_name() -> None:
    env = CheckEnv(
        glossary=[
            GlossaryEntry(
                term="Phantom Rin", translation="Rin Fantasma", aliases=["Rinrin", "The Phantom"], source="extracted"
            )
        ],
        names=[["Rin Okada", "Rinrin"]],
    )
    # só o alias (que é apelido de personagem) casou: a forma esperada do termo não é exigida
    assert not only(run_line_checks([line("Rinrin!", "Rinrin!")], env), "glossary")
    # alias que não é de personagem continua exigindo a forma esperada
    assert only(run_line_checks([line("The Phantom strikes.", "O vilão ataca.")], env), "glossary")
    # o termo em si casou: exige a forma esperada mesmo com o alias de personagem presente
    assert only(run_line_checks([line("Phantom Rin, Rinrin!", "Rinrin!")], env), "glossary")


def test_glossary_ignores_alias_that_is_another_entry_term() -> None:
    env = CheckEnv(
        glossary=[
            GlossaryEntry(term="Northtown", translation="Cidade Norte", aliases=["Northville"]),
            GlossaryEntry(term="Northville", translation="Vila Norte"),
        ]
    )
    findings = only(run_line_checks([line("Welcome to Northville.", "Bem-vindo à Vila Norte.")], env), "glossary")
    assert not findings
    assert only(run_line_checks([line("Welcome to Northtown.", "Bem-vindo à vila.")], env), "glossary")


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


def test_reading_speed_composite_skips_cpl_and_lines_but_checks_cps() -> None:
    comp = LineInput(id="u1+u2", line_type="dialogue", source="a b", target="a" * 75, duration_ms=1000, composite=True)
    found = only(run_line_checks([comp], CheckEnv()), "reading_speed")
    assert [f.message.split()[0] for f in found] == ["CPS"]
    multi = comp.model_copy(update={"target": "a\\Nb\\Nc", "duration_ms": 10_000})
    assert only(run_line_checks([multi], CheckEnv()), "reading_speed") == []
