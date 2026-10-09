"""Endpoints RESTful para visualização e customização do pipeline."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from translaterany.web.services.pipeline_service import PipelineGraph, PipelineService

router = APIRouter(tags=["pipeline"])


class ToggleRequest(BaseModel):
    stage_name: str
    enabled: bool


def get_pipeline_service(request: Request) -> PipelineService:
    return request.app.state.pipeline_service


@router.get("/pipeline", response_model=PipelineGraph)
def get_global_pipeline(request: Request) -> PipelineGraph:
    svc = get_pipeline_service(request)
    return svc.get_pipeline()


@router.put("/pipeline/toggle", response_model=PipelineGraph)
def toggle_global_stage(req: ToggleRequest, request: Request) -> PipelineGraph:
    svc = get_pipeline_service(request)
    svc.set_stage_enabled(req.stage_name, req.enabled)
    return svc.get_pipeline()


@router.get("/series/{key}/pipeline", response_model=PipelineGraph)
def get_series_pipeline(key: str, request: Request) -> PipelineGraph:
    svc = get_pipeline_service(request)
    return svc.get_pipeline(series_key=key)


@router.put("/series/{key}/pipeline/toggle", response_model=PipelineGraph)
def toggle_series_stage(key: str, req: ToggleRequest, request: Request) -> PipelineGraph:
    svc = get_pipeline_service(request)
    svc.set_stage_enabled(req.stage_name, req.enabled, series_key=key)
    return svc.get_pipeline(series_key=key)
