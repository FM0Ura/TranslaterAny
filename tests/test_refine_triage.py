"""Triagem por regras do M6."""

from translaterany.checks import CheckEnv, LineInput
from translaterany.refine.triage import colloquial_signals, meaning_signals


def line(i: str, src: str, tgt: str) -> LineInput:
    return LineInput(id=i, line_type="dialogue", source=src, target=tgt, duration_ms=3000)


def test_meaning_signals_from_checks() -> None:
    lines = [line("u1", "I don't know.", "Eu sei."), line("u2", "Great!", "Ótimo!"),
             line("u3", "You lied 3 times.", "Você mentiu, seu merda.")]  # fmt: skip
    got = meaning_signals(lines, CheckEnv())
    assert got == {"u1": ["negation"], "u3": ["numbers", "profanity_added"]}


def test_colloquial_signals() -> None:
    lines = [
        line("u1", "However, I lost it.", "No entanto, eu perdi."),
        line("u2", "I'll do it.", "Vou fazê-lo."),
        line("u3", "I'm really tired.", "Eu estou cansado."),
        line("u4", "Are you coming?", "Tu vens?"),
        line("u5", "Thanks for the help.", "Muito obrigado mesmo por toda essa ajuda que você me deu hoje."),
        line("u6", "Let's go.", "Vamos."),
        line("u7", "Let's go.", "Vamos."),
    ]
    got = colloquial_signals(lines, speaker_of={"u7": "Yu"}, speakers_with_style={"Yu"})
    assert got == {
        "u1": ["formal_connective"],
        "u2": ["enclisis"],
        "u3": ["redundant_subject"],
        "u4": ["archaic_pronoun"],
        "u5": ["too_long"],
        "u7": ["speech_style"],
    }
