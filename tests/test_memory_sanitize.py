"""Higienização do glossário: aliases duplicados/colidentes e variantes quase idênticas (dados sintéticos)."""

from translaterany.memory.models import CharacterEntry, EntrySource, GlossaryCategory, GlossaryEntry
from translaterany.memory.sanitize import sanitize_glossary


def entry(
    term: str,
    translation: str = "",
    *,
    aliases: list[str] | None = None,
    category: GlossaryCategory = GlossaryCategory.GENERAL,
    source: EntrySource = EntrySource.EXTRACTED,
) -> GlossaryEntry:
    return GlossaryEntry(
        term=term, translation=translation or term, category=category, aliases=aliases or [], source=source
    )


def by_term(entries: list[GlossaryEntry]) -> dict[str, GlossaryEntry]:
    return {e.term: e for e in entries}


def test_drops_alias_equal_to_own_term() -> None:
    out = sanitize_glossary([entry("Zorn Castle", aliases=["zorn castle", "The Keep"])], [])
    assert out[0].aliases == ["The Keep"]


def test_drops_alias_that_is_another_entry_term() -> None:
    out = by_term(
        sanitize_glossary(
            [entry("Hero Alpha", aliases=["Alpha", "Beta"]), entry("Beta"), entry("Alpha")],
            [],
        )
    )
    assert out["Hero Alpha"].aliases == []


def test_swapped_aliases_between_two_entries_are_dropped() -> None:
    out = by_term(
        sanitize_glossary(
            [
                entry("Northtown", aliases=["Northtown", "Northville"], category=GlossaryCategory.PLACE),
                entry("Northville", aliases=["Northtown"], category=GlossaryCategory.PLACE),
            ],
            [],
        )
    )
    assert out["Northtown"].aliases == []
    assert out["Northville"].aliases == []


def test_shared_alias_stays_with_higher_precedence_owner() -> None:
    out = by_term(
        sanitize_glossary(
            [
                entry("Gadget One", aliases=["The Gadget"]),
                entry("Gadget Two", aliases=["The Gadget"], source=EntrySource.METADATA),
            ],
            [],
        )
    )
    assert out["Gadget One"].aliases == []
    assert out["Gadget Two"].aliases == ["The Gadget"]


def test_shared_alias_between_equals_stays_with_first_entry() -> None:
    out = by_term(
        sanitize_glossary(
            [entry("Gadget One", aliases=["The Gadget"]), entry("Gadget Two", aliases=["The Gadget"])], []
        )
    )
    assert out["Gadget One"].aliases == ["The Gadget"]
    assert out["Gadget Two"].aliases == []


def test_drops_alias_that_is_a_character_name_or_alias() -> None:
    chars = [CharacterEntry(name="Rin Okada", aliases=["Rinrin", "Okada"])]
    out = sanitize_glossary(
        [entry("Phantom Rin", aliases=["Rin Okada", "rinrin", "Okada", "Phantom"], category=GlossaryCategory.NAME)],
        chars,
    )
    assert out[0].aliases == ["Phantom"]


def test_user_entries_are_never_touched() -> None:
    chars = [CharacterEntry(name="Rin Okada", aliases=["Rinrin"])]
    user = entry("Gadget One", aliases=["Gadget One", "Rinrin", "Gadget Two"], source=EntrySource.USER)
    out = by_term(sanitize_glossary([user, entry("Gadget Three", aliases=["Gadget One", "Rinrin"])], chars))
    assert out["Gadget One"].aliases == ["Gadget One", "Rinrin", "Gadget Two"]
    assert out["Gadget Three"].aliases == []


def test_extracted_entry_duplicating_user_alias_is_dropped() -> None:
    user = entry("Phone Gadget (draft name)", aliases=["Phone Gadget"], source=EntrySource.USER)
    out = sanitize_glossary([user, entry("Phone Gadget", "Gadget de Telefone")], [])
    assert [e.term for e in out] == ["Phone Gadget (draft name)"]


def test_merges_parenthetical_and_comma_variants_into_shorter_term() -> None:
    cat = GlossaryCategory.OBJECT
    out = sanitize_glossary(
        [
            entry("Phone Gadget, 2nd edition, Version 1.03", "Gadget B", aliases=["Phone Gadget (beta)"], category=cat),
            entry("Phone Gadget", "Gadget de Telefone", aliases=["PG"], category=cat),
            entry("Phone Gadget (name subject to change)", "Gadget C", category=cat),
        ],
        [],
    )
    assert [e.term for e in out] == ["Phone Gadget"]
    merged = out[0]
    assert merged.translation == "Gadget de Telefone"
    assert merged.source == EntrySource.EXTRACTED
    assert set(merged.aliases) == {
        "PG",
        "Phone Gadget (beta)",
        "Phone Gadget, 2nd edition, Version 1.03",
        "Phone Gadget (name subject to change)",
    }


def test_does_not_merge_plain_prefix_or_different_category() -> None:
    out = sanitize_glossary(
        [
            entry("Northtown", category=GlossaryCategory.PLACE),
            entry("Northtown Radio Building", category=GlossaryCategory.PLACE),
            entry("Northtown (band)", category=GlossaryCategory.ORGANIZATION),
        ],
        [],
    )
    assert [e.term for e in out] == ["Northtown", "Northtown Radio Building", "Northtown (band)"]


def test_does_not_merge_into_or_out_of_user_entries() -> None:
    cat = GlossaryCategory.OBJECT
    out = sanitize_glossary(
        [
            entry("Phone Gadget (draft)", source=EntrySource.USER, category=cat),
            entry("Phone Gadget, v2", category=cat),
        ],
        [],
    )
    assert [e.term for e in out] == ["Phone Gadget (draft)", "Phone Gadget, v2"]


def test_is_idempotent() -> None:
    chars = [CharacterEntry(name="Rin Okada", aliases=["Rinrin"])]
    cat = GlossaryCategory.OBJECT
    entries = [
        entry("Phone Gadget, v2", aliases=["Phone Gadget"], category=cat),
        entry("Phone Gadget", aliases=["Phone Gadget (beta)", "Rinrin"], category=cat),
        entry("Northtown", aliases=["Northville"], category=GlossaryCategory.PLACE),
        entry("Northville", aliases=["Northtown"], category=GlossaryCategory.PLACE),
    ]
    once = sanitize_glossary(entries, chars)
    twice = sanitize_glossary(once, chars)
    assert [e.model_dump() for e in once] == [e.model_dump() for e in twice]


def test_input_is_not_mutated() -> None:
    original = entry("Zorn Castle", aliases=["Zorn Castle", "The Keep"])
    sanitize_glossary([original], [])
    assert original.aliases == ["Zorn Castle", "The Keep"]
