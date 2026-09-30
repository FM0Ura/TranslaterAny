"""Checagem profanity_added (M6)."""

from translaterany.checks import CheckEnv, LineInput, check_names, run_line_checks


def found(src: str, tgt: str, kind: str = "dialogue") -> list:
    line = LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=3000)
    return [f for f in run_line_checks([line], CheckEnv()) if f.check == "profanity_added"]


def test_flags_profanity_absent_in_source() -> None:
    hits = found("You've been using it to cheat on all your tests.", "Você colou em tudo, seu merda.")
    assert len(hits) == 1 and hits[0].severity == "warn" and "merda" in hits[0].message


def test_accepts_profanity_present_in_source() -> None:
    assert not found("Damn it!", "Droga, porra!")
    assert not found("You idiot!", "Seu idiota!")


def test_clean_lines_and_other_types_are_ignored() -> None:
    assert not found("Great!", "Ótimo!")
    assert found("Hello", "Olá, cacete", kind="sign") == []  # placas não são checadas


def test_word_boundaries() -> None:
    # EN: "ass" não casa dentro de "Classic", portanto merda é flagged
    assert len(found("Classic", "Que merda")) == 1
    # EN: "hell" não casa dentro de "Hello there", portanto merda é flagged
    assert len(found("Hello there", "Que merda")) == 1
    # PT: "puta" não casa dentro de "computador" (word boundary)
    assert found("Look at this.", "Olha o computador.") == []


def test_registered() -> None:
    assert "profanity_added" in check_names()
