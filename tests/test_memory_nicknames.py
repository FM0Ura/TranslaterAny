"""Limpeza de personagens extraídos que são apelidos de outro personagem (dados sintéticos)."""

from translaterany.memory.models import CharacterEntry, EntrySource
from translaterany.memory.nicknames import merge_nickname_characters

META = EntrySource.METADATA


def cast() -> list[CharacterEntry]:
    return [
        CharacterEntry(name="Luka Urushibara", aliases=["Luka"], source=META),
        CharacterEntry(name="Mika Sato", source=EntrySource.USER, speech_style="meu estilo"),
        CharacterEntry(name="Ren Aoki", aliases=["Super Ren"], source=META),
    ]


def names(chars: list[CharacterEntry]) -> list[str]:
    return [c.name for c in chars]


def test_extracted_nickname_is_merged_into_the_character_as_alias() -> None:
    chars = [*cast(), CharacterEntry(name="Lukako", source=EntrySource.EXTRACTED, speech_style="doce")]
    out = merge_nickname_characters(chars)
    assert names(out) == ["Luka Urushibara", "Mika Sato", "Ren Aoki"]
    assert out[0].aliases == ["Luka", "Lukako"]
    assert out[0].speech_style is None  # personagem de metadata não recebe nada além de aliases


def test_parenthetical_and_alias_forms_are_merged() -> None:
    chars = [
        *cast(),
        CharacterEntry(name="Rukako (Luka Urushibara)", source=EntrySource.EXTRACTED),
        CharacterEntry(name="Super Ren", source=EntrySource.EXTRACTED),
    ]
    out = merge_nickname_characters(chars)
    assert names(out) == ["Luka Urushibara", "Mika Sato", "Ren Aoki"]
    assert out[0].aliases == ["Luka", "Rukako"]
    assert out[2].aliases == ["Super Ren"]


def test_extracted_aliases_are_carried_to_the_target() -> None:
    chars = [*cast(), CharacterEntry(name="Lukako", aliases=["Lukaa"], source=EntrySource.EXTRACTED)]
    assert merge_nickname_characters(chars)[0].aliases == ["Luka", "Lukako", "Lukaa"]


def test_unrelated_extracted_character_is_kept() -> None:
    chars = [*cast(), CharacterEntry(name="Zanzibar", source=EntrySource.EXTRACTED)]
    assert names(merge_nickname_characters(chars)) == [*names(cast()), "Zanzibar"]


def test_extracted_entry_listing_several_characters_is_dropped() -> None:
    chars = [*cast(), CharacterEntry(name="Mika Sato, Ren Aoki", source=EntrySource.EXTRACTED)]
    out = merge_nickname_characters(chars)
    assert names(out) == names(cast())
    assert [c.aliases for c in out] == [["Luka"], [], ["Super Ren"]]


def test_ambiguous_nickname_is_kept() -> None:
    chars = [
        CharacterEntry(name="Lukas Berg", source=META),
        CharacterEntry(name="Lukan Moor", source=META),
        CharacterEntry(name="Luka", source=EntrySource.EXTRACTED),
    ]
    assert names(merge_nickname_characters(chars)) == ["Lukas Berg", "Lukan Moor", "Luka"]


def test_user_and_metadata_characters_are_never_merged_or_removed() -> None:
    chars = [
        CharacterEntry(name="Luka Urushibara", source=META),
        CharacterEntry(name="Lukako", source=EntrySource.USER),
        CharacterEntry(name="Rukako", source=META),
    ]
    assert merge_nickname_characters(chars) == chars


def test_merge_is_idempotent_and_does_not_mutate_input() -> None:
    chars = [*cast(), CharacterEntry(name="Lukako", source=EntrySource.EXTRACTED)]
    first = merge_nickname_characters(chars)
    assert len(chars) == 4 and chars[0].aliases == ["Luka"]
    assert merge_nickname_characters(first) == first
