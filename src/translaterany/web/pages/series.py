"""Páginas HTML de detalhes da série, editor de memórias e inspetor de episódios."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response

from translaterany.web.pages import templates

router = APIRouter()


@router.get("/series/{key}", response_class=Response)
def series_detail_page(key: str, request: Request) -> Response:
    series_svc = request.app.state.series_service
    detail = series_svc.get_series(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="Série não encontrada")

    return templates.TemplateResponse(
        request=request,
        name="series.html",
        context={"active_page": "dashboard", "series": detail},
    )


@router.get("/series/{key}/memory", response_class=Response)
def memory_editor_page(key: str, request: Request) -> Response:
    mem_svc = request.app.state.memory_service
    memory_doc = mem_svc.load_memory(key)

    return templates.TemplateResponse(
        request=request,
        name="memory.html",
        context={"active_page": "dashboard", "series_key": key, "memory": memory_doc},
    )


@router.get("/series/{key}/episodes/{ep}", response_class=Response)
def episode_inspector_page(key: str, ep: str, request: Request) -> Response:
    series_svc = request.app.state.series_service
    detail = series_svc.get_series(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="Série não encontrada")

    subs = series_svc.get_episode_subtitles(key, ep)
    qa_report = series_svc.get_qa_report(key, ep)

    return templates.TemplateResponse(
        request=request,
        name="inspector.html",
        context={
            "active_page": "dashboard",
            "series_key": key,
            "episode_key": ep,
            "subtitles_text": subs,
            "qa_report": qa_report,
        },
    )
