"""Endpoints RESTful para séries e episódios."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from translaterany.web.services.series_service import EpisodeSummary, SeriesDetail, SeriesService, SeriesSummary

router = APIRouter(prefix="/series", tags=["series"])


def get_series_service(request: Request) -> SeriesService:
    return request.app.state.series_service


@router.get("", response_model=list[SeriesSummary])
def list_series(request: Request) -> list[SeriesSummary]:
    svc = get_series_service(request)
    return svc.list_series()


@router.get("/{key}", response_model=SeriesDetail)
def get_series(key: str, request: Request) -> SeriesDetail:
    svc = get_series_service(request)
    detail = svc.get_series(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="Série não encontrada")
    return detail


@router.get("/{key}/episodes/{ep}", response_model=EpisodeSummary)
def get_episode(key: str, ep: str, request: Request) -> EpisodeSummary:
    svc = get_series_service(request)
    detail = svc.get_series(key)
    if detail is None:
        raise HTTPException(status_code=404, detail="Série não encontrada")
    episode = next((e for e in detail.episodes if e.key == ep), None)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episódio não encontrado")
    return episode


@router.get("/{key}/episodes/{ep}/subtitles")
def get_subtitles(key: str, ep: str, request: Request) -> dict[str, str]:
    svc = get_series_service(request)
    subs = svc.get_episode_subtitles(key, ep)
    if subs is None:
        raise HTTPException(status_code=404, detail="Legendas não encontradas para o episódio")
    return {"content": subs}


@router.get("/{key}/episodes/{ep}/qa_report")
def get_qa_report(key: str, ep: str, request: Request) -> dict[str, Any]:
    svc = get_series_service(request)
    report = svc.get_qa_report(key, ep)
    if report is None:
        raise HTTPException(status_code=404, detail="Relatório de QA não encontrado")
    return report
