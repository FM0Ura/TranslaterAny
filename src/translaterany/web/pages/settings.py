"""Página HTML de configurações da aplicação."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from translaterany.web.pages import templates

router = APIRouter()


@router.get("/settings", response_class=Response)
def settings_page(request: Request) -> Response:
    cfg_svc = request.app.state.config_service
    config = cfg_svc.get_config()
    return templates.TemplateResponse(
        request=request,
        name="settings.html",
        context={"active_page": "settings", "config": config},
    )
