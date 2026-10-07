"""Serviço para leitura, validação e persistência do arquivo config.toml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from translaterany.config.loader import default_config_path, load_config_from_str
from translaterany.config.model import AppConfig


def _format_toml_val(val: Any) -> str:
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(val, (list, tuple)):
        items_str = ", ".join(_format_toml_val(x) for x in val)
        return f"[{items_str}]"
    return f'"{str(val)}"'


def dump_toml(data: dict[str, Any], prefix: str = "") -> str:
    """Serializa dicionário simples ou aninhado para formato TOML."""
    scalars: dict[str, Any] = {}
    tables: dict[str, dict[str, Any]] = {}

    for k, v in data.items():
        if v is None:
            continue
        if isinstance(v, dict):
            tables[k] = v
        else:
            scalars[k] = v

    lines: list[str] = []
    # Grava escalares no nível atual
    for k, v in scalars.items():
        lines.append(f"{k} = {_format_toml_val(v)}")

    # Grava tabelas aninhadas
    for k, v in tables.items():
        table_name = f"{prefix}.{k}" if prefix else k
        lines.append(f"\n[{table_name}]")
        sub_str = dump_toml(v, prefix=table_name)
        if sub_str.strip():
            lines.append(sub_str.strip())

    return "\n".join(lines)


class ConfigService:
    """Gerencia a leitura e gravação da configuração da aplicação."""

    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path is not None else default_config_path()

    def get_config(self) -> AppConfig:
        if not self.config_path.is_file():
            return AppConfig()
        content = self.config_path.read_text(encoding="utf-8")
        if not content.strip():
            return AppConfig()
        return load_config_from_str(content)

    def save_config(self, config: AppConfig) -> None:
        # Validação estrita via Pydantic
        validated = AppConfig.model_validate(config.model_dump())
        dumped = validated.model_dump(mode="json")
        toml_content = dump_toml(dumped)

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(toml_content.strip() + "\n", encoding="utf-8")
