"""Etapa consolidate_voice_bank: consolidação do banco de vozes da série (voice_bank.json)."""

from __future__ import annotations

import logging
from typing import ClassVar, Literal

from translaterany.media.audio.artifacts import VoiceEmbeddingsArtifact
from translaterany.media.audio.clustering import cluster_acoustic_segments
from translaterany.media.audio.voice_bank import VoiceBankDoc, VoiceProfile
from translaterany.memory.artifacts import MetadataArtifact
from translaterany.memory.models import CharacterEntry
from translaterany.pipeline.registry import register_stage
from translaterany.pipeline.stage import Stage, StageContext, StageScope

logger = logging.getLogger(__name__)


@register_stage
class ConsolidateVoiceBankStage(Stage):
    """Etapa de série que agrupa assinaturas acústicas de todos os episódios e gera voice_bank.json."""

    name: ClassVar[str] = "consolidate_voice_bank"
    version: ClassVar[str] = "1"
    scope: ClassVar[StageScope] = StageScope.SERIES
    inputs: ClassVar[tuple[str, ...]] = ("extract_voice", "metadata")
    translates: ClassVar[bool] = False
    enabled_by_default: ClassVar[bool] = True

    def run(self, ctx: StageContext) -> None:
        # 1. Carrega todos os artefatos de episódios da etapa extract_voice
        episodes_map = ctx.inputs.json_all("extract_voice", VoiceEmbeddingsArtifact)
        all_segments = []
        for ep_art in episodes_map.values():
            all_segments.extend(ep_art.segments)

        # 2. Carrega metadados da série (AniList) se disponíveis
        characters: list[CharacterEntry] = []
        try:
            meta = ctx.inputs.json("metadata", MetadataArtifact)
            characters = meta.characters
        except Exception:
            logger.debug("Metadados da série não disponíveis ou incompletos.")

        if not all_segments:
            logger.info("Nenhum segmento de voz encontrado para a série. Gerando voice_bank vazio.")
            ctx.output.json(VoiceBankDoc(profiles=[]))
            return

        # 3. Agrupamento acústico global
        clusters = cluster_acoustic_segments(all_segments, threshold=0.25)

        # Ordena clusters pelo número de falas (mais frequentes primeiro)
        clusters.sort(key=lambda c: len(c.segments), reverse=True)

        # 4. Mapeamento com personagens do AniList
        # Personagens principais (MAIN) têm preferência sobre os clusters mais frequentes
        main_chars = [c for c in characters if str(c.role).lower() == "main"]
        supp_chars = [c for c in characters if str(c.role).lower() != "main"]
        available_chars = main_chars + supp_chars

        assigned_names: set[str] = set()
        profiles: list[VoiceProfile] = []

        for c_res in clusters:
            best_char: CharacterEntry | None = None

            # Tenta encontrar correspondência por gênero compatível com candidatos ainda não mapeados
            for cand in available_chars:
                if cand.name in assigned_names:
                    continue

                cand_gender = str(cand.gender or "").lower()
                # Verifica compatibilidade básica de gênero
                if cand_gender and c_res.dominant_gender != "unknown":
                    if cand_gender == "male" and c_res.dominant_gender == "male":
                        best_char = cand
                        break
                    elif cand_gender == "female" and c_res.dominant_gender == "female":
                        best_char = cand
                        break
                elif cand_gender:
                    best_char = cand
                    break

            if best_char:
                assigned_names.add(best_char.name)
                canonical_gender: Literal["male", "female", "unknown"] = (
                    "male"
                    if str(best_char.gender).lower() == "male"
                    else ("female" if str(best_char.gender).lower() == "female" else "unknown")
                )
                profiles.append(
                    VoiceProfile(
                        character_name=best_char.name,
                        canonical_gender=canonical_gender,
                        centroid=c_res.centroid,
                        sample_count=len(c_res.segments),
                        confidence="high",
                    )
                )
            elif len(c_res.segments) >= 3:
                # Figurante recorrente sem nome conhecido
                profiles.append(
                    VoiceProfile(
                        character_name=f"Unknown_Voice_{c_res.cluster_id + 1}",
                        canonical_gender=c_res.dominant_gender,
                        centroid=c_res.centroid,
                        sample_count=len(c_res.segments),
                        confidence="medium",
                    )
                )

        doc = VoiceBankDoc(profiles=profiles)
        ctx.output.json(doc)
