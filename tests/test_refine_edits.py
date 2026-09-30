"""Protocolo de edições do M6: validação fala a fala."""

from translaterany.checks import CheckEnv
from translaterany.checks.snapshots import LineSource
from translaterany.refine.edits import LineEdit, apply_edits

SOURCES = {
    "u1": LineSource("I don't know.", "dialogue", "Default", 2000),
    "u2": LineSource("To the ⟦1⟧old⟦2⟧ station.", "dialogue", "Default", 2000),
    "u3": LineSource("You cheated on all your tests.", "dialogue", "Default", 2000),
}
TEXTS = {"u1": "Eu não sei.", "u2": "Para a ⟦1⟧velha⟦2⟧ estação.", "u3": "Você colou em tudo."}
ENV = CheckEnv()


def run(*edits: LineEdit, targets=frozenset(SOURCES), forbidden=None):
    return apply_edits(TEXTS, edits, set(targets), SOURCES, ENV, forbidden=forbidden)


def test_valid_edit_is_applied_and_map_stays_complete() -> None:
    out = run(LineEdit(id="[u3]", new="Você colou em todas as provas."))
    assert out.applied == {"u3": "Você colou em todas as provas."}
    assert out.texts == {**TEXTS, "u3": "Você colou em todas as provas."}
    assert sum(out.rejected.values()) == 0


def test_rejection_reasons() -> None:
    out = run(
        LineEdit(id="u9", new="x"),  # unknown_id
        LineEdit(id="u1", new="  "),  # empty
        LineEdit(id="u2", new="Para a ⟦1⟧velha⟦2⟧ estação."),  # unchanged
        LineEdit(id="u2", new="Para a velha estação."),  # markers (a última edição de u2 vale)
    )
    assert out.rejected == {"unknown_id": 1, "empty": 1, "unchanged": 0, "markers": 1, "reversal": 0, "worse": 0}
    assert out.applied == {}


def test_edit_outside_targets_is_unknown() -> None:
    out = run(LineEdit(id="u1", new="Não sei."), targets={"u3"})
    assert out.rejected["unknown_id"] == 1 and out.applied == {}


def test_worse_negation_and_profanity_are_rejected() -> None:
    out = run(LineEdit(id="u1", new="Eu sei."), LineEdit(id="u3", new="Colou, porra."))
    assert out.rejected["worse"] == 2 and out.applied == {}


def test_edit_back_to_english_is_worse() -> None:
    out = run(LineEdit(id="u1", new="I don't know."))
    assert out.rejected["worse"] == 1


def test_reversal_is_rejected() -> None:
    texts = {**TEXTS, "u3": "Você colou em todas as provas."}
    out = apply_edits(texts, [LineEdit(id="u3", new="Você colou em tudo, seu  merda.")], {"u3"}, SOURCES, ENV,
                      forbidden={"u3": "Você colou em tudo, seu merda."})  # fmt: skip
    assert out.rejected["reversal"] == 1 and out.applied == {}
