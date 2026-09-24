from pathlib import Path

import pytest

from translaterany.config.loader import ConfigError, default_data_dir, find_config, load_config
from translaterany.pipeline.registry import StageRegistry


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _load(tmp_path: Path, registry: StageRegistry, text: str | None, **kw):
    path = _write(tmp_path, text) if text is not None else None
    return load_config(path, registry=registry, default_pipeline=("t_source",), env={}, **kw)


def test_default_without_file(tmp_path: Path, registry: StageRegistry) -> None:
    cfg = _load(tmp_path, registry, None)
    assert cfg.source is None
    assert [s.name for s in cfg.stages] == ["t_source"]
    assert cfg.data_dir == Path.home() / ".local" / "share" / "translaterany"
    assert cfg.log_level == "INFO"


def test_xdg_dirs() -> None:
    assert default_data_dir({"XDG_DATA_HOME": "/x"}) == Path("/x/translaterany")


def test_find_config_precedence(tmp_path: Path) -> None:
    explicit = _write(tmp_path, "")
    env_file = tmp_path / "env.toml"
    env_file.write_text("")
    assert find_config(explicit, {"TRANSLATERANY_CONFIG": str(env_file)}) == explicit
    assert find_config(None, {"TRANSLATERANY_CONFIG": str(env_file)}) == env_file
    xdg = tmp_path / "xdg"
    (xdg / "translaterany").mkdir(parents=True)
    (xdg / "translaterany" / "config.toml").write_text("")
    assert find_config(None, {"XDG_CONFIG_HOME": str(xdg)}) == xdg / "translaterany" / "config.toml"
    assert find_config(None, {"XDG_CONFIG_HOME": str(tmp_path / "vazio")}) is None


def test_explicit_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="não encontrado"):
        find_config(tmp_path / "nao.toml", {})


def test_full_config_with_options_and_data_dir(tmp_path: Path, registry: StageRegistry) -> None:
    cfg = _load(
        tmp_path,
        registry,
        f"""
[general]
data_dir = "{tmp_path / "d"}"
log_level = "DEBUG"
[pipeline]
stages = ["t_source", "t_upper"]
[stages.t_upper.options]
suffix = "!"
""",
    )
    assert [s.name for s in cfg.stages] == ["t_source", "t_upper"]
    assert cfg.stages[1].options.suffix == "!"
    assert cfg.data_dir == tmp_path / "d"
    assert cfg.log_level == "DEBUG"


def test_data_dir_override_wins(tmp_path: Path, registry: StageRegistry) -> None:
    cfg = _load(tmp_path, registry, None, data_dir_override=tmp_path / "cli")
    assert cfg.data_dir == tmp_path / "cli"


def test_unknown_stage(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="etapa desconhecida 'nope'"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["nope"]')


def test_duplicate_stage(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="mais de uma vez"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_source", "t_source"]')


def test_orphan_stage_section(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="stages.t_upper: seção"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_source"]\n[stages.t_upper]\nenabled = true')


def test_invalid_option_points_to_key(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match=r"stages\.t_upper\.options\.suffix"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_source", "t_upper"]\n[stages.t_upper.options]\nsuffix = 3')


def test_unknown_option_rejected(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="stages.t_source.options.foo"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_source"]\n[stages.t_source.options]\nfoo = 1')


def test_unknown_top_level_key(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="pipelin"):
        _load(tmp_path, registry, '[pipelin]\nstages = []\n[pipeline]\nstages = ["t_source"]')


def test_invalid_toml(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="TOML inválido"):
        _load(tmp_path, registry, "[pipeline\nstages = ")


def test_dependency_out_of_order(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="depende de 't_source', que não vem antes"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_upper", "t_source"]')


def test_dependency_disabled(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="está desabilitada"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_source", "t_upper"]\n[stages.t_source]\nenabled = false')


def test_disabled_stage_is_dropped(tmp_path: Path, registry: StageRegistry) -> None:
    cfg = _load(tmp_path, registry, '[pipeline]\nstages = ["t_source", "t_length"]\n[stages.t_length]\nenabled = false')
    assert [s.name for s in cfg.stages] == ["t_source"]


def test_error_message_names_file(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError) as info:
        _load(tmp_path, registry, '[pipeline]\nstages = ["nope"]')
    assert str(info.value).startswith(f"Erro no config ({tmp_path / 'config.toml'}):")


def test_dependency_not_in_pipeline(tmp_path: Path, registry: StageRegistry) -> None:
    with pytest.raises(ConfigError, match="não está no pipeline"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_upper"]')


def test_data_dir_tilde_is_expanded(tmp_path: Path, registry: StageRegistry) -> None:
    cfg = _load(tmp_path, registry, '[general]\ndata_dir = "~/tl-data"\n[pipeline]\nstages = ["t_source"]')
    assert cfg.data_dir == Path.home() / "tl-data"


def test_config_without_pipeline_uses_default(tmp_path: Path, registry: StageRegistry) -> None:
    cfg = _load(tmp_path, registry, f'[general]\ndata_dir = "{tmp_path / "d"}"')
    assert [s.name for s in cfg.stages] == ["t_source"]
    assert cfg.data_dir == tmp_path / "d"


def test_series_stage_reading_source_rejected(tmp_path: Path, registry: StageRegistry) -> None:
    from fake_stages import CollectStage

    class SeriesSource(CollectStage):
        name = "t_series_source"
        inputs = ()
        reads_source = True

    registry.register(SeriesSource)
    with pytest.raises(ConfigError, match="reads_source"):
        _load(tmp_path, registry, '[pipeline]\nstages = ["t_series_source"]')
