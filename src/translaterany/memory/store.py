"""Armazenamento e precedência YAML com ruamel.yaml para memória da série."""

from __future__ import annotations

import hashlib
import io
from collections.abc import Iterable
from pathlib import Path
from typing import Any

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
        gender = incoming.gender if existing.gender == Gender.UNKNOWN and incoming.gender != Gender.UNKNOWN else existing.gender
        all_aliases = list(dict.fromkeys(existing.aliases + incoming.aliases + ([incoming.name] if incoming.name != existing.name else [])))
        return existing.model_copy(update={"gender": gender, "aliases": all_aliases})

    native_name = incoming.native_name if incoming.native_name is not None else existing.native_name
    speech_style = incoming.speech_style if incoming.speech_style is not None else existing.speech_style
    notes = incoming.notes if incoming.notes is not None else existing.notes
    all_aliases = list(dict.fromkeys(existing.aliases + incoming.aliases + ([existing.name] if existing.name != incoming.name else [])))
    gender = incoming.gender if incoming.gender != Gender.UNKNOWN else existing.gender
    role = incoming.role

    return CharacterEntry(
        name=incoming.name,
        native_name=native_name,
        aliases=all_aliases,
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

    def _write_yaml(self, path: Path, data: Any) -> str:
        """Serializa dados para o arquivo de forma atômica e retorna o hash sha256."""
        self.dir.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        self._yaml.dump(data, buf)
        yaml_text = buf.getvalue()

        # Gravação atômica via arquivo temporário no mesmo diretório
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(yaml_text, encoding="utf-8")
        tmp_path.replace(path)

        return hashlib.sha256(yaml_text.encode("utf-8")).hexdigest()

    def _sync_and_save_seq(self, path: Path, entries_dicts: list[dict], key_field: str) -> str:
        """Salva sequência preservando nós existentes e comentários de ruamel.yaml."""
        self.dir.mkdir(parents=True, exist_ok=True)
        doc = None
        if path.is_file():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                try:
                    loaded = self._yaml.load(content)
                    if isinstance(loaded, list):
                        doc = loaded
                except Exception:
                    doc = None

        if doc is None:
            data_to_dump = entries_dicts
        else:
            existing_by_key = {}
            for item in doc:
                if isinstance(item, dict) and key_field in item and item[key_field] is not None:
                    existing_by_key[str(item[key_field]).strip().lower()] = item

            updated_items = []
            for entry in entries_dicts:
                k = str(entry[key_field]).strip().lower()
                if k in existing_by_key:
                    node = existing_by_key[k]
                    for field_k, field_v in entry.items():
                        node[field_k] = field_v
                    updated_items.append(node)
                else:
                    updated_items.append(entry)

            doc[:] = updated_items
            data_to_dump = doc

        return self._write_yaml(path, data_to_dump)

    def _sync_and_save_story(self, path: Path, story_dict: dict) -> str:
        """Salva a história preservando comentários de ruamel.yaml se o arquivo já existir."""
        self.dir.mkdir(parents=True, exist_ok=True)
        doc = None
        if path.is_file():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                try:
                    loaded = self._yaml.load(content)
                    if isinstance(loaded, dict):
                        doc = loaded
                except Exception:
                    doc = None

        if doc is None:
            data_to_dump = story_dict
        else:
            for k, v in story_dict.items():
                if k == "episodes" and isinstance(v, dict) and isinstance(doc.get("episodes"), dict):
                    ep_doc = doc["episodes"]
                    for ep_k, ep_v in v.items():
                        if ep_k in ep_doc and isinstance(ep_doc[ep_k], dict) and isinstance(ep_v, dict):
                            for sub_k, sub_v in ep_v.items():
                                ep_doc[ep_k][sub_k] = sub_v
                        else:
                            ep_doc[ep_k] = ep_v
                    for ep_k in list(ep_doc.keys()):
                        if ep_k not in v:
                            del ep_doc[ep_k]
                else:
                    doc[k] = v
            data_to_dump = doc

        return self._write_yaml(path, data_to_dump)

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
        """Salva a lista de personagens em characters.yaml preservando comentários e formatação."""
        char_list = list(characters)
        data = [c.model_dump(mode="json") for c in char_list]
        return self._sync_and_save_seq(self.characters_path, data, "name")

    def merge_characters(self, incoming: list[CharacterEntry]) -> list[CharacterEntry]:
        """Mescla novos personagens com os existentes preservando precedência estrita."""
        existing_list = self.load_characters()
        merged: list[CharacterEntry] = list(existing_list)
        name_to_index: dict[str, int] = {c.name.strip().lower(): idx for idx, c in enumerate(merged)}

        def find_existing_index(inc: CharacterEntry) -> int | None:
            key = inc.name.strip().lower()
            if key in name_to_index:
                return name_to_index[key]
            inc_tokens = set(key.split())
            for idx, c in enumerate(merged):
                c_key = c.name.strip().lower()
                c_tokens = set(c_key.split())
                # Se ambos têm 2+ tokens e exatamente os mesmos tokens (ex.: "Hyoudou Issei" vs "Issei Hyoudou")
                if len(inc_tokens) >= 2 and inc_tokens == c_tokens:
                    return idx
                # Se o nome de um está nos aliases do outro
                if key in [a.lower() for a in c.aliases] or c_key in [a.lower() for a in inc.aliases]:
                    return idx
            return None

        for inc in incoming:
            idx = find_existing_index(inc)
            if idx is not None:
                merged[idx] = merge_character_entry(merged[idx], inc)
            else:
                name_to_index[inc.name.strip().lower()] = len(merged)
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
        """Salva entradas no glossary.yaml preservando comentários e formatação."""
        if isinstance(entries, dict):
            entries_list = list(entries.values())
        else:
            entries_list = list(entries)
        data = [e.model_dump(mode="json") for e in entries_list]
        return self._sync_and_save_seq(self.glossary_path, data, "term")

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
        """Salva os dados da história em story.yaml preservando comentários se existentes."""
        data = story.model_dump(mode="json")
        return self._sync_and_save_story(self.story_path, data)
