"""Contadores específicos de uma etapa (fallbacks, acertos na TM...), gravados no manifest."""

from dataclasses import dataclass, field


@dataclass
class StageMetrics:
    counters: dict[str, int] = field(default_factory=dict)

    def count(self, name: str, n: int = 1) -> None:
        self.counters[name] = self.counters.get(name, 0) + n


def count(ctx: object, name: str, n: int = 1) -> None:
    """Conta em ctx.metrics, se existir (etapas também rodam com contextos falsos nos testes)."""
    metrics = getattr(ctx, "metrics", None)
    if isinstance(metrics, StageMetrics):
        metrics.count(name, n)
