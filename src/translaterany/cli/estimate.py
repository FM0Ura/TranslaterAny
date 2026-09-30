"""Comando estimate: estatísticas e estimativa de tokens, custos e tempo para tradução."""

from pathlib import Path
from typing import Annotated

import typer
from rich.table import Table

from translaterany.cli.app import EXIT_OK, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import scan_library
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.subtitles.chunking import estimate_tokens
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.normalize import NormalizedDoc


def _format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes = seconds / 60.0
    return f"{minutes:.1f} min"


@app.command()
def estimate(
    ctx: typer.Context,
    path: Annotated[Path | None, typer.Argument(help="Pasta da série ou da biblioteca.")] = None,
) -> None:
    """Exibe estatísticas e estimativa de tokens e custos para tradução."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    target_path = path or Path.cwd()
    if not target_path.exists():
        console.print(f"[red]Caminho não encontrado: {target_path}[/red]")
        raise typer.Exit(EXIT_USAGE)

    try:
        scans = scan_library(target_path, min_file_age=0)
    except NotADirectoryError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc

    if not scans:
        console.print(f"Nenhuma série encontrada em {target_path}.")
        raise typer.Exit(EXIT_OK)

    store = ArtifactStore(cfg.data_dir)
    profile_name = cfg.llm.profile
    profile = cfg.llm.profiles.get(profile_name)
    translate_model_name = profile.translate if profile else "translategemma"
    model_cfg = cfg.llm.models.get(translate_model_name)
    provider = model_cfg.provider if model_cfg else "ollama"

    total_episodes = 0
    total_dialogues = 0
    total_input_tokens = 0
    total_output_tokens = 0
    total_seconds = 0.0

    table = Table(title="Estimativa de Tradução de Legendas")
    table.add_column("Série", style="bold")
    table.add_column("Episódio")
    table.add_column("Falas", justify="right")
    table.add_column("Tokens Entrada", justify="right")
    table.add_column("Tokens Saída", justify="right")
    table.add_column("Custo Est. (USD)", justify="right")
    table.add_column("Tempo Est.", justify="right")

    for scan in scans:
        series = scan.series
        for ep in scan.episodes:
            total_episodes += 1
            art_dir = store.artifact_dir(series.key, ep.key)
            classify_file = art_dir / "classify.json"
            normalize_file = art_dir / "normalize.json"

            dialogues = 0
            input_tokens = 0
            output_tokens = 0

            if classify_file.exists():
                try:
                    c_data = classify_file.read_text(encoding="utf-8")
                    classification = Classification.model_validate_json(c_data)
                    dialogue_unit_ids = {
                        uid for uid, uclass in classification.units.items() if uclass.type == "dialogue"
                    }
                    dialogues = classification.counts.get("dialogue", len(dialogue_unit_ids))

                    if normalize_file.exists():
                        n_data = normalize_file.read_text(encoding="utf-8")
                        norm_doc = NormalizedDoc.model_validate_json(n_data)
                        dialogue_units = [u for u in norm_doc.units if u.id in dialogue_unit_ids]
                        dialogues = len(dialogue_units)
                        char_tokens = sum(estimate_tokens(u.text) for u in dialogue_units)
                        input_tokens = char_tokens + (dialogues * 8)
                        output_tokens = char_tokens
                    else:
                        input_tokens = dialogues * 17
                        output_tokens = dialogues * 11
                except Exception:
                    dialogues = 350
                    input_tokens = 6000
                    output_tokens = 4000
            else:
                dialogues = 350
                input_tokens = 6000
                output_tokens = 4000

            # Custo financeiro (preços do config; Ollama tem preço 0 por padrão)
            if model_cfg is None:
                cost_usd = 0.0
            else:
                cost_usd = (
                    input_tokens * model_cfg.input_price_per_mtok + output_tokens * model_cfg.output_price_per_mtok
                ) / 1_000_000

            # Projeção de tempo (~25 tokens/s em GPU local; na nuvem ~50 tokens/s + 1s por bloco)
            if provider == "ollama" or profile_name == "local":
                ep_seconds = max(1.0, output_tokens / 25.0)
            else:
                batches = max(1, dialogues // 10)
                ep_seconds = (output_tokens / 50.0) + (batches * 1.0)

            total_dialogues += dialogues
            total_input_tokens += input_tokens
            total_output_tokens += output_tokens
            total_seconds += ep_seconds

            table.add_row(
                series.name,
                ep.source.name,
                f"{dialogues:,}",
                f"{input_tokens:,}",
                f"{output_tokens:,}",
                f"${cost_usd:.4f}",
                _format_time(ep_seconds),
            )

    console.print(table)
    console.print()
    console.print("[bold]Resumo:[/bold]")
    console.print(f"- Total de episódios: {total_episodes}")
    console.print(f"- Total estimado de falas: {total_dialogues:,}")
    console.print(
        f"- Total estimado de tokens: {total_input_tokens + total_output_tokens:,} "
        f"({total_input_tokens:,} entrada / {total_output_tokens:,} saída)"
    )
    console.print(f"- Tempo estimado: ~{_format_time(total_seconds)}")
    console.print(
        f"- Perfil LLM: [cyan]{profile_name}[/cyan] "
        f"(Modelo: [cyan]{translate_model_name}[/cyan] via [cyan]{provider}[/cyan])"
    )

    total_cost = (
        (total_input_tokens * model_cfg.input_price_per_mtok + total_output_tokens * model_cfg.output_price_per_mtok)
        / 1_000_000
        if model_cfg is not None
        else 0.0
    )
    if total_cost == 0.0:
        console.print("- Custo estimado: [green]$0.00 USD[/green] (Inferência 100% local)")
    else:
        console.print(
            f"- Custo total estimado: [yellow]${total_cost:.4f} USD[/yellow] "
            f"(Limite configurado: ${cfg.llm.max_cost_usd:.2f} USD)"
        )
        if total_cost > cfg.llm.max_cost_usd:
            console.print(
                f"[red]Atenção: O custo estimado excede o teto configurado de max_cost_usd "
                f"(${cfg.llm.max_cost_usd:.2f})![/red]"
            )
