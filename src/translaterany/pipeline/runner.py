"""Runner: executa as etapas por etapa (todas as unidades passam pela etapa N antes da N+1)."""

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from translaterany.llm.client import LLMClient
from translaterany.pipeline.artifacts import (
    ArtifactStore,
    InputError,
    InputReader,
    ManifestSet,
    OutputWriter,
)
from translaterany.pipeline.cache import combine_hashes, compute_key
from translaterany.pipeline.lock import SeriesLock
from translaterany.pipeline.manifest import StageRecord
from translaterany.pipeline.stage import SkipEpisode, Stage, StageContext, StageScope
from translaterany.pipeline.units import Episode, Series
from translaterany.util.fs import cleanup_tmp, file_sha256, fingerprint

type Outcome = Literal["done", "cached", "failed", "skipped"]
type ProgressFn = Callable[[str, int, int], None]


@dataclass
class StageCounts:
    done: int = 0
    cached: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass
class RunSummary:
    stages: dict[str, StageCounts] = field(default_factory=dict)

    @property
    def failed(self) -> bool:
        return any(c.failed for c in self.stages.values())

    @property
    def status(self) -> str:
        return "failed" if self.failed else "success"


class Runner:
    def __init__(
        self,
        stages: Sequence[Stage],
        store: ArtifactStore,
        llm: LLMClient,
        log: logging.Logger | None = None,
        on_progress: ProgressFn | None = None,
    ) -> None:
        self.stages = list(stages)
        self.store = store
        self.llm = llm
        self.log = log or logging.getLogger("translaterany.runner")
        self.on_progress = on_progress
        self._scopes: dict[str, StageScope] = {}
        for stage in self.stages:
            if stage.reads_source and stage.scope is StageScope.SERIES:
                raise ValueError(f"etapa '{stage.name}': reads_source não é suportado em etapas de série")
            for name in stage.inputs:
                if name not in self._scopes:
                    raise ValueError(f"etapa '{stage.name}' depende de '{name}', que não vem antes dela")
            self._scopes[stage.name] = stage.scope

    def run(self, series: Series, episodes: Sequence[Episode], *, force: bool = False) -> RunSummary:
        with SeriesLock(self.store.lock_path(series.key)):
            cleanup_tmp(self.store.series_dir(series.key))
            self.store.write_series_info(series)
            manifests = ManifestSet(self.store, series, episodes)
            for manifest in [manifests.series, *manifests.episodes.values()]:
                if manifest.status == "failed":  # falhas anteriores tentam de novo
                    manifest.status = "ok"
                elif force and manifest.status == "skipped":  # --force reabre os pulados
                    manifest.status = "ok"
                    manifest.skip_reason = None
            summary = RunSummary({s.name: StageCounts() for s in self.stages})
            fingerprints: dict[str, str] = {}

            for stage in self.stages:
                if manifests.series.status != "ok":
                    break
                units: list[Episode | None]
                if stage.scope is StageScope.SERIES:
                    units = [None]
                else:
                    units = [ep for ep in episodes if manifests.get(ep).status == "ok"]
                counts = summary.stages[stage.name]
                for index, unit in enumerate(units, start=1):
                    outcome = self._run_unit(stage, series, unit, episodes, manifests, fingerprints, force)
                    setattr(counts, outcome, getattr(counts, outcome) + 1)
                    if self.on_progress:
                        self.on_progress(stage.name, index, len(units))
            return summary

    def _input_hashes(
        self,
        stage: Stage,
        episode: Episode | None,
        episodes: Sequence[Episode],
        manifests: ManifestSet,
    ) -> dict[str, str]:
        hashes: dict[str, str] = {}
        for name in stage.inputs:
            if self._scopes[name] is StageScope.SERIES:
                hashes[name] = _done_hash(manifests.series.stages.get(name), name)
            elif episode is not None:
                hashes[name] = _done_hash(manifests.get(episode).stages.get(name), name)
            else:
                pairs = {
                    ep.key: _done_hash(manifests.get(ep).stages.get(name), name)
                    for ep in episodes
                    if manifests.get(ep).status == "ok"
                }
                hashes[name] = combine_hashes(pairs)
        return hashes

    def _run_unit(
        self,
        stage: Stage,
        series: Series,
        episode: Episode | None,
        episodes: Sequence[Episode],
        manifests: ManifestSet,
        fingerprints: dict[str, str],
        force: bool = False,
    ) -> Outcome:
        manifest = manifests.get(episode)
        unit_name = episode.key if episode else series.key
        directory = self.store.artifact_dir(series.key, episode.key if episode else None)
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        try:  # origem ilegível ou artefato inacessível falham só esta unidade
            source_fp = None
            if stage.reads_source and episode is not None:
                if episode.key not in fingerprints:
                    fingerprints[episode.key] = fingerprint(episode.source)
                source_fp = fingerprints[episode.key]
            episode_set = [ep.key for ep in episodes] if episode is None else None
            key = compute_key(
                stage,
                self._input_hashes(stage, episode, episodes, manifests),
                source_fp,
                episode_set,
                stage.cache_payload(series, episode),
            )
            record = manifest.stages.get(stage.name)
            previous = None
            if record is not None and record.status == "done" and record.artifact is not None:
                candidate = directory / record.artifact
                previous = candidate if candidate.exists() else None
            writer = OutputWriter(directory, stage.name)
            ctx = self._context(stage, series, episode, episodes, manifests, writer, previous, force)
            if (
                previous is not None
                and record is not None
                and record.key == key
                and file_sha256(previous) == record.artifact_hash
                and stage.verify_cached(ctx, previous)
            ):
                self.log.debug("%s: %s em cache", stage.name, unit_name)
                return "cached"
        except Exception as exc:
            return self._fail(stage, manifests, episode, unit_name, exc, started, t0)

        error: Exception | None = None
        digest = ""
        try:
            stage.run(ctx)
            if writer.path is None:
                raise RuntimeError(f"a etapa '{stage.name}' terminou sem gravar artefato")
            digest = file_sha256(writer.path)
        except SkipEpisode as exc:
            if episode is None:
                error = RuntimeError(f"SkipEpisode não é permitido em etapa de série: {exc.reason}")
            else:
                manifest.status = "skipped"
                manifest.skip_reason = exc.reason
                manifests.save(episode)
                self.log.info("%s: %s pulado — %s", stage.name, unit_name, exc.reason)
                return "skipped"
        except Exception as exc:  # KeyboardInterrupt não é Exception: propaga
            error = exc
        return self._finish(stage, manifests, episode, unit_name, error, digest, key, writer, started, t0)

    def _context(
        self,
        stage: Stage,
        series: Series,
        episode: Episode | None,
        episodes: Sequence[Episode],
        manifests: ManifestSet,
        writer: OutputWriter,
        previous: Path | None,
        force: bool,
    ) -> StageContext:
        return StageContext(
            series=series,
            episode=episode,
            episodes=episodes,
            inputs=InputReader(
                self.store,
                series,
                episode,
                episodes,
                stage.inputs,
                {n: self._scopes[n].value for n in stage.inputs},
                manifests,
            ),
            output=writer,
            llm=self.llm,
            log=self.log.getChild(stage.name),
            previous_output=previous,
            force=force,
            store=self.store,
        )

    def _finish(
        self,
        stage: Stage,
        manifests: ManifestSet,
        episode: Episode | None,
        unit_name: str,
        error: Exception | None,
        digest: str,
        key: str,
        writer: OutputWriter,
        started: datetime,
        t0: float,
    ) -> Outcome:
        manifest = manifests.get(episode)

        if error is not None:
            return self._fail(stage, manifests, episode, unit_name, error, started, t0)

        assert writer.written is not None
        manifest.stages[stage.name] = StageRecord(
            status="done",
            key=key,
            artifact=writer.written,
            artifact_hash=digest,
            started_at=started,
            finished_at=datetime.now(UTC),
            duration_s=round(time.perf_counter() - t0, 3),
        )
        manifests.save(episode)
        return "done"

    def _fail(
        self,
        stage: Stage,
        manifests: ManifestSet,
        episode: Episode | None,
        unit_name: str,
        error: Exception,
        started: datetime,
        t0: float,
    ) -> Outcome:
        self.log.error("%s: falha em %s — %s: %s", stage.name, unit_name, type(error).__name__, error)
        self.log.debug("traceback da falha em %s", unit_name, exc_info=error)  # arquivo de log / --verbose
        manifest = manifests.get(episode)
        manifest.stages[stage.name] = StageRecord(
            status="failed",
            started_at=started,
            finished_at=datetime.now(UTC),
            duration_s=round(time.perf_counter() - t0, 3),
            error=f"{type(error).__name__}: {error}",
        )
        manifest.status = "failed"
        manifests.save(episode)
        return "failed"


def _done_hash(record: StageRecord | None, name: str) -> str:
    if record is None or record.status != "done" or record.artifact_hash is None:
        raise InputError(f"entrada '{name}' ainda não foi produzida")
    return record.artifact_hash


class PipelineRunner:
    """Helper de conveniência para executar o pipeline em uma série."""

    def __init__(
        self,
        config: object = None,
        client: LLMClient | None = None,
        store: ArtifactStore | None = None,
    ) -> None:
        from translaterany.config.loader import ResolvedConfig, _build_stages, default_data_dir, load_config
        from translaterany.config.model import AppConfig, PipelineConfig
        from translaterany.llm.fake import FakeLLM
        from translaterany.pipeline.registry import REGISTRY
        from translaterany.stages import DEFAULT_PIPELINE

        if isinstance(config, ResolvedConfig):
            self.stages = config.stages
            self.data_dir = config.data_dir
        elif isinstance(config, AppConfig):
            cfg_copy = config.model_copy(deep=True)
            if cfg_copy.pipeline is None:
                cfg_copy.pipeline = PipelineConfig(stages=list(DEFAULT_PIPELINE))
            stages = _build_stages(cfg_copy, REGISTRY, "AppConfig")
            data_dir = cfg_copy.general.data_dir or default_data_dir()
            self.stages = tuple(stages)
            self.data_dir = Path(data_dir).expanduser()
        else:
            resolved = load_config()
            self.stages = resolved.stages
            self.data_dir = resolved.data_dir

        self._store = store
        self.client = client if client is not None else FakeLLM()

    def run_series(self, path: Path, *, force: bool = False) -> RunSummary:
        from translaterany.library import discover

        series, episodes = discover(path)
        store = self._store or ArtifactStore(self.data_dir)
        runner = Runner(self.stages, store, self.client)
        return runner.run(series, episodes, force=force)
