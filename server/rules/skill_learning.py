"""F.18 스스로 배우는 스킬의 채택·롤백 판정. 순수 함수.

채택 조건: 새 버전의 성공률(풀이율 또는 검수 통과율)이 이전보다 max_rate_drop(2%p) *넘게* 떨어지지 않고,
비용 지표(평균 행동 수 또는 재시도 수)가 이전보다 max_cost_increase(10%) *넘게* 늘지 않을 것. 못 넘으면 이전 버전 유지.
경계값(정확히 2%p 하락, 정확히 10% 증가)은 채택. 부동소수 오차는 9자리 반올림으로 흡수.
rollback_on_regression 이 꺼져 있으면 퇴보해도 채택(판정만 기록).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from server.config import GameConfig

Decision = Literal["adopt", "keep_previous"]


class EvalMetrics(BaseModel):
    success_rate: float  # 0~1
    cost: float  # 평균 행동 수 또는 재시도 수


class AdoptionResult(BaseModel):
    decision: Decision
    rate_drop: float
    cost_increase: float
    reasons: list[str]


def can_update(cfg: GameConfig, clears_since_last_update: int) -> bool:
    """클리어 min_clears_between_updates 회마다 최대 1회 갱신."""
    return cfg.skills_learning.enabled and clears_since_last_update >= cfg.skills_learning.min_clears_between_updates


def needs_summary(cfg: GameConfig, token_count: int) -> bool:
    """스킬 길이 상한을 넘으면 요약 후 재평가."""
    return token_count > cfg.skills_learning.max_tokens_per_skill


def decide_adoption(cfg: GameConfig, previous: EvalMetrics, candidate: EvalMetrics) -> AdoptionResult:
    sl = cfg.skills_learning
    drop = round(previous.success_rate - candidate.success_rate, 9)
    if previous.cost > 0:
        inc = round((candidate.cost - previous.cost) / previous.cost, 9)
    else:
        inc = 0.0 if candidate.cost <= 0 else float("inf")
    reasons: list[str] = []
    if drop > sl.max_rate_drop:
        reasons.append("success_rate_dropped")
    if inc > sl.max_cost_increase:
        reasons.append("cost_increased")
    if reasons and sl.rollback_on_regression:
        return AdoptionResult(decision="keep_previous", rate_drop=drop, cost_increase=inc, reasons=reasons)
    return AdoptionResult(decision="adopt", rate_drop=drop, cost_increase=inc, reasons=reasons)
