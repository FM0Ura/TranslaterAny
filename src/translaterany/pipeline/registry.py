"""Registro de etapas por nome (o config referencia etapas pelo nome)."""

from translaterany.pipeline.stage import Stage


class StageRegistry:
    def __init__(self) -> None:
        self._stages: dict[str, type[Stage]] = {}

    def register[S: type[Stage]](self, cls: S) -> S:
        if cls.name in self._stages:
            raise ValueError(f"etapa '{cls.name}' registrada duas vezes")
        self._stages[cls.name] = cls
        return cls

    def get(self, name: str) -> type[Stage]:
        return self._stages[name]

    def names(self) -> list[str]:
        return list(self._stages)

    def __contains__(self, name: object) -> bool:
        return name in self._stages


REGISTRY = StageRegistry()


def register_stage[S: type[Stage]](cls: S) -> S:
    """Decorador: registra a etapa no registro global."""
    return REGISTRY.register(cls)
