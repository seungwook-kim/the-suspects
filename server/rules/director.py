"""F.9 AI 연출 감독 트리거. 순수 함수.

입력은 진행 지표(DirectorMetrics), 출력은 개입 종류 또는 None.
우선순위(위가 먼저): late_struggle > early_progress > same_place > no_clue event > no_clue hint.
공통 제약: 개입 사이 최소 cooldown_actions 행동, 하루 최대 max_per_day 개.
한 번 쓴 개입이 같은 상황에서 반복되지 않게 호출자가 아래 필드로 알려 준다(애매한 부분을 직접 정함):
  hint_given_in_streak / event_given_in_streak : 지금 '새 단서 없는 구간'에서 이미 낸 개입
  fired : 한 번만 내는 개입("early_progress", "late_struggle")의 사용 기록
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from server.config import GameConfig

Intervention = Literal[
    "partner_hint",  # 파트너 형사 중얼거림(1단계 힌트)
    "event",  # 거래 제안, 제보 등
    "call_elsewhere",  # 다른 장소로 부르는 이벤트
    "escalate_crisis",  # 위기를 앞당김(두 번째 사건, 협박)
    "report_nudge",  # 반장 보고 권유 + 힌트
]


class DirectorMetrics(BaseModel):
    actions_since_clue: int = 0  # 새 단서 없이 지나간 행동 수
    consecutive_same_place: int = 0  # 같은 장소에서 연속 행동 수
    day: int = 1
    is_last_day: bool = False
    max_sufficiency: float = 0.0  # 용의자 중 최대 증거 충분도
    actions_since_last_event: int = 10**6  # 마지막 개입 이후 행동 수(없으면 매우 큼)
    events_today: int = 0
    hint_given_in_streak: bool = False
    event_given_in_streak: bool = False
    fired: list[str] = Field(default_factory=list)


def decide(cfg: GameConfig, m: DirectorMetrics) -> Intervention | None:
    d = cfg.director
    if m.events_today >= d.max_per_day:
        return None
    if m.actions_since_last_event < d.cooldown_actions:
        return None
    if m.is_last_day and m.max_sufficiency < d.late_struggle and "late_struggle" not in m.fired:
        return "report_nudge"
    if m.day < d.early_progress_before_day and m.max_sufficiency >= d.early_progress and "early_progress" not in m.fired:
        return "escalate_crisis"
    if m.consecutive_same_place >= d.same_place_limit:
        return "call_elsewhere"
    if m.actions_since_clue >= d.no_clue.event_after and not m.event_given_in_streak:
        return "event"
    if m.actions_since_clue >= d.no_clue.hint_after and not m.hint_given_in_streak:
        return "partner_hint"
    return None
