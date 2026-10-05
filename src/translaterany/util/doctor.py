"""Verificações de ambiente (comando doctor e pré-voo do run)."""

import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

type CheckStatus = Literal["ok", "warn", "fail"]


@dataclass(frozen=True)
class CheckResult:
    status: CheckStatus
    message: str


class Check(Protocol):
    name: str

    def run(self) -> CheckResult: ...


@dataclass(frozen=True)
class FunctionCheck:
    name: str
    fn: Callable[[], CheckResult]

    def run(self) -> CheckResult:
        return self.fn()


def python_version_check(minimum: tuple[int, int] = (3, 14)) -> Check:
    def run() -> CheckResult:
        current = sys.version_info[:2]
        version = ".".join(map(str, sys.version_info[:3]))
        if current >= minimum:
            return CheckResult("ok", f"Python {version}")
        return CheckResult("fail", f"Python {version}; é necessário {minimum[0]}.{minimum[1]} ou superior")

    return FunctionCheck("python", run)


def data_dir_check(data_dir: Path) -> Check:
    def run() -> CheckResult:
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=data_dir):
                pass
        except OSError as exc:
            return CheckResult("fail", f"diretório de dados sem permissão de escrita: {data_dir} ({exc})")
        return CheckResult("ok", f"diretório de dados gravável: {data_dir}")

    return FunctionCheck("data_dir", run)


def run_checks(checks: Iterable[Check]) -> list[tuple[str, CheckResult]]:
    results: list[tuple[str, CheckResult]] = []
    for check in checks:
        try:
            result = check.run()
        except Exception as exc:  # uma verificação quebrada não derruba as outras
            result = CheckResult("fail", f"erro ao verificar: {exc}")
        results.append((check.name, result))
    return results


def has_failure(results: Iterable[tuple[str, CheckResult]]) -> bool:
    return any(result.status == "fail" for _, result in results)


def check_ollama_status(url: str = "http://localhost:11434") -> tuple[bool, str]:
    import httpx

    clean_url = url.rstrip("/")
    if clean_url.endswith("/v1"):
        clean_url = clean_url[:-3]
    try:
        version = None
        resp_v = httpx.get(f"{clean_url}/api/version", timeout=5.0)
        if resp_v.status_code == 200:
            v_data = resp_v.json()
            if isinstance(v_data, dict):
                version = v_data.get("version")

        resp = httpx.get(f"{clean_url}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            return False, f"Ollama em {clean_url} não está acessível (HTTP {resp.status_code})"
        data = resp.json()
        models = [m.get("name", "") for m in data.get("models", []) if m.get("name")]
        version_part = f" v{version}" if version else ""
        if models:
            return True, f"Ollama{version_part} acessível ({', '.join(models)})"
        return True, f"Ollama{version_part} acessível (nenhum modelo instalado)"
    except Exception as exc:
        return False, f"Ollama não está acessível em {clean_url}: {exc}"


check_ollama_service = check_ollama_status


def check_languagetool_service(
    url: str = "http://localhost:8010/v2/check",
    transport: Any = None,
    target_lang: str | None = None,
) -> CheckResult:
    """Verifica se o servidor LanguageTool está acessível via HTTP."""
    import httpx

    base = url.split("/v2")[0] if "/v2" in url else url.rstrip("/")
    try:
        with httpx.Client(timeout=3.0, transport=transport) as client:
            resp = client.get(f"{base}/v2/languages")
            if resp.status_code == 200:
                if target_lang:
                    try:
                        langs = resp.json()
                        target_code = target_lang.lower().split("-")[0]
                        has_lang = any(
                            target_code in (item.get("code") or "").lower()
                            or target_code in (item.get("longCode") or "").lower()
                            or target_code in (item.get("name") or "").lower()
                            for item in langs
                            if isinstance(item, dict)
                        )
                        if has_lang:
                            return CheckResult("ok", f"LanguageTool acessível em {base} (suporta {target_lang})")
                    except Exception:
                        pass
                return CheckResult("ok", f"LanguageTool acessível em {base}")
            return CheckResult("warn", f"LanguageTool em {base} retornou status HTTP {resp.status_code}")
    except Exception as exc:
        return CheckResult("warn", f"LanguageTool indisponível em {url}: {exc}")


def check_ollama_models(
    url: str = "http://localhost:11434",
    required_models: list[str] | None = None,
) -> tuple[bool, str]:
    import httpx

    if required_models is None:
        required_models = ["translategemma:12b", "gemma4:12b"]

    clean_url = url.rstrip("/")
    if clean_url.endswith("/v1"):
        clean_url = clean_url[:-3]
    try:
        resp = httpx.get(f"{clean_url}/api/tags", timeout=5.0)
        if resp.status_code != 200:
            return False, f"Ollama não está acessível em {clean_url} (HTTP {resp.status_code})"
        data = resp.json()
        available_names = {m.get("name", "") for m in data.get("models", [])}
        missing = [
            req for req in required_models if req not in available_names and f"{req}:latest" not in available_names
        ]
        if missing:
            return False, f"Modelos ausentes no Ollama: {', '.join(missing)} (execute 'ollama pull <modelo>')"
        return True, f"Modelos presentes: {', '.join(required_models)}"
    except Exception as exc:
        return False, f"Ollama não está acessível em {clean_url}: {exc}"


def check_nvidia_gpu() -> tuple[bool, str]:
    import subprocess

    try:
        proc = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if proc.returncode != 0:
            return False, f"nvidia-smi retornou erro ({proc.returncode}): {proc.stderr.strip()}"
        lines = [line.strip() for line in proc.stdout.strip().splitlines() if line.strip()]
        if not lines:
            return False, "nvidia-smi não retornou informações de GPU"
        gpus: list[str] = []
        for line in lines:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name, total, free = parts[0], parts[1], parts[2]
                gpus.append(f"{name} ({free} MiB livres / {total} MiB total)")
            else:
                gpus.append(line)
        return True, "; ".join(gpus)
    except FileNotFoundError:
        return False, "nvidia-smi não encontrado no PATH"
    except Exception as exc:
        return False, f"Erro ao consultar nvidia-smi: {exc}"


def ollama_check(url: str = "http://localhost:11434") -> Check:
    def run() -> CheckResult:
        ok, msg = check_ollama_status(url)
        return CheckResult("ok" if ok else "fail", msg)

    return FunctionCheck("ollama", run)


def ollama_models_check(url: str = "http://localhost:11434", required: list[str] | None = None) -> Check:
    def run() -> CheckResult:
        ok, msg = check_ollama_models(url, required)
        return CheckResult("ok" if ok else "fail", msg)

    return FunctionCheck("ollama_models", run)


def nvidia_gpu_check() -> Check:
    def run() -> CheckResult:
        ok, msg = check_nvidia_gpu()
        return CheckResult("ok" if ok else "warn", msg)

    return FunctionCheck("gpu", run)


def check_tesseract_installed(source_lang: str | None = None) -> CheckResult:
    """Verifica se o binário tesseract está instalado e se possui o pacote de idioma necessário."""
    import shutil
    import subprocess

    binary = shutil.which("tesseract")
    if not binary:
        return CheckResult(
            "warn",
            "tesseract não encontrado no PATH (necessário para legendas PGS/VobSub; "
            "instale via 'brew install tesseract' ou gerenciador do sistema)",
        )

    try:
        proc_ver = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=5.0)
        ver_line = proc_ver.stdout.splitlines()[0] if proc_ver.stdout else "tesseract"
    except Exception as exc:
        return CheckResult("fail", f"erro ao executar tesseract: {exc}")

    if source_lang:
        from translaterany.media.ocr.engine import get_tesseract_lang

        tess_lang = get_tesseract_lang(source_lang)
        try:
            proc_langs = subprocess.run([binary, "--list-langs"], capture_output=True, text=True, timeout=5.0)
            available = [
                line.strip().lower()
                for line in proc_langs.stdout.splitlines()
                if line.strip() and not line.startswith("List of")
            ]
            if tess_lang not in available:
                return CheckResult(
                    "warn",
                    f"{ver_line} instalado, mas o pacote de idioma '{tess_lang}' "
                    "não foi encontrado em 'tesseract --list-langs' "
                    "(instale 'tesseract-lang' ou o pacote correspondente)",
                )
        except Exception:
            pass

    return CheckResult("ok", f"{ver_line} instalado")
