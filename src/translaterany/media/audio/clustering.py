"""Algoritmos de agrupamento acústico e cálculo de centróides de voz."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from translaterany.media.audio.models import AcousticSegment


def cosine_distance(v1: list[float], v2: list[float]) -> float:
    """Calcula a distância cosseno entre dois vetores (1.0 - similaridade)."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 1.0

    dot = sum(a * b for a, b in zip(v1, v2, strict=False))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 == 0 or norm2 == 0:
        return 1.0

    similarity = dot / (norm1 * norm2)
    similarity = max(-1.0, min(1.0, similarity))
    return 1.0 - similarity


def compute_centroid(vectors: list[list[float]]) -> list[float]:
    """Calcula o vetor médio (centróide) com normalização L2."""
    if not vectors:
        return []
    dim = len(vectors[0])
    avg = [0.0] * dim
    for v in vectors:
        for i, val in enumerate(v):
            avg[i] += val

    n = len(vectors)
    avg = [x / n for x in avg]
    norm = math.sqrt(sum(x * x for x in avg))
    if norm > 0:
        avg = [round(x / norm, 4) for x in avg]
    return avg


@dataclass
class ClusterResult:
    cluster_id: int
    segments: list[AcousticSegment] = field(default_factory=list)
    centroid: list[float] = field(default_factory=list)
    dominant_gender: Literal["male", "female", "unknown"] = "unknown"


def cluster_acoustic_segments(
    segments: list[AcousticSegment],
    threshold: float = 0.25,
) -> list[ClusterResult]:
    """Agrupa segmentos de áudio com base na distância cosseno entre seus embeddings.
    Segmentos com distância <= threshold são agrupados no mesmo cluster.
    """
    valid_segs = [s for s in segments if s.has_speech and s.embedding and any(x != 0 for x in s.embedding)]
    if not valid_segs:
        return []

    clusters: list[list[AcousticSegment]] = []
    centroids: list[list[float]] = []

    for seg in valid_segs:
        best_idx = -1
        best_dist = float("inf")

        for idx, cent in enumerate(centroids):
            dist = cosine_distance(seg.embedding, cent)
            if dist < best_dist and dist <= threshold:
                best_dist = dist
                best_idx = idx

        if best_idx >= 0:
            clusters[best_idx].append(seg)
            # Atualiza centróide do cluster
            centroids[best_idx] = compute_centroid([s.embedding for s in clusters[best_idx]])
        else:
            clusters.append([seg])
            centroids.append(list(seg.embedding))

    results: list[ClusterResult] = []
    for idx, (clust_segs, cent) in enumerate(zip(clusters, centroids, strict=False)):
        genders = [s.acoustic_gender for s in clust_segs]
        male_count = genders.count("male")
        female_count = genders.count("female")

        dominant: Literal["male", "female", "unknown"] = "unknown"
        if male_count > female_count:
            dominant = "male"
        elif female_count > male_count:
            dominant = "female"

        results.append(
            ClusterResult(
                cluster_id=idx,
                segments=clust_segs,
                centroid=cent,
                dominant_gender=dominant,
            )
        )

    return results
