import asyncio

import pytest

from translaterany.web.jobs import JobManager, JobStatus


@pytest.mark.anyio
async def test_job_manager_enqueue_and_status() -> None:
    manager = JobManager(start_worker=False)
    job = manager.enqueue(series_key="test-series", episode_key="S01E01")
    assert job.status == JobStatus.PENDING
    assert job.id is not None
    assert job.series_key == "test-series"
    assert job.episode_key == "S01E01"

    # Testa pausa e cancelamento
    assert manager.pause(job.id) is True
    rec = manager.get_job(job.id)
    assert rec is not None
    assert rec.status == JobStatus.PAUSED

    assert manager.resume(job.id) is True
    rec = manager.get_job(job.id)
    assert rec is not None
    assert rec.status == JobStatus.PENDING

    assert manager.cancel(job.id) is True
    rec = manager.get_job(job.id)
    assert rec is not None
    assert rec.status == JobStatus.CANCELLED


@pytest.mark.anyio
async def test_job_manager_list_jobs() -> None:
    manager = JobManager(start_worker=False)
    j1 = manager.enqueue(series_key="series-1")
    j2 = manager.enqueue(series_key="series-2")

    jobs = manager.list_jobs()
    assert len(jobs) == 2
    assert {j.id for j in jobs} == {j1.id, j2.id}


@pytest.mark.anyio
async def test_job_manager_event_streaming() -> None:
    manager = JobManager(start_worker=False)
    job = manager.enqueue(series_key="series-1")

    # Publica evento de teste
    manager.publish_event(job.id, event="log", data={"message": "Iniciando etapa"})
    manager.publish_event(job.id, event="progress", data={"percent": 50.0, "stage": "scene_analysis"})

    events = []
    # Consome da stream do job
    stream = manager.subscribe_events(job.id)
    # Pega os 3 eventos publicados (status inicial + log + progress)
    async def collect() -> None:
        async for evt in stream:
            events.append(evt)
            if len(events) >= 3:
                break

    await asyncio.wait_for(collect(), timeout=2.0)
    assert len(events) == 3
    assert events[0]["event"] == "status"
    assert events[0]["data"]["status"] == "pending"
    assert events[1]["event"] == "log"
    assert events[1]["data"]["message"] == "Iniciando etapa"
    assert events[2]["event"] == "progress"
    assert events[2]["data"]["percent"] == 50.0
