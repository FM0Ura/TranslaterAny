"""Comando memory: inspeciona e gerencia a memória da série."""

import re
import shutil
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.table import Table
from ruamel.yaml import YAML

from translaterany.cli.app import EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.memory.models import (
    CharacterEntry,
    EntrySource,
    EpisodeSynopsis,
    GlossaryEntry,
    StoryMemory,
)
from translaterany.memory.store import MemoryStore
from translaterany.pipeline.artifacts import ArtifactStore


def _load_yaml_content(path: Path) -> Any:
    yaml = YAML(typ="safe")
    return yaml.load(path.read_text(encoding="utf-8"))


def _import_file_into_store(file_path: Path, mem_store: MemoryStore) -> None:
    data = _load_yaml_content(file_path)
    if not data:
        return

    if isinstance(data, list):
        if data and isinstance(data[0], dict) and "term" in data[0]:
            entries: list[GlossaryEntry] = []
            for item in data:
                if isinstance(item, dict) and "term" in item:
                    item_copy = dict(item)
                    if "source" not in item_copy:
                        item_copy["source"] = EntrySource.USER
                    entries.append(GlossaryEntry.model_validate(item_copy))
            if entries:
                mem_store.merge_glossary(entries)
        elif data and isinstance(data[0], dict) and "name" in data[0]:
            chars: list[CharacterEntry] = []
            for item in data:
                if isinstance(item, dict) and "name" in item:
                    item_copy = dict(item)
                    if "source" not in item_copy:
                        item_copy["source"] = EntrySource.USER
                    chars.append(CharacterEntry.model_validate(item_copy))
            if chars:
                mem_store.merge_characters(chars)
    elif isinstance(data, dict):
        if "glossary" in data and isinstance(data["glossary"], list):
            entries = []
            for item in data["glossary"]:
                if isinstance(item, dict) and "term" in item:
                    item_copy = dict(item)
                    if "source" not in item_copy:
                        item_copy["source"] = EntrySource.USER
                    entries.append(GlossaryEntry.model_validate(item_copy))
            if entries:
                mem_store.merge_glossary(entries)
        elif "characters" in data and isinstance(data["characters"], list):
            chars = []
            for item in data["characters"]:
                if isinstance(item, dict) and "name" in item:
                    item_copy = dict(item)
                    if "source" not in item_copy:
                        item_copy["source"] = EntrySource.USER
                    chars.append(CharacterEntry.model_validate(item_copy))
            if chars:
                mem_store.merge_characters(chars)
        elif "title" in data or "synopsis" in data:
            story = StoryMemory.model_validate(data)
            mem_store.save_story(story)


@app.command()
def memory(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série.")],
    export: Annotated[
        Path | None,
        typer.Option("--export", help="Diretório de destino para exportar arquivos de memória."),
    ] = None,
    import_path: Annotated[
        Path | None,
        typer.Option("--import", help="Arquivo ou pasta com arquivos YAML de memória para importar."),
    ] = None,
    refresh: Annotated[
        bool,
        typer.Option("--refresh", help="Força atualização dos metadados externos e limpa cache em disco."),
    ] = False,
) -> None:
    """Inspeciona e gerencia a memória da série (glossário, personagens e história)."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    store = ArtifactStore(cfg.data_dir)

    try:
        series, _ = discover(path)
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc

    mem_dir = store.series_dir(series.key) / "memory"
    mem_store = MemoryStore(mem_dir)

    if refresh:
        cache_dir = cfg.data_dir / "cache"
        if (cache_dir / "anilist").exists():
            for f in (cache_dir / "anilist").glob("*.json"):
                f.unlink(missing_ok=True)
        if (cache_dir / "jikan").exists():
            for f in (cache_dir / "jikan").glob("*.json"):
                f.unlink(missing_ok=True)

        raw_name = series.name.strip()
        match_re = re.match(r"^(.*?)(?:\s*\((\d{4})\))?$", raw_name)
        title = match_re.group(1).strip() if match_re else raw_name
        year = int(match_re.group(2)) if match_re and match_re.group(2) else None

        from translaterany.memory.anilist import AniListClient
        from translaterany.memory.jikan import JikanClient

        anilist = AniListClient(cache_dir)
        jikan = JikanClient(cache_dir)
        match = anilist.search_anime(title, year)
        if match:
            synopses: dict[int, EpisodeSynopsis] = {}
            if match.mal_id:
                try:
                    synopses = jikan.get_episode_synopses(match.mal_id) or {}
                except Exception:
                    synopses = {}
            episodes_map = {
                (syn.episode_key if getattr(syn, "episode_key", None) else f"EP{num}"): syn
                for num, syn in synopses.items()
            }
            story = StoryMemory(
                title=match.title,
                romaji_title=match.romaji,
                year=match.year,
                synopsis="",
                genres=match.genres,
                episodes=episodes_map,
            )
            mem_store.save_story(story)
            if match.characters:
                mem_store.merge_characters(match.characters)
        console.print(f"[green]Metadados e memória da série '{series.name}' atualizados com sucesso.[/green]")
        return

    if export is not None:
        export.mkdir(parents=True, exist_ok=True)
        count = 0
        for fname in ("characters.yaml", "glossary.yaml", "story.yaml"):
            src = mem_dir / fname
            if src.is_file():
                shutil.copy2(src, export / fname)
                count += 1
        console.print(f"[green]{count} arquivo(s) de memória exportado(s) para {export}.[/green]")
        return

    if import_path is not None:
        if not import_path.exists():
            console.print(f"[red]Caminho de importação não encontrado: {import_path}[/red]")
            raise typer.Exit(EXIT_USAGE)

        if import_path.is_dir():
            for fname in ("characters.yaml", "glossary.yaml", "story.yaml"):
                f = import_path / fname
                if f.is_file():
                    _import_file_into_store(f, mem_store)
        else:
            _import_file_into_store(import_path, mem_store)

        console.print(f"[green]Memória importada com sucesso a partir de {import_path}.[/green]")
        return

    glossary = mem_store.load_glossary()
    characters = mem_store.load_characters()
    story = mem_store.load_story()

    if not glossary and not characters and not story:
        console.print(f"Nenhum registro de memória encontrado para a série: {series.name}")
        return

    if story and story.title:
        title_str = f"[bold]{story.title}[/bold]"
        if story.year:
            title_str += f" ({story.year})"
        console.print(f"Série: {title_str}")
        if story.synopsis:
            console.print(f"Sinopse: {story.synopsis}")
        console.print()

    if characters:
        char_table = Table(title=f"Personagens — {series.name}")
        for col in ("Nome", "Gênero", "Papel", "Estilo de fala", "Origem", "Notas"):
            char_table.add_column(col)
        for c in characters:
            gender_val = c.gender.value if hasattr(c.gender, "value") else str(c.gender)
            role_val = c.role.value if hasattr(c.role, "value") else str(c.role)
            src_val = c.source.value if hasattr(c.source, "value") else str(c.source)
            char_table.add_row(
                c.name,
                gender_val,
                role_val,
                c.speech_style or "—",
                src_val,
                c.notes or "—",
            )
        console.print(char_table)
        console.print()

    if glossary:
        gloss_table = Table(title=f"Glossário — {series.name}")
        for col in ("Termo", "Tradução", "Categoria", "Origem", "Notas"):
            gloss_table.add_column(col)
        for entry in glossary.values():
            cat_val = entry.category.value if hasattr(entry.category, "value") else str(entry.category)
            src_val = entry.source.value if hasattr(entry.source, "value") else str(entry.source)
            gloss_table.add_row(
                entry.term,
                entry.translation,
                cat_val,
                src_val,
                entry.notes or "—",
            )
        console.print(gloss_table)
