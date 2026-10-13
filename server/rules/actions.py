"""F.1 행동 비용. 순수 함수."""

from __future__ import annotations

from server.config import GameConfig
from server.schemas import GameState

# 행동 이름 -> actions.* 설정 키. 숫자는 설정에서만 읽는다.
_KIND_TO_KEY = {
    "move": "default",
    "investigate": "default",
    "ask": "default",
    "present_evidence": "default",
    "small_talk": "default",
    "bluff": "default",
    "default": "default",
    "warrant": "warrant",
    "confrontation": "confrontation",
    "report": "report",
    "stakeout": "stakeout",
    "hint": "hint",
}


def action_cost(cfg: GameConfig, kind: str) -> int:
    """행동 종류의 낮 행동 소모량. 모르는 종류는 KeyError."""
    return getattr(cfg.actions, _KIND_TO_KEY[kind])


def can_perform(cfg: GameConfig, state: GameState, kind: str) -> tuple[bool, str]:
    """(가능 여부, 불가 사유). 판당 대질·잠복 상한(F.16)도 여기서 본다."""
    if kind == "confrontation" and state.confrontations_used >= cfg.limits.confrontation_per_game:
        return False, "confrontation_limit"
    if kind == "stakeout" and state.stakeouts_used >= cfg.limits.stakeout_per_game:
        return False, "stakeout_limit"
    if state.actions_left < action_cost(cfg, kind):
        return False, "no_actions_left"
    return True, ""


def spend(cfg: GameConfig, state: GameState, kind: str) -> GameState:
    """행동을 소모한 새 상태. 불가하면 ValueError.

    action_no(누적 행동 번호)는 소모량만큼 오른다. 비용 0 행동(힌트·잠복)은 번호가 오르지 않는다.
    """
    ok, reason = can_perform(cfg, state, kind)
    if not ok:
        raise ValueError(reason)
    cost = action_cost(cfg, kind)
    updates: dict = {
        "actions_left": state.actions_left - cost,
        "action_no": state.action_no + cost,
    }
    if kind == "confrontation":
        updates["confrontations_used"] = state.confrontations_used + 1
    elif kind == "stakeout":
        updates["stakeouts_used"] = state.stakeouts_used + 1
    elif kind == "hint":
        updates["hints_used"] = state.hints_used + 1
    return state.model_copy(update=updates)


def new_day_actions(cfg: GameConfig) -> int:
    return cfg.day_actions


def investigation_days(cfg: GameConfig, difficulty: str) -> int:
    return cfg.investigation_days[difficulty]
