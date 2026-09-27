from translaterany.memory.tm import TMEntry, TMEntrySource, TranslationMemoryDoc, TranslationMemoryStore
from translaterany.subtitles.classify import Classification, UnitClass
from translaterany.subtitles.normalize import Encoding, EventInfo, NormalizedDoc, Unit


def test_tm_store_save_and_load(tmp_path):
    tm_file = tmp_path / "translation_memory.yaml"
    store = TranslationMemoryStore(tm_file)
    doc = TranslationMemoryDoc(
        entries={
            "brave shine": TMEntry(
                clean_text="Brave Shine",
                translation="Brilho Corajoso",
                category="song",
                source=TMEntrySource.AUTO,
                occurrences=1,
                episodes=["S01E01"],
            )
        }
    )
    store.save(doc)

    loaded = store.load()
    assert "brave shine" in loaded.entries
    assert loaded.entries["brave shine"].translation == "Brilho Corajoso"


def test_tm_precedence_user_over_auto(tmp_path):
    tm_file = tmp_path / "translation_memory.yaml"
    store = TranslationMemoryStore(tm_file)
    doc = TranslationMemoryDoc(
        entries={
            "op song": TMEntry(
                clean_text="OP Song",
                translation="Tradução Manual do Usuário",
                category="song",
                source=TMEntrySource.USER,
            )
        }
    )
    store.save(doc)

    store.record_translation("OP Song", "Tradução Automática Nova", "song", "S01E02")
    loaded = store.load()
    assert loaded.entries["op song"].translation == "Tradução Manual do Usuário"
    assert loaded.entries["op song"].source == TMEntrySource.USER
    assert loaded.entries["op song"].occurrences == 2


def test_tm_lookup_and_match(tmp_path):
    tm_file = tmp_path / "translation_memory.yaml"
    store = TranslationMemoryStore(tm_file)
    doc = TranslationMemoryDoc(
        entries={
            "chapter 1": TMEntry(clean_text="Chapter 1", translation="Capítulo 1", category="sign"),
            "brave shine": TMEntry(clean_text="Brave Shine", translation="Brilho Corajoso", category="song"),
            "yes": TMEntry(clean_text="Yes", translation="Sim", category="dialogue", source=TMEntrySource.AUTO),
            "i am the hope of the universe": TMEntry(
                clean_text="I am the hope of the universe",
                translation="Eu sou a esperança do universo",
                category="dialogue",
                source=TMEntrySource.AUTO,
            ),
        }
    )
    store.save(doc)

    # Song e Sign casam imediatamente
    assert store.lookup("Chapter 1", "sign") == "Capítulo 1"
    assert store.lookup("Brave Shine", "song") == "Brilho Corajoso"

    # Diálogo curto automático NÃO casa (proteção contra contaminação de contexto)
    assert store.lookup("Yes", "dialogue", min_dialogue_chars=15) is None

    # Diálogo longo automático casa
    assert store.lookup("I am the hope of the universe", "dialogue", min_dialogue_chars=15) == "Eu sou a esperança do universo"
