"""밤 시뮬레이션 그래프 (PRD §6.4~6.5, §11.3 그래프 C).

[NPC 자율 행동 판단(코드)] → [만남 결정(짝 상한)] → [NPC끼리 대화(LLM, 구조화 출력)] → [소문 검증(코드)]
→ [기억·관계 그래프 기록] → [기억 확신도 감소] → [평판 소문] → [아침]

핫 패스가 아니다. 예산은 "수십 초, 연출 장면 뒤"(PRD §14.1).
LLM은 대화 내용만 만들고, 무엇을 퍼뜨려도 되는지(왜곡 범위)는 코드가 정한다.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from server.game.events import EventBuilder
from server.llm.client import LLMClient
from server.schemas import CaseBible, GameState, NPCAction, Rumor


class NightLine(BaseModel):
    speaker_id: str
    text: str


class NightTalk(BaseModel):
    """NPC 둘의 밤 대화 결과 (LLM 구조화 출력)."""

    lines: list[NightLine] = Field(default_factory=list, max_length=8)
    rumors: list[Rumor] = Field(default_factory=list, max_length=3)


@dataclass
class NightDeps:
    llm: LLMClient
    decide_actions: Callable[[CaseBible, GameState], list[NPCAction]]
    pick_encounters: Callable[[CaseBible, GameState, list[NPCAction]], list[tuple[str, str]]]
    talk_prompt: Callable[[CaseBible, GameState, str, str], tuple[str, str]]  # (system, user)
    fake_talk: Callable[[CaseBible, GameState, str, str], NightTalk]
    validate_rumor: Callable[[CaseBible, Rumor], list[str]]  # 위반 목록 (코드)
    apply_talk: Callable[[GameState, str, str, NightTalk], None]  # 기억·관계 그래프 기록
    apply_actions: Callable[[CaseBible, GameState, list[NPCAction]], list[dict]]  # 이동·증거 숨기기 등 → 피드·기록
    end_of_night: Callable[[CaseBible, GameState], list[dict]]  # 확신도 감소, 평판 소문, 아침 처리 → 이벤트


class NightState(TypedDict, total=False):
    case: CaseBible
    game: GameState
    actions: list[NPCAction]
    pairs: list[tuple[str, str]]
    events: list[dict]
    eb: EventBuilder
    deps: Any
    log: list[dict]


def node_decide(s: NightState) -> NightState:
    d: NightDeps = s["deps"]
    s["actions"] = d.decide_actions(s["case"], s["game"])
    s["events"].append(s["eb"].custom("night_progress", {"step": 1, "total": 4, "text": "모두가 잠든 척하는 밤…"}))
    return s


def node_encounters(s: NightState) -> NightState:
    d: NightDeps = s["deps"]
    s["pairs"] = d.pick_encounters(s["case"], s["game"], s["actions"])
    s["events"].append(s["eb"].custom("night_progress", {"step": 2, "total": 4, "text": "어디선가 낮은 목소리가 들린다…"}))
    return s


async def node_talks(s: NightState) -> NightState:
    d: NightDeps = s["deps"]
    case, game = s["case"], s["game"]

    async def one(a: str, b: str) -> tuple[NightTalk, bool]:
        system, user = d.talk_prompt(case, game, a, b)

        def validate(t: NightTalk) -> list[str]:
            problems: list[str] = []
            speakers = {a, b}
            if any(line.speaker_id not in speakers for line in t.lines):
                problems.append("대화 참가자가 아닌 화자")
            for r in t.rumors:
                problems += d.validate_rumor(case, r)
            return problems

        return await d.llm.structured(
            role="night", bucket="night", schema=NightTalk, system=system, user=user,
            fake=lambda: d.fake_talk(case, game, a, b),
            fallback=lambda: NightTalk(),  # 실패하면 그 만남은 건너뛴다 (PRD §6.5)
            validate=validate, max_retries=2, game_id=game.game_id, node="night_talk",
        )

    # 만남끼리는 서로 기다릴 이유가 없으니 LLM 호출은 동시에, 결과 반영은 순서대로 (밤 대기 시간 = 가장 느린 대화 1개)
    results = await asyncio.gather(*(one(a, b) for a, b in s["pairs"]))
    for (a, b), (talk, fb) in zip(s["pairs"], results):
        if not fb:
            d.apply_talk(game, a, b, talk)
            s["log"].append({"pair": [a, b], "lines": [l.model_dump() for l in talk.lines],
                             "rumors": [r.model_dump() for r in talk.rumors]})
    s["events"].append(s["eb"].custom("night_progress", {"step": 3, "total": 4, "text": "소문이 퍼져 나간다…"}))
    return s


def node_actions(s: NightState) -> NightState:
    d: NightDeps = s["deps"]
    for ev in d.apply_actions(s["case"], s["game"], s["actions"]):
        s["events"].append(ev)
    return s


def node_morning(s: NightState) -> NightState:
    d: NightDeps = s["deps"]
    for ev in d.end_of_night(s["case"], s["game"]):
        s["events"].append(ev)
    s["game"].events_log.append({"type": "night", "day": s["game"].day, "talks": s["log"],
                                 "actions": [a.model_dump() for a in s["actions"]]})
    s["events"].append(s["eb"].custom("night_progress", {"step": 4, "total": 4, "text": "아침이 밝았다."}))
    return s


def build_night_graph():
    g = StateGraph(NightState)
    g.add_node("decide", node_decide)
    g.add_node("encounters", node_encounters)
    g.add_node("talks", node_talks)
    g.add_node("actions", node_actions)
    g.add_node("morning", node_morning)
    g.add_edge(START, "decide")
    g.add_edge("decide", "encounters")
    g.add_edge("encounters", "talks")
    g.add_edge("talks", "actions")
    g.add_edge("actions", "morning")
    g.add_edge("morning", END)
    return g.compile()


NIGHT_GRAPH = build_night_graph()


async def run_night(case: CaseBible, game: GameState, deps: NightDeps) -> tuple[GameState, list[dict]]:
    init: NightState = {"case": case, "game": game, "events": [], "eb": EventBuilder(), "deps": deps, "log": []}
    out: NightState = await NIGHT_GRAPH.ainvoke(init)
    return out["game"], out["events"]
