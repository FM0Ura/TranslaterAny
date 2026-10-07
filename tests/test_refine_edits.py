"""Protocolo de edições do M6: validação fala a fala."""

from translaterany.checks import CheckEnv
from translaterany.checks.snapshots import LineSource
from translaterany.refine.edits import LineEdit, apply_edits

SOURCES = {
    "u1": LineSource("I don't know.", "dialogue", "Default", 2000),
    "u2": LineSource("To the ⟦1⟧old⟦2⟧ station.", "dialogue", "Default", 2000),
    "u3": LineSource("You lied about all the recipes.", "dialogue", "Default", 2000),
}
TEXTS = {"u1": "Eu não sei.", "u2": "Para a ⟦1⟧velha⟦2⟧ estação.", "u3": "Você mentiu sobre tudo."}
ENV = CheckEnv()


def run(*edits: LineEdit, targets=frozenset(SOURCES), forbidden=None):
    return apply_edits(TEXTS, edits, set(targets), SOURCES, ENV, forbidden=forbidden)


def test_valid_edit_is_applied_and_map_stays_complete() -> None:
    out = run(LineEdit(id="[u3]", new="Você mentiu sobre todas as receitas."))
    assert out.applied == {"u3": "Você mentiu sobre todas as receitas."}
    assert out.texts == {**TEXTS, "u3": "Você mentiu sobre todas as receitas."}
    assert sum(out.rejected.values()) == 0


def test_rejection_reasons() -> None:
    out = run(
        LineEdit(id="u9", new="x"),  # unknown_id
        LineEdit(id="u1", new="  "),  # empty
        LineEdit(id="u2", new="Para a ⟦1⟧velha⟦2⟧ estação."),  # unchanged
        LineEdit(id="u2", new="Para a velha estação."),  # markers (a última edição de u2 vale)
    )
    assert out.rejected == {
        "unknown_id": 1, "empty": 1, "unchanged": 0, "markers": 1, "reversal": 0, "worse": 0, "glossary": 0,
    }  # fmt: skip
    assert out.applied == {}


def test_edit_outside_targets_is_unknown() -> None:
    out = run(LineEdit(id="u1", new="Não sei."), targets={"u3"})
    assert out.rejected["unknown_id"] == 1 and out.applied == {}


def test_worse_negation_and_profanity_are_rejected() -> None:
    out = run(LineEdit(id="u1", new="Eu sei."), LineEdit(id="u3", new="Mentiu, porra."))
    assert out.rejected["worse"] == 2 and out.applied == {}


def test_edit_back_to_english_is_worse() -> None:
    out = run(LineEdit(id="u1", new="I don't know."))
    assert out.rejected["worse"] == 1


def test_reversal_is_rejected() -> None:
    texts = {**TEXTS, "u3": "Você mentiu sobre todas as receitas."}
    out = apply_edits(texts, [LineEdit(id="u3", new="Você mentiu sobre tudo, seu  merda.")], {"u3"}, SOURCES, ENV,
                      forbidden={"u3": "Você mentiu sobre tudo, seu merda."})  # fmt: skip
    assert out.rejected["reversal"] == 1 and out.applied == {}


def test_accepted_edit_is_whitespace_normalized() -> None:
    out = run(LineEdit(id="u1", new="  Eu não\nsei,  cara. "))
    assert out.applied == {"u1": "Eu não sei, cara."}
    assert out.texts["u1"] == "Eu não sei, cara."


def test_override_tags_are_rejected_as_markers() -> None:
    out = run(LineEdit(id="u1", new="{\\an8}Eu não sei mesmo."))
    assert out.rejected["markers"] == 1 and out.applied == {}


def test_reordered_markers_are_rejected() -> None:
    out = run(LineEdit(id="u2", new="Para a ⟦2⟧velha⟦1⟧ estação."))
    assert out.rejected["markers"] == 1 and out.applied == {}


def test_fragment_answer_is_rejected_as_worse() -> None:
    texts = {**TEXTS, "u3": "Você mentiu sobre todas as receitas."}
    out = apply_edits(texts, [LineEdit(id="u3", new="as receitas")], {"u3"}, SOURCES, ENV)
    assert out.rejected["worse"] == 1 and out.applied == {}


def test_edit_id_inner_whitespace_is_removed() -> None:
    from translaterany.refine.edits import normalize_edit_id

    assert normalize_edit_id(" [u2 + u3] ") == "u2+u3"


def test_synthetic_or_malformed_markers_are_rejected() -> None:
    # u1 original não tem marcadores; nova edição introduz marcador sintético ⟦n⟧
    out = run(LineEdit(id="u1", new="Ai! ⟦n⟧"))
    assert out.rejected["markers"] == 1
    assert out.applied == {}

    # Marcador não fechado ou texto inválido entre colchetes
    out2 = run(LineEdit(id="u1", new="Ai! ⟦invalido"))
    assert out2.rejected["markers"] == 1
    assert out2.applied == {}



def _glossary_case():
    from translaterany.memory.models import GlossaryEntry

    sources = {"g1": LineSource("The widget maker met Zorblax and the gizmo.", "dialogue", "Default", 3000)}
    texts = {"g1": "O fabricante de engenhocas encontrou Zorblax e o gizmo."}
    env = CheckEnv(
        glossary=[
            GlossaryEntry(term="widget maker", translation="fabricante de engenhocas"),
            GlossaryEntry(term="Zorblax", translation="Zorblax", keep_original=True),
            GlossaryEntry(term="gizmo", translation="geringonça"),  # já violado no texto atual
        ]
    )
    return texts, sources, env


def test_edit_removing_canonical_glossary_form_is_rejected() -> None:
    texts, sources, env = _glossary_case()
    edit = LineEdit(id="g1", new="O criador de engenhocas encontrou Zorblax e o gizmo.")
    out = apply_edits(texts, [edit], {"g1"}, sources, env)
    assert out.rejected["glossary"] == 1 and out.applied == {} and out.texts == texts


def test_glossary_rejection_holds_even_when_another_term_is_already_violated() -> None:
    texts, sources, env = _glossary_case()
    edit = LineEdit(id="g1", new="O fabricante de engenhocas encontrou o Zorblax e o gizmo.")  # mantém tudo: ok
    assert apply_edits(texts, [edit], {"g1"}, sources, env).applied
    edit = LineEdit(id="g1", new="O fabricante de engenhocas encontrou Zorbla e o gizmo.")  # perde o nome mantido
    assert apply_edits(texts, [edit], {"g1"}, sources, env).rejected["glossary"] == 1


def test_edit_keeping_glossary_forms_and_fixing_others_is_applied() -> None:
    texts, sources, env = _glossary_case()
    edit = LineEdit(id="g1", new="O Fabricante de Engenhocas encontrou Zorblax e a geringonça.")
    out = apply_edits(texts, [edit], {"g1"}, sources, env)
    assert out.applied == {"g1": "O Fabricante de Engenhocas encontrou Zorblax e a geringonça."}
    assert out.rejected["glossary"] == 0
