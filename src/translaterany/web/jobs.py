"""Gerenciador de tarefas em background com suporte a pausa, cancelamento e streaming SSE."""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from translaterany.config.loader import default_config_path, default_data_dir


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobCancelledError(Exception):
    """Lançada quando uma tarefa é cancelada pelo usuário."""


class JobControlToken:
    """Token de sincronização thread-safe para pausa cooperativa e cancelamento de jobs."""

    def __init__(self) -> None:
        self.pause_event = threading.Event()
        self.pause_event.set()  # Começa não-pausado
        self.cancel_event = threading.Event()

    def pause(self) -> None:
        self.pause_event.clear()

    def resume(self) -> None:
        self.pause_event.set()

    def cancel(self) -> None:
        self.cancel_event.set()
        self.pause_event.set()  # Desbloqueia wait se estava pausado

    def check_point(self) -> None:
        if self.cancel_event.is_set():
            raise JobCancelledError("Tarefa cancelada pelo usuário.")
        while not self.pause_event.is_set():
            if self.cancel_event.is_set():
                raise JobCancelledError("Tarefa cancelada pelo usuário.")
            self.pause_event.wait(timeout=0.2)


class JobRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    series_key: str
    series_name: str = ""
    episode_key: str | None = None
    stage_from: str | None = None
    status: JobStatus = JobStatus.PENDING
    current_stage: str = ""
    current_unit: str = ""
    progress_percent: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None


class JobLogHandler(logging.Handler):
    """Handler de logging que repassa mensagens do pipeline para o JobManager como SSE."""

    def __init__(self, manager: JobManager, job_id: str) -> None:
        super().__init__()
        self.manager = manager
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.manager.publish_event(
                self.job_id,
                event="log",
                data={
                    "level": record.levelname,
                    "message": msg,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        except Exception:
            pass


class JobManager:
    """Fila de jobs assíncrona com execução serial pesada (max_workers=1) para poupar GPU."""

    def __init__(
        self,
        data_dir: Path | None = None,
        config_path: Path | None = None,
        start_worker: bool = True,
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self._jobs: dict[str, JobRecord] = {}
        self._tokens: dict[str, JobControlToken] = {}
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._history: dict[str, list[dict[str, Any]]] = {}
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="translaterany-worker")
        self._worker_task: asyncio.Task | None = None
        self._running_job_id: str | None = None

        if start_worker:
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._worker_loop())
            except RuntimeError:
                pass

    def enqueue(
        self,
        series_key: str,
        episode_key: str | None = None,
        from_stage: str | None = None,
        force: bool = False,
    ) -> JobRecord:
        job = JobRecord(
            series_key=series_key,
            series_name=series_key.replace("-", " ").title(),
            episode_key=episode_key,
            stage_from=from_stage,
            status=JobStatus.PENDING,
        )
        self._jobs[job.id] = job
        self._tokens[job.id] = JobControlToken()
        self._subscribers[job.id] = []
        self._history[job.id] = []

        self._queue.put_nowait(job.id)
        self.publish_event(
            job.id,
            event="status",
            data={"status": job.status.value, "job_id": job.id},
        )
        return job

    def get_job(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[JobRecord]:
        return list(self._jobs.values())

    def pause(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        token = self._tokens.get(job_id)
        if not job or not token:
            return False

        if job.status in (JobStatus.PENDING, JobStatus.RUNNING):
            token.pause()
            job.status = JobStatus.PAUSED
            self.publish_event(
                job_id,
                event="status",
                data={"status": job.status.value, "job_id": job.id},
            )
            return True
        return False

    def resume(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        token = self._tokens.get(job_id)
        if not job or not token:
            return False

        if job.status == JobStatus.PAUSED:
            token.resume()
            if self._running_job_id == job_id:
                job.status = JobStatus.RUNNING
            else:
                job.status = JobStatus.PENDING
            self.publish_event(
                job_id,
                event="status",
                data={"status": job.status.value, "job_id": job.id},
            )
            return True
        return False

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        token = self._tokens.get(job_id)
        if not job or not token:
            return False

        if job.status not in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            token.cancel()
            job.status = JobStatus.CANCELLED
            job.finished_at = datetime.now(UTC)
            self.publish_event(
                job_id,
                event="status",
                data={"status": job.status.value, "job_id": job.id},
            )
            return True
        return False

    def publish_event(self, job_id: str, event: str, data: dict[str, Any]) -> None:
        payload = {"event": event, "data": data}
        if job_id not in self._history:
            self._history[job_id] = []
        self._history[job_id].append(payload)

        subscribers = self._subscribers.get(job_id, [])
        for q in subscribers:
            try:
                q.put_nowait(payload)
            except Exception:
                pass

    async def subscribe_events(self, job_id: str) -> AsyncGenerator[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(q)

        # Envia histórico inicial
        for prev in self._history.get(job_id, []):
            yield prev

        try:
            while True:
                item = await q.get()
                yield item
        finally:
            if job_id in self._subscribers and q in self._subscribers[job_id]:
                self._subscribers[job_id].remove(q)

    async def _worker_loop(self) -> None:
        while True:
            try:
                job_id = await self._queue.get()
                job = self._jobs.get(job_id)
                token = self._tokens.get(job_id)
                if not job or not token or job.status == JobStatus.CANCELLED:
                    continue

                token.check_point()
                self._running_job_id = job_id
                job.status = JobStatus.RUNNING
                job.started_at = datetime.now(UTC)
                self.publish_event(
                    job_id,
                    event="status",
                    data={"status": job.status.value, "job_id": job.id},
                )

                loop = asyncio.get_running_loop()
                try:
                    await loop.run_in_executor(self._executor, self._run_job_sync, job, token)
                    if job.status == JobStatus.RUNNING:
                        job.status = JobStatus.COMPLETED
                        job.progress_percent = 100.0
                except JobCancelledError:
                    job.status = JobStatus.CANCELLED
                except Exception as exc:
                    job.status = JobStatus.FAILED
                    job.error = str(exc)
                    self.publish_event(
                        job_id,
                        event="error",
                        data={"message": str(exc)},
                    )
                finally:
                    job.finished_at = datetime.now(UTC)
                    self._running_job_id = None
                    self.publish_event(
                        job_id,
                        event="status",
                        data={"status": job.status.value, "job_id": job.id},
                    )
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1.0)

    def _run_job_sync(self, job: JobRecord, token: JobControlToken) -> None:
        """Execução síncrona dentro da thread pool."""
        token.check_point()
        # Aqui o pipeline real pode ser chamado se desejado.
        token.check_point()

    async def shutdown(self) -> None:
        """Cancela jobs ativos de forma cooperativa, encerra o loop do worker e o executor."""
        for job_id, job in list(self._jobs.items()):
            if job.status in (JobStatus.PENDING, JobStatus.RUNNING, JobStatus.PAUSED):
                self.cancel(job_id)

        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        self._executor.shutdown(wait=False, cancel_futures=True)

