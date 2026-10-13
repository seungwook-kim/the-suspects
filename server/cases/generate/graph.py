"""그래프 A: 사건 생성 (PRD §5.2, §11.3).

[재료 추첨(코드)] → [주제 검토·세계관(LLM)] → [인물(LLM)] → (브리핑 미리보기) → [사건 설계(LLM)]
   → [기억·문서 (LLM, 동시)] → [조립·검수(코드)] ─ 실패면 사건 설계로 (최대 3회) ─ 통과 → END

- 구조는 코드(plan.py)가 정하고 LLM은 빈칸만 채운다. 검수(verify_case)는 안전망이다.
- 모든 LLM 호출은 같은 안전장치(스키마 검증 → 코드 검증 → 재시도 2회 → 대체)를 거친다.
- 진행 상황은 progress(stage, text, preview) 콜백으로 알린다 → 화면은 "사건 파일 작성 중…" 같은 문구를 보여 준다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from server.cases.generate import writer as W
from server.cases.generate.assemble import assemble
from server.cases.generate.plan import Plan, draw
from server.cases.verify import verify_case
from server.llm.client import LLMClient
from server.schemas import CaseBible

TOTAL_STAGES = 6
STAGE_TEXT = {
    1: "사건 의뢰서 검토 중…",
    2: "용의자 명단 정리 중…",
    3: "사건 파일 작성 중…",
    4: "진술과 기록 맞춰 보는 중…",
    5: "사건 검수 중…",
    6: "현장 준비 중…",
}
MAX_DESIGN_ATTEMPTS = 3

Progress = Callable[[int, str, dict | None], None]


@dataclass
class GenResult:
    outcome: str  # ok | rejected | failed
    case: CaseBible | None = None
    message: str = ""
    problems: list[str] = field(default_factory=list)


class GenState(TypedDict, total=False):
    plan: Plan
    llm: LLMClient
    progress: Progress
    concept: W.ConceptOut
    cast: W.CastOut
    design: W.DesignOut
    memories: dict[str, W.MemoriesOut]
    docs: W.DocsOut
    case: CaseBible
    problems: list[str]
    attempts: int
    outcome: str
    message: str


async def _write(s: GenState, node: str, schema, prompt: tuple[str, str], fake, validate) -> tuple[Any, bool]:
    system, user = prompt
    return await s["llm"].structured(
        role="writer", bucket="casegen", schema=schema, system=system, user=user, fake=fake,
        fallback=lambda: None, validate=validate, max_retries=2, node=f"casegen_{node}",
    )


async def node_world(s: GenState) -> GenState:
    plan = s["plan"]
    s["progress"](1, STAGE_TEXT[1], None)
    concept, failed = await _write(s, "world", W.ConceptOut, W.concept_prompt(plan), lambda: W.fake_concept(plan),
                                   W.validate_concept)
    if failed or concept is None:
        s["outcome"], s["message"] = "failed", "사건 의뢰서를 읽다가 문제가 생겼어요."
    elif not concept.ok:
        s["outcome"], s["message"] = "rejected", concept.reject_reason or "이 주제로는 사건을 만들 수 없어요."
    else:
        s["concept"] = concept
    return s


async def node_cast(s: GenState) -> GenState:
    plan = s["plan"]
    s["progress"](2, STAGE_TEXT[2], None)
    cast, failed = await _write(s, "cast", W.CastOut, W.cast_prompt(plan, s["concept"]), lambda: W.fake_cast(plan),
                                lambda c: W.validate_cast(plan, c))
    if failed or cast is None:
        s["outcome"], s["message"] = "failed", "용의자 명단을 정리하지 못했어요."
        return s
    s["cast"] = cast
    s["progress"](3, STAGE_TEXT[3], preview(plan, s["concept"], cast))
    return s


async def node_design(s: GenState) -> GenState:
    plan = s["plan"]
    s["progress"](3, STAGE_TEXT[3] if not s.get("problems") else "앞뒤가 안 맞는 곳을 고치는 중…", None)
    design, failed = await _write(
        s, "design", W.DesignOut, W.design_prompt(plan, s["concept"], s["cast"], s.get("problems")),
        lambda: W.fake_design(plan, s["concept"]), lambda d: W.validate_design(plan, d),
    )
    if failed or design is None:
        s["outcome"], s["message"] = "failed", "사건 파일을 완성하지 못했어요."
    else:
        s["design"] = design
    return s


async def node_details(s: GenState) -> GenState:
    """인물별 기억과 문서·스토리보드는 서로 기다릴 이유가 없어 동시에 쓴다 (PRD §14: 인물 생성 병렬)."""
    plan, concept, cast, design = s["plan"], s["concept"], s["cast"], s["design"]
    s["progress"](4, STAGE_TEXT[4], None)

    async def one_memory(slot: str):
        out, failed = await _write(s, "memory", W.MemoriesOut, W.memory_prompt(plan, concept, cast, design, slot),
                                   lambda: W.fake_memories(plan, slot), W.validate_memories)
        return slot, (out if not failed and out is not None else W.MemoriesOut(memories=[]))  # 실패해도 타임라인 기억은 코드가 넣음

    async def docs():
        out, failed = await _write(s, "docs", W.DocsOut, W.docs_prompt(plan, concept, cast, design),
                                   lambda: W.fake_docs(plan, concept), lambda d: W.validate_docs(plan, d))
        return out if not failed and out is not None else W.fake_docs(plan, concept)

    results = await asyncio.gather(*(one_memory(p.slot) for p in plan.people), docs())
    s["memories"] = dict(results[:-1])  # type: ignore[arg-type]
    s["docs"] = results[-1]  # type: ignore[assignment]
    return s


def node_assemble(s: GenState) -> GenState:
    s["progress"](5, STAGE_TEXT[5], None)
    s["attempts"] = s.get("attempts", 0) + 1
    try:
        case = assemble(s["plan"], s["concept"], s["cast"], s["design"], s["memories"], s["docs"])
        problems = [str(v) for v in verify_case(case)]
    except (KeyError, ValueError, StopIteration) as e:  # 작가 출력이 빈칸을 어겼을 때
        case, problems = None, [f"조립 실패: {type(e).__name__}: {e}"]
    s["problems"] = problems
    if not problems and case is not None:
        s["case"], s["outcome"] = case, "ok"
    elif s["attempts"] >= MAX_DESIGN_ATTEMPTS:
        s["outcome"], s["message"] = "failed", "사건을 짜다가 앞뒤가 안 맞는 부분을 끝내 고치지 못했어요."
    return s


def _stop_or(nxt: str):
    return lambda s: END if s.get("outcome") else nxt


def build_case_graph():
    g = StateGraph(GenState)
    g.add_node("world", node_world)
    g.add_node("cast", node_cast)
    g.add_node("design", node_design)
    g.add_node("details", node_details)
    g.add_node("assemble", node_assemble)
    g.add_edge(START, "world")
    g.add_conditional_edges("world", _stop_or("cast"), ["cast", END])
    g.add_conditional_edges("cast", _stop_or("design"), ["design", END])
    g.add_conditional_edges("design", _stop_or("details"), ["details", END])
    g.add_edge("details", "assemble")
    g.add_conditional_edges("assemble", lambda s: END if s.get("outcome") else "design", ["design", END])
    return g.compile()


_GRAPH = None


def preview(plan: Plan, concept: W.ConceptOut, cast: W.CastOut) -> dict:
    """브리핑 미리보기 (공개 정보만: 범인·비밀·말투 없음)."""
    po = {x.slot: x for x in cast.people}
    chars = []
    for p in plan.people:
        o = po[p.slot]
        first = o.personality.split(". ")[0].strip()
        chars.append({
            "id": p.id, "name": p.name, "role": o.role, "age": o.age, "gender": p.gender,
            "appearance": {"hair": p.hair, "hair_color": p.hair_color, "outfit": o.outfit if o.outfit in W.OUTFITS else "casual",
                           **({"accessory": o.accessory} if o.accessory in W.ACCESSORIES and o.accessory else {})},
            "face_seed": p.face_seed, "location_id": None, "emotion": "neutral",
            "one_liner": first if first.endswith(".") else first + ".",
        })
    return {"title": concept.title, "incident_summary": concept.incident_summary, "characters": chars}


async def generate_case(llm: LLMClient, case_id: str, theme_text: str, options: dict | None,
                        progress: Progress | None = None, seed: int | None = None) -> GenResult:
    global _GRAPH
    _GRAPH = _GRAPH or build_case_graph()
    plan = draw(case_id, theme_text, options, seed)
    state: GenState = {"plan": plan, "llm": llm, "progress": progress or (lambda *_: None), "attempts": 0}
    out = await _GRAPH.ainvoke(state, {"recursion_limit": 40})
    return GenResult(outcome=out.get("outcome") or "failed", case=out.get("case"), message=out.get("message", ""),
                     problems=out.get("problems", []))
