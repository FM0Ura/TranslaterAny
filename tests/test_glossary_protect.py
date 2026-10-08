"""Proteção determinística de termos do glossário: placeholder antes do modelo, forma canônica depois."""

from translaterany.llm.client import LLMClient, LLMResponse
from translaterany.memory.models import GlossaryEntry
from translaterany.pipeline.stage_metrics import StageMetrics
from translaterany.subtitles.chunking import DialogueLine
from translaterany.subtitles.glossary_protect import GlossaryProtector
from translaterany.subtitles.translator import DialogueBatchTranslator, TranslationBatch, TranslationItem

WIDGET = GlossaryEntry(term="widget maker", translation="fabricante de engenhocas", aliases=["widget machine"])
SHORT = GlossaryEntry(term="widget", translation="engenhoca")
KEPT = GlossaryEntry(term="Zorblax", translation="Zorblax", keep_original=True)
SAME = GlossaryEntry(term="Quux", translation="Quux", keep_original=True)


def test_round_trip_restores_canonical_form() -> None:
    protector = GlossaryProtector([WIDGET])
    protected = protector.protect("Where is the widget maker?")
    assert protected.text == "Where is the ⟦G1⟧?"
    assert protected.canonicals == ["fabricante de engenhocas"]
    restored, ok = protector.restore("Cadê o ⟦G1⟧?", protected.canonicals)
    assert (restored, ok) == ("Cadê o fabricante de engenhocas?", True)


def test_alias_is_protected_and_case_insensitive() -> None:
    protector = GlossaryProtector([WIDGET])
    protected = protector.protect("The WIDGET MACHINE broke.")
    assert protected.text == "The ⟦G1⟧ broke."
    assert protected.canonicals == ["fabricante de engenhocas"]


def test_overlapping_terms_longest_match_wins_without_overlap() -> None:
    protector = GlossaryProtector([SHORT, WIDGET])  # a ordem da lista não importa
    protected = protector.protect("The widget maker and the widget.")
    assert protected.text == "The ⟦G1⟧ and the ⟦G2⟧."
    assert protected.canonicals == ["fabricante de engenhocas", "engenhoca"]


def test_word_boundaries_are_respected() -> None:
    protector = GlossaryProtector([SHORT])
    protected = protector.protect("Widgets and widgetry.")
    assert protected.text == "Widgets and widgetry."
    assert protected.canonicals == []


def test_keep_original_uses_term_and_skips_when_nothing_to_enforce() -> None:
    protector = GlossaryProtector([KEPT, SAME])
    protected = protector.protect("zorblax met Quux.")
    assert protected.text == "⟦G1⟧ met Quux."  # Quux já está na forma canônica: o modelo o mantém
    assert protected.canonicals == ["Zorblax"]


def test_sentence_start_is_capitalized_and_midsentence_is_not() -> None:
    protector = GlossaryProtector([SHORT])
    canon = ["engenhoca"]
    assert protector.restore("⟦G1⟧ quebrou.", canon)[0] == "Engenhoca quebrou."
    assert protector.restore("- ⟦G1⟧ quebrou.", canon)[0] == "- Engenhoca quebrou."
    assert protector.restore("¿⟦G1⟧?", canon)[0] == "¿Engenhoca?"
    assert protector.restore("⟦1⟧⟦G1⟧ quebrou.", canon)[0] == "⟦1⟧Engenhoca quebrou."
    assert protector.restore("Parou. ⟦G1⟧ quebrou.", canon)[0] == "Parou. Engenhoca quebrou."
    assert protector.restore("A ⟦G1⟧ quebrou.", canon)[0] == "A engenhoca quebrou."
    assert protector.restore("Bem... ⟦G1⟧ quebrou.", canon)[0] == "Bem... engenhoca quebrou."


def test_lost_placeholder_is_reported() -> None:
    protector = GlossaryProtector([WIDGET])
    restored, ok = protector.restore("Cadê o fabricante?", ["fabricante de engenhocas"])
    assert (restored, ok) == ("Cadê o fabricante?", False)


def test_duplicated_placeholder_keeps_first_and_reports() -> None:
    protector = GlossaryProtector([WIDGET])
    restored, ok = protector.restore("O ⟦G1⟧ e o ⟦G1⟧.", ["fabricante de engenhocas"])
    assert ok is False
    assert restored.count("fabricante de engenhocas") == 1
    assert "⟦" not in restored


def test_unknown_placeholder_is_stripped() -> None:
    protector = GlossaryProtector([WIDGET])
    restored, ok = protector.restore("O ⟦G2⟧ quebrou.", ["fabricante de engenhocas"])
    assert ok is False and "⟦" not in restored


def test_tolerates_spacing_and_case_mangling() -> None:
    protector = GlossaryProtector([WIDGET])
    restored, ok = protector.restore("O ⟦ g1 ⟧ quebrou.", ["fabricante de engenhocas"])
    assert (restored, ok) == ("O fabricante de engenhocas quebrou.", True)


class RecordingLLM(LLMClient):
    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[str] = []

    def generate(self, request):
        self.prompts.append(request.prompt)
        return LLMResponse(
            output=TranslationBatch(items=[TranslationItem(id="1", text=self.reply(request.prompt))]), model_id="t"
        )


def test_translator_sends_placeholder_and_restores_canonical_term() -> None:
    llm = RecordingLLM(lambda prompt: "Cadê o ⟦G1⟧?")
    translator = DialogueBatchTranslator(client=llm, glossary=[WIDGET])
    result = translator.translate_lines([DialogueLine(id="1", text="Where is the widget maker?")])
    assert result == {"1": "Cadê o fabricante de engenhocas?"}
    assert "widget maker" not in llm.prompts[0]
    assert "[1] Where is the ⟦G1⟧?" in llm.prompts[0]
    assert "⟦G1⟧" in llm.prompts[0].split("[FALAS A TRADUZIR]")[0]  # instrução para manter os marcadores


def test_translator_lost_placeholder_is_counted_and_does_not_crash() -> None:
    metrics = StageMetrics()
    llm = RecordingLLM(lambda prompt: "Cadê o fabricante?")
    translator = DialogueBatchTranslator(client=llm, glossary=[WIDGET], metrics=metrics)
    result = translator.translate_lines([DialogueLine(id="1", text="Where is the widget maker?")])
    assert result == {"1": "Cadê o fabricante?"}  # o portão do glossário trata a violação restante
    assert metrics.counters["glossary_markers_lost"] == 1


def test_translator_without_glossary_is_unchanged() -> None:
    llm = RecordingLLM(lambda prompt: "Olá")
    translator = DialogueBatchTranslator(client=llm)
    assert translator.translate_lines([DialogueLine(id="1", text="Hello")]) == {"1": "Olá"}
    assert "⟦G" not in llm.prompts[0]


def test_translate_signs_protects_glossary_terms() -> None:
    from translaterany.llm.fake import FakeLLM
    from translaterany.subtitles.classify import UnitClass
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit
    from translaterany.subtitles.signs import translate_signs

    unit = Unit(id="s1", style="Sign", text="Widget Maker Lab", markers=0, events=[0])
    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=[unit])
    classes = {"s1": UnitClass(type="sign", uncertain=False, rule="")}
    fake = FakeLLM(responses={"⟦G1⟧ Lab": "Laboratório de ⟦G1⟧"})

    res = translate_signs(doc, classes, client=fake, glossary=[WIDGET])
    assert res.texts["s1"] == "Laboratório de fabricante de engenhocas"
    assert "Widget Maker" not in fake.calls[0].prompt


def test_short_term_inside_longer_canonical_entry_is_not_protected() -> None:
    longer = GlossaryEntry(term="Zorb Gate", translation="Zorb Gate", keep_original=True, aliases=["Zorb;Gate"])
    short = GlossaryEntry(term="Gate", translation="Portal")
    protected = GlossaryProtector([short, longer]).protect("Is it the choice of Zorb Gate?")
    assert protected.text == "Is it the choice of Zorb Gate?"
    assert protected.canonicals == []
