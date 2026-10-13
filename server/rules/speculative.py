"""F.15 추측 생성 적중률 추적과 자동 끔. 순수 함수(불변 갱신).

한 번 칩을 표시할 때마다 (미리 만든 수, 실제 쓰인 수) 한 쌍을 기록한다.
적중률 = 최근 window 회의 쓰인 수 합 / 미리 만든 수 합. 기록이 window 회 찬 뒤 적중률 < min_hit_rate 이면 그 판에서 끈다.
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
    prepared = sum(p for p, _ in stats.shows)
    if prepared == 0:
        return None
    return sum(u for _, u in stats.shows) / prepared


def should_disable(cfg: GameConfig, stats: SpeculativeStats) -> bool:
    auto = cfg.speed.speculative_auto_off
    if len(stats.shows) < auto.window:
        return False
    rate = hit_rate(stats)
    return rate is not None and rate < auto.min_hit_rate


def is_enabled(cfg: GameConfig, stats: SpeculativeStats) -> bool:
    return cfg.speed.speculative_chips and not stats.disabled
