"""F.17 반복 방지 판정. 순수 함수.

1. 동기 유형 + 트릭 유형 + 범인 역할이 모두 같은 지난 사건이 있으면 바로 재생성(우선).
2. 그다음 요약 임베딩 코사인 유사도 >= similarity_threshold 면 재생성.
비교 대상은 같은 플레이어의 최근 history_size 개 사건 지문(history 는 오래된 것 -> 최신 순).
지문 키 중 하나라도 비어 있으면 1번 일치로 보지 않는다(정보 없음을 같다고 단정하지 않음).
임베딩은 호출자가 만들어 넘긴다(여기서는 네트워크·LLM 없음).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel

from server.config import GameConfig


class DedupResult(BaseModel):
    duplicate: bool
    reason: Literal["fingerprint", "similarity"] | None = None
    matched_index: int | None = None  # 입력 history 안에서의 위치
    similarity: float | None = None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("embedding dimension mismatch")
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def same_fingerprint(cfg: GameConfig, a: dict, b: dict) -> bool:
    keys = cfg.case_gen.dedup.fingerprint_keys
    return all(a.get(k) and a.get(k) == b.get(k) for k in keys)


def check_duplicate(
    cfg: GameConfig,
    new_fingerprint: dict,
    history: Sequence[dict],
    new_embedding: Sequence[float] | None = None,
    history_embeddings: Sequence[Sequence[float] | None] | None = None,
) -> DedupResult:
    d = cfg.case_gen.dedup
    start = max(0, len(history) - d.history_size)
    recent = range(start, len(history))

    for i in recent:  # 1순위: 지문 일치
        if same_fingerprint(cfg, new_fingerprint, history[i]):
            return DedupResult(duplicate=True, reason="fingerprint", matched_index=i)

    if new_embedding is not None and history_embeddings is not None:  # 2순위: 임베딩 유사도
        best_i, best = None, -1.0
        for i in recent:
            emb = history_embeddings[i] if i < len(history_embeddings) else None
            if emb is None:
                continue
            s = cosine(new_embedding, emb)
            if s > best:
                best_i, best = i, s
        if best_i is not None and best >= d.similarity_threshold:
            return DedupResult(duplicate=True, reason="similarity", matched_index=best_i, similarity=best)
        if best_i is not None:
            return DedupResult(duplicate=False, similarity=best)
    return DedupResult(duplicate=False)
