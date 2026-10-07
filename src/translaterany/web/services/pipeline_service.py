"""Serviço para inspeção e customização do Grafo de Pipeline (global e por série)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from translaterany.config.loader import default_config_path, default_data_dir
from translaterany.pipeline.registry import REGISTRY
from translaterany.stages import DEFAULT_PIPELINE

STAGE_METADATA: dict[str, dict[str, str]] = {
    "inventory": {"label": "Inventário de Faixas", "desc": "Mapeia faixas de áudio e legendas nos arquivos MKV"},
    "metadata": {"label": "Metadados AniList", "desc": "Busca pôster, sinopse e dados da série no AniList"},
    "select_track": {"label": "Seleção de Faixa", "desc": "Seleciona a melhor faixa de legenda em inglês"},
    "extract": {"label": "Extração de Mídia", "desc": "Extrai faixas de legenda e áudio do container MKV"},
    "ocr": {"label": "OCR de Imagem", "desc": "Reconhecimento ótico para legendas PGS/VobSub"},
    "normalize": {"label": "Normalização", "desc": "Converte e padroniza formatos para ASS/SRT unificado"},
    "extract_voice": {"label": "Diarização de Áudio", "desc": "Identifica falantes e vetores de voz com PyAnnote"},
    "classify": {"label": "Classificação", "desc": "Separa diálogos, sinais/placas, canções e créditos"},
    "extract_terms": {"label": "Extração de Termos", "desc": "Detecta termos-chave, nomes próprios e vocabulário"},
    "consolidate_memory": {"label": "Consolidação de Memória", "desc": "Unifica personagens e termos no YAML da série"},
    "consolidate_voice_bank": {"label": "Consolidação de Voz", "desc": "Funde perfis acústicos no voice_bank.json"},
    "translation_memory": {"label": "Memória de Tradução", "desc": "Busca traduções prévias e correspondências exatas"},
    "merge_sentences": {"label": "Junção de Frases", "desc": "Agrupa quebras de fala em sentenças completas"},
    "scene_analysis": {"label": "Análise de Cena", "desc": "Gera contexto cênico e pistas visuais para os diálogos"},
    "translate_dialogue": {"label": "Tradução de Diálogos", "desc": "Traduz diálogos EN → PT-BR contextualizados"},
    "translate_signs": {"label": "Tradução de Sinais", "desc": "Traduz placas, títulos e textos em tela"},
    "translate_songs": {"label": "Tradução de Músicas", "desc": "Traduz abertura (OP) e encerramento (ED)"},
    "review_meaning": {"label": "Revisão Semântica", "desc": "Verifica precisão da tradução contra o original"},
    "colloquial": {"label": "Adaptação Coloquial", "desc": "Ajusta naturalidade, gírias e fluência em PT-BR"},
    "treatment_consistency": {"label": "Consistência de Tratamento", "desc": "Valida pronomes e vocativos"},
    "adapt": {"label": "Adaptação Cultural", "desc": "Refina trocadilhos e referências culturais"},
    "orthography": {"label": "Correção Ortográfica", "desc": "Verificação gramatical via LanguageTool"},
    "final_readthrough": {"label": "Leitura Final", "desc": "Polimento final da legenda em bloco contínuo"},
    "redistribute_sentences": {"label": "Redistribuição de Falas", "desc": "Realinha o texto traduzido aos tempos"},
    "qa_loop": {"label": "Ciclo de QA Automático", "desc": "Valida e corrige limites de CPS, CPL e sobreposição"},
    "write": {"label": "Geração de Legenda", "desc": "Grava o arquivo final de legendas ASS/SRT"},
    "publish": {"label": "Publicação", "desc": "Copia legendas prontas para a biblioteca com sufixo"},
    "remux": {"label": "Remux em MKV", "desc": "Embute nova legenda como faixa padrão no MKV"},
    "quality_checks": {"label": "Métricas de Qualidade", "desc": "Calcula pontuações de QA e conformidade"},
}


class StageNode(BaseModel):
    name: str
    label: str
    description: str
    scope: str
    enabled: bool
    inputs: list[str] = Field(default_factory=list)
    produces: list[str] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class PipelineGraph(BaseModel):
    stages: list[StageNode] = Field(default_factory=list)
    is_customized: bool = False


class PipelineService:
    """Inspeciona o registro de etapas e gerencia ativação/desativação de nós do pipeline."""

    def __init__(self, config_path: Path | None = None, data_dir: Path | None = None) -> None:
        self.config_path = Path(config_path) if config_path is not None else default_config_path()
        self.data_dir = Path(data_dir) if data_dir is not None else default_data_dir()

    def _get_enabled_stages(self, series_key: str | None = None) -> tuple[list[str], bool]:
        """Retorna a lista de etapas ativas e um booleano indicando se é customizado."""
        # Verifica series.toml se series_key foi informado
        if series_key:
            series_dir = self.data_dir / "series" / series_key
            series_toml = series_dir / "series.toml"
            if series_toml.is_file():
                try:
                    data = tomllib.loads(series_toml.read_text(encoding="utf-8"))
                    if "pipeline" in data and "stages" in data["pipeline"]:
                        return list(data["pipeline"]["stages"]), True
                except Exception:
                    pass

        # Verifica config.toml
        if self.config_path.is_file():
            try:
                data = tomllib.loads(self.config_path.read_text(encoding="utf-8"))
                if "pipeline" in data and "stages" in data["pipeline"]:
                    return list(data["pipeline"]["stages"]), False
            except Exception:
                pass

        # Padrão: todas do DEFAULT_PIPELINE exceto remux
        default_active = [s for s in DEFAULT_PIPELINE if s != "remux"]
        return default_active, False

    def get_pipeline(self, series_key: str | None = None) -> PipelineGraph:
        enabled_stages, is_customized = self._get_enabled_stages(series_key)
        enabled_set = set(enabled_stages)

        stages: list[StageNode] = []
        for name in DEFAULT_PIPELINE:
            meta = STAGE_METADATA.get(name, {"label": name, "desc": ""})
            scope = "episode"
            inputs: list[str] = []
            if name in REGISTRY:
                cls = REGISTRY.get(name)
                scope = cls.scope.value if hasattr(cls.scope, "value") else str(cls.scope)
                inputs = list(cls.inputs) if hasattr(cls, "inputs") and cls.inputs else []

            stages.append(
                StageNode(
                    name=name,
                    label=meta["label"],
                    description=meta["desc"],
                    scope=scope,
                    enabled=(name in enabled_set),
                    inputs=inputs,
                )
            )

        return PipelineGraph(stages=stages, is_customized=is_customized)

    def set_stage_enabled(self, stage_name: str, enabled: bool, series_key: str | None = None) -> None:
        current_enabled, _ = self._get_enabled_stages(series_key)
        enabled_set = set(current_enabled)

        if enabled:
            enabled_set.add(stage_name)
        else:
            enabled_set.discard(stage_name)

        # Preserva a ordem canônica do DEFAULT_PIPELINE
        new_active = [s for s in DEFAULT_PIPELINE if s in enabled_set]

        if series_key:
            series_dir = self.data_dir / "series" / series_key
            series_dir.mkdir(parents=True, exist_ok=True)
            series_toml = series_dir / "series.toml"
            self._write_pipeline_to_toml(series_toml, new_active)
        else:
            self._write_pipeline_to_toml(self.config_path, new_active)

    def _write_pipeline_to_toml(self, path: Path, active_stages: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = ""
        if path.is_file():
            content = path.read_text(encoding="utf-8")

        stages_repr = "[\n" + ",\n".join(f'    "{s}"' for s in active_stages) + "\n]"
        pipeline_block = f"[pipeline]\nstages = {stages_repr}\n"

        if "[pipeline]" in content:
            # Substitui o bloco [pipeline] existente
            import re
            pattern = re.compile(r"\[pipeline\][^\[]*", re.MULTILINE | re.DOTALL)
            new_content = pattern.sub(pipeline_block, content)
            path.write_text(new_content, encoding="utf-8")
        else:
            # Adiciona ao final
            sep = "\n\n" if content.strip() else ""
            path.write_text(content.rstrip() + sep + pipeline_block, encoding="utf-8")
