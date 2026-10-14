"""플레이어 대화 한 번 처리 그래프 (PRD §11.3 그래프 B).

[입력] → 외면 확인 → 라우터 ─┬ 수사·증거 제시 → 검색(권한 필터) → NPC 답변(LLM 1회) → 게임 마스터 → 수첩 갱신
                            ├ 잡담 → 잡담 답변(싼 모델, 검색 없음) → 신뢰도
                            ├ 메타·부적절·무의미 → 엉뚱한 입력 처리(규칙) → 캐릭터 유지 대사
                            ├ 블러핑 시도(자유 입력) → 블러핑 버튼 안내 + 수사 질문으로 처리
                            └ 영장 → 영장 버튼 안내

규칙 엔진·RAG·저장소는 TurnDeps로 주입받는다(테스트에서 가짜로 바꿔 끼울 수 있게).
추천 질문 칩은 답을 미리 만들어 둘 수 있다(prepare_answer, PRD §14.1 추측 생성). 미리 만든 답(prepared)이 오면
검색·인물 답·게임 마스터 LLM 검사를 건너뛰고 그 결과로 뒤처리(수첩·기억·증거)만 한다.
그래프는 이벤트(AG-UI 형식 dict) 목록과 바뀐 게임 상태를 만든다. 전송은 API 계층이 한다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from server.agents import npc as npc_agent
from server.agents.router import SemanticRouter
from server.game.events import EventBuilder
from server.game.view import public_statement
from server.llm.client import LLMClient
from server.schemas import (
    CaseBible,
    Character,
    GameState,
    GMVerdict,
    NotebookStatement,
    NPCReply,
    RetrievalHit,
    RouterOutput,
)


@dataclass
class TurnDeps:
    llm: LLMClient
    router: SemanticRouter
    # 검색: (게임 상태, NPC id, 질문) → 그 NPC 권한 안의 검색 결과
    retrieve: Callable[[GameState, str, str], list[RetrievalHit]]
    # 게임 마스터 코드 검사: (사건, 상태, NPC id, 답변) → 판정
    gm_code_check: Callable[[CaseBible, GameState, str, NPCReply], GMVerdict]
    # 성격별 기본 대사
    fallback_line: Callable[[Character], str]
    # 엉뚱한 입력 처리: (상태, NPC id, 라우터 결과) → {"line": 대사, "turn_away": bool, "events": [...]} 상태는 내부에서 갱신
    handle_offtopic: Callable[[GameState, str, RouterOutput], dict]
    # 잡담 처리 후 신뢰도 갱신
    on_small_talk: Callable[[GameState, Character], None]
    # 답변 후 저장: NPC가 한 말(said)을 기억에 기록 + 단서·모순 판정 → 새로 얻은 증거 id 목록
    after_answer: Callable[[GameState, str, str, NPCReply, list[RetrievalHit]], dict]
    # 그 NPC의 거짓말 지침 (범인·공범만)
    lie_guidance: Callable[[CaseBible, str, str], list[str]]
    case_brief: Callable[[CaseBible, GameState], str]  # 한 판 동안 그대로인 사건 공통 정보 (지시문 쪽)
    # 지금 날짜·시각·장소 (행동마다 바뀌어 사용자 글 쪽에 넣는다, PRD §12.8 캐싱 순서)
    scene: Callable[[CaseBible, GameState], str] | None = None
    # 게임 마스터 LLM 검사: 코드 검사가 트리거만 남겼을 때(확정 위반 없음) 실행. True면 통과
    gm_llm_check: Callable[[CaseBible, GameState, str, NPCReply, GMVerdict], Awaitable[bool]] | None = None


@dataclass
class PreparedAnswer:
    """미리 만든 인물 답 한 개(게임 상태는 건드리지 않은 결과)."""
    npc_id: str
    text: str
    role: str
    reply: NPCReply
    verdict: GMVerdict
    fallback_used: bool
    hits: list[RetrievalHit] = field(default_factory=list)


class TurnState(TypedDict, total=False):
    case: CaseBible
    game: GameState
    npc_id: str
    text: str
    chip_route: RouterOutput | None
    prepared: PreparedAnswer | None
    route: RouterOutput
    hits: list[RetrievalHit]
    reply: NPCReply
    verdict: GMVerdict
    fallback_used: bool
    events: list[dict]
    eb: EventBuilder
    deps: Any
    stop: bool


def _char(case: CaseBible, npc_id: str) -> Character:
    return next(c for c in case.characters if c.id == npc_id)


def _say(s: TurnState, speaker: str | None, text: str, role: str = "npc") -> None:
    s["events"].extend(s["eb"].text(role, speaker, text))


# ---------------------------------------------------------------------------- nodes
def node_turn_away_check(s: TurnState) -> TurnState:
    ns = s["game"].npc_states[s["npc_id"]]
    if ns.turned_away_until is not None and s["game"].action_no < ns.turned_away_until:  # server.rules.trust.is_turned_away와 같은 기준
        s["events"].append(s["eb"].custom("turn_away", {"npcId": s["npc_id"],
                                                         "untilActions": ns.turned_away_until - s["game"].action_no}))
        _say(s, s["npc_id"], "…지금은 얘기하고 싶지 않아요.")
        s["route"] = RouterOutput(kind="gibberish", via="rule")
        s["stop"] = True
    return s


async def node_route(s: TurnState) -> TurnState:
    if s.get("stop"):
        return s
    deps: TurnDeps = s["deps"]
    if s.get("chip_route"):
        s["route"] = s["chip_route"]  # 칩은 라우터 생략
        return s
    out = deps.router.classify(s["text"], target_npc=s["npc_id"])
    if out.via == "llm":
        out, _ = await deps.llm.structured(
            role="router", bucket="npc", schema=RouterOutput,
            system="형사가 추리 게임 속 인물에게 한 말의 의도를 분류한다.",
            user=f"문장: {s['text']}",
            fake=lambda: out.model_copy(update={"via": "llm"}),
            fallback=lambda: RouterOutput(kind="investigate", target_npc=s["npc_id"], via="llm"),
            game_id=s["game"].game_id, node="router",
        )
        out.via = "llm"
        out.target_npc = s["npc_id"]
    s["route"] = out
    return s


def route_branch(s: TurnState) -> str:
    if s.get("stop"):
        return "end"
    k = s["route"].kind
    if k in ("investigate", "present_evidence"):
        return "retrieve"
    if k == "bluff_attempt":
        return "bluff_hint"
    if k == "warrant":
        return "warrant_hint"
    if k == "small_talk":
        return "small_talk"
    return "offtopic"


def node_bluff_hint(s: TurnState) -> TurnState:
    _say(s, "partner", "선배, 블러핑하려면 '블러핑' 버튼으로 근거 증거를 같이 내밀어야 먹혀요.", role="partner")
    s["route"] = s["route"].model_copy(update={"kind": "investigate"})
    return s


def node_warrant_hint(s: TurnState) -> TurnState:
    _say(s, "partner", "영장은 수첩에서 근거를 골라 '영장 신청'으로 올리면 돼요.", role="partner")
    return s


def node_retrieve(s: TurnState) -> TurnState:
    deps: TurnDeps = s["deps"]
    if s.get("prepared"):
        s["hits"] = list(s["prepared"].hits)
        return s
    with deps.llm.tracer.span("retrieval", s["game"].game_id):
        s["hits"] = deps.retrieve(s["game"], s["npc_id"], s["text"])
    return s


def _answer_role(ch: Character, route: RouterOutput) -> str:
    return "npc_minor" if ch.tier == "minor" else ("npc_hard" if route.difficulty == "hard" else "npc")


async def node_npc_answer(s: TurnState) -> TurnState:
    deps: TurnDeps = s["deps"]
    case, game, npc_id = s["case"], s["game"], s["npc_id"]
    if p := s.get("prepared"):
        s["reply"], s["verdict"], s["fallback_used"] = p.reply.model_copy(deep=True), p.verdict, p.fallback_used
        return s
    ch = _char(case, npc_id)
    ctx = npc_agent.NPCContext(
        character=ch, state=game.npc_states[npc_id], question=s["text"], hits=s.get("hits", []),
        case_brief=deps.case_brief(case, game), lie_guidance=deps.lie_guidance(case, npc_id, s["text"]),
        scene=deps.scene(case, game) if deps.scene else "",
        conversation_summary=game.conversation_summary,
    )
    role = _answer_role(ch, s["route"])
    reply, verdict, fb = await npc_agent.answer(
        deps.llm, ctx, role=role,
        gm_code_check=lambda r: deps.gm_code_check(case, game, npc_id, r),
        fallback_line=lambda: deps.fallback_line(ch), game_id=game.game_id,
    )
    s["reply"], s["verdict"], s["fallback_used"] = reply, verdict, fb
    return s


def gm_branch(s: TurnState) -> str:
    if s.get("prepared"):  # 미리 만들 때 게임 마스터 LLM 검사까지 마쳤다
        return "after_answer"
    v = s.get("verdict")
    if s.get("fallback_used") or v is None or not v.needs_llm_check or v.violations:
        return "after_answer"
    return "gm_llm" if s["deps"].gm_llm_check else "after_answer"


async def node_gm_llm(s: TurnState) -> TurnState:
    """핫 패스 LLM 1회 원칙의 허용 예외. 근거 없는 핵심 정보 언급일 때만 온다(PRD 부록 F.11)."""
    deps: TurnDeps = s["deps"]
    ok = await deps.gm_llm_check(s["case"], s["game"], s["npc_id"], s["reply"], s["verdict"])  # type: ignore[misc]
    if not ok:
        ch = _char(s["case"], s["npc_id"])
        s["reply"] = NPCReply(text=deps.fallback_line(ch), emotion=s["reply"].emotion, used_ids=[])
        s["fallback_used"] = True
    return s


def node_after_answer(s: TurnState) -> TurnState:
    deps: TurnDeps = s["deps"]
    game, npc_id, reply = s["game"], s["npc_id"], s["reply"]
    game.npc_states[npc_id].emotion = reply.emotion
    s["events"].append(s["eb"].custom("emotion", {"npcId": npc_id, "emotion": reply.emotion}))
    _say(s, npc_id, reply.text)
    stmt = NotebookStatement(id=f"t_{uuid.uuid4().hex[:8]}", npc_id=npc_id, content=reply.text,
                             game_time=game.clock, source_ids=list(reply.used_ids))
    game.notebook.statements.append(stmt)
    game.question_count += 1
    result = deps.after_answer(game, npc_id, s["text"], reply, s.get("hits", []))
    added: dict[str, Any] = {"statements": [public_statement(stmt).model_dump()]}  # 계약: 객체로, 근거 ID는 가림
    if result.get("evidence_ids"):
        added["evidence_ids"] = result["evidence_ids"]
    if result.get("contradictions"):
        added["contradictions"] = result["contradictions"]
        s["events"].append(s["eb"].custom("cutin", {"text": "모순 발견!", "style": "contradiction"}))
    s["events"].append(s["eb"].custom("notebook", {"added": added}))
    return s


async def node_small_talk(s: TurnState) -> TurnState:
    deps: TurnDeps = s["deps"]
    case, game, npc_id = s["case"], s["game"], s["npc_id"]
    ch = _char(case, npc_id)
    style_line = {"chatty": "어머, 그런 얘기 좋죠! 요즘 다들 바빠서 말할 사람이 없었어요.",
                  "blunt": "…그런 걸 왜 물어요.", "normal": "아, 네… 그냥 그렇죠 뭐."}[ch.small_talk_style]
    reply, _ = await deps.llm.structured(
        role="small_talk", bucket="npc", schema=NPCReply,
        system=f"{npc_agent.COMMON_RULES}\n이름: {ch.name}, 역할: {ch.role}, 성격: {ch.personality}, 말투: {ch.speech_style}\n"
               "사건과 무관한 잡담이다. 사건 정보를 꺼내지 말고 성격대로 짧게 답한다.",
        user=s["text"], fake=lambda: NPCReply(text=style_line),
        fallback=lambda: NPCReply(text=style_line), game_id=game.game_id, node="small_talk",
    )
    deps.on_small_talk(game, ch)
    _say(s, npc_id, reply.text)
    return s


def node_offtopic(s: TurnState) -> TurnState:
    deps: TurnDeps = s["deps"]
    res = deps.handle_offtopic(s["game"], s["npc_id"], s["route"])
    for ev in res.get("events", []):
        s["events"].append(ev)
    if res.get("chips_again"):
        s["events"].append(s["eb"].custom("chips_refresh", {}))
    _say(s, s["npc_id"], res.get("line", "네?"))
    return s


# ---------------------------------------------------------------------------- graph
def build_turn_graph():
    g = StateGraph(TurnState)
    g.add_node("turn_away_check", node_turn_away_check)
    g.add_node("route", node_route)
    g.add_node("bluff_hint", node_bluff_hint)
    g.add_node("warrant_hint", node_warrant_hint)
    g.add_node("retrieve", node_retrieve)
    g.add_node("npc_answer", node_npc_answer)
    g.add_node("gm_llm", node_gm_llm)
    g.add_node("after_answer", node_after_answer)
    g.add_node("small_talk", node_small_talk)
    g.add_node("offtopic", node_offtopic)
    g.add_edge(START, "turn_away_check")
    g.add_edge("turn_away_check", "route")
    g.add_conditional_edges("route", route_branch, {
        "retrieve": "retrieve", "bluff_hint": "bluff_hint", "warrant_hint": "warrant_hint",
        "small_talk": "small_talk", "offtopic": "offtopic", "end": END,
    })
    g.add_edge("bluff_hint", "retrieve")
    g.add_edge("warrant_hint", END)
    g.add_edge("retrieve", "npc_answer")
    g.add_conditional_edges("npc_answer", gm_branch, {"gm_llm": "gm_llm", "after_answer": "after_answer"})
    g.add_edge("gm_llm", "after_answer")
    g.add_edge("after_answer", END)
    g.add_edge("small_talk", END)
    g.add_edge("offtopic", END)
    return g.compile()


TURN_GRAPH = build_turn_graph()


async def run_turn(case: CaseBible, game: GameState, npc_id: str, text: str, deps: TurnDeps,
                   chip_route: RouterOutput | None = None,
                   prepared: PreparedAnswer | None = None) -> tuple[GameState, list[dict], TurnState]:
    eb = EventBuilder()
    if prepared is not None and (prepared.npc_id != npc_id or prepared.text != text or chip_route is None):
        prepared = None  # 다른 질문용으로 만든 답은 쓰지 않는다
    init: TurnState = {"case": case, "game": game, "npc_id": npc_id, "text": text, "chip_route": chip_route,
                       "prepared": prepared, "events": [], "eb": eb, "deps": deps}
    out: TurnState = await TURN_GRAPH.ainvoke(init)
    return out["game"], out["events"], out


async def prepare_answer(case: CaseBible, game: GameState, npc_id: str, text: str, deps: TurnDeps) -> PreparedAnswer:
    """칩 질문의 답을 미리 만든다: 검색 → 인물 답 → (필요하면) 게임 마스터 LLM 검사.
    실제 턴과 같은 노드를 그대로 쓴다. game은 호출자가 넘긴 복사본이어야 한다(뒤처리는 하지 않음)."""
    route = RouterOutput(kind="investigate", target_npc=npc_id, via="chip")
    s: TurnState = {"case": case, "game": game, "npc_id": npc_id, "text": text, "chip_route": route, "route": route,
                    "events": [], "eb": EventBuilder(), "deps": deps}
    node_retrieve(s)
    await node_npc_answer(s)
    if gm_branch(s) == "gm_llm":
        await node_gm_llm(s)
    return PreparedAnswer(npc_id=npc_id, text=text, role=_answer_role(_char(case, npc_id), route), reply=s["reply"],
                          verdict=s["verdict"], fallback_used=s["fallback_used"], hits=list(s.get("hits", [])))
