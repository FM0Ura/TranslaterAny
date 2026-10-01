# tests/test_report_m7.py
"""Testes de relatório para as etapas do M7."""

from translaterany.pipeline.report import SeriesReport, StageSummary
from translaterany.cli.report import _render


def test_report_renders_m7_stages() -> None:
    report = SeriesReport(
        series="Test Series (2026)",
        episodes=1,
        lines=100,
        stages={
            "treatment_consistency": StageSummary(units_done=1, units_failed=0, duration_s=1.5, counters={"edits_applied": 2}),
            "adapt": StageSummary(units_done=1, units_failed=0, duration_s=1.2, counters={"edits_applied": 3}),
            "orthography": StageSummary(units_done=1, units_failed=0, duration_s=0.5, counters={"corrections_applied": 4}),
            "final_readthrough": StageSummary(units_done=1, units_failed=0, duration_s=2.0, counters={"edits_applied": 1}),
        },
    )
    # Testa que a renderização do rich console não levanta exceções
    _render(report)
