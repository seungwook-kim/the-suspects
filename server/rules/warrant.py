"""F.7 영장. 순수 함수.

근거 점수 = 고른 근거 증거(수첩에 있는 것만)의 무게 합. 증거 하나는 해당하는 분류 중 가장 큰 무게 하나만 낸다.
  direct        : 대상과 연결되고(linked_suspects) 기회 태그가 있거나 사건 장소에서 나온 증거 (대상을 사건 시각·장소와 직접 잇는 증거)
  contradiction : 대상의 거짓말을 깨는 증거 (reveals_contradiction_of 가 대상의 장부 항목이거나, 수첩 모순에 쓰인 것)
  motive        : 대상과 연결된 동기 태그 증거
  other         : 그 밖 모든 증거
통과 기준은 warrant.threshold[system]. 부록 F.7 에 없는 기록 종류(access_log, server_log, messenger,
delivery)의 기준은 직접 정했다(game.yaml 참고).
통과하면 대상 인물에 한해 사건 시각 전후 scope_hours 시간 열람 가능. 통과 여부와 무관하게 행동 비용은 actions.warrant.
"""

from __future__ import annotations

from pydantic import BaseModel

from server.config import GameConfig
from server.schemas import CaseBible, GameState, Warrant

from .actions import action_cost


class WarrantDecision(BaseModel):
    needed: bool = True  # False: 공용 구역 CCTV 처럼 영장이 필요 없음
    approved: bool
    score: float
    threshold: float
    action_cost: int
    warrant: Warrant | None = None


def evidence_weight(cfg: GameConfig, case: CaseBible, state: GameState, target_id: str, evidence_id: str) -> float:
    ev = next((e for e in case.evidence if e.id == evidence_id), None)
    if ev is None or evidence_id not in state.notebook.evidence_ids:
        return 0.0
    w = cfg.warrant.weights
    linked = target_id in ev.linked_suspects
    candidates = [w.other]
    if linked and ("opportunity" in ev.element_tags or ev.location_id == case.incident.location_id):
        candidates.append(w.direct)
    if linked and "motive" in ev.element_tags:
        candidates.append(w.motive)
    target_lies = {lie.id for lie in case.lie_ledger if lie.liar_id == target_id}
    used_in_contradiction = any(
        c.evidence_id == evidence_id and c.lie_id in target_lies for c in state.notebook.contradictions
    )
    if used_in_contradiction or target_lies.intersection(ev.reveals_contradiction_of):
        candidates.append(w.contradiction)
    return max(candidates)


def warrant_score(
    cfg: GameConfig, case: CaseBible, state: GameState, target_id: str, evidence_ids: list[str]
) -> float:
    total = sum(evidence_weight(cfg, case, state, target_id, eid) for eid in dict.fromkeys(evidence_ids))
    return round(total, 6)


def threshold_for(cfg: GameConfig, system: str) -> float:
    try:
        return cfg.warrant.threshold[system]
    except KeyError as e:
        raise ValueError(f"영장 기준이 없는 기록 종류: {system}") from e


def make_warrant(cfg: GameConfig, case: CaseBible, system: str, target_id: str) -> Warrant:
    span = cfg.warrant.scope_hours * 60
    return Warrant(
        system=system, target_id=target_id, from_time=case.incident.time - span, to_time=case.incident.time + span
    )


def request_warrant(
    cfg: GameConfig,
    case: CaseBible,
    state: GameState,
    system: str,
    target_id: str,
    evidence_ids: list[str],
    *,
    public_area: bool = False,
) -> WarrantDecision:
    """영장 신청 판정. public_area=True 인 CCTV 는 영장이 필요 없다(공용 구역 밖만 영장)."""
    cost = action_cost(cfg, "warrant")
    th = threshold_for(cfg, system)
    if system == "cctv" and public_area:
        return WarrantDecision(needed=False, approved=True, score=0.0, threshold=th, action_cost=cost)
    score = warrant_score(cfg, case, state, target_id, evidence_ids)
    ok = score >= th
    return WarrantDecision(
        approved=ok,
        score=score,
        threshold=th,
        action_cost=cost,
        warrant=make_warrant(cfg, case, system, target_id) if ok else None,
    )


def has_warrant(warrants: list[Warrant], system: str, target_id: str, time: int) -> bool:
    """이 시각의 기록을 열람할 영장이 있는가 (시간 창 경계 포함)."""
    return any(w.system == system and w.target_id == target_id and w.from_time <= time <= w.to_time for w in warrants)
