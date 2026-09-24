import pytest

from translaterany.pipeline.registry import StageRegistry
from translaterany.pipeline.stage import Stage, StageContext, StageScope


class Dummy(Stage):
    name = "dummy"
    version = "1"
    scope = StageScope.EPISODE

    def run(self, ctx: StageContext) -> None:
        pass


def test_register_and_get() -> None:
    reg = StageRegistry()
    assert reg.register(Dummy) is Dummy
    assert "dummy" in reg
    assert reg.get("dummy") is Dummy
    assert reg.names() == ["dummy"]


def test_duplicate_name_rejected() -> None:
    reg = StageRegistry()
    reg.register(Dummy)
    with pytest.raises(ValueError, match="duas vezes"):
        reg.register(Dummy)
