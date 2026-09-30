"""Comando report: processo por etapa, por modelo, indicadores finais e instantâneos."""

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.markup import escape
from rich.table import Table

from translaterany.cli.app import EXIT_FAILURE, EXIT_USAGE, AppState, app, console, load_or_exit
from translaterany.library import discover
from translaterany.pipeline.artifacts import ArtifactStore
from translaterany.pipeline.manifest import ManifestError
from translaterany.pipeline.report import (
    REPORT_SCHEMA,
    MetricsError,
    SeriesReport,
    build_report,
    compare_reports,
    load_episode_metrics,
)


def _arrow(delta: float) -> str:
    if abs(delta) < 1e-9:
        return "="
    return "[red]▲[/red]" if delta > 0 else "[green]▼[/green]"


def _render(report: SeriesReport) -> None:
    table = Table(title=f"Processo por etapa — {escape(report.series)}")
    for col in ("Etapa", "OK", "Falhas", "Tempo total", "Tempo médio", "Chamadas", "Tokens ent.", "Tokens saída",
                "Custo (USD)", "Erros IA", "Contadores"):  # fmt: skip
        table.add_column(col)
    for name, s in report.stages.items():
        table.add_row(
            escape(name), str(s.units_done), str(s.units_failed), f"{s.duration_s:.1f}s", f"{s.mean_duration_s:.1f}s",
            str(s.llm.calls), str(s.llm.input_tokens), str(s.llm.output_tokens), f"{s.llm.cost_usd:.4f}",
            escape(", ".join(f"{k}={v}" for k, v in s.llm.errors.items())) or "—",
            escape(", ".join(f"{k}={v}" for k, v in s.counters.items())) or "—",
        )  # fmt: skip
    console.print(table)

    if report.models:
        models = Table(title="Por modelo")
        for col in ("Modelo", "Chamadas", "Tokens ent.", "Tokens saída", "Custo (USD)"):
            models.add_column(col)
        for model_id, m in report.models.items():
            models.add_row(
                escape(model_id), str(m.calls), str(m.input_tokens), str(m.output_tokens), f"{m.cost_usd:.4f}"
            )
        console.print(models)

    final = Table(title=f"Indicadores finais — {report.lines} linhas em {report.episodes} episódio(s)")
    for col in ("Checagem", "error", "warn", "info", "Linhas afetadas", "Taxa"):
        final.add_column(col)
    for check, c in sorted(report.final_checks.items()):
        final.add_row(escape(check), str(c.counts.error), str(c.counts.warn), str(c.counts.info),
                      str(c.affected_lines), f"{c.rate:.1%}")
    console.print(final)
    rs = report.reading_speed
    console.print(
        f"CPS: p50 ≤ {rs.cps_p50:g} · p95 ≤ {rs.cps_p95:g} · máx {rs.cps_max:g} · acima do limite: {rs.over_limit}"
    )

    if report.snapshots:
        snaps = Table(title="Instantâneos (por etapa de texto)")
        for col in ("Etapa", "Episódios", "Linhas alteradas", "Achados novos", "Resolvidos", "Edição média"):
            snaps.add_column(col)
        for name, s in report.snapshots.items():
            snaps.add_row(
                escape(name), str(s.episodes), str(s.changed), str(s.new), str(s.resolved), f"{s.edit_ratio_mean:.1%}"
            )
        console.print(snaps)

    if report.worst_episodes:
        worst = Table(title="Piores episódios (linhas com error)")
        for col in ("Episódio", "Linhas", "Com error", "Taxa"):
            worst.add_column(col)
        for r in report.worst_episodes:
            worst.add_row(escape(r.episode), str(r.lines), str(r.error_lines), f"{r.error_rate:.1%}")
        console.print(worst)
    if report.missing_metrics:
        console.print(
            f"[yellow]Sem métricas (rode `translaterany run`): {escape(', '.join(report.missing_metrics))}[/yellow]"
        )
    for warning in report.warnings:
        console.print(f"[yellow]Aviso: {escape(warning)}[/yellow]")


@app.command()
def report(
    ctx: typer.Context,
    path: Annotated[Path, typer.Argument(help="Pasta da série.")],
    episode: Annotated[str | None, typer.Option("--episode", help="Só um episódio (ex.: S01E03).")] = None,
    json_out: Annotated[Path | None, typer.Option("--json", help="Grava o relatório (linha de base) em JSON.")] = None,
    baseline: Annotated[Path | None, typer.Option("--baseline", help="Compara com um relatório salvo.")] = None,
) -> None:
    """Mostra métricas de processo e indicadores de qualidade da série."""
    state: AppState = ctx.obj
    cfg = load_or_exit(state)
    store = ArtifactStore(cfg.data_dir)
    try:
        series, _ = discover(path)
    except NotADirectoryError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(EXIT_USAGE) from exc
    if not store.series_dir(series.key).exists():
        console.print(f"Pasta nunca processada: {escape(series.name)}")
        raise typer.Exit(EXIT_FAILURE)

    base: SeriesReport | None = None
    if baseline is not None:
        try:
            base = SeriesReport.model_validate_json(baseline.read_text(encoding="utf-8"))
        except (OSError, ValidationError, UnicodeDecodeError) as exc:
            console.print(f"[red]Linha de base ilegível: {escape(str(baseline))} ({type(exc).__name__})[/red]")
            raise typer.Exit(EXIT_USAGE) from exc
        if base.schema_version != REPORT_SCHEMA:
            console.print(f"[red]Linha de base com schema {base.schema_version}; esperado {REPORT_SCHEMA}.[/red]")
            raise typer.Exit(EXIT_USAGE)

    try:
        result = build_report(store, series.key, series.name, [s.name for s in cfg.stages],
                              episodes=[episode] if episode else None)  # fmt: skip
    except ManifestError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise typer.Exit(EXIT_FAILURE) from exc
    if len(result.missing_metrics) == result.episodes:
        console.print("Nenhuma métrica encontrada — rode `translaterany run` primeiro.")
        raise typer.Exit(EXIT_FAILURE)

    _render(result)
    if episode:
        try:
            metrics = load_episode_metrics(store, series.key, episode)
        except MetricsError as exc:
            console.print(f"[yellow]{escape(str(exc))}[/yellow]")
            metrics = None
        if metrics is not None:
            table = Table(title=f"Achados finais — {escape(episode)}")
            for col in ("Unidade", "Checagem", "Severidade", "Mensagem", "Trecho"):
                table.add_column(col)
            for f in metrics.final.findings + metrics.episode_checks:
                table.add_row(
                    escape(f.unit_id or "—"), escape(f.check), f.severity, escape(f.message), escape(f.excerpt or "")
                )
            console.print(table)
    if base is not None:
        if base.episodes != result.episodes:
            console.print(
                f"[yellow]Aviso: número de episódios diferente (atual {result.episodes}, base {base.episodes}); "
                "tokens e custos são totais da série e não são diretamente comparáveis.[/yellow]"
            )
        table = Table(title="Comparação com a linha de base")
        for col in ("Métrica", "Atual", "Base", "Δ", ""):
            table.add_column(col)
        for row in compare_reports(result, base):
            table.add_row(
                escape(row.metric), f"{row.current:.4g}", f"{row.baseline:.4g}", f"{row.delta:+.4g}", _arrow(row.delta)
            )
        console.print(table)
    if json_out is not None:
        try:
            json_out.parent.mkdir(parents=True, exist_ok=True)
            json_out.write_text(result.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
        except OSError as exc:
            console.print(
                f"[red]Não foi possível gravar o relatório em {escape(str(json_out))} ({type(exc).__name__})[/red]"
            )
            raise typer.Exit(EXIT_USAGE) from exc
        console.print(f"Relatório salvo em {escape(str(json_out))}")
