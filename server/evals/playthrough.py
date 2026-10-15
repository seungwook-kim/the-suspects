"""한 판 자동 플레이 점검 (실제 모델로 처음부터 클리어까지 막힘 없이 도는지).

정답을 아는 확인용 봇이다(풀이율 평가용 탐정 에이전트 §7.6과 다름). 장소를 여는 인물과 먼저 말하고, 증거가 남은
장소만 조사하고, 하루를 넘기고, 최종 추리에서 단계마다 맞는 증거를 낸다. 심문은 추천 질문(미리 만들기 포함)과
직접 쓴 질문을 섞는다. 결과: 성공 여부, 오류 이벤트, 대체 대사 수, 응답 지연 요약.

  uv run python -m server.evals.playthrough          # 진짜 모델(개발 연결) 사용량이 든다
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from server.game import content as C
from server.game.masking import IdMasker


@dataclass
class PlayResult:
    ending: str = "none"
    days: int = 0
    actions: int = 0
    errors: list[str] = field(default_factory=list)
    lines: list[tuple[str, str, str]] = field(default_factory=list)  # (누가, 질문, 화면에 나간 답)
    seconds: float = 0.0


async def _act(svc: Any, gid: str, action: dict, res: PlayResult, who: str = "", q: str = "") -> list[dict]:
    evs = [e async for e in svc.act(gid, action)]
    res.actions += 1
    res.errors += [e.get("message", "") for e in evs if e["type"] == "RUN_ERROR"]
    npc_msgs = {e["messageId"] for e in evs if e["type"] == "TEXT_MESSAGE_START" and e.get("role") == "npc"}
    text = "".join(e.get("delta", "") for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT" and e["messageId"] in npc_msgs)
    if who:
        res.lines.append((who, q, text))
    return evs


async def play(svc: Any, theme: str = "demo_db_deleted", read_s: float = 6.0,
               typed: str = "그날 밤 누구랑 같이 있었어요?") -> PlayResult:
    res, t0 = PlayResult(), time.perf_counter()
    case = svc.cases[theme]
    gid, _ = svc.new_game(theme, {"difficulty": "normal"})
    unlockers = [loc.unlock_condition.split(":", 1)[1] for loc in case.locations
                 if loc.unlock_condition and loc.unlock_condition.startswith("talk:")]
    talked: set[str] = set()

    async def interrogate(npc: str) -> None:
        name = C.char(case, npc).name
        chip = next((c for c in svc.view(gid).chips if c.kind == "ask" and c.target_npc == npc), None)
        if chip:  # 추천 질문: 심문을 열면 화면이 /prepare를 부르고, 플레이어가 읽는 동안 답이 만들어진다
            await svc.prepare(gid, npc)
            await asyncio.sleep(read_s)
            await _act(svc, gid, {"type": "chip", "chip_id": chip.id}, res, name, chip.label)
        st = svc.store.load_live(gid)
        if st.actions_left >= 1 and st.npc_states[npc].location_id == st.player_location:
            await _act(svc, gid, {"type": "ask", "npc_id": npc, "text": typed}, res, name, typed)
        talked.add(npc)

    for _ in range(6):
        st = svc.store.load_live(gid)
        if st.ending != "none":
            break
        for npc in unlockers:
            st = svc.store.load_live(gid)
            if npc in talked or st.actions_left < 3 or not st.npc_states[npc].visible:
                continue
            loc = st.npc_states[npc].location_id
            if loc in st.unlocked_locations:
                if loc != st.player_location:
                    await _act(svc, gid, {"type": "move", "location_id": loc}, res)
                await interrogate(npc)
        for loc in list(svc.store.load_live(gid).unlocked_locations):
            st = svc.store.load_live(gid)
            if C.remaining_at(case, st, loc) == 0 or st.actions_left < 2:
                continue
            if loc != st.player_location:
                await _act(svc, gid, {"type": "move", "location_id": loc}, res)
            while True:
                st = svc.store.load_live(gid)
                if C.remaining_at(case, st, loc) == 0 or st.actions_left < 1:
                    break
                await _act(svc, gid, {"type": "investigate"}, res)
        st = svc.store.load_live(gid)
        done = all(C.remaining_at(case, st, l) == 0 for l in st.unlocked_locations) and all(n in talked for n in unlockers)
        if st.day >= st.max_days or done:
            break
        evs = [e async for e in svc.night(gid)]
        res.errors += [e.get("message", "") for e in evs if e["type"] == "RUN_ERROR"]

    st = svc.store.load_live(gid)
    culprit = case.culprit_ids[0]
    owned = set(st.notebook.evidence_ids)
    masker = IdMasker(case, st.id_salt)
    evs = [e async for e in svc.finale(gid, {"type": "start", "accused_id": culprit})]
    for stage in ("opportunity", "means", "motive"):
        ev = next((e for e in case.evidence if e.id in owned and stage in e.element_tags and culprit in e.linked_suspects), None)
        if ev is None:
            res.errors.append(f"최종 추리 {stage} 단계 증거를 수사로 얻지 못함")
            break
        evs += [e async for e in svc.finale(gid, {"type": "present", "stage": stage,
                                                   "evidence_id": masker.out("evidence", ev.id)})]
    res.errors += [e.get("message", "") for e in evs if e["type"] == "RUN_ERROR"]
    st = svc.store.load_live(gid)
    res.ending, res.days, res.seconds = st.ending, st.day, time.perf_counter() - t0
    return res


def render(res: PlayResult, records: list[dict]) -> str:
    from server.llm.latency import render_markdown, summarize

    fb = sum(1 for r in records if r.get("fallback_used"))
    stopped = sum(1 for r in records if (r.get("extra") or {}).get("stopped"))
    lines = [f"결과: {res.ending} · {res.days}일차 · 행동 {res.actions}번 · 걸린 시간 {res.seconds:.0f}초 · "
             f"오류 {len(res.errors)}개 · 대체 동작 {fb}번 · 중간에 끊은 답 {stopped}번", ""]
    lines += [f"- 오류: {e}" for e in res.errors]
    lines += ["", "| 누구 | 질문 | 화면에 나간 답 |", "|:--|:--|:--|"]
    lines += [f"| {w} | {q} | {a.replace('|', '/')} |" for w, q, a in res.lines]
    lines += ["", render_markdown(summarize(records), title="이번 판 호출 기록")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="한 판 자동 플레이 점검 (진짜 모델 사용량이 든다)")
    ap.add_argument("--read", type=float, default=6.0, help="추천 질문을 누르기 전 읽는 시간(초)")
    args = ap.parse_args(argv)
    from server.llm.latency import _temp_service

    svc = _temp_service()
    res = asyncio.run(play(svc, read_s=args.read))
    print(render(res, [r.__dict__ for r in svc.llm.tracer.records]))


if __name__ == "__main__":
    main()
