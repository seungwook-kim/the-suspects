"""F.2 형사 평판. 순수 함수."""

from __future__ import annotations

from server.config import GameConfig
from server.schemas import GameState

# 평판에 영향을 주는 사건 이름 == reputation.* 설정 키
EVENTS = (
    "clue_found",
    "offtopic_turnaway",
    "offtopic_rumor",
    "meta",
    "rude",
    "bluff_fail",
    "stakeout_caught",
    "deal_exposed",
    "apology",
    "subquest",
)


def event_delta(cfg: GameConfig, event: str) -> int:
    if event not in EVENTS:
        raise KeyError(event)
    return getattr(cfg.reputation, event)


def clamp_reputation(cfg: GameConfig, value: int) -> int:
    low, high = cfg.reputation_range
    return max(low, min(high, value))


def apply_event(cfg: GameConfig, state: GameState, event: str, *, npc_id: str | None = None) -> GameState:
    """사건 하나를 반영한 새 상태.

    - clue_found: 하루 상한(clue_found_daily_cap)까지만 오른다. 남은 한도보다 크면 잘라서 더한다.
    - 감점 사건은 had_negative_today 를 켠다(하루 자연 회복 막음).
    - apology: npc_id 를 주면 그 NPC 에게 하루 1회만 인정한다(npc_states[].apologized_day).
      이미 사과했으면 변화 없음. NPC 신뢰도 쪽 변화는 trust.apply_event 로 따로 반영한다.
    """
    delta = event_delta(cfg, event)
    updates: dict = {}
    if event == "clue_found":
        room = cfg.reputation.clue_found_daily_cap - state.reputation_gain_today
        delta = max(0, min(delta, room))
        updates["reputation_gain_today"] = state.reputation_gain_today + delta
    elif event == "apology" and npc_id is not None:
        npc = state.npc_states.get(npc_id)
        if npc is not None:
            if npc.apologized_day == state.day:
                return state
            updates["npc_states"] = {**state.npc_states, npc_id: npc.model_copy(update={"apologized_day": state.day})}
    if delta < 0:
        updates["had_negative_today"] = True
    updates["reputation"] = clamp_reputation(cfg, state.reputation + delta)
    return state.model_copy(update=updates)


def end_of_day(cfg: GameConfig, state: GameState) -> GameState:
    """하루 마감: 감점 사건이 없었으면 자연 회복. 하루 카운터 초기화. (day 증가는 호출자 몫)"""
    rep = state.reputation
    if not state.had_negative_today:
        rep = clamp_reputation(cfg, rep + cfg.reputation.daily_recovery)
    return state.model_copy(
        update={
            "reputation": rep,
            "reputation_gain_today": 0,
            "had_negative_today": False,
            "bluff_failures_today": 0,
        }
    )


def rumor_count(cfg: GameConfig, reputation: int) -> int:
    """그날 밤 형사에 대한 소문 개수. 평판이 임계값 이하일 때 그 임계값의 count (가장 센 것)."""
    count = 0
    for th in cfg.reputation.rumor_threshold:
        if reputation <= th.at:
            count = max(count, th.count)
    return count


def title_for(cfg: GameConfig, reputation: int) -> str | None:
    """칭호. 구간에 칭호가 없으면 None."""
    for band in cfg.reputation.titles:
        if reputation >= band.min:
            return band.name
    return None


def bluff_rumor_candidate(cfg: GameConfig, bluff_failures_today: int) -> bool:
    """하루 N회 이상 블러핑 실패 시 "허세 형사" 소문 후보."""
    return bluff_failures_today >= cfg.reputation.bluff_fail_rumor_count
