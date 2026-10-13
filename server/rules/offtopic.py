"""4.7 엉뚱한 입력 단계. 순수 함수.

연속 횟수(streak) -> 단계. 설정 offtopic_steps: chips_again(3), turn_away(4), rumor(6).
  streak 0                    : none (엉뚱한 입력 아님)
  1 .. chips_again-1          : in_character (성격대로 반응)
  chips_again .. turn_away-1  : chips_again (칩 다시 표시, 짜증 표정)
  turn_away .. rumor-1        : turn_away (등 돌림, 평판 offtopic_turnaway)
  rumor 이상                  : rumor (평판 offtopic_rumor, 그날 밤 소문 후보)
정상 질문 1회마다 decay_per_normal 만큼 줄어든다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from server.config import GameConfig

Stage = Literal["none", "in_character", "chips_again", "turn_away", "rumor"]


class OfftopicOutcome(BaseModel):
    streak: int
    stage: Stage
    show_chips: bool = False
    turn_away: bool = False
    reputation_event: str | None = None  # reputation.apply_event 에 넘길 이름
    rumor_candidate: bool = False
    partner_interject: bool = False


def stage_for(cfg: GameConfig, streak: int) -> Stage:
    s = cfg.offtopic_steps
    if streak <= 0:
        return "none"
    if streak >= s.rumor:
        return "rumor"
    if streak >= s.turn_away:
        return "turn_away"
    if streak >= s.chips_again:
        return "chips_again"
    return "in_character"


def register_offtopic(cfg: GameConfig, streak: int) -> OfftopicOutcome:
    """엉뚱한 입력이 들어왔다. streak 를 올리고 그 단계의 결과를 돌려준다."""
    new = streak + 1
    stage = stage_for(cfg, new)
    return OfftopicOutcome(
        streak=new,
        stage=stage,
        show_chips=stage in ("chips_again", "turn_away", "rumor"),
        turn_away=stage in ("turn_away", "rumor"),
        reputation_event={"turn_away": "offtopic_turnaway", "rumor": "offtopic_rumor"}.get(stage),
        rumor_candidate=stage == "rumor",
        partner_interject=new >= cfg.offtopic.partner_interject_at,
    )


def register_normal(cfg: GameConfig, streak: int) -> int:
    """정상 질문이 들어왔다. 연속 횟수를 서서히 낮춘다(0 아래로는 안 감)."""
    return max(0, streak - cfg.offtopic.decay_per_normal)
