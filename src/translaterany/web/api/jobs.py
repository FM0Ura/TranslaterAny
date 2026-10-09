"""Endpoints RESTful para gerenciamento e streaming de jobs em tempo real."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from translaterany.web.jobs import JobManager, JobRecord

router = APIRouter(prefix="/jobs", tags=["jobs"])


class RunJobRequest(BaseModel):
    series_key: str
    episode_key: str | None = None
    from_stage: str | None = None
    force: bool = False


def get_job_manager(request: Request) -> JobManager:
    return request.app.state.job_manager


@router.get("", response_model=list[JobRecord])
def list_jobs(request: Request) -> list[JobRecord]:
    manager = get_job_manager(request)
    return manager.list_jobs()


@router.post("/run", response_model=JobRecord)
def run_job(req: RunJobRequest, request: Request) -> JobRecord:
    manager = get_job_manager(request)
    return manager.enqueue(
        series_key=req.series_key,
        episode_key=req.episode_key,
        from_stage=req.from_stage,
        force=req.force,
    )


@router.get("/{id}", response_model=JobRecord)
def get_job(id: str, request: Request) -> JobRecord:
    manager = get_job_manager(request)
    job = manager.get_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job


@router.post("/{id}/pause", response_model=JobRecord)
def pause_job(id: str, request: Request) -> JobRecord:
    manager = get_job_manager(request)
    ok = manager.pause(id)
    job = manager.get_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if not ok:
        raise HTTPException(status_code=400, detail="Não foi possível pausar o job")
    return job


@router.post("/{id}/resume", response_model=JobRecord)
def resume_job(id: str, request: Request) -> JobRecord:
    manager = get_job_manager(request)
    ok = manager.resume(id)
    job = manager.get_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if not ok:
        raise HTTPException(status_code=400, detail="Não foi possível retomar o job")
    return job


@router.post("/{id}/cancel", response_model=JobRecord)
def cancel_job(id: str, request: Request) -> JobRecord:
    manager = get_job_manager(request)
    ok = manager.cancel(id)
    job = manager.get_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    if not ok:
        raise HTTPException(status_code=400, detail="Não foi possível cancelar o job")
    return job


@router.get("/{id}/stream")
async def stream_job_events(id: str, request: Request) -> StreamingResponse:
    manager = get_job_manager(request)
    job = manager.get_job(id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job não encontrado")

    async def event_generator():
        async for evt in manager.subscribe_events(id):
            evt_name = evt.get("event", "message")
            data_str = json.dumps(evt.get("data", {}), ensure_ascii=False)
            yield f"event: {evt_name}\ndata: {data_str}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
