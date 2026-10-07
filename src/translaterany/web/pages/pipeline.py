"""Páginas HTML do Grafo Visual do Pipeline."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from translaterany.web.pages import templates

router = APIRouter()


@router.get("/pipeline", response_class=Response)
def global_pipeline_page(request: Request) -> Response:
    pipe_svc = request.app.state.pipeline_service
    graph = pipe_svc.get_pipeline()

    return templates.TemplateResponse(
        request=request,
        name="pipeline.html",
        context={"active_page": "pipeline", "graph": graph, "series_key": None},
    )


@router.get("/series/{key}/pipeline", response_class=Response)
def series_pipeline_page(key: str, request: Request) -> Response:
    pipe_svc = request.app.state.pipeline_service
    graph = pipe_svc.get_pipeline(series_key=key)

    return templates.TemplateResponse(
        request=request,
        name="pipeline.html",
        context={"active_page": "dashboard", "graph": graph, "series_key": key},
    )
