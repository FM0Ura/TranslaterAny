from pathlib import Path

from translaterany.llm.fake import FakeLLM
from translaterany.pipeline.registry import REGISTRY
from translaterany.pipeline.stage import StageScope
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.subtitles.classify import ClassifiedUnit, ClassifiedUnitCollection


def test_translate_dialogue_preserves_inline_tags(tmp_path: Path) -> None:
    # Unidade com tags de formatação ASS
    unit = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text=r"{\an8}Hello {\b1}world{\b0}!",
        clean_text="Hello world!",
        prefix=r"{\an8}",
        suffix="",
        start_ms=1000,
        end_ms=2500,
        style="Default",
    )
    collection = ClassifiedUnitCollection(units=[unit])

    # FakeLLM devolvendo tradução simples
    fake_llm = FakeLLM(responses={"Hello world!": "Olá mundo!"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated_collection = stage.translate_collection(collection)
    res_unit = translated_collection.units[0]
    assert res_unit.clean_text == "Olá mundo!"
    assert r"{\an8}" in res_unit.raw_text
    assert res_unit.start_ms == 1000
    assert res_unit.end_ms == 2500


def test_translate_dialogue_ignores_non_dialogue_units() -> None:
    u_dialogue = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text="Hello",
        clean_text="Hello",
        prefix="",
        suffix="",
        start_ms=1000,
        end_ms=2000,
        style="Default",
    )
    u_sign = ClassifiedUnit(
        id="u2",
        line_type="sign",
        raw_text="Tokyo Station",
        clean_text="Tokyo Station",
        prefix="",
        suffix="",
        start_ms=1000,
        end_ms=2000,
        style="Sign",
    )
    collection = ClassifiedUnitCollection(units=[u_dialogue, u_sign])

    fake_llm = FakeLLM(responses={"Hello": "Olá"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated = stage.translate_collection(collection)
    assert translated.units[0].clean_text == "Olá"
    assert translated.units[1].clean_text == "Tokyo Station"
    assert translated.units[1].line_type == "sign"


def test_translate_dialogue_preserves_metadata() -> None:
    unit = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text="Good morning",
        clean_text="Good morning",
        prefix="",
        suffix="",
        start_ms=500,
        end_ms=1500,
        style="MainStyle",
        actor="Alice",
        layer=2,
    )
    collection = ClassifiedUnitCollection(units=[unit])
    fake_llm = FakeLLM(responses={"Good morning": "Bom dia"})
    stage = StageTranslateDialogue(client=fake_llm)

    translated = stage.translate_collection(collection)
    res = translated.units[0]
    assert res.clean_text == "Bom dia"
    assert res.actor == "Alice"
    assert res.layer == 2
    assert res.style == "MainStyle"
    assert res.start_ms == 500
    assert res.end_ms == 1500


def test_translate_dialogue_stage_metadata() -> None:
    assert StageTranslateDialogue.name == "translate_dialogue"
    assert StageTranslateDialogue.translates is True
    assert StageTranslateDialogue.scope in (StageScope.EPISODE, "episode")
    assert StageTranslateDialogue.enabled_by_default is True
    assert "translate_dialogue" in REGISTRY


def test_translate_dialogue_run_artifact(tmp_path: Path) -> None:
    classify_file = tmp_path / "classify.json"
    unit = ClassifiedUnit(
        id="u1",
        line_type="dialogue",
        raw_text="Hello world!",
        clean_text="Hello world!",
        prefix="",
        suffix="",
        start_ms=1000,
        end_ms=2500,
        style="Default",
    )
    collection = ClassifiedUnitCollection(units=[unit])
    classify_file.write_text(collection.model_dump_json(indent=2), encoding="utf-8")

    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()

    from types import SimpleNamespace

    ctx = SimpleNamespace(
        input_artifacts={"classify": classify_file},
        artifact_dir=artifact_dir,
        output=None,
    )

    fake_llm = FakeLLM(responses={"Hello world!": "Olá mundo!"})
    stage = StageTranslateDialogue(client=fake_llm)

    out_path = stage.run(ctx)  # type: ignore[arg-type]
    assert out_path == artifact_dir / "translated_units.json"
    assert out_path.exists()
    saved = ClassifiedUnitCollection.model_validate_json(out_path.read_text(encoding="utf-8"))
    assert saved.units[0].clean_text == "Olá mundo!"
