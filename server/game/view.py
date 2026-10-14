"""플레이어 시점 뷰 만들기 (AGENTS.md 규칙 7).

여기서 만든 PlayerView만 클라이언트로 나간다. 들어가면 안 되는 것:
범인 여부, 비밀, 목표, 거짓말 장부, 동기·수단·기회, 타임라인, 다른 NPC의 기억, 내부 ID, 정확한 수치(평판·충분도).
"""

from __future__ import annotations

from server.game.masking import IdMasker
from server.rules.actions import visited as act_visited
from server.schemas import (
    CaseBible,
    Chip,
    Contradiction,
    GameState,
    Notebook,
    NotebookStatement,
    PlayerView,
    PublicCharacter,
    PublicEvidence,
    PublicLocation,
)

# 칭호 구간은 규칙 엔진 설정(reputation.titles)으로 넘겨받는다. 없으면 기본값.
_DEFAULT_BANDS = [(40, "믿음직한 형사"), (-19, ""), (-49, "동네 괴짜 형사"), (-100, "말썽꾼 형사")]


def reputation_band(reputation: int, bands: list[tuple[int, str]] | None = None) -> str:
    for threshold, name in bands or _DEFAULT_BANDS:
        if reputation >= threshold:
            return name
    return ""


def _first_sentence(text: str) -> str:
    """성격 설명의 첫 문장만 공개한다. 뒤 문장일수록 비밀에 가까운 힌트가 붙기 쉽다."""
    head = text.split(". ")[0].strip()
    return head if head.endswith(".") else head + "."


def public_statement(s: NotebookStatement) -> NotebookStatement:
    """화면용 진술. 근거 기억 ID는 감추고 자리표시만 남긴다 (출처 원문은 별도 API로)."""
    return NotebookStatement(id=s.id, npc_id=s.npc_id, content=s.content, game_time=s.game_time, memory_id=None,
                             source_ids=[f"{s.id}:{i}" for i, _ in enumerate(s.source_ids)])


def gauge(value: float, cells: int = 5) -> int:
    value = max(0.0, min(1.0, value))
    return min(cells, int(value * cells + 1e-9))


def build_view(
    case: CaseBible,
    state: GameState,
    masker: IdMasker,
    chips: list[Chip] | None = None,
    bands: list[tuple[int, str]] | None = None,
    actions_total: int = 12,
    portraits: dict[str, str] | None = None,  # 인물 id → AI 초상화 주소 (없으면 화면이 절차적 SVG로 그림)
    portrait_emotions: dict[str, dict[str, str]] | None = None,  # 인물 id → {표정: 주소}
) -> PlayerView:
    unlocked = set(state.unlocked_locations)
    portraits = portraits or {}
    portrait_emotions = portrait_emotions or {}
    locations = [
        PublicLocation(
            id=loc.id,
            name=loc.name,
            description=loc.description,
            connections=[c for c in loc.connections if c in unlocked],
            background_ref=loc.background_ref,
            overlays=["night"] if state.phase == "night" else [],
        )
        for loc in case.locations
        if loc.id in unlocked
    ]

    characters = []
    # 사건 데이터의 인물 순서(범인을 앞이나 뒤에 둘 수 있음)를 그대로 보내지 않고, 판마다 소금으로 섞는다.
    ordered = sorted(case.characters, key=lambda c: masker.out("source", c.id))
    for ch in ordered:
        ns = state.npc_states.get(ch.id)
        if ns is None or not ns.visible:
            continue
        characters.append(
            PublicCharacter(
                id=ch.id,
                name=ch.name,
                role=ch.role,
                age=ch.age,
                gender=ch.gender,
                appearance=dict(ch.appearance),
                face_seed=ch.face_seed,
                location_id=ns.location_id if ns.location_id in unlocked else None,
                emotion=ns.emotion,
                one_liner=_first_sentence(ch.personality),  # 이름·직업·나이는 카드에 따로 보인다
                portrait_url=portraits.get(ch.id),
                portrait_emotions=portrait_emotions.get(ch.id) or None,
            )
        )

    ev_by_id = {e.id: e for e in case.evidence}
    evidence = [
        PublicEvidence(id=masker.out("evidence", eid), name=ev_by_id[eid].name, kind=ev_by_id[eid].kind,
                       content=ev_by_id[eid].content)
        for eid in state.notebook.evidence_ids
        if eid in ev_by_id
    ]

    nb = state.notebook
    public_nb = Notebook(
        evidence_ids=[masker.out("evidence", e) for e in nb.evidence_ids],
        statements=[public_statement(s) for s in nb.statements],
        contradictions=[
            Contradiction(id=c.id, statement_id=c.statement_id, evidence_id=masker.out("evidence", c.evidence_id),
                          lie_id="", note=c.note)
            for c in nb.contradictions
        ],
        relations_known=list(nb.relations_known),
        board_links=list(nb.board_links),
        sufficiency={},  # 정확한 수치는 숨기고 게이지만 보낸다
    )

    visible_ids = {c.id for c in characters}
    return PlayerView(
        game_id=state.game_id,
        case_title=case.title,
        incident_summary=case.incident.summary,
        day=state.day,
        phase=state.phase,
        clock=state.clock,
        actions_left=state.actions_left,
        actions_total=actions_total,
        max_days=state.max_days,
        player_location=state.player_location,
        visited_locations=sorted(act_visited(state)),
        locations=locations,
        characters=characters,
        evidence=evidence,
        notebook=public_nb,
        sufficiency_gauge={k: gauge(v) for k, v in nb.sufficiency.items() if k in visible_ids},
        reputation_band=reputation_band(state.reputation, bands),
        chips=chips or [],
        feed=list(state.feed[-30:]),
        bluff_claims=[{"id": masker.out("claim", c.id), "label": c.label} for c in case.bluff_claims],
        ending=state.ending,
    )
