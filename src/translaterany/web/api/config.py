"""Endpoints RESTful para configuração da aplicação."""

from __future__ import annotations

from fastapi import APIRouter, Request

from translaterany.config.model import AppConfig
from translaterany.web.services.config_service import ConfigService

router = APIRouter(prefix="/config", tags=["config"])


def get_config_service(request: Request) -> ConfigService:
    return request.app.state.config_service


@router.get("", response_model=AppConfig)
def get_config(request: Request) -> AppConfig:
    svc = get_config_service(request)
    return svc.get_config()


@router.put("", response_model=AppConfig)
def update_config(config: AppConfig, request: Request) -> AppConfig:
    svc = get_config_service(request)
    svc.save_config(config)
    return svc.get_config()
