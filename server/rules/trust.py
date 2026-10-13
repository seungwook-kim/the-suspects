"""F.3 NPC 신뢰도, 외면, 최소 공개. 순수 함수."""

from __future__ import annotations

from typing import Literal

from server.config import GameConfig
from server.schemas import Character, NPCState

# 신뢰도에 영향을 주는 사건 이름 == trust.* 설정 키 (small_talk 은 성격별로 따로)
EVENTS = ("lie_exposed", "cleared", "rude", "bluff_fail", "apology")

Disclosure = Literal["normal", "terse", "key_fact_only"]


def clamp_trust(cfg: GameConfig, value: int) -> int:
    return max(cfg.trust.min, min(cfg.trust.max, value))


def start_trust(cfg: GameConfig, character: Character) -> int:
    """시작 신뢰도: 주요 50 / 주변 40, 수다쟁이 +offset / 무뚝뚝 -offset (보통은 0)."""
    base = cfg.trust.start_main if character.tier == "main" else cfg.trust.start_minor
    off = cfg.trust.personality_offset
    if character.small_talk_style == "chatty":
        base += off
    elif character.small_talk_style == "blunt":
        base -= off
    return clamp_trust(cfg, base)


def small_talk_delta(cfg: GameConfig, style: str) -> int:
    return {
        "chatty": cfg.trust.small_talk_chatty,
        "blunt": cfg.trust.small_talk_blunt,
        "normal": cfg.trust.small_talk_normal,
    }[style]


def event_delta(cfg: GameConfig, event: str) -> int:
    if event not in EVENTS:
        raise KeyError(event)
    return getattr(cfg.trust, event)


def apply_event(cfg: GameConfig, npc: NPCState, event: str) -> NPCState:
    return npc.model_copy(update={"trust": clamp_trust(cfg, npc.trust + event_delta(cfg, event))})


def apply_small_talk(cfg: GameConfig, npc: NPCState, style: str) -> NPCState:
    return npc.model_copy(update={"trust": clamp_trust(cfg, npc.trust + small_talk_delta(cfg, style))})


def is_uncooperative(cfg: GameConfig, trust: int) -> bool:
    """신뢰도가 기준 미만이면 짧고 비협조적으로 답한다."""
    return trust < cfg.trust.uncooperative_below


def disclosure_policy(cfg: GameConfig, character: Character, trust: int) -> Disclosure:
    """답변 공개 수준.

    - 기준 이상: normal
    - 기준 미만 + 핵심 증인(min_disclosure 켜짐): key_fact_only (핵심 사실 하나는 반드시 말함)
    - 기준 미만 + 그 밖: terse
    """
    if not is_uncooperative(cfg, trust):
        return "normal"
    if cfg.trust.min_disclosure and character.key_witness:
        return "key_fact_only"
    return "terse"


def turn_away(cfg: GameConfig, npc: NPCState, action_no: int) -> NPCState:
    """외면: 지금 행동 번호부터 turnaway_actions 번의 행동 동안 대화 거부.

    turned_away_until = action_no + turnaway_actions. is_turned_away 는 `현재번호 < until` 이면 거부.
    """
    return npc.model_copy(update={"turned_away_until": action_no + cfg.trust.turnaway_actions})


def is_turned_away(npc: NPCState, action_no: int) -> bool:
    return npc.turned_away_until is not None and action_no < npc.turned_away_until
