"""Endpoints RESTful para diagnóstico de ambiente (doctor)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from translaterany.util.doctor import (
    check_audio_runtimes,
    check_ffmpeg_audio_codecs,
    check_languagetool_service,
    check_nvidia_gpu,
    check_ollama_status,
    check_tesseract_installed,
    data_dir_check,
    python_version_check,
)

router = APIRouter(prefix="/doctor", tags=["doctor"])


class DoctorItem(BaseModel):
    name: str
    status: str
    message: str


class DoctorResponse(BaseModel):
    checks: list[DoctorItem]


@router.get("", response_model=DoctorResponse)
def run_doctor(request: Request) -> DoctorResponse:
    checks: list[DoctorItem] = []
    data_dir = getattr(request.app.state, "data_dir", None)
    if data_dir is None:
        data_dir = request.app.state.series_service.data_dir

    # 1. Python version
    py_res = python_version_check().run()
    checks.append(DoctorItem(name="python", status=py_res.status, message=py_res.message))

    # 2. Data dir
    dd_res = data_dir_check(data_dir).run()
    checks.append(DoctorItem(name="data_dir", status=dd_res.status, message=dd_res.message))

    # 3. GPU
    gpu_ok, gpu_msg = check_nvidia_gpu()
    checks.append(DoctorItem(name="gpu", status="ok" if gpu_ok else "warn", message=gpu_msg))

    # 4. Ollama
    cfg_svc = getattr(request.app.state, "config_service", None)
    ollama_url = "http://localhost:11434"
    if cfg_svc:
        try:
            cfg = cfg_svc.get_config()
            prov = cfg.llm.providers.get("ollama")
            if prov and prov.base_url:
                ollama_url = prov.base_url
        except Exception:
            pass
    ol_ok, ol_msg = check_ollama_status(ollama_url)
    checks.append(DoctorItem(name="ollama", status="ok" if ol_ok else "warn", message=ol_msg))

    # 5. Tesseract
    tess_res = check_tesseract_installed()
    checks.append(DoctorItem(name="tesseract", status=tess_res.status, message=tess_res.message))

    # 6. LanguageTool
    lt_res = check_languagetool_service()
    checks.append(DoctorItem(name="languagetool", status=lt_res.status, message=lt_res.message))

    # 7. Audio runtime & FFmpeg
    audio_res = check_audio_runtimes()
    checks.append(DoctorItem(name="audio", status=audio_res.status, message=audio_res.message))
    ff_res = check_ffmpeg_audio_codecs()
    checks.append(DoctorItem(name="ffmpeg", status=ff_res.status, message=ff_res.message))

    return DoctorResponse(checks=checks)
