"""Uso real: músicas puladas por padrão; legibilidade (quebra de linha e orçamento de caracteres)."""

from pathlib import Path

from translaterany.config.model import AppConfig
from translaterany.pipeline.registry import REGISTRY
from translaterany.stages.translate_dialogue import StageTranslateDialogue
from translaterany.stages.translate_songs import TranslateSongsOptions
from translaterany.subtitles.chunking import DialogueLine, format_batch_prompt
from translaterany.subtitles.linebreak import char_budget, flatten_breaks, wrap_line


def test_songs_are_skipped_by_default() -> None:
    assert TranslateSongsOptions().translate is False
    assert TranslateSongsOptions(translate=True).translate is True


def test_flatten_breaks_joins_lines() -> None:
    assert flatten_breaks("When the rain stopped,\\NI walked home alone.") == "When the rain stopped, I walked home alone."
    assert flatten_breaks("a \\N b\\nc") == "a b c"


def test_wrap_line_keeps_short_lines_on_one_line() -> None:
    assert wrap_line("Fecha a porta logo.", 42) == "Fecha a porta logo."
    assert wrap_line("Quando a chuva parou,\\Neu voltei sozinho.", 42) == "Quando a chuva parou, eu voltei sozinho."


def test_wrap_line_splits_long_lines_balanced_and_bottom_heavy() -> None:
    text = "Você tem escondido as chaves da padaria em todas as gavetas desde o começo do ano."
    wrapped = wrap_line(text, 42)
    top, bottom = wrapped.split("\\N")
    assert top + " " + bottom == text
    assert len(top) <= 42 and len(bottom) <= 42
    assert abs(len(top) - len(bottom)) <= 4  # equilibrado


def test_wrap_line_breaks_ties_toward_longer_bottom_line() -> None:
    top, bottom = wrap_line("aaaa bbbb cccc dddd eeee ffff gggg hhhh iiii", 30).split("\\N")
    assert len(top) < len(bottom)


def test_wrap_line_prefers_break_after_punctuation() -> None:
    wrapped = wrap_line("Depois de esperar tanto tempo sob a chuva, eu finalmente consegui abrir a velha porta.", 42)
    assert wrapped.startswith("Depois de esperar tanto tempo sob a chuva,") or wrapped.split("\\N")[0].endswith(",")


def test_wrap_line_counts_visible_chars_only() -> None:
    text = "⟦1⟧Uau!⟦2⟧ Eu nunca imaginei que o bolo ficaria tão macio desse jeito!"
    top, bottom = wrap_line(text, 42).split("\\N")
    assert "⟦1⟧" in top and "⟦2⟧" in top


def test_char_budget_from_duration() -> None:
    assert char_budget(2000, max_cps=17, max_cpl=42) == 34
    assert char_budget(10_000, max_cps=17, max_cpl=42) == 84  # teto: 2 linhas
    assert char_budget(0, max_cps=17, max_cpl=42) is None


def test_prompt_includes_char_budget() -> None:
    prompt = format_batch_prompt([DialogueLine(id="u1", text="Hello")], [], char_budgets={"u1": 34})
    assert "34 caracteres" in prompt
    assert "caracteres" not in format_batch_prompt([DialogueLine(id="u1", text="Hello")], [])


def test_translate_dialogue_takes_limits_from_checks_config() -> None:
    stage = StageTranslateDialogue()
    assert (stage.max_cps, stage.max_cpl) == (17.0, 42)
    stage.bind_pipeline([], AppConfig.model_validate({"checks": {"max_cps": 15, "max_cpl": 40}}))
    assert (stage.max_cps, stage.max_cpl) == (15.0, 40)
    assert stage.cache_payload(None, None) != StageTranslateDialogue().cache_payload(None, None)


def test_redistribute_wraps_with_checks_cpl() -> None:
    stage = REGISTRY.get("redistribute_sentences")()
    assert stage.max_cpl == 42
    stage.bind_pipeline([], AppConfig.model_validate({"checks": {"max_cpl": 30}}))
    assert stage.max_cpl == 30


def test_default_pipeline_still_loads(tmp_path: Path) -> None:
    from translaterany.config.loader import load_config

    cfg = tmp_path / "c.toml"
    cfg.write_text("", encoding="utf-8")
    assert any(s.name == "translate_songs" for s in load_config(cfg, tmp_path / "d").stages)
