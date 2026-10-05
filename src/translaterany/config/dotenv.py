"""Carregamento de variáveis de ambiente a partir de arquivo .env."""

from __future__ import annotations

import os
from pathlib import Path


def load_dotenv(env_path: Path | str | None = None) -> bool:
    """Lê um arquivo .env e injeta as variáveis no os.environ se ainda não estiverem definidas."""
    if env_path is not None:
        target = Path(env_path)
    else:
        # Não carregar automaticamente o .env do workspace se estiver executando a suíte de testes (pytest)
        if "PYTEST_CURRENT_TEST" in os.environ:
            return False
        # Busca .env no diretório de trabalho atual ou subindo até a raiz do projeto/git
        cwd = Path.cwd()
        candidate = cwd / ".env"
        if not candidate.is_file():
            for parent in cwd.parents:
                c = parent / ".env"
                if c.is_file():
                    candidate = c
                    break
        target = candidate

    if not target.is_file():
        return False

    try:
        content = target.read_text(encoding="utf-8")
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = val
        return True
    except Exception:
        return False
