"""F.14 역할 반전 모드 판정. 순수 함수.

AI 형사의 수첩으로 플레이어(범인)에 대한 증거 충분도를 F.6 과 같은 방식으로 계산하고,
플레이어 진술이 AI 형사가 볼 수 있는 기록과 어긋날 때마다 reversal.contradiction_weight(0.2)를 더한다.
플레이어는 CaseBible 인물이 아니므로 호출자가 "플레이어와 연결된 증거 목록"을 넘긴다
(예: [e for e in ai_notebook 증거 if "player" in e.linked_suspects]).
"""

from __future__ import annotations

from collections.abc import Iterable

from server.config import GameConfig
from server.schemas import Evidence

from . import sufficiency as suff
from ._util import clamp

ELEMENTS = {"motive", "means", "opportunity"}


def player_sufficiency(
    cfg: GameConfig,
    linked_evidence: Iterable[Evidence],
    contradiction_count: int,
) -> float:
    return suff.score_parts(
        cfg,
        linked_evidence,
        contradiction_count,
        contradiction_weight=cfg.reversal.contradiction_weight,
    )


def covers_all_elements(linked_evidence: Iterable[Evidence]) -> bool:
    tags: set[str] = set()
    for e in linked_evidence:
        tags.update(e.element_tags)
    return ELEMENTS <= tags


def is_arrest(cfg: GameConfig, sufficiency: float, linked_evidence: Iterable[Evidence]) -> bool:
    """체포(패배): 충분도 >= arrest_threshold 이고 기회·수단·동기를 모두 채움."""
    return sufficiency >= cfg.reversal.arrest_threshold and covers_all_elements(linked_evidence)


def is_framed(cfg: GameConfig, ai_accused_other: bool, sufficiency_on_other: float) -> bool:
    """혐의 돌리기 성공: AI 형사가 다른 NPC 를 지목했고 그 NPC 에 대한 충분도 >= frame_threshold."""
    return ai_accused_other and sufficiency_on_other >= cfg.reversal.frame_threshold


def player_wins(
    cfg: GameConfig,
    *,
    deadline_reached: bool,
    sufficiency: float,
    ai_accused_other: bool = False,
    sufficiency_on_other: float = 0.0,
) -> bool:
    """승리: 기한 종료 시 충분도 < arrest_threshold, 또는 혐의 돌리기 성공."""
    if is_framed(cfg, ai_accused_other, sufficiency_on_other):
        return True
    return deadline_reached and sufficiency < cfg.reversal.arrest_threshold


def add_contradictions(cfg: GameConfig, sufficiency: float, new_contradictions: int) -> float:
    """진술 모순이 새로 드러날 때 충분도에 바로 더하는 보조 함수(상한 sufficiency.max)."""
    return clamp(round(sufficiency + new_contradictions * cfg.reversal.contradiction_weight, 6), 0.0, cfg.sufficiency.max)
