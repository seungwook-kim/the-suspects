"""F.10 범인 경계 수준 + 콜롬보 효과. 순수 함수.

콜롬보 효과(평판이 음수면 -(|평판| / columbo_divisor))는 *저장되는 변화량이 아니라 유효 경계 수준에 매번
적용하는 보정*으로 정했다. 밤마다 누적 차감하면 평판이 그대로여도 경계가 계속 0 으로 떨어지기 때문이다.
  유효 경계 = clamp(저장된 경계 + 콜롬보 보정)   ->  임계값 판정에는 유효 경계를 쓴다.
예: 평판 -50 -> 보정 -10 (경계 30 이면 유효 20). 보정은 소수점 이하 버림.
"""

from __future__ import annotations

from typing import Literal

from server.config import GameConfig

from ._util import clamp

AlertEvent = Literal["heard_suspicion", "bluff_fail", "repeat_visit"]


def clamp_alertness(cfg: GameConfig, value: float) -> int:
    return int(clamp(value, cfg.alertness.min, cfg.alertness.max))


def event_delta(cfg: GameConfig, event: str) -> int:
    if event not in ("heard_suspicion", "bluff_fail", "repeat_visit"):
        raise KeyError(event)
    return getattr(cfg.alertness, event)


def apply_event(cfg: GameConfig, level: int, event: str) -> int:
    return clamp_alertness(cfg, level + event_delta(cfg, event))


def repeat_visit_triggered(cfg: GameConfig, visits_today: int) -> bool:
    """하루에 자기 위치를 N번 이상 찾아왔는가."""
    return visits_today >= cfg.alertness.repeat_visit_count


def columbo_adjustment(cfg: GameConfig, reputation: int) -> int:
    """평판이 음수일 때만 -(|평판| / divisor). 0 이상이면 0."""
    if reputation >= 0:
        return 0
    return -int(abs(reputation) / cfg.alertness.columbo_divisor)


def effective_alertness(cfg: GameConfig, level: int, reputation: int) -> int:
    return clamp_alertness(cfg, level + columbo_adjustment(cfg, reputation))


def night_action_candidates(cfg: GameConfig, level: int, reputation: int, max_sufficiency: float) -> list[str]:
    """그날 밤 범인이 고를 수 있는 행동 후보(NPCAction.action 값). 유효 경계 기준.

    - >= hide_evidence_at : hide_evidence (흔적은 반드시 남음, 3.4)
    - >= contact_accomplice_at : contact(공범에게 연락), anonymous_tip(가짜 제보)
    - 증거 충분도 >= threat_sufficiency : threat_message 후보(시점은 연출 감독이 정함)
    - 아무 후보도 없으면 keep_routine
    """
    eff = effective_alertness(cfg, level, reputation)
    out: list[str] = []
    if eff >= cfg.alertness.hide_evidence_at:
        out.append("hide_evidence")
    if eff >= cfg.alertness.contact_accomplice_at:
        out += ["contact", "anonymous_tip"]
    if max_sufficiency >= cfg.alertness.threat_sufficiency:
        out.append("threat_message")
    return out or ["keep_routine"]
