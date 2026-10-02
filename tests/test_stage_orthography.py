# tests/test_stage_orthography.py
"""Testes da etapa orthography."""

import httpx
from translaterany.stages.orthography import OrthographyStage


def test_orthography_stage_attributes() -> None:
    stage = OrthographyStage()
    assert stage.name == "orthography"
    assert stage.produces_dialogue is True
    assert stage.default_dialogue_input == "adapt"


def test_orthography_stage_graceful_degradation_when_offline() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("Connection refused")

    stage = OrthographyStage()
    stage.client = stage.make_client(transport=httpx.MockTransport(handler))

    outcome_texts, offline, applied = stage.process_texts({"u1": "Texto normal"}, exemptions=set())
    assert outcome_texts["u1"] == "Texto normal"
    assert offline is True
    assert applied == 0


def test_orthography_stage_applies_valid_edits() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Erro de digitação",
                        "offset": 0,
                        "length": 4,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Você"}],
                    }
                ]
            },
        )

    stage = OrthographyStage()
    stage.client = stage.make_client(transport=httpx.MockTransport(handler))

    outcome_texts, offline, applied = stage.process_texts({"u1": "Voce foi lá?"}, exemptions=set())
    assert outcome_texts["u1"] == "Você foi lá?"
    assert offline is False
    assert applied == 1


def test_orthography_stage_rejects_corrupted_markers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Corrupção",
                        "offset": 0,
                        "length": 3,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "[0]"}],
                    }
                ]
            },
        )

    stage = OrthographyStage()
    stage.client = stage.make_client(transport=httpx.MockTransport(handler))
    outcome_texts, offline, applied = stage.process_texts({"u1": "⟦0⟧ Olá"}, exemptions=set())
    assert outcome_texts["u1"] == "⟦0⟧ Olá"
    assert applied == 0


def test_orthography_stage_with_glossary_and_character_memory(tmp_path) -> None:
    from pathlib import Path
    from translaterany.memory.models import CharacterEntry, GlossaryEntry
    from translaterany.memory.store import MemoryStore
    from translaterany.pipeline.artifacts import ArtifactStore, InputReader, OutputWriter
    from translaterany.pipeline.manifest import ManifestSet
    from translaterany.pipeline.stage import StageContext
    from translaterany.pipeline.stage_metrics import StageMetrics
    from translaterany.pipeline.units import Episode, Series
    from translaterany.subtitles.classify import Classification
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc
    from translaterany.subtitles.texts import UnitTexts

    store = ArtifactStore(tmp_path / "data")
    series = Series(key="Show (2020)", name="Show")
    episode = Episode(series=series, key="S01E01", number=1, season=1)

    mem = MemoryStore(store.series_dir(series.key) / "memory")
    mem.save_glossary({"g1": GlossaryEntry(term="Apple", translation="Maçã")})
    mem.save_characters([CharacterEntry(name="Alice")])

    class FakeInputs:
        def json(self, name, model):
            if name == "adapt":
                return UnitTexts(texts={"u1": "Olá Alice, coma uma Apple."})
            if name == "normalize":
                return NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=[])
            if name == "classify":
                return Classification.model_construct(main_style="Default", units={}, counts={}, scenes=[])
            return None

    class FakeOutput:
        def __init__(self):
            self.saved = None

        def json(self, obj):
            self.saved = obj

    from unittest.mock import MagicMock

    output = FakeOutput()
    ctx = MagicMock()
    ctx.series = Series(key="Show (2020)", name="Show")
    ctx.store = store
    ctx.inputs = FakeInputs()
    ctx.output = output

    stage = OrthographyStage()
    # Não deve lançar AttributeError: 'GlossaryEntry' object has no attribute 'target'
    stage.run(ctx)
    assert output.saved is not None
    assert output.saved.texts["u1"] == "Olá Alice, coma uma Apple."


def test_orthography_stage_protects_multiword_names_and_honorifics(tmp_path) -> None:
    from translaterany.memory.models import CharacterEntry, GlossaryEntry
    from translaterany.memory.store import MemoryStore
    from translaterany.pipeline.artifacts import ArtifactStore
    from translaterany.pipeline.units import Episode, Series
    from translaterany.subtitles.classify import Classification
    from translaterany.subtitles.normalize import Encoding, NormalizedDoc
    from translaterany.subtitles.texts import UnitTexts
    from unittest.mock import MagicMock

    store = ArtifactStore(tmp_path / "data")
    series = Series(key="DxD (2012)", name="DxD")

    mem = MemoryStore(store.series_dir(series.key) / "memory")
    mem.save_glossary({"g1": GlossaryEntry(term="Hyoudou Issei", translation="Hyoudou Issei")})
    mem.save_characters([CharacterEntry(name="Hyoudou Issei")])

    class FakeInputs:
        def json(self, name, model):
            if name == "adapt":
                return UnitTexts(texts={"u1": "Concordo com o Hyoudou Issei-kun!"})
            if name == "normalize":
                return NormalizedDoc(encoding=Encoding(bom=False, newline="\n"), format=[], events=[], units=[])
            if name == "classify":
                return Classification.model_construct(main_style="Default", units={}, counts={}, scenes=[])
            return None

    class FakeOutput:
        def __init__(self):
            self.saved = None

        def json(self, obj):
            self.saved = obj

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "matches": [
                    {
                        "message": "Palavra desconhecida",
                        "offset": 15,
                        "length": 7,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "Violou"}],
                    },
                    {
                        "message": "Palavra desconhecida",
                        "offset": 29,
                        "length": 3,
                        "rule": {"category": {"id": "TYPOS"}},
                        "replacements": [{"value": "cum"}],
                    },
                ]
            },
        )

    output = FakeOutput()
    ctx = MagicMock()
    ctx.series = series
    ctx.store = store
    ctx.inputs = FakeInputs()
    ctx.output = output
    ctx.app = MagicMock()
    ctx.app.checks = None

    stage = OrthographyStage()
    stage.client = stage.make_client(transport=httpx.MockTransport(handler))
    stage.run(ctx)

    assert output.saved is not None
    # "Hyoudou" e "-kun" JAMAIS podem ser substituídos por "Violou" ou "-cum"
    assert output.saved.texts["u1"] == "Concordo com o Hyoudou Issei-kun!"

