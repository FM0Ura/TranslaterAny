"""Consolidação de speech_style de personagens a partir de vários episódios (dados sintéticos)."""

from translaterany.memory.artifacts import CharacterStyle, ExtractTermsArtifact
from translaterany.memory.models import CharacterEntry, EntrySource
from translaterany.memory.styles import apply_character_styles, find_character, pick_style


def styles(*pairs: tuple[str, str]) -> list[CharacterStyle]:
    return [CharacterStyle(name=n, speech_style=s) for n, s in pairs]


def test_pick_style_prefers_most_frequent_then_longest() -> None:
    assert pick_style(["formal", "Formal ", "casual e debochado"]) == "formal"
    assert pick_style(["formal", "casual e debochado"]) == "casual e debochado"
    assert pick_style(["", "  "]) == ""


def test_old_extract_artifact_without_styles_loads() -> None:
    art = ExtractTermsArtifact.model_validate({"episode_key": "S01E01", "terms": [], "character_mentions": []})
    assert art.character_styles == []


def test_sets_style_on_matching_character_by_name_alias_or_unique_token() -> None:
    chars = [
        CharacterEntry(name="Rin Okada", aliases=["Rinrin"]),
        CharacterEntry(name="Taro Sato"),
    ]
    out = apply_character_styles(
        chars, styles(("Rin Okada", "fala rápido"), ("Taro", "polido e hesitante"), ("rinrin", "fala rápido"))
    )
    by_name = {c.name: c for c in out}
    assert by_name["Rin Okada"].speech_style == "fala rápido"
    assert by_name["Taro Sato"].speech_style == "polido e hesitante"
    assert len(out) == 2


def test_ambiguous_token_does_not_match() -> None:
    chars = [CharacterEntry(name="Rin Okada"), CharacterEntry(name="Rin Sato")]
    out = apply_character_styles(chars, styles(("Rin", "alegre")))
    assert [c.speech_style for c in out[:2]] == [None, None]
    assert any(c.name == "Rin" and c.speech_style == "alegre" for c in out)


def test_merges_across_episodes_and_keeps_source() -> None:
    chars = [CharacterEntry(name="Rin Okada", source=EntrySource.METADATA)]
    out = apply_character_styles(
        chars, styles(("Rin Okada", "fala rápido"), ("Rin Okada", "fala rápido"), ("Rin Okada", "mais longo mas raro"))
    )
    assert out[0].speech_style == "fala rápido"
    assert out[0].source == EntrySource.METADATA


def test_never_overwrites_non_empty_style_from_user_or_metadata() -> None:
    chars = [
        CharacterEntry(name="Rin Okada", speech_style="meu estilo", source=EntrySource.USER),
        CharacterEntry(name="Taro Sato", speech_style="estilo da metadata", source=EntrySource.METADATA),
    ]
    out = apply_character_styles(chars, styles(("Rin Okada", "novo"), ("Taro Sato", "novo")))
    assert [c.speech_style for c in out] == ["meu estilo", "estilo da metadata"]


def test_fills_empty_style_of_user_character_but_replaces_extracted_one() -> None:
    chars = [
        CharacterEntry(name="Rin Okada", source=EntrySource.USER),
        CharacterEntry(name="Taro Sato", speech_style="antigo", source=EntrySource.EXTRACTED),
    ]
    out = apply_character_styles(chars, styles(("Rin Okada", "novo"), ("Taro Sato", "atualizado")))
    assert [c.speech_style for c in out] == ["novo", "atualizado"]
    assert out[0].source == EntrySource.USER


def test_unknown_character_is_added_as_extracted() -> None:
    out = apply_character_styles([], styles(("Mika", "meiga, usa diminutivos")))
    assert len(out) == 1
    assert out[0].name == "Mika"
    assert out[0].speech_style == "meiga, usa diminutivos"
    assert out[0].source == EntrySource.EXTRACTED


def test_honorific_only_name_is_ignored() -> None:
    assert apply_character_styles([], styles(("sensei", "formal"), ("", "x"), ("Rin", ""))) == []


def test_input_characters_not_mutated() -> None:
    chars = [CharacterEntry(name="Rin Okada")]
    apply_character_styles(chars, styles(("Rin Okada", "alegre")))
    assert chars[0].speech_style is None


def test_find_character_ignores_case_and_diacritics() -> None:
    chars = [CharacterEntry(name="Zoë Lund", aliases=["Zozo"])]
    assert find_character(chars, "ZOE LUND") == 0
    assert find_character(chars, "zoë") == 0
    assert find_character(chars, "ZOZO") == 0


def test_find_character_strips_honorifics_from_the_style_name() -> None:
    chars = [CharacterEntry(name="Taro Sato", aliases=["Tarou"])]
    assert find_character(chars, "Taro-kun") == 0
    assert find_character(chars, "Dr. Sato") == 0
    assert find_character(chars, "tarou-chan") == 0


def test_find_character_resolves_nickname_by_containment() -> None:
    chars = [
        CharacterEntry(name="Luka Urushibara"),
        CharacterEntry(name="Mika Sato"),
        CharacterEntry(name="Yukitaka Aoi"),
    ]
    assert find_character(chars, "Lukako") == 0  # "luka" + sufixo de apelido
    assert find_character(chars, "Rukako") == 0  # troca L/R da romanização
    assert find_character(chars, "Urushiba") == 0  # prefixo do sobrenome
    assert find_character(chars, "Yuki") is None  # curto demais perto de "yukitaka"
    assert find_character(chars, "Mik") is None  # menos de 4 letras


def test_containment_with_two_candidates_is_ambiguous() -> None:
    chars = [CharacterEntry(name="Lukas Berg"), CharacterEntry(name="Lukan Moor")]
    assert find_character(chars, "Luka") is None


def test_nickname_with_parenthetical_name_resolves_to_the_inner_character() -> None:
    chars = [CharacterEntry(name="Luka Urushibara")]
    assert find_character(chars, "Zumbi (Luka Urushibara)") == 0
    assert find_character(chars, "Lukako (Urushibara)") == 0


def test_nickname_style_resolves_to_existing_character_and_becomes_alias() -> None:
    chars = [CharacterEntry(name="Luka Urushibara", source=EntrySource.METADATA)]
    out = apply_character_styles(chars, styles(("Lukako", "doce e tímido")))
    assert len(out) == 1
    assert out[0].speech_style == "doce e tímido"
    assert out[0].source == EntrySource.METADATA
    assert out[0].aliases == ["Lukako"]


def test_exact_alias_resolution_does_not_duplicate_the_alias() -> None:
    chars = [CharacterEntry(name="Luka Urushibara", aliases=["Lukako"], source=EntrySource.METADATA)]
    out = apply_character_styles(chars, styles(("lukako", "doce")))
    assert out[0].aliases == ["Lukako"]


def test_unresolvable_nickname_still_creates_extracted_character() -> None:
    chars = [CharacterEntry(name="Luka Urushibara", source=EntrySource.METADATA)]
    out = apply_character_styles(chars, styles(("Zanzibar", "rouco")))
    assert [c.name for c in out] == ["Luka Urushibara", "Zanzibar"]
    assert out[1].source == EntrySource.EXTRACTED
    assert out[0].aliases == []
