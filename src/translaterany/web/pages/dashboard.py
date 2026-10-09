"""Página inicial e Dashboard da Biblioteca."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from translaterany.web.pages import templates

router = APIRouter()


@router.get("/", response_class=Response)
def dashboard_page(request: Request) -> Response:
    series_svc = request.app.state.series_service
    series_list = series_svc.list_series()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"active_page": "dashboard", "series_list": series_list},
    )
