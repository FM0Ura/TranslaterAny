from translaterany.llm.fake import FakeLLM
from translaterany.subtitles.classify import UnitClass
from translaterany.subtitles.normalize import Encoding, NormalizedDoc, Unit
from translaterany.subtitles.signs import translate_signs
from translaterany.subtitles.songs import translate_songs


def test_translate_signs_conciseness():
    unit = Unit(id="s1", style="Sign", text="Student Council Room", markers=0, events=[0])
    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=[unit])
    classes = {"s1": UnitClass(type="sign", uncertain=False, rule="")}
    fake_llm = FakeLLM(responses={"Student Council Room": "Sala do Conselho Estudantil"})

    res = translate_signs(doc, classes, tm_resolved={}, client=fake_llm)
    assert res.texts["s1"] == "Sala do Conselho Estudantil"


def test_translate_songs_preserves_karaoke_and_romaji():
    u_rom = Unit(id="m1", style="Romaji", text=r"{\k20}demo {\k30}zutto", markers=0, events=[0])
    u_eng = Unit(id="m2", style="Song_EN", text="Brave shine in the dark", markers=0, events=[1])

    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=[u_rom, u_eng])
    classes = {
        "m1": UnitClass(type="karaoke", uncertain=False, rule=""),
        "m2": UnitClass(type="song", uncertain=False, rule=""),
    }
    fake_llm = FakeLLM(responses={"Brave shine in the dark": "Brilho corajoso na escuridão"})

    res = translate_songs(doc, classes, tm_resolved={}, client=fake_llm)
    assert "m1" not in res.texts
    assert res.texts["m2"] == "Brilho corajoso na escuridão"


def test_stages_translate_signs_and_songs():
    from types import SimpleNamespace
    from translaterany.stages.translate_signs import TranslateSignsStage
    from translaterany.stages.translate_songs import TranslateSongsStage
    from translaterany.stages.translation_memory import TranslationMemoryArtifact
    from translaterany.subtitles.classify import Classification

    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[
            Unit(id="s1", style="Sign", text="Classroom 1-A", markers=0, events=[0]),
            Unit(id="s2", style="Sign", text="Teacher's Lounge", markers=0, events=[1]),
            Unit(id="m1", style="Song", text="Fly high to the sky", markers=0, events=[2]),
        ],
    )
    classification = Classification(
        main_style="Default",
        units={
            "s1": UnitClass(type="sign", uncertain=False, rule=""),
            "s2": UnitClass(type="sign", uncertain=False, rule=""),
            "m1": UnitClass(type="song", uncertain=False, rule=""),
        },
        counts={},
        scenes=[],
    )
    # s1 já resolvida pela TM
    tm_art = TranslationMemoryArtifact(
        matched_units={"s1": "Sala de Aula 1-A"},
        matched_keys=["classroom 1-a"],
    )

    class MockInputs:
        def json(self, name: str, model: type):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            if name == "translation_memory":
                return tm_art
            raise ValueError(name)

    captured_signs = None
    captured_songs = None

    class MockSignsOutput:
        def json(self, obj):
            nonlocal captured_signs
            captured_signs = obj

    class MockSongsOutput:
        def json(self, obj):
            nonlocal captured_songs
            captured_songs = obj

    fake_signs_llm = FakeLLM(responses={"Teacher's Lounge": "Sala dos Professores"})
    signs_stage = TranslateSignsStage(client=fake_signs_llm)
    signs_ctx = SimpleNamespace(inputs=MockInputs(), output=MockSignsOutput(), llm=fake_signs_llm)
    signs_stage.run(signs_ctx)  # type: ignore[arg-type]

    assert captured_signs is not None
    assert captured_signs.texts["s1"] == "Sala de Aula 1-A"
    assert captured_signs.texts["s2"] == "Sala dos Professores"

    fake_songs_llm = FakeLLM(responses={"Fly high to the sky": "Voe alto para o céu"})
    from translaterany.stages.translate_songs import TranslateSongsOptions

    skipping = TranslateSongsStage(client=fake_songs_llm)  # padrão: músicas ficam no original
    skip_out = MockSongsOutput()
    skipping.run(SimpleNamespace(inputs=MockInputs(), output=skip_out, llm=fake_songs_llm))  # type: ignore[arg-type]
    assert captured_songs is not None and captured_songs.texts == {}
    assert fake_songs_llm.calls == []
    captured_songs = None

    songs_stage = TranslateSongsStage(client=fake_songs_llm, options=TranslateSongsOptions(translate=True))
    songs_ctx = SimpleNamespace(inputs=MockInputs(), output=MockSongsOutput(), llm=fake_songs_llm)
    songs_stage.run(songs_ctx)  # type: ignore[arg-type]

    assert captured_songs is not None
    assert captured_songs.texts["m1"] == "Voe alto para o céu"



def _song_doc(rows: list[tuple[str, str, str, str]]):
    """rows: (id, style, text, tipo). Devolve (doc, classes)."""
    units = [Unit(id=i, style=st, text=tx, markers=0, events=[n]) for n, (i, st, tx, _t) in enumerate(rows)]
    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=units)
    classes = {i: UnitClass(type=t, uncertain=False, rule="") for i, _st, _tx, t in rows}
    return doc, classes


def test_lyric_translation_style_is_translated_even_when_songs_are_skipped():
    doc, classes = _song_doc(
        [
            ("u1", "op kara", "kimi no sono egao mamoritai no sa", "song"),
            ("u2", "op trans", "and protect your smile", "song"),
            ("u3", "Song", "Fly high to the sky", "song"),
        ]
    )
    fake = FakeLLM(responses={"and protect your smile": "e proteger o seu sorriso"})
    res = translate_songs(doc, classes, client=fake, translate_all=False)
    assert res.texts == {"u2": "e proteger o seu sorriso"}  # karaokê e música avulsa intactos
    assert all("kimi no sono" not in c.prompt and "Fly high" not in c.prompt for c in fake.calls)


def test_translation_style_without_karaoke_companion_follows_translate_option():
    doc, classes = _song_doc([("u1", "Song trans", "Fly high to the sky", "song")])
    fake = FakeLLM(responses={"Fly high to the sky": "Voe alto para o céu"})
    assert translate_songs(doc, classes, client=fake, translate_all=False).texts == {}
    assert fake.calls == []


def test_translate_all_leaves_karaoke_style_alone_when_translation_line_exists():
    doc, classes = _song_doc(
        [
            ("u1", "op kara", "kimi no sono egao mamoritai no sa", "song"),
            ("u2", "op trans", "and protect your smile", "song"),
        ]
    )
    fake = FakeLLM(responses={"and protect your smile": "e proteger o seu sorriso"})
    res = translate_songs(doc, classes, client=fake, translate_all=True)
    assert res.texts == {"u2": "e proteger o seu sorriso"}


_BILINGUAL = "Kimi to taiyo ga shinda hi\\NThe day you and the sun died"


def _bilingual_doc():
    doc = NormalizedDoc(
        encoding=Encoding(bom=False, newline="\n"),
        format=[],
        events=[],
        units=[Unit(id="u1", style="Default", text=_BILINGUAL, markers=0, events=[0])],
    )
    classes = {"u1": UnitClass(type="song", uncertain=False, rule="letra bilíngue romaji/inglês")}
    return doc, classes


def test_bilingual_lyric_keeps_romaji_and_translates_only_the_gloss():
    doc, classes = _bilingual_doc()
    fake = FakeLLM(responses={"The day you and the sun died": "O dia em que você e o sol morreram"})
    res = translate_songs(doc, classes, client=fake, translate_all=False)
    assert res.texts == {"u1": "Kimi to taiyo ga shinda hi\\NO dia em que você e o sol morreram"}
    assert all("Kimi to taiyo" not in c.prompt for c in fake.calls)  # o romaji nunca vai ao modelo


def test_bilingual_gloss_drop_and_keep():
    doc, classes = _bilingual_doc()
    fake = FakeLLM()
    dropped = translate_songs(doc, classes, client=fake, translate_all=False, bilingual_gloss="drop")
    assert dropped.texts == {"u1": "Kimi to taiyo ga shinda hi"}
    kept = translate_songs(doc, classes, client=fake, translate_all=False, bilingual_gloss="keep")
    assert kept.texts == {}
    assert fake.calls == []


def test_bilingual_gloss_falls_back_to_original_when_markers_are_lost():
    unit = Unit(
        id="u1",
        style="Default",
        text="Kimi to taiyo ga shinda hi\\N⟦1⟧The day you and the sun died⟦2⟧",
        markers=2,
        events=[0],
    )
    doc = NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=[unit])
    classes = {"u1": UnitClass(type="song", uncertain=False, rule="letra bilíngue romaji/inglês")}
    fake = FakeLLM(responses={"The day you and the sun died": "O dia em que você e o sol morreram"})
    res = translate_songs(doc, classes, client=fake, translate_all=False)
    assert res.texts["u1"] == "Kimi to taiyo ga shinda hi\\N⟦1⟧The day you and the sun died⟦2⟧"


def test_stage_translates_lyric_translation_line_with_default_options():
    from types import SimpleNamespace

    from translaterany.stages.translate_songs import TranslateSongsStage
    from translaterany.subtitles.classify import Classification

    doc, classes = _song_doc(
        [
            ("u1", "op kara", "kimi no sono egao mamoritai no sa", "song"),
            ("u2", "op trans", "and protect your smile", "song"),
        ]
    )
    classification = Classification(main_style="Default", units=classes, counts={}, scenes=[])
    captured = {}

    class Inputs:
        def json(self, name: str, model: type):
            if name == "normalize":
                return doc
            if name == "classify":
                return classification
            raise ValueError(name)

    class Output:
        def json(self, obj):
            captured["texts"] = obj.texts

    fake = FakeLLM(responses={"and protect your smile": "e proteger o seu sorriso"})
    stage = TranslateSongsStage(client=fake)  # translate=False (padrão)
    stage.run(SimpleNamespace(inputs=Inputs(), output=Output(), llm=fake))  # type: ignore[arg-type]
    assert captured["texts"] == {"u2": "e proteger o seu sorriso"}
