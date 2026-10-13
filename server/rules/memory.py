"""F.8 기억 확신도. 순수 함수.

- 초기 확신도: source(direct/heard/guess) 별.
- 일일 감소: 세부(시각·옷 색) x decay.detail, 핵심(누구였나) x decay.core, 최저 floor.
- 오염: 확신도 < contaminate_below 인 기억이, 신뢰(>= contaminate_min_source_trust)하는 상대에게서 상충하는
  소문을 들으면 내용이 소문 쪽으로 바뀌고 확신도 contaminated_confidence. contaminated_by 에 출처를 남기고
  원래 기억은 숨겨서 보존(진실 리플레이용). 이미 형사에게 한 첫 진술(is_first_testimony)은 기록이므로 바꾸지 않는다.
- 말투 구간: speech_bands.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from server.config import GameConfig
from server.config.game_config import SpeechBand
from server.schemas import MemoryDoc

DetailKind = Literal["detail", "core"]


def initial_confidence(cfg: GameConfig, source: str) -> float:
    return getattr(cfg.memory.initial, source)


def daily_decay(cfg: GameConfig, confidence: float, kind: DetailKind, days: int = 1) -> float:
    """하루(또는 days 일) 지난 뒤 확신도. 이미 floor 이하이면 그대로(더 내려가지 않음)."""
    if confidence <= cfg.memory.floor:
        return confidence
    rate = getattr(cfg.memory.decay, kind)
    return round(max(cfg.memory.floor, confidence * rate**days), 6)


def should_contaminate(cfg: GameConfig, confidence: float, source_trust: float, conflicts: bool) -> bool:
    return conflicts and confidence < cfg.memory.contaminate_below and source_trust >= cfg.memory.contaminate_min_source_trust


class ContaminationResult(BaseModel):
    contaminated: bool
    updated: MemoryDoc
    preserved_original: MemoryDoc | None = None  # 숨김 보존본(visibility=[] : 누구에게도 안 보임)


def contaminate(cfg: GameConfig, doc: MemoryDoc, rumor_content: str, source_npc: str) -> ContaminationResult:
    if doc.is_first_testimony:
        return ContaminationResult(contaminated=False, updated=doc)
    original = doc.model_copy(
        update={"id": f"{doc.id}#original", "visibility": [], "tags": [*doc.tags, "original_hidden"]}
    )
    updated = doc.model_copy(
        update={
            "content": rumor_content,
            "confidence": cfg.memory.contaminated_confidence,
            "source": "heard",
            "source_npc": source_npc,
            "contaminated_by": [*doc.contaminated_by, source_npc],
        }
    )
    return ContaminationResult(contaminated=True, updated=updated, preserved_original=original)


def speech_band(cfg: GameConfig, confidence: float) -> SpeechBand:
    """확신도에 맞는 말투 구간(assertive / hedged / uncertain)."""
    for band in cfg.memory.speech_bands:
        if confidence >= band.min:
            return band
    return cfg.memory.speech_bands[-1]
