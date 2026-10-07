"""Aplicação principal FastAPI com routers RESTful /api/v1 e SSR."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from translaterany.config.loader import default_config_path, default_data_dir
from translaterany.web.api.config import router as config_router
from translaterany.web.api.doctor import router as doctor_router
from translaterany.web.api.jobs import router as jobs_router
from translaterany.web.api.memory import router as memory_router
from translaterany.web.api.pipeline import router as pipeline_router
from translaterany.web.api.series import router as series_router
from translaterany.web.jobs import JobManager
from translaterany.web.pages.dashboard import router as dashboard_router
from translaterany.web.pages.pipeline import router as pipeline_page_router
from translaterany.web.pages.series import router as series_page_router
from translaterany.web.pages.settings import router as settings_page_router
from translaterany.web.services.config_service import ConfigService
from translaterany.web.services.memory_service import MemoryService
from translaterany.web.services.pipeline_service import PipelineService
from translaterany.web.services.series_service import SeriesService


def create_app(
    data_dir: Path | None = None,
    config_path: Path | None = None,
    start_worker: bool = True,
) -> FastAPI:
    app = FastAPI(
        title="TranslaterAny Web",
        description="Interface Web moderna e API RESTful desacoplada para tradução de legendas de anime",
        version="1.3.0",
    )

    # Middleware CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Resolução de diretórios
    effective_data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
    effective_config_path = Path(config_path) if config_path is not None else default_config_path()

    # Inicialização dos serviços
    app.state.data_dir = effective_data_dir
    app.state.config_path = effective_config_path
    app.state.series_service = SeriesService(data_dir=effective_data_dir)
    app.state.memory_service = MemoryService(data_dir=effective_data_dir)
    app.state.pipeline_service = PipelineService(config_path=effective_config_path, data_dir=effective_data_dir)
    app.state.config_service = ConfigService(config_path=effective_config_path)
    app.state.job_manager = JobManager(
        data_dir=effective_data_dir,
        config_path=effective_config_path,
        start_worker=start_worker,
    )

    # Router da API RESTful /api/v1
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(series_router)
    api_v1.include_router(memory_router)
    api_v1.include_router(pipeline_router)
    api_v1.include_router(config_router)
    api_v1.include_router(doctor_router)
    api_v1.include_router(jobs_router)
    app.include_router(api_v1)

    # Rotas de páginas HTML
    app.include_router(dashboard_router)
    app.include_router(pipeline_page_router)
    app.include_router(series_page_router)
    app.include_router(settings_page_router)

    # Servir arquivos estáticos locais se o diretório existir
    static_dir = Path(__file__).parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    return app
