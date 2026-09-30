from translaterany.subtitles.merge import CompositeUnit
from translaterany.subtitles.redistribute import redistribute_composite_unit


def test_redistribute_splits_at_natural_comma():
    # Frase composta: dur1 = 2000ms, dur2 = 2000ms (50% / 50%)
    comp = CompositeUnit(
        composite_id="u1+u2",
        unit_ids=["u1", "u2"],
        durations_ms=[2000, 2000],
        clean_text="Even if you say that, I cannot believe it.",
        text_with_markers="Even if you say that, I cannot believe it.",
    )
    translated_text = "Mesmo que você diga isso, não posso acreditar."
    split_texts = redistribute_composite_unit(comp, translated_text)
    assert len(split_texts) == 2
    assert split_texts["u1"] == "Mesmo que você diga isso,"
    assert split_texts["u2"] == "não posso acreditar."


def test_redistribute_preserves_inline_markers():
    comp = CompositeUnit(
        composite_id="u1+u2",
        unit_ids=["u1", "u2"],
        durations_ms=[2000, 2000],
        clean_text="Word1 Word2",
        text_with_markers="⟦1⟧Word1⟦2⟧ ⟦3⟧Word2⟦4⟧",
    )
    # Marcadores ⟦1⟧ e ⟦2⟧ na u1 e ⟦3⟧ e ⟦4⟧ na u2
    translated_text = "⟦1⟧Palavra1⟦2⟧ ⟦3⟧Palavra2⟦4⟧"
    split_texts = redistribute_composite_unit(comp, translated_text)
    assert "⟦1⟧" in split_texts["u1"]
    assert "⟦2⟧" in split_texts["u1"]
    assert "⟦3⟧" in split_texts["u2"]
    assert "⟦4⟧" in split_texts["u2"]


def test_stage_redistribute_sentences_consolidation_and_tm_autofeed(tmp_path):
    from types import SimpleNamespace
    from translaterany.memory.tm import TranslationMemoryStore
    from translaterany.pipeline.artifacts import ArtifactStore
    from translaterany.stages.redistribute_sentences import RedistributeSentencesStage
    from translaterany.stages.translation_memory import TranslationMemoryArtifact
    from translaterany.subtitles.classify import Classification, UnitClass
    from translaterany.subtitles.merge import CompositeUnit, MergedUnitsDoc
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit
    from translaterany.subtitles.texts import UnitTexts

    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[
            Unit(id="u1", style="Default", text="Even if you say that,", markers=0, events=[0]),
            Unit(id="u2", style="Default", text="I cannot believe it.", markers=0, events=[1]),
            Unit(id="s1", style="Sign", text="Library", markers=0, events=[2]),
            Unit(id="m1", style="Song", text="Fly away", markers=0, events=[3]),
        ],
    )
    classification = Classification(
        main_style="Default",
        units={
            "u1": UnitClass(type="dialogue", uncertain=False, rule=""),
            "u2": UnitClass(type="dialogue", uncertain=False, rule=""),
            "s1": UnitClass(type="sign", uncertain=False, rule=""),
            "m1": UnitClass(type="song", uncertain=False, rule=""),
        },
        counts={},
        scenes=[],
    )
    merged_doc = MergedUnitsDoc(
        units=[
            CompositeUnit(
                composite_id="u1+u2",
                unit_ids=["u1", "u2"],
                durations_ms=[2000, 2000],
                clean_text="Even if you say that, I cannot believe it.",
                text_with_markers="Even if you say that, I cannot believe it.",
            )
        ]
    )
    tm_art = TranslationMemoryArtifact(matched_units={}, matched_keys=[])
    dialogue_texts = UnitTexts(texts={"u1+u2": "Mesmo que você diga isso, não posso acreditar."})
    signs_texts = UnitTexts(texts={"s1": "Biblioteca"})
    songs_texts = UnitTexts(texts={"m1": "Voe para longe"})

    class MockInputs:
        def json(self, name: str, model: type):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name == "translation_memory":
                return tm_art
            if name == "merge_sentences":
                return merged_doc
            if name == "translate_dialogue":
                return dialogue_texts
            if name == "translate_signs":
                return signs_texts
            if name == "translate_songs":
                return songs_texts
            raise ValueError(name)

    captured_output = None

    class MockOutput:
        def json(self, obj):
            nonlocal captured_output
            captured_output = obj

    store = ArtifactStore(tmp_path)
    series_obj = SimpleNamespace(key="test-series")
    ep_obj = SimpleNamespace(key="S01E01")

    stage = RedistributeSentencesStage()
    ctx = SimpleNamespace(
        inputs=MockInputs(),
        output=MockOutput(),
        store=store,
        series=series_obj,
        episode=ep_obj,
    )
    stage.run(ctx)  # type: ignore[arg-type]

    assert captured_output is not None
    # Verifica que u1+u2 foi redistribuído para u1 e u2
    assert captured_output.texts["u1"] == "Mesmo que você diga isso,"
    assert captured_output.texts["u2"] == "não posso acreditar."
    assert captured_output.texts["s1"] == "Biblioteca"
    assert captured_output.texts["m1"] == "Voe para longe"

    # Verifica auto-feed da TM da série
    tm_file = store.series_dir(series_obj.key) / "memory" / "translation_memory.yaml"
    assert tm_file.exists()
    tm_store = TranslationMemoryStore(tm_file)
    tm_doc = tm_store.load()
    assert "library" in tm_doc.entries
    assert tm_doc.entries["library"].translation == "Biblioteca"
    assert "fly away" in tm_doc.entries
    assert tm_doc.entries["fly away"].translation == "Voe para longe"

