"""Divisão da tradução de uma frase composta de volta aos eventos (dados sintéticos)."""

import random
import re

from translaterany.subtitles.merge import CompositeUnit
from translaterany.subtitles.redistribute import redistribute_composite_unit


def _comp(n: int, durations: list[int] | None = None) -> CompositeUnit:
    ids = [f"u{i}" for i in range(1, n + 1)]
    return CompositeUnit(
        composite_id="+".join(ids),
        unit_ids=ids,
        durations_ms=durations or [2000] * n,
        clean_text="x",
        text_with_markers="x",
    )


def _parts(comp: CompositeUnit, text: str) -> list[str]:
    out = redistribute_composite_unit(comp, text)
    return [out[uid] for uid in comp.unit_ids]


def test_prefers_clause_boundary_over_mid_phrase_cut():
    # O corte proporcional cairia depois de "impacto"; a reticência é a fronteira certa
    comp = _comp(2, [3210, 4340])
    parts = _parts(comp, "Direto pro chão... O impacto da queda ia esmagar minha cabeça.")
    assert parts == ["Direto pro chão...", "O impacto da queda ia esmagar minha cabeça."]


def test_three_events_follow_the_clauses():
    comp = _comp(3, [4700, 2040, 4250])
    text = (
        "Vocês vão encontrar um jeito de voltar no tempo, ajudar e vê-lo, até construir "
        "a máquina do tempo... mas no fim, desistirão, porque não conseguirão ser honestos."
    )
    parts = _parts(comp, text)
    assert parts[0].endswith("vê-lo,")
    assert parts[1] == "até construir a máquina do tempo..."
    assert parts[2].startswith("mas no fim,")


def test_never_ends_event_on_dangling_function_word():
    comp = _comp(2, [1000, 1000])
    # sem pontuação: o corte proporcional cairia depois de "da"
    parts = _parts(comp, "Ele quebrou a janela da sala de jantar ontem")
    assert not re.search(r"\b(da|de|a|o|no|na|e|mas|que)$", parts[0])
    assert " ".join(parts) == "Ele quebrou a janela da sala de jantar ontem"


def test_uses_lines_when_model_kept_one_line_per_event():
    comp = _comp(3, [1000, 5000, 1000])
    text = "Primeira linha curta.\nSegunda linha mais longa do que a primeira.\nTerceira."
    assert _parts(comp, text) == [
        "Primeira linha curta.",
        "Segunda linha mais longa do que a primeira.",
        "Terceira.",
    ]


def test_literal_ass_breaks_are_not_leaked_into_parts():
    comp = _comp(2)
    parts = _parts(comp, "Uma frase inteira,\\Ne a outra metade.")
    assert parts == ["Uma frase inteira,", "e a outra metade."]


def test_markers_are_never_split():
    comp = _comp(2)
    parts = _parts(comp, "⟦1⟧Olha⟦2⟧ isso, ⟦3⟧agora mesmo⟦4⟧.")
    assert "".join(parts).count("⟦") == 4
    for p in parts:
        assert len(re.findall(r"⟦\d+⟧", p)) == p.count("⟦")


def test_fewer_words_than_events_never_drops_words():
    comp = _comp(4)
    parts = _parts(comp, "Só duas")
    assert " ".join(p for p in parts if p) == "Só duas"
    assert len(parts) == 4


def test_cps_budget_pushes_text_to_the_longer_event():
    # evento curto (500 ms) só comporta ~8 caracteres a 17 cps
    comp = _comp(2, [500, 6000])
    parts = _parts(comp, "Sim. Eu realmente não sei como isso aconteceu com a gente.")
    assert parts[0] == "Sim."


def test_property_concatenation_equals_original_modulo_whitespace():
    rng = random.Random(1234)
    vocab = ["casa", "de", "e", "mas", "que", "não", "sei", "vou", "o", "a", "tempo", "para",
             "ir", "agora", "porque", "ele", "disse", "ontem", "da", "no"]
    punct = ["", "", "", ",", ".", "...", "?", "!", ";", " —"]
    for _ in range(300):
        words = rng.randint(1, 40)
        text = ""
        for _w in range(words):
            text += rng.choice(vocab) + rng.choice(punct) + rng.choice([" ", " ", " ", "\n"])
        text = text.strip()
        n = rng.randint(1, 6)
        durs = [rng.randint(300, 9000) for _ in range(n)]
        comp = _comp(n, durs)
        parts = _parts(comp, text)
        assert len(parts) == n
        assert re.sub(r"\s+", "", "".join(parts)) == re.sub(r"\s+", "", text)
