"""Testes de atribuicao de culpa (blame) a partir do historico de artefatos."""

from translaterany.checks import CheckEnv, Finding
from translaterany.checks.snapshots import LineSource
from translaterany.memory.models import GlossaryEntry
from translaterany.quality.blame import attribute_blame


def test_attribute_blame_finds_origin_stage() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto perfeito."}),
        ("review_meaning", {"u1": "Texto perfeito."}),
        ("colloquial", {"u1": "máx. 20 Texto perfeito."}),  # Defeito surgiu aqui
        ("adapt", {"u1": "máx. 20 Texto perfeito."}),
    ]
    finding = Finding(unit_id="u1", check="prompt_leak", message="vazamento", severity="error")
    blamed = attribute_blame("u1", finding, history)
    assert blamed == "colloquial"


def test_attribute_blame_origin_in_first_stage() -> None:
    history = [
        ("translate_dialogue", {"u1": "máx. 10 Olá mundo."}),
        ("review_meaning", {"u1": "máx. 10 Olá mundo."}),
        ("colloquial", {"u1": "máx. 10 Olá mundo."}),
    ]
    finding = Finding(unit_id="u1", check="prompt_leak", message="vazamento", severity="error")
    blamed = attribute_blame("u1", finding, history)
    assert blamed == "translate_dialogue"


def test_attribute_blame_defaults_to_redistribute_when_clean_or_timing() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto perfeito."}),
        ("review_meaning", {"u1": "Texto perfeito."}),
        ("colloquial", {"u1": "Texto perfeito."}),
    ]
    finding = Finding(unit_id="u1", check="timing_bounds", message="tempo invertido", severity="error")
    blamed = attribute_blame("u1", finding, history)
    assert blamed == "redistribute_sentences"


def test_attribute_blame_ass_syntax_error() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto perfeito."}),
        ("review_meaning", {"u1": "Texto perfeito."}),
        ("adapt", {"u1": r"{\pos(100,200)Texto sem fechar"}),
    ]
    finding = Finding(unit_id="u1", check="ass_syntax", message="chaves desbalanceadas", severity="error")
    blamed = attribute_blame("u1", finding, history)
    assert blamed == "adapt"


def test_attribute_blame_markers_broken_with_sources() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto ⟦1⟧ perfeito."}),
        ("review_meaning", {"u1": "Texto perfeito sem marcador."}),  # marcador sumiu
        ("colloquial", {"u1": "Texto perfeito sem marcador."}),
    ]
    sources = {"u1": LineSource(source="Source ⟦1⟧ text.", line_type="dialogue", style="", duration_ms=2000)}
    finding = Finding(unit_id="u1", check="markers", message="marcadores divergentes", severity="error")
    blamed = attribute_blame("u1", finding, history, sources=sources)
    assert blamed == "review_meaning"


def test_attribute_blame_check_aliases() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto ⟦1⟧ correto."}),
        ("review_meaning", {"u1": "Texto corrompido."}),
    ]
    sources = {"u1": "Source ⟦1⟧."}
    finding = Finding(unit_id="u1", check="markers_broken", message="tag perdida", severity="error")
    blamed = attribute_blame("u1", finding, history, sources=sources)
    assert blamed == "review_meaning"

    # Teste para alias glossary_violation
    env = CheckEnv(glossary=[GlossaryEntry(term="Blade", translation="Lâmina")])
    history_glossary = [
        ("translate_dialogue", {"u1": "A Lâmina afiada."}),
        ("colloquial", {"u1": "A Espada afiada."}),  # violou glossário
    ]
    finding_glossary = Finding(unit_id="u1", check="glossary_violation", message="termo incorreto", severity="warn")
    blamed_glossary = attribute_blame("u1", finding_glossary, history_glossary, env=env, sources={"u1": "The Blade."})
    assert blamed_glossary == "colloquial"


def test_attribute_blame_empty_history_defaults_to_redistribute() -> None:
    finding = Finding(unit_id="u1", check="prompt_leak", message="vazamento", severity="error")
    blamed = attribute_blame("u1", finding, [])
    assert blamed == "redistribute_sentences"


def test_attribute_blame_unit_absent_in_some_stages() -> None:
    history = [
        ("translate_dialogue", {"u1": "Texto perfeito.", "u2": "Outro texto."}),
        ("review_meaning", {"u2": "Outro texto modificado."}),  # u1 não tocado
        ("colloquial", {"u1": "máx. 10 Texto perfeito."}),  # u1 modificado aqui com leak
    ]
    finding = Finding(unit_id="u1", check="prompt_leak", message="vazamento", severity="error")
    blamed = attribute_blame("u1", finding, history)
    assert blamed == "colloquial"
