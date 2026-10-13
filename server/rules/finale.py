"""F.12 최종 추리 쇼 판정표 (상태 기계). 순수 함수.

흐름
  start_finale -> accuse(범인으로 지목)
    - 지목이 실제 범인(culprit_ids)이면 단계 증거 제시로 진행.
    - 무고한 인물이면 pending_confirmation (NPC 반박). 플레이어가 confirm_accusation 하면 wrong_accusation 엔딩,
      retract_accusation 하면 다시 지목할 수 있다. (목숨은 깎이지 않음: PRD 에 규정 없어 직접 정함)
  present_evidence(stage, evidence_id)
    - 정답: 증거에 그 단계 태그(element_tags)가 있고 지목한 인물과 연결(linked_suspects)됨.
    - 오답: 목숨 -1 (NPC 반박). 목숨 0 -> escaped.
    - 세 단계(finale.stages) 모두 통과 -> success. 단계 순서는 자유.
  블러핑은 비활성 (bluff_allowed -> finale.bluff_enabled).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from server.config import GameConfig
from server.schemas import CaseBible

Outcome = Literal["ongoing", "success", "escaped", "wrong_accusation"]


class FinaleState(BaseModel):
    difficulty: str
    lives: int
    accused_id: str | None = None
    pending_confirmation: bool = False
    passed: list[str] = Field(default_factory=list)
    wrong: int = 0  # GameState.finale_wrong 에 반영
    outcome: Outcome = "ongoing"


class PresentResult(BaseModel):
    state: FinaleState
    correct: bool
    rebuttal: bool  # 오답이면 NPC 반박 연출
    stage_passed: bool  # 이번 제시로 단계가 통과됐는가


def start_finale(cfg: GameConfig, difficulty: str) -> FinaleState:
    return FinaleState(difficulty=difficulty, lives=cfg.finale.lives[difficulty])


def bluff_allowed(cfg: GameConfig) -> bool:
    return cfg.finale.bluff_enabled


def _ensure_ongoing(st: FinaleState) -> None:
    if st.outcome != "ongoing":
        raise ValueError("finale already ended")


def accuse(cfg: GameConfig, case: CaseBible, st: FinaleState, suspect_id: str) -> FinaleState:
    _ensure_ongoing(st)
    guilty = suspect_id in case.culprit_ids
    return st.model_copy(update={"accused_id": suspect_id, "pending_confirmation": not guilty})


def confirm_accusation(st: FinaleState) -> FinaleState:
    """반박을 듣고도 무고한 사람을 확정 지목 -> 오지목 엔딩."""
    _ensure_ongoing(st)
    if not st.pending_confirmation:
        raise ValueError("no pending accusation")
    return st.model_copy(update={"outcome": "wrong_accusation"})


def retract_accusation(st: FinaleState) -> FinaleState:
    _ensure_ongoing(st)
    return st.model_copy(update={"accused_id": None, "pending_confirmation": False})


def stage_evidence_ok(case: CaseBible, st: FinaleState, stage: str, evidence_id: str, owned: set[str] | None) -> bool:
    ev = next((e for e in case.evidence if e.id == evidence_id), None)
    if ev is None or st.accused_id is None:
        return False
    if owned is not None and evidence_id not in owned:
        return False
    return stage in ev.element_tags and st.accused_id in ev.linked_suspects


def present_evidence(
    cfg: GameConfig,
    case: CaseBible,
    st: FinaleState,
    stage: str,
    evidence_id: str,
    owned_evidence_ids: set[str] | None = None,
) -> PresentResult:
    _ensure_ongoing(st)
    if stage not in cfg.finale.stages:
        raise ValueError(f"unknown stage: {stage}")
    if st.accused_id is None or st.pending_confirmation:
        raise ValueError("no confirmed accusation")
    if stage in st.passed:
        return PresentResult(state=st, correct=True, rebuttal=False, stage_passed=False)

    if stage_evidence_ok(case, st, stage, evidence_id, owned_evidence_ids):
        passed = [*st.passed, stage]
        outcome: Outcome = "success" if set(passed) >= set(cfg.finale.stages) else "ongoing"
        new = st.model_copy(update={"passed": passed, "outcome": outcome})
        return PresentResult(state=new, correct=True, rebuttal=False, stage_passed=True)

    lives = st.lives - 1
    new = st.model_copy(
        update={"lives": lives, "wrong": st.wrong + 1, "outcome": "escaped" if lives <= 0 else "ongoing"}
    )
    return PresentResult(state=new, correct=False, rebuttal=True, stage_passed=False)


def ending_of(st: FinaleState) -> str:
    """GameState.ending 값. 진행 중이면 "none"."""
    return "none" if st.outcome == "ongoing" else st.outcome
