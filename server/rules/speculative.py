"""F.15 추측 생성 적중률 추적과 자동 끔. 순수 함수(불변 갱신).

한 번 준비(칩 표시)할 때마다 (미리 만든 수, 실제 쓰인 수) 한 쌍을 기록한다.
적중률 = 최근 window 회 준비 중 미리 만든 답을 하나라도 쓴 준비의 비율(2026-10-15 정의 변경, PRD D-60).
  한 번 준비에 칩 2~3개를 만들지만 하나를 누르면 상태가 바뀌어 나머지는 못 쓴다. 그래서 "쓴 답 ÷ 만든 답"은
  구조상 50%(또는 33%)를 넘을 수 없어 기준 0.5로는 늘 꺼진다. 그 값은 버린 비율로 따로 본다.
기록이 window 회 찬 뒤 적중률 < min_hit_rate 이면 그 판에서 끈다.
다음 판에서는 새 SpeculativeStats 로 다시 켜서 측정한다. (기록이 모자랄 때는 끄지 않음)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from server.config import GameConfig


class SpeculativeStats(BaseModel):
    shows: list[tuple[int, int]] = Field(default_factory=list)  # (prepared, used) 칩 표시 1회당
    disabled: bool = False


def record_show(cfg: GameConfig, stats: SpeculativeStats, prepared: int, used: int) -> SpeculativeStats:
    window = cfg.speed.speculative_auto_off.window
    shows = [*stats.shows, (prepared, min(used, prepared))][-window:]
    new = stats.model_copy(update={"shows": shows})
    return new.model_copy(update={"disabled": stats.disabled or should_disable(cfg, new)})


def hit_rate(stats: SpeculativeStats) -> float | None:
    """미리 만든 답을 하나라도 쓴 준비 ÷ 무언가 미리 만든 준비."""
    shows = [(p, u) for p, u in stats.shows if p > 0]
    if not shows:
        return None
    return sum(1 for _, u in shows if u > 0) / len(shows)


def discard_rate(stats: SpeculativeStats) -> float | None:
    """버린 비율 = 쓰지 않은 답 ÷ 미리 만든 답 (비용 쪽 지표)."""
    prepared = sum(p for p, _ in stats.shows)
    if prepared == 0:
        return None
    return 1 - sum(u for _, u in stats.shows) / prepared


def should_disable(cfg: GameConfig, stats: SpeculativeStats) -> bool:
    auto = cfg.speed.speculative_auto_off
    if len(stats.shows) < auto.window:
        return False
    rate = hit_rate(stats)
    return rate is not None and rate < auto.min_hit_rate


def is_enabled(cfg: GameConfig, stats: SpeculativeStats) -> bool:
    return cfg.speed.speculative_chips and not stats.disabled
