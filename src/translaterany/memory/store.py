"""Armazenamento e precedência YAML com ruamel.yaml para memória da série."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable
from pathlib import Path

from ruamel.yaml import YAML

from translaterany.memory.models import (
    CharacterEntry,
    EntrySource,
    Gender,
    GlossaryEntry,
    StoryMemory,
)

PRECEDENCE_RANK: dict[EntrySource, int] = {
    EntrySource.USER: 3,
    EntrySource.METADATA: 2,
    EntrySource.EXTRACTED: 1,
}


def should_overwrite(existing_source: EntrySource, incoming_source: EntrySource) -> bool:
    """Verifica se uma entrada recebida pode substituir/atualizar uma existente.

    Regra de precedência estrita:
    USER (3) > METADATA (2) > EXTRACTED (1).
    Entradas com source=USER NUNCA são sobrescritas.
    """
    if existing_source == EntrySource.USER:
        return False
    return PRECEDENCE_RANK.get(incoming_source, 1) >= PRECEDENCE_RANK.get(existing_source, 1)


def merge_character_entry(existing: CharacterEntry, incoming: CharacterEntry) -> CharacterEntry:
    """Funde duas entradas do mesmo personagem respeitando precedência."""
    if not should_overwrite(existing.source, incoming.source):
        return existing

    native_name = incoming.native_name if incoming.native_name is not None else existing.native_name
    speech_style = incoming.speech_style if incoming.speech_style is not None else existing.speech_style
    notes = incoming.notes if incoming.notes is not None else existing.notes
    aliases = list(dict.fromkeys(existing.aliases + incoming.aliases))
    gender = incoming.gender if incoming.gender != Gender.UNKNOWN else existing.gender
    role = incoming.role

    return CharacterEntry(
        name=incoming.name,
        native_name=native_name,
        aliases=aliases,
        gender=gender,
        role=role,
        speech_style=speech_style,
        notes=notes,
        source=incoming.source,
    )


def merge_glossary_entry(existing: GlossaryEntry, incoming: GlossaryEntry) -> GlossaryEntry:
    """Funde duas entradas de mesmo termo respeitando precedência."""
    if not should_overwrite(existing.source, incoming.source):
        return existing

    notes = incoming.notes if incoming.notes is not None else existing.notes
    aliases = list(dict.fromkeys(existing.aliases + incoming.aliases))

    return GlossaryEntry(
        term=incoming.term,
        translation=incoming.translation,
        category=incoming.category,
        keep_original=incoming.keep_original,
        aliases=aliases,
        notes=notes,
        source=incoming.source,
    )


def _init_yaml() -> YAML:
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    yaml.default_flow_style = False
    return yaml


class MemoryStore:
    """Gerenciador de persistência em YAML para a memória da série."""

    def __init__(self, dir: Path) -> None:
        self.dir = Path(dir)
        self._yaml = _init_yaml()
        self.characters_path = self.dir / "characters.yaml"
        self.glossary_path = self.dir / "glossary.yaml"
        self.story_path = self.dir / "story.yaml"

    def load_characters(self) -> list[CharacterEntry]:
        """Carrega a lista de personagens salvos em characters.yaml."""
        if not self.characters_path.is_file():
            return []
        content = self.characters_path.read_text(encoding="utf-8").strip()
        if not content:
            return []
        data = self._yaml.load(content)
        if not data:
            return []
        if isinstance(data, list):
            return [CharacterEntry.model_validate(item) for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            if "characters" in data and isinstance(data["characters"], list):
                return [CharacterEntry.model_validate(item) for item in data["characters"] if isinstance(item, dict)]
            return [CharacterEntry.model_validate(item) for item in data.values() if isinstance(item, dict)]
        return []

    def save_characters(self, characters: Iterable[CharacterEntry]) -> str:
        """Salva a lista de personagens em characters.yaml e retorna o sha256 do arquivo."""
        self.dir.mkdir(parents=True, exist_ok=True)
        char_list = list(characters)
        data = [c.model_dump(mode="json") for c in char_list]
        buf = io.StringIO()
        self._yaml.dump(data, buf)
        yaml_text = buf.getvalue()
        self.characters_path.write_text(yaml_text, encoding="utf-8")
        return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()

    def merge_characters(self, incoming: list[CharacterEntry]) -> list[CharacterEntry]:
        """Mescla novos personagens com os existentes preservando precedência estrita."""
        existing_list = self.load_characters()
        merged: list[CharacterEntry] = list(existing_list)
        name_to_index: dict[str, int] = {c.name.strip().lower(): idx for idx, c in enumerate(merged)}

        for inc in incoming:
            key = inc.name.strip().lower()
            if key in name_to_index:
                idx = name_to_index[key]
                merged[idx] = merge_character_entry(merged[idx], inc)
            else:
                name_to_index[key] = len(merged)
                merged.append(inc)

        self.save_characters(merged)
        return merged

    def load_glossary(self) -> dict[str, GlossaryEntry]:
        """Carrega o glossário salvo em glossary.yaml indexado por termo."""
        if not self.glossary_path.is_file():
            return {}
        content = self.glossary_path.read_text(encoding="utf-8").strip()
        if not content:
            return {}
        data = self._yaml.load(content)
        if not data:
            return {}
        res: dict[str, GlossaryEntry] = {}
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    entry = GlossaryEntry.model_validate(item)
                    res[entry.term] = entry
        elif isinstance(data, dict):
            if "glossary" in data and isinstance(data["glossary"], list):
                for item in data["glossary"]:
                    if isinstance(item, dict):
                        entry = GlossaryEntry.model_validate(item)
                        res[entry.term] = entry
            else:
                for term, val in data.items():
                    if isinstance(val, dict):
                        if "term" not in val:
                            val = {**val, "term": term}
                        entry = GlossaryEntry.model_validate(val)
                        res[entry.term] = entry
        return res

    def save_glossary(self, entries: Iterable[GlossaryEntry] | dict[str, GlossaryEntry]) -> str:
        """Salva entradas no glossary.yaml e retorna o sha256 do arquivo."""
        self.dir.mkdir(parents=True, exist_ok=True)
        if isinstance(entries, dict):
            entries_list = list(entries.values())
        else:
            entries_list = list(entries)
        data = [e.model_dump(mode="json") for e in entries_list]
        buf = io.StringIO()
        self._yaml.dump(data, buf)
        yaml_text = buf.getvalue()
        self.glossary_path.write_text(yaml_text, encoding="utf-8")
        return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()

    def merge_glossary(self, incoming: list[GlossaryEntry]) -> list[GlossaryEntry]:
        """Mescla novos termos com os existentes preservando precedência estrita."""
        existing_dict = self.load_glossary()
        entries_list: list[GlossaryEntry] = list(existing_dict.values())
        term_to_index: dict[str, int] = {e.term.strip().lower(): idx for idx, e in enumerate(entries_list)}

        for inc in incoming:
            key = inc.term.strip().lower()
            if key in term_to_index:
                idx = term_to_index[key]
                entries_list[idx] = merge_glossary_entry(entries_list[idx], inc)
            else:
                term_to_index[key] = len(entries_list)
                entries_list.append(inc)

        self.save_glossary(entries_list)
        return entries_list

    def load_story(self) -> StoryMemory | None:
        """Carrega a história salva em story.yaml ou None se não existir."""
        if not self.story_path.is_file():
            return None
        content = self.story_path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        data = self._yaml.load(content)
        if not data or not isinstance(data, dict):
            return None
        return StoryMemory.model_validate(data)

    def save_story(self, story: StoryMemory) -> str:
        """Salva os dados da história em story.yaml e retorna o sha256 do arquivo."""
        self.dir.mkdir(parents=True, exist_ok=True)
        data = story.model_dump(mode="json")
        buf = io.StringIO()
        self._yaml.dump(data, buf)
        yaml_text = buf.getvalue()
        self.story_path.write_text(yaml_text, encoding="utf-8")
        return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()
