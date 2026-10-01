"""Checagem prompt_leak: instruções do prompt ou enchimento que o modelo devolveu como tradução."""

from translaterany.checks import CheckEnv, LineInput, check_names, run_line_checks


def found(src: str, tgt: str, kind: str = "dialogue") -> list:
    line = LineInput(id="u1", line_type=kind, source=src, target=tgt, duration_ms=3000)
    return [f for f in run_line_checks([line], CheckEnv()) if f.check == "prompt_leak"]


def test_registered() -> None:
    assert "prompt_leak" in check_names()


def test_flags_budget_instruction_echoed_in_target() -> None:
    hits = found("Really?", "Sério mesmo? (máx. 84)")
    assert len(hits) == 1 and hits[0].severity == "error"
    assert found("Hello.", "Olá. no máximo 20 caracteres")
    assert found("Hello.", "[u12] Olá.")


def test_flags_emoji_absent_in_source() -> None:
    assert found("Really?", "Sério mesmo? 😮")
    assert not found("Really? 😮", "Sério mesmo? 😮")


def test_clean_text_and_music_notes_pass() -> None:
    assert not found("Really?", "Sério mesmo?")
    assert not found("La la la", "♪ La la la ♪")
    assert not found("It's at most 5 miles.", "Fica a no máximo 8 km.")
