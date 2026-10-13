"""F.5 블러핑 판정. 순수 함수, 결정적.

점수 = wE*E + wP*P + wV*V + wR*R + wF*(1-F)   (가중치는 bluff.weights)

애매한 부분을 이렇게 정했다:
- BluffAction.target_npc 는 블러핑을 *듣는* NPC. claim_subject 는 주장이 가리키는 인물(없으면 target_npc).
  BluffClaimDef.truth_by_target 의 키는 claim_subject 로 조회한다(P). 없으면 P=0(거짓).
- E: 수첩에 있고(notebook.evidence_ids) claim_subject 와 연결된(linked_suspects) 근거 카드의 무게 합.
  핵심 증거 evidence_weight.key, 진술(kind=testimony) evidence_weight.testimony, 그 밖 evidence_weight.aux. 최대 1.
- 자백: 점수 >= confession_score, 듣는 NPC 가 범인/공범, 듣는 NPC 에 대한 증거 충분도 >= confession_sufficiency.
- 흔들림: 점수 >= shaken_score. leaked_hint_id 는 그 NPC 의 거짓말 장부 중 아직 수첩에 없는 반박 증거 첫 번째(결정적).
- 즉시 실패: claim.known_false_by 에 듣는 NPC 가 있거나 npc_knows_false=True.
- 증인 오염: 듣는 NPC 가 무고, 관련 기억 확신도 < contaminate_confidence_below, P == 0 이면
  사건 id·슬롯·NPC·주장·이전 실패 수로 정한 결정적 확률(contaminate_probability)로 오염.
"""

from __future__ import annotations

from pydantic import BaseModel

from server.config import GameConfig
from server.schemas import BluffAction, BluffResult, CaseBible, GameState

from . import reputation as rep_rules
from . import sufficiency as suff_rules
from . import trust as trust_rules
from ._util import clamp, stable_unit


def _character(case: CaseBible, npc_id: str):
    for c in case.characters:
        if c.id == npc_id:
            return c
    raise KeyError(npc_id)


def is_guilty(case: CaseBible, npc_id: str) -> bool:
    ch = _character(case, npc_id)
    return ch.is_culprit or ch.is_accomplice or npc_id in case.culprit_ids


def evidence_strength(cfg: GameConfig, case: CaseBible, state: GameState, action: BluffAction) -> float:
    subject = action.claim_subject or action.target_npc
    owned = set(state.notebook.evidence_ids)
    by_id = {e.id: e for e in case.evidence}
    w = cfg.bluff.evidence_weight
    total = 0.0
    for eid in dict.fromkeys(action.basis_evidence_ids):  # 중복 카드 한 번만
        ev = by_id.get(eid)
        if ev is None or eid not in owned or subject not in ev.linked_suspects:
            continue
        if ev.is_key:
            total += w.key
        elif ev.kind == "testimony":
            total += w.testimony
        else:
            total += w.aux
    return clamp(round(total, 6), 0.0, 1.0)


def claim_truth(case: CaseBible, action: BluffAction) -> float:
    subject = action.claim_subject or action.target_npc
    for claim in case.bluff_claims:
        if claim.id == action.claim_id:
            return claim.truth_by_target.get(subject, 0.0)
    raise KeyError(action.claim_id)


def temperament_v(cfg: GameConfig, temperament: str) -> float:
    return getattr(cfg.bluff.temperament_v, temperament)


def reputation_trust(cfg: GameConfig, reputation: int) -> float:
    """R = (평판 - 최소) / (최대 - 최소). 기본 범위 -100~100 이면 (평판+100)/200."""
    low, high = cfg.reputation_range
    return (reputation - low) / (high - low)


def prior_failure(cfg: GameConfig, failures: int) -> float:
    return min(1.0, failures * cfg.bluff.failure_step)


def score_from_factors(cfg: GameConfig, E: float, P: float, V: float, R: float, F: float) -> float:
    w = cfg.bluff.weights
    return round(w.E * E + w.P * P + w.V * V + w.R * R + w.F * (1.0 - F), 9)


def should_contaminate_witness(
    cfg: GameConfig,
    case: CaseBible,
    state: GameState,
    action: BluffAction,
    *,
    P: float,
    memory_confidence: float | None,
) -> bool:
    if memory_confidence is None or P != 0.0 or is_guilty(case, action.target_npc):
        return False
    if memory_confidence >= cfg.bluff.contaminate_confidence_below:
        return False
    npc = state.npc_states.get(action.target_npc)
    failures = npc.bluff_failures if npc else 0
    coin = stable_unit(case.case_id, state.slot_id, action.target_npc, action.claim_id, failures)
    return coin < cfg.bluff.contaminate_probability


def resolve_bluff(
    cfg: GameConfig,
    case: CaseBible,
    state: GameState,
    action: BluffAction,
    *,
    npc_knows_false: bool = False,
    sufficiency: float | None = None,
    memory_confidence: float | None = None,
) -> BluffResult:
    """블러핑 판정. 같은 입력이면 항상 같은 결과.

    npc_knows_false: 시간 관계 그래프 조회 결과(듣는 NPC 가 반대 사실을 앎). claim.known_false_by 와 OR.
    sufficiency: 듣는 NPC 에 대한 증거 충분도. None 이면 수첩으로 직접 계산.
    memory_confidence: 증인 오염 판정용, 관련 기억의 확신도(없으면 오염 없음).
    """
    target = _character(case, action.target_npc)
    npc = state.npc_states.get(action.target_npc)
    failures = npc.bluff_failures if npc else 0

    E = evidence_strength(cfg, case, state, action)
    P = claim_truth(case, action)
    V = temperament_v(cfg, target.temperament)
    R = reputation_trust(cfg, state.reputation)
    F = prior_failure(cfg, failures)
    factors = {"E": E, "P": P, "V": V, "R": R, "F": F}
    contaminate = should_contaminate_witness(cfg, case, state, action, P=P, memory_confidence=memory_confidence)

    claim = next(c for c in case.bluff_claims if c.id == action.claim_id)
    if npc_knows_false or action.target_npc in claim.known_false_by:
        return BluffResult(outcome="instant_fail", score=0.0, factors=factors, contaminates_witness=contaminate)

    score = score_from_factors(cfg, E, P, V, R, F)
    if sufficiency is None:
        sufficiency = suff_rules.suspect_sufficiency(cfg, case, state.notebook, action.target_npc)

    if (
        score >= cfg.bluff.confession_score
        and is_guilty(case, action.target_npc)
        and sufficiency >= cfg.bluff.confession_sufficiency
    ):
        return BluffResult(outcome="confession", score=score, factors=factors, contaminates_witness=contaminate)
    if score >= cfg.bluff.shaken_score:
        return BluffResult(
            outcome="shaken",
            score=score,
            factors=factors,
            contaminates_witness=contaminate,
            leaked_hint_id=leak_hint(case, state, action.target_npc),
        )
    return BluffResult(outcome="rebutted", score=score, factors=factors, contaminates_witness=contaminate)


def leak_hint(case: CaseBible, state: GameState, npc_id: str) -> str | None:
    """거짓말 장부에서 그 NPC 의 아직 수첩에 없는 반박 증거 하나(장부 순서대로 첫 번째)."""
    owned = set(state.notebook.evidence_ids)
    for lie in case.lie_ledger:
        if lie.liar_id != npc_id:
            continue
        for eid in lie.rebuttal_evidence_ids:
            if eid not in owned:
                return eid
    return None


class BluffEffects(BaseModel):
    failed: bool
    trust_event: str | None = None
    reputation_event: str | None = None
    alertness_delta: int = 0


def failure_effects(cfg: GameConfig, case: CaseBible, action: BluffAction, result: BluffResult) -> BluffEffects:
    """실패(반박·즉시 실패)의 효과. 신뢰도 bluff_fail, 평판 bluff_fail, 범인이면 경계 +alertness_on_fail."""
    if result.outcome not in ("rebutted", "instant_fail"):
        return BluffEffects(failed=False)
    return BluffEffects(
        failed=True,
        trust_event="bluff_fail",
        reputation_event="bluff_fail",
        alertness_delta=cfg.bluff.alertness_on_fail if is_guilty(case, action.target_npc) else 0,
    )


def apply_failure(
    cfg: GameConfig, case: CaseBible, state: GameState, action: BluffAction, result: BluffResult
) -> GameState:
    """실패 효과를 상태에 반영한 새 상태(성공·흔들림·자백이면 그대로)."""
    eff = failure_effects(cfg, case, action, result)
    if not eff.failed:
        return state
    npc = state.npc_states[action.target_npc]
    npc = trust_rules.apply_event(cfg, npc, eff.trust_event)
    npc = npc.model_copy(
        update={
            "bluff_failures": npc.bluff_failures + 1,
            "alertness": int(clamp(npc.alertness + eff.alertness_delta, cfg.alertness.min, cfg.alertness.max)),
        }
    )
    state = state.model_copy(
        update={
            "npc_states": {**state.npc_states, action.target_npc: npc},
            "bluff_failures_today": state.bluff_failures_today + 1,
        }
    )
    return rep_rules.apply_event(cfg, state, eff.reputation_event)
