# tests/stages/test_prompts_multilingual.py
from unittest.mock import MagicMock

from translaterany.languages.registry import LanguageRegistry
from translaterany.stages.review_meaning import ReviewMeaningStage
from translaterany.subtitles.translator import render_system_instructions


def test_system_instructions_dynamic_languages() -> None:
    ja = LanguageRegistry.resolve("ja")
    es = LanguageRegistry.resolve("es")
    instructions = render_system_instructions(source=ja, target=es)
    assert "japonês para espanhol" in instructions.lower()
    assert "fansubs de alta qualidade em espanhol" in instructions.lower()


def test_review_meaning_prompt_dynamic_languages() -> None:
    ja = LanguageRegistry.resolve("ja")
    es = LanguageRegistry.resolve("es")
    stage = ReviewMeaningStage()
    ctx = MagicMock(
        source_language=ja,
        target_language=es,
    )
    instr = stage.get_instructions(ctx)
    assert "japonês -> espanhol" in instr.lower()
    assert "espanhol" in instr.lower()
