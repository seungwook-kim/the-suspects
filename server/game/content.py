"""게임 진행용 순수 계산 (LLM·저장소 없음).

장소 해금, 증거가 드러나는 순서, 낮 동안 인물 위치, 추천 질문 칩, 거짓말 지침 고르기, 힌트 문구.
"""

from __future__ import annotations

import hashlib
from collections import Counter

from server.schemas import CaseBible, Character, Chip, Evidence, GameState


def hhmm(minutes: int) -> str:
    m = minutes % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def stable_pick(seq: list, *keys: object):
    if not seq:
        return None
    h = int(hashlib.sha256("|".join(map(str, keys)).encode()).hexdigest(), 16)
    return seq[h % len(seq)]


def char(case: CaseBible, npc_id: str) -> Character:
    return next(c for c in case.characters if c.id == npc_id)


def evidence(case: CaseBible, evidence_id: str) -> Evidence:
    return next(e for e in case.evidence if e.id == evidence_id)


# ---------------------------------------------------------------------------- 위치
def in_building(case: CaseBible, loc_id: str) -> bool:
    return any(l.id == loc_id for l in case.locations)


def day_location(case: CaseBible, ch: Character, unlocked: list[str], day: int) -> str:
    """수사하는 낮 동안의 위치. 일과에서 건물 안 위치 중 가장 오래 머문 곳(열린 장소 우선)."""
    weights: Counter[str] = Counter()
    for r in ch.routine:
        if in_building(case, r.location_id):
            weights[r.location_id] += max(1, r.end - r.start)
    ranked = [loc for loc, _ in weights.most_common()]
    for loc in ranked:
        if loc in unlocked:
            return loc
    # 일과가 건물 밖뿐이거나 아직 안 열린 곳이면, 열린 장소 중 하나 (날마다 조금씩 다르게)
    return stable_pick(sorted(unlocked), case.case_id, ch.id, day) or case.start_location_id


# ---------------------------------------------------------------------------- 해금
def condition_met(cond: str | None, state: GameState) -> bool:
    if not cond:
        return True
    kind, _, value = cond.partition(":")
    if kind == "evidence":
        return value in state.notebook.evidence_ids
    if kind == "day":
        return state.day >= int(value)
    if kind == "talk":
        return value in state.director_state.get("talked", [])
    return False


def apply_unlocks(case: CaseBible, state: GameState) -> tuple[list[str], list[str]]:
    """새로 열린 장소 id 목록, 새로 드러난 인물 id 목록."""
    new_locs = []
    for loc in case.locations:
        if loc.id not in state.unlocked_locations and condition_met(loc.unlock_condition, state):
            state.unlocked_locations.append(loc.id)
            new_locs.append(loc.id)
    new_chars = []
    for ch in case.characters:
        ns = state.npc_states.get(ch.id)
        if ns and not ns.visible and condition_met(ch.reveal_condition, state):
            ns.visible = True
            new_chars.append(ch.id)
    return new_locs, new_chars


# ---------------------------------------------------------------------------- 조사
def next_reveals(case: CaseBible, state: GameState, location_id: str, per_action: int, key_last: bool) -> list[str]:
    """이 장소를 조사하면 이번에 드러나는 증거. 플레이어가 볼 수 있는 것만, 핵심 증거는 나중에."""
    loc = next(l for l in case.locations if l.id == location_id)
    owned = set(state.notebook.evidence_ids)
    pending = [e for e in (evidence(case, i) for i in loc.investigate_evidence_ids)
               if e.id not in owned and "player" in e.visibility]
    if key_last:
        non_key = [e for e in pending if not e.is_key]
        pending = non_key if non_key else [e for e in pending if e.is_key]
    return [e.id for e in pending[:per_action]]


def remaining_at(case: CaseBible, state: GameState, location_id: str) -> int:
    loc = next(l for l in case.locations if l.id == location_id)
    owned = set(state.notebook.evidence_ids)
    return sum(1 for i in loc.investigate_evidence_ids if i not in owned and "player" in evidence(case, i).visibility)


# ---------------------------------------------------------------------------- 거짓말 지침
def _grams(text: str) -> set[str]:
    t = "".join(text.split())
    return {t[i:i + 2] for i in range(len(t) - 1)}


def relevant_lies(case: CaseBible, npc_id: str, question: str, min_overlap: int = 2) -> list[str]:
    """그 NPC의 거짓말 장부 중 질문과 관련 있는 것만 지침으로 준다(관련 없으면 거짓말하지 않음)."""
    q = _grams(question)
    out = []
    for lie in case.lie_ledger:
        if lie.liar_id != npc_id:
            continue
        if len(q & (_grams(lie.topic) | _grams(lie.lie))) >= min_overlap:
            out.append(f"{lie.topic}에 대해 물으면 → {lie.lie}")
    return out


def hidden_topics(case: CaseBible, npc_id: str, revealed: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """그 인물(범인·공범)이 숨겨야 하는 주제 전체와 그때 할 말. 질문과 관련 없어 보여도 늘 준다:
    돌려 묻는 질문("제일 화났던 일")에 거짓말 지침이 빠져 진실을 말한 일(2026-10-15 탈옥 평가)을 막는다.
    revealed: 형사가 반박 증거를 내밀어 이미 깨진 거짓말 id(그 주제는 숨기지 않는다)."""
    return [f"{lie.topic}: 물으면 '{lie.lie}'라고 한다" for lie in case.lie_ledger
            if lie.liar_id == npc_id and lie.id not in revealed]


# ---------------------------------------------------------------------------- 추천 칩
def base_questions(case: CaseBible) -> list[str]:
    """어느 사건에나 통하는 기본 질문. 현장 이름만 사건에서 가져온다."""
    scene = next((l.name for l in case.locations if l.id == case.incident.location_id), "현장")
    return [
        "어젯밤 사건 시각쯤 어디 계셨어요?",
        "그날 밤 이상한 걸 보거나 들으신 건 없어요?",
        "누구랑 같이 있었어요?",
        f"{scene}에 들어간 적 있으세요?",
        "요즘 불만이나 걱정거리 같은 건 없었어요?",
    ]


def build_chips(case: CaseBible, state: GameState, out_evidence) -> tuple[list[Chip], dict[str, dict]]:
    """플레이어 위치에 있는 인물에 대한 질문·증거 제시 칩. (칩 목록, 서버 보관용 정의)

    out_evidence: 내부 증거 id → 클라이언트용 불투명 id 변환 함수
    """
    chips: list[Chip] = []
    defs: dict[str, dict] = {}
    asked = state.director_state.get("asked_texts", {})
    here = [c for c in case.characters
            if (ns := state.npc_states.get(c.id)) and ns.visible and ns.location_id == state.player_location]
    n = 0
    questions = base_questions(case)
    for ch in here:
        done = set(asked.get(ch.id, []))
        for q in [q for q in questions if q not in done][:2]:
            n += 1
            cid = f"chip_{state.action_no}_{n}"
            label = f"{ch.name}: {q}" if len(here) > 1 else q  # 여러 명이면 누구에게 묻는지 보이게
            chips.append(Chip(id=cid, label=label, target_npc=ch.id, kind="ask"))
            defs[cid] = {"kind": "ask", "npc": ch.id, "text": q}
        for eid in state.notebook.evidence_ids:
            ev = evidence(case, eid)
            if ch.id in ev.linked_suspects:
                n += 1
                cid = f"chip_{state.action_no}_{n}"
                chips.append(Chip(id=cid, label=f"{ch.name}에게 '{ev.name}' 보여 주기", target_npc=ch.id, kind="present",
                                  evidence_id=out_evidence(eid)))
                defs[cid] = {"kind": "present", "npc": ch.id, "evidence": eid}
                break
    return chips[:6], defs


# ---------------------------------------------------------------------------- 힌트
def hint_text(case: CaseBible, state: GameState) -> str:
    """다음에 볼 만한 곳을 정답 없이 가리킨다."""
    for loc in case.locations:
        if loc.id in state.unlocked_locations and remaining_at(case, state, loc.id) > 0:
            return f"선배, {loc.name}은(는) 아직 다 안 살펴본 것 같아요."
    for loc in case.locations:
        if loc.id not in state.unlocked_locations and loc.unlock_condition:
            kind, _, value = loc.unlock_condition.partition(":")
            if kind == "talk":
                return f"선배, {char(case, value).name} 씨한테 아직 제대로 얘기 못 들어 봤죠?"
    if not state.warrants:
        return "선배, 통화나 결제 기록은 영장이 있어야 볼 수 있어요. 근거가 모이면 신청해 보죠."
    return "선배, 진술이랑 증거를 하나씩 맞춰 보면 어긋나는 데가 있을 거예요."
