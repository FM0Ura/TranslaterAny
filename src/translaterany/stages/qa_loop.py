"""Etapa qa_loop: auditoria pós-redistribuição, algoritmo de blame e cascata de reprocessamento (M8).

Audita o texto gerado por redistribute_sentences usando checagens finais de sintaxe ASS,
limites de timing e regras severas de qualidade. Em caso de defeitos bloqueantes,
atribui culpa à etapa causadora no histórico de artefatos, executa correção pontual
em cascata com feedback e grava qa_report.json no diretório do episódio.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

from translaterany.checks.final_qa import check_ass_syntax, check_event_integrity, check_timing_bounds
from translaterany.checks.models import CheckEnv, Finding
from translaterany.checks.registry import run_line_checks
from translaterany.checks.snapshots import LineSource, build_sources, lines_for
from translaterany.config.model import AppConfig, ChecksConfig, QALoopOptions
from translaterany.llm.client import LLMRequest
from translaterany.memory.matching import load_memory_for_text
from translaterany.pipeline.gates import StageGate, is_blocking, severity_score
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope
from translaterany.pipeline.stage_metrics import count
from translaterany.pipeline.units import Episode, Series
from translaterany.quality.blame import attribute_blame
from translaterany.subtitles.classify import Classification
from translaterany.subtitles.linebreak import wrap_line
from translaterany.subtitles.merge import MergedUnitsDoc
from translaterany.subtitles.normalize import NormalizedDoc
from translaterany.subtitles.segments import marker_ids
from translaterany.subtitles.texts import UnitTexts
from translaterany.subtitles.translator import TranslationBatch
from translaterany.util.fs import atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_STAGES: tuple[str, ...] = (
    "translate_dialogue",
    "review_meaning",
    "colloquial",
    "treatment_consistency",
    "adapt",
    "orthography",
    "final_readthrough",
    "redistribute_sentences",
)

_OPTIONAL: tuple[str, ...] = ("merge_sentences", "scene_analysis", "consolidate_memory")


class QAReport(BaseModel):
    """Relatório estruturado de auditoria e intervenções do QA Loop."""

    model_config = ConfigDict(extra="ignore")

    rounds_executed: int = 0
    extra_calls_used: int = 0
    blame_summary: dict[str, int] = Field(default_factory=dict)
    interventions: list[dict[str, Any]] = Field(default_factory=list)
    edit_rate: float = 0.0
    unresolved_findings: list[dict[str, Any]] = Field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


def _get_episode_dir(ctx: StageContext) -> Path | None:
    """Recupera o diretório de artefatos do episódio para gravação de relatórios auxiliares."""
    if hasattr(ctx.output, "_directory") and ctx.output._directory:
        return Path(ctx.output._directory)
    if getattr(ctx, "store", None) is not None and getattr(ctx, "series", None) is not None:
        ep_key = ctx.episode.key if getattr(ctx, "episode", None) is not None else None
        return ctx.store.artifact_dir(ctx.series.key, ep_key)
    return None


@register_stage
class QALoopStage(Stage):
    """Etapa do Laço de QA final com auditoria, blame e cascata de reprocessamento."""

    name: ClassVar[str] = "qa_loop"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.EPISODE
    translates: ClassVar[bool] = True
    produces_texts: ClassVar[bool] = True
    produces_dialogue: ClassVar[bool] = True
    enabled_by_default: ClassVar[bool] = True
    Options: ClassVar[type[BaseModel]] = QALoopOptions

    def __init__(self, options: BaseModel | None = None) -> None:
        if options is None:
            opts = QALoopOptions()
        elif isinstance(options, QALoopOptions):
            opts = options
        else:
            opts = QALoopOptions.model_validate(options)
        super().__init__(opts)
        self.options: QALoopOptions = opts
        self.max_cpl = 42
        self.max_cps = 17.0
        self.limits = ChecksConfig()
        self.gate = StageGate()
        self.snapshot_stages: list[str] = list(DEFAULT_SNAPSHOT_STAGES)
        self.dialogue_input: str = "redistribute_sentences"
        self.inputs = ("normalize", "classify", *_OPTIONAL, *self.snapshot_stages)

    def bind_pipeline(self, previous: Sequence[Stage], app: AppConfig | None) -> None:
        names = [s.name for s in previous]
        self.snapshot_stages = [s.name for s in previous if s.produces_texts]
        if app is not None:
            self.limits = app.checks
            self.max_cpl = app.checks.max_cpl
            self.max_cps = app.checks.max_cps
            if hasattr(app, "gates"):
                self.gate = StageGate(config=app.gates)

        if "redistribute_sentences" in names:
            self.dialogue_input = "redistribute_sentences"
        else:
            dialogue = [s.name for s in previous if s.produces_dialogue]
            if dialogue:
                self.dialogue_input = dialogue[-1]

        optional = tuple(n for n in _OPTIONAL if n in names)
        self.inputs = ("normalize", "classify", *optional, *self.snapshot_stages)

    def cache_payload(self, series: Series | None, episode: Episode | None) -> Any:
        return {
            "options": self.options.model_dump(mode="json"),
            "snapshots": self.snapshot_stages,
            "dialogue_input": self.dialogue_input,
        }

    def run(self, ctx: StageContext) -> None:
        self.gate.reset()
        try:
            doc = ctx.inputs.json("normalize", NormalizedDoc)
        except Exception:
            doc = NormalizedDoc(encoding={"bom": False, "newline": "\n"}, format=[], events=[], units=[])

        try:
            classes = ctx.inputs.json("classify", Classification)
        except Exception:
            classes = Classification()

        merged: MergedUnitsDoc | None = None
        if "merge_sentences" in self.inputs:
            try:
                merged = ctx.inputs.json("merge_sentences", MergedUnitsDoc)
            except Exception:
                merged = None

        sources = build_sources(doc, classes, merged)

        series_key = ctx.series.key if getattr(ctx, "series", None) is not None else ""
        store = getattr(ctx, "store", None)
        text_all = "\n".join(sources[u].source for u in sources)
        glossary, characters = load_memory_for_text(store, series_key, text_all)
        env = CheckEnv(
            glossary=glossary,
            names=[[c.name, *c.aliases] for c in characters],
            limits=self.limits,
        )
        exemptions: set[str] = set()
        for term in glossary:
            exemptions.add(term.term)
            exemptions.add(term.translation)
            exemptions.update(term.aliases)
        for char in characters:
            exemptions.add(char.name)
            exemptions.update(char.aliases)

        history: list[tuple[str, Mapping[str, str]]] = []
        for name in self.snapshot_stages:
            if name in self.inputs:
                try:
                    texts = ctx.inputs.json(name, UnitTexts).texts
                    history.append((name, texts))
                except Exception:
                    continue

        input_texts: dict[str, str] = {}
        used_terms: dict[str, str] = {}
        if self.dialogue_input in self.inputs:
            try:
                dt = ctx.inputs.json(self.dialogue_input, UnitTexts)
                input_texts = dict(dt.texts)
                used_terms = dict(dt.used_terms)
            except Exception:
                pass

        if not input_texts and history:
            input_texts = dict(history[-1][1])

        current_texts = dict(input_texts)
        original_texts = dict(input_texts)

        for uid, txt in current_texts.items():
            if uid not in sources:
                sources[uid] = LineSource(source=txt, line_type="dialogue", style="", duration_ms=2000)

        events_by_unit: dict[str, list[Any]] = {}
        for ev in doc.events:
            if ev.unit:
                events_by_unit.setdefault(ev.unit, []).append(ev)

        def _audit_unit(uid: str, text: str) -> list[Finding]:
            findings: list[Finding] = []
            findings.extend(check_ass_syntax(uid, text, env))
            for ev in events_by_unit.get(uid, []):
                findings.extend(check_timing_bounds(uid, ev.start_ms, ev.end_ms, env))
            lines, _ = lines_for({uid: text}, sources)
            if lines:
                line_findings = run_line_checks(lines, env)
                findings.extend(f for f in line_findings if is_blocking(f) or f.severity == "error")
            return findings

        all_findings: list[Finding] = []
        integrity_findings = check_event_integrity(
            expected_count=len(sources),
            actual_count=len(current_texts),
            env=env,
        )
        all_findings.extend(integrity_findings)

        rounds_executed = 0
        extra_calls_used = 0
        blame_summary: dict[str, int] = {}
        interventions: list[dict[str, Any]] = []

        for _ in range(self.options.max_rounds):
            rounds_executed += 1
            failing_units: dict[str, list[Finding]] = {}
            for uid, txt in current_texts.items():
                findings = _audit_unit(uid, txt)
                if findings:
                    failing_units[uid] = findings
                    all_findings.extend(findings)

            if not failing_units:
                break

            budget_depleted = False
            recorded_uids = {item["unit_id"] for item in interventions}
            for uid, unit_findings in failing_units.items():
                if extra_calls_used >= self.options.max_extra_calls:
                    logger.warning(
                        "qa_loop: teto de chamadas extras (%d) atingido. Interrompendo intervenções.",
                        self.options.max_extra_calls,
                    )
                    for rem_uid, rem_findings in failing_units.items():
                        if rem_uid not in recorded_uids:
                            interventions.append(
                                {
                                    "unit_id": rem_uid,
                                    "blamed_stage": "budget_exhausted",
                                    "error": rem_findings[0].message,
                                    "outcome": "exhausted",
                                }
                            )
                            recorded_uids.add(rem_uid)
                    budget_depleted = True
                    break

                f_primary = unit_findings[0]
                blamed_stage = attribute_blame(uid, f_primary, history, env=env, sources=sources)
                blame_summary[blamed_stage] = blame_summary.get(blamed_stage, 0) + 1
                feedback = self.gate.generate_feedback(unit_findings)

                source_text = sources[uid].source if uid in sources else ""
                prev_text = ""
                stage_names = [n for n, _ in history]
                if blamed_stage in stage_names:
                    idx = stage_names.index(blamed_stage)
                    if idx > 0:
                        prev_text = history[idx - 1][1].get(uid, "")
                if not prev_text and blamed_stage != "translate_dialogue":
                    prev_text = current_texts.get(uid, "")

                from translaterany.languages.registry import LanguageRegistry

                src_lang = getattr(ctx, "source_language", None) or LanguageRegistry.resolve("en")
                tgt_lang = getattr(ctx, "target_language", None) or LanguageRegistry.resolve("pt-BR")
                src_code = src_lang.code.upper()
                tgt_code = tgt_lang.code.upper()
                tgt_name = "português do Brasil (PT-BR)" if tgt_lang.code == "pt-BR" else tgt_lang.name_pt

                prompt_parts: list[str] = []
                if source_text:
                    prompt_parts.append(f"TEXTO ORIGINAL ({src_code}):\n[{uid}] {source_text}")
                else:
                    prompt_parts.append(f"FALA:\n[{uid}]")

                if prev_text and prev_text != current_texts.get(uid, ""):
                    prompt_parts.append(f"ÚLTIMA TRADUÇÃO VÁLIDA ({tgt_code}):\n{prev_text}")

                prompt_parts.append(f"TEXTO ATUAL COM DEFEITO:\n{current_texts.get(uid, '')}")
                prompt_parts.append(feedback)

                prompt = "\n\n".join(prompt_parts)
                instructions = (
                    f"Você é um revisor especialista de legendas em {tgt_name}. "
                    "Sua tarefa é corrigir a fala indicada eliminando estritamente os erros apontados no feedback. "
                    "Mantenha todos os marcadores especiais como ⟦n⟧ intactos na ordem original. "
                    "Não inclua explicações ou notas adicionais, apenas a tradução corrigida."
                )
                req = LLMRequest(
                    model=getattr(self.options, "model", "review"),
                    instructions=instructions,
                    prompt=prompt,
                    output_type=TranslationBatch,
                    tag=f"qa_loop:{blamed_stage}:{uid}",
                )

                extra_calls_used += 1
                count(ctx, "qa_extra_calls")

                try:
                    res = ctx.llm.generate(req)
                    candidate = ""
                    if isinstance(res.output, TranslationBatch) and res.output.items:
                        for it in res.output.items:
                            if it.id == uid:
                                candidate = it.text
                                break
                        if not candidate:
                            candidate = res.output.items[0].text
                    elif hasattr(res.output, "text"):
                        candidate = res.output.text
                    elif isinstance(res.output, str):
                        candidate = res.output
                except Exception as exc:
                    logger.warning("qa_loop: chamada LLM falhou para %s: %s", uid, exc)
                    interventions.append(
                        {
                            "unit_id": uid,
                            "blamed_stage": blamed_stage,
                            "error": f_primary.message,
                            "outcome": "exhausted",
                        }
                    )
                    continue

                if not candidate or not candidate.strip():
                    interventions.append(
                        {
                            "unit_id": uid,
                            "blamed_stage": blamed_stage,
                            "error": f_primary.message,
                            "outcome": "exhausted",
                        }
                    )
                    continue

                if self.gate.is_oscillating(uid, candidate):
                    logger.info("qa_loop: oscilação detectada para %s; retentativa ignorada.", uid)
                    interventions.append(
                        {
                            "unit_id": uid,
                            "blamed_stage": blamed_stage,
                            "error": f_primary.message,
                            "outcome": "exhausted",
                        }
                    )
                    continue

                if "orthography" in self.snapshot_stages:
                    try:
                        from translaterany.stages.orthography import OrthographyStage

                        ortho = OrthographyStage()
                        ortho_result, _, _ = ortho.process_texts(
                            {uid: candidate},
                            sources=sources,
                            exemptions=exemptions,
                            limits=self.limits,
                        )
                        if uid in ortho_result:
                            candidate = ortho_result[uid]
                    except Exception as exc:
                        logger.debug("qa_loop: orthography ignorada para %s (%s)", uid, exc)

                wrapped_candidate = wrap_line(candidate, self.max_cpl)

                new_findings = _audit_unit(uid, wrapped_candidate)
                score_orig = severity_score(unit_findings)
                score_new = severity_score(new_findings)

                exp_markers = marker_ids(source_text)
                if (
                    sorted(marker_ids(wrapped_candidate)) != sorted(exp_markers)
                    or "⟦" in re.sub(r"⟦\d+⟧", "", wrapped_candidate)
                    or "⟧" in re.sub(r"⟦\d+⟧", "", wrapped_candidate)
                ):
                    score_new += 1000

                if score_new == 0:
                    current_texts[uid] = wrapped_candidate
                    interventions.append(
                        {
                            "unit_id": uid,
                            "blamed_stage": blamed_stage,
                            "error": f_primary.message,
                            "outcome": "fixed",
                        }
                    )
                elif score_new < score_orig:
                    current_texts[uid] = wrapped_candidate
                    interventions.append(
                        {
                            "unit_id": uid,
                            "blamed_stage": blamed_stage,
                            "error": f_primary.message,
                            "outcome": "exhausted",
                        }
                    )
                else:
                    interventions.append(
                        {
                            "unit_id": uid,
                            "blamed_stage": blamed_stage,
                            "error": f_primary.message,
                            "outcome": "reverted",
                        }
                    )

            if budget_depleted or extra_calls_used >= self.options.max_extra_calls:
                break

        changed = sum(1 for uid, txt in current_texts.items() if original_texts.get(uid) != txt)
        total = len(original_texts)
        edit_rate = round(changed / total, 4) if total > 0 else 0.0

        if edit_rate > self.options.warn_edit_rate_threshold:
            logger.warning(
                "Taxa de edição alta no QA Loop: %.1f%% das falas foram alteradas (limiar: %.1f%%)",
                edit_rate * 100,
                self.options.warn_edit_rate_threshold * 100,
            )

        final_unresolved: list[dict[str, Any]] = []
        for f in integrity_findings:
            final_unresolved.append(
                {
                    "unit_id": f.unit_id or "",
                    "check": f.check,
                    "severity": f.severity,
                    "message": f.message,
                }
            )
        for uid, txt in current_texts.items():
            rem = _audit_unit(uid, txt)
            for f in rem:
                final_unresolved.append(
                    {
                        "unit_id": f.unit_id,
                        "check": f.check,
                        "severity": f.severity,
                        "message": f.message,
                    }
                )

        report = QAReport(
            rounds_executed=rounds_executed,
            extra_calls_used=extra_calls_used,
            blame_summary=blame_summary,
            interventions=interventions,
            edit_rate=edit_rate,
            unresolved_findings=final_unresolved,
        )

        ep_dir = _get_episode_dir(ctx)
        if ep_dir is not None:
            ep_dir.mkdir(parents=True, exist_ok=True)
            report_path = ep_dir / "qa_report.json"
            atomic_write_text(report_path, json.dumps(report.to_dict(), indent=2, ensure_ascii=False))

        ctx.output.json(UnitTexts(texts=current_texts, used_terms=used_terms))
