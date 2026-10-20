"""탐정 자동 플레이 에이전트 (PRD §7.6, 풀이율 평가용).

사람 없이 스스로 수사해 사건이 풀리는지 잰다. 정답을 아는 확인용 봇(`playthrough.py`)과 달리 **플레이어가 보는
정보(PlayerView)만** 본다. 사건 원본·범인·거짓말 장부는 에이전트에 넘기지 않는다. 하네스(이 파일의 `play`)는
끝났는지·엔딩이 무엇인지 보려고 저장된 상태를 읽을 뿐 에이전트의 판단에는 쓰지 않는다.

흐름: 한 걸음마다 LLM이 행동 하나를 고른다(이동·조사·질문·추천 질문·증거 제시·하루 끝내기·지목).
지목하면 범인과 단계별(기회·수단·동기) 증거를 한 번에 정하고, 최종 추리를 그 순서대로 진행한다.
- 한 번에 한 사람만 지목한다. 틀린 사람이면 한 번 물릴 수 있고(사람 플레이어도 그렇다) 그 결과는 따로 센다.
  `first_try`가 처음 지목이 맞았는지, `success`가 끝내 풀었는지다.
- 틀린 증거를 내도 다시 시도하지 않는다(무차별 대입 방지). 그래서 사람보다 보수적인 풀이율이다.

  uv run python -m server.evals.detective                       # 키가 없으면 가짜 LLM(배관 점검용, 풀이율 아님)
  uv run python -m server.evals.detective --real --games 1      # 진짜 모델 사용량이 든다(--real 없이는 안 돈다)

진짜 모델 실행은 Max 요금제의 5시간·주간 한도 안에서만 한다. `--max-calls`(기본 300)를 넘으면 그 판을 멈춘다.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from server.schemas import PlayerView

ActionName = Literal["move", "investigate", "ask", "chip", "present", "end_day", "accuse"]
STAGES = ("opportunity", "means", "motive")


class DetectiveStep(BaseModel):
    thought: str = Field(default="", description="지금 왜 이 행동인지 한두 문장")
    action: ActionName
    location_id: str = ""
    npc_id: str = ""
    text: str = ""
    chip_id: str = ""
    evidence_id: str = ""


class DetectiveVerdict(BaseModel):
    reasoning: str = ""
    accused_id: str
    opportunity: str = Field(default="", description="기회(그 시각 현장에 있을 수 있었음)를 보이는 증거 id")
    means: str = Field(default="", description="수단(그 일을 할 방법)을 보이는 증거 id")
    motive: str = Field(default="", description="동기(그럴 이유)를 보이는 증거 id")


@dataclass
class DetectiveResult:
    ending: str = "none"
    success: bool = False
    first_try: bool = False  # 처음 지목이 맞았는가 (물리기 전)
    accusations: list[str] = field(default_factory=list)
    days: int = 0
    actions: int = 0
    steps: int = 0
    invalid_steps: int = 0
    detective_calls: int = 0
    total_calls: int = 0
    fallbacks: int = 0
    seconds: float = 0.0
    stopped: str = ""
    errors: list[str] = field(default_factory=list)
    log: list[str] = field(default_factory=list)  # 한 걸음마다 한 줄 (사람이 읽고 복기)


@dataclass
class Memory:
    """에이전트가 직접 적어 두는 수사 메모(보이는 정보로만 만든다)."""
    notes: list[str] = field(default_factory=list)
    investigated: dict[str, int] = field(default_factory=dict)
    chips_used: set[str] = field(default_factory=set)


SYSTEM = """너는 추리 게임의 탐정(형사)이다. 사건을 직접 수사해 범인을 찾는다. 아는 것은 화면에 보이는 정보뿐이다.
한 번에 행동 하나만 고른다.
- move: 열린 장소(location_id)로 이동. 처음 가는 곳은 행동을 쓰고, 가 본 곳은 무료다.
- investigate: 지금 장소를 조사해 증거를 찾는다.
- ask: 지금 장소에 있는 인물(npc_id)에게 직접 질문(text). 알리바이, 본 것, 다른 사람과의 관계를 구체적으로 묻는다.
- chip: 화면에 뜬 추천 질문(chip_id) 하나를 누른다. 증거 제시 칩도 있다.
- present: 가진 증거(evidence_id)를 지금 장소의 인물(npc_id)에게 내민다. 진술과 어긋나는 증거에서 모순이 드러난다.
- end_day: 하루를 끝낸다(남은 행동이 있어도). 밤에 인물들이 움직이고 새 정보가 생긴다. 마지막 날에는 쓸 수 없고 지목해야 한다.
- accuse: 범인을 지목한다. 증거가 충분하거나 마지막 날 행동을 다 썼을 때만.
규칙: 화면에 없는 id를 지어내지 않는다. 증거와 진술이 어긋나는 사람을 의심하고, 기회·수단·동기를 각각 보이는 증거를 모은다.
행동 수가 한정되어 있으니 같은 질문·같은 장소 조사를 되풀이하지 않는다. 낭비 없이 모순을 찾는다."""

VERDICT_SYSTEM = """너는 추리 게임의 탐정이다. 수사를 마치고 범인을 지목한다. 화면에 보이는 정보(인물, 증거, 진술, 모순)만 근거로 쓴다.
범인(accused_id)을 정하고, 기회·수단·동기 각각을 가장 잘 보이는 증거 id를 고른다(증거 목록에 있는 id만, 다른 사람 얘기인 증거는 쓰지 않는다).
확신이 없어도 가장 가능성 높은 사람을 고른다."""


def observe(view: PlayerView, mem: Memory) -> str:
    """에이전트에 보여 줄 관찰(PlayerView만). 범인 여부·비밀 같은 건 애초에 뷰에 없다."""
    loc = {l.id: l for l in view.locations}
    here = loc.get(view.player_location)
    lines = [f"사건: {view.case_title} — {view.incident_summary}",
             f"{view.day}일차/{view.max_days}일 · 행동 {view.actions_left}/{view.actions_total} · 지금 장소: "
             f"{here.name if here else view.player_location}({view.player_location})",
             "열린 장소: " + "; ".join(f"{l.id}={l.name}(이동 {','.join(l.connections) or '-'})" +
                                   ("[가 봄]" if l.id in view.visited_locations else "") for l in view.locations),
             "인물: " + "; ".join(f"{c.id}={c.name}({c.role},{c.age}세,{c.location_id or '위치 모름'}) {c.one_liner}"
                                for c in view.characters)]
    if view.evidence:
        lines.append("가진 증거:\n" + "\n".join(f"- {e.id} [{e.kind}] {e.name}: {e.content}" for e in view.evidence))
    else:
        lines.append("가진 증거: 없음")
    if view.notebook.statements:
        who = {c.id: c.name for c in view.characters}
        lines.append("진술:\n" + "\n".join(f"- {who.get(s.npc_id, s.npc_id)}: {s.content}" for s in view.notebook.statements[-25:]))
    if view.notebook.contradictions:
        lines.append("찾아낸 모순: " + "; ".join(c.note or f"진술 {c.statement_id} ↔ 증거 {c.evidence_id}"
                                               for c in view.notebook.contradictions))
    if view.chips:
        lines.append("추천 질문(chip): " + "; ".join(f"{c.id}[{c.kind}] {c.label}" for c in view.chips if c.id not in mem.chips_used))
    if view.sufficiency_gauge:
        lines.append("형사의 감: " + ", ".join(f"{k}={v}/5" for k, v in view.sufficiency_gauge.items()))
    if mem.notes:
        lines.append("내 메모:\n" + "\n".join(f"- {n}" for n in mem.notes[-12:]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- 가짜 LLM(배관 점검용)
def _fake_step(view: PlayerView, mem: Memory) -> DetectiveStep:
    """키 없이 돌 때 쓰는 단순 규칙(풀이율을 재는 게 아니라 흐름이 끝까지 도는지 보는 용도)."""
    if view.actions_left <= 0:
        return DetectiveStep(action="accuse" if view.day >= view.max_days else "end_day")
    here = view.player_location
    if mem.investigated.get(here, 0) < 2:
        return DetectiveStep(action="investigate")
    for l in view.locations:
        if l.id != here and l.id not in view.visited_locations and l.id in {c for c in next(
                (x.connections for x in view.locations if x.id == here), [])}:
            return DetectiveStep(action="move", location_id=l.id)
    chip = next((c for c in view.chips if c.id not in mem.chips_used and c.kind == "ask"), None)
    if chip:
        return DetectiveStep(action="chip", chip_id=chip.id)
    return DetectiveStep(action="accuse" if view.day >= view.max_days else "end_day")


def _fake_verdict(view: PlayerView) -> DetectiveVerdict:
    ids = [e.id for e in view.evidence] + ["", "", ""]
    return DetectiveVerdict(accused_id=view.characters[0].id, opportunity=ids[0], means=ids[1], motive=ids[2])


# --------------------------------------------------------------------------- 하네스
async def _events(svc: Any, gid: str, action: dict, res: DetectiveResult) -> tuple[list[dict], str]:
    evs = [e async for e in svc.act(gid, action)]
    res.actions += 1
    errs = [e.get("message", "") for e in evs if e["type"] == "RUN_ERROR"]
    npc = {e["messageId"] for e in evs if e["type"] == "TEXT_MESSAGE_START" and e.get("role") == "npc"}
    said = "".join(e.get("delta", "") for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT" and e["messageId"] in npc)
    return evs, said or "; ".join(errs)


def _valid(view: PlayerView, step: DetectiveStep, mem: Memory) -> str:
    """보이는 정보와 맞지 않는 행동이면 이유, 맞으면 빈 문자열."""
    ids_loc = {l.id for l in view.locations}
    here_chars = {c.id for c in view.characters if c.location_id == view.player_location}
    a = step.action
    if a == "move" and (step.location_id not in ids_loc or step.location_id == view.player_location):
        return "열려 있지 않거나 이미 있는 장소"
    if a == "ask" and (step.npc_id not in here_chars or not step.text.strip()):
        return "이 장소에 없는 인물이거나 질문이 비었음"
    if a == "chip" and step.chip_id not in {c.id for c in view.chips}:
        return "화면에 없는 추천 질문"
    if a == "present" and (step.npc_id not in here_chars or step.evidence_id not in {e.id for e in view.evidence}):
        return "이 장소에 없는 인물이거나 가지고 있지 않은 증거"
    if a == "end_day" and view.day >= view.max_days:
        return "마지막 날에는 하루를 끝낼 수 없다(지목해야 함)"
    return ""


async def play(svc: Any, theme: str = "demo_db_deleted", *, max_steps: int = 80, max_calls: int = 300,
               difficulty: str = "normal") -> DetectiveResult:
    res, t0 = DetectiveResult(), time.perf_counter()
    gid, _ = svc.new_game(theme, {"difficulty": difficulty})
    mem, bad_streak = Memory(), 0
    tracer = svc.llm.tracer

    def calls() -> int:
        return len(tracer.records)

    async def decide(view: PlayerView) -> DetectiveStep:
        step, fb = await svc.llm.structured(
            role="detective", bucket="detective", schema=DetectiveStep, system=SYSTEM, user=observe(view, mem),
            fake=lambda: _fake_step(view, mem), fallback=lambda: DetectiveStep(action="end_day" if view.day < view.max_days else "accuse"),
            game_id=gid, node="detective_step")
        res.detective_calls += 1
        res.fallbacks += int(fb)
        return step

    for _ in range(max_steps):
        st = svc.store.load_live(gid)  # 하네스 전용(끝났는지만). 에이전트에는 안 넘긴다
        if st.ending != "none":
            break
        if calls() >= max_calls:
            res.stopped = f"호출 {max_calls}번 상한"
            break
        view = svc.view(gid)
        step = await decide(view)
        res.steps += 1
        why = _valid(view, step, mem)
        if why:
            res.invalid_steps += 1
            bad_streak += 1
            res.log.append(f"[{res.steps}] 무효 {step.action}: {why}")
            if bad_streak >= 3:  # 헛도는 것을 끊는다
                step = DetectiveStep(action="accuse" if view.day >= view.max_days else "end_day")
            else:
                mem.notes.append(f"(무효: {step.action} — {why})")
                continue
        bad_streak = 0
        if step.thought:
            mem.notes.append(step.thought[:160])
        res.log.append(f"[{res.steps}] {step.action} {step.location_id or step.npc_id or step.chip_id} {step.text[:50]}")
        if step.action == "accuse":
            break
        if step.action == "end_day":
            evs = [e async for e in svc.night(gid)]
            res.errors += [e.get("message", "") for e in evs if e["type"] == "RUN_ERROR"]
            mem.notes.append(f"{view.day}일차 밤이 지났다.")
            continue
        payload = {"move": {"type": "move", "location_id": step.location_id},
                   "investigate": {"type": "investigate"},
                   "ask": {"type": "ask", "npc_id": step.npc_id, "text": step.text},
                   "chip": {"type": "chip", "chip_id": step.chip_id},
                   "present": {"type": "present", "npc_id": step.npc_id, "evidence_id": step.evidence_id}}[step.action]
        if step.action == "chip":
            mem.chips_used.add(step.chip_id)
        if step.action == "investigate":
            mem.investigated[view.player_location] = mem.investigated.get(view.player_location, 0) + 1
        _, out = await _events(svc, gid, payload, res)
        if out:
            mem.notes.append(f"{step.action} 결과: {out[:200]}")
    else:
        res.stopped = res.stopped or f"걸음 {max_steps}번 상한"

    if svc.store.load_live(gid).ending == "none":
        await _accuse(svc, gid, res, mem)
    st = svc.store.load_live(gid)
    # 최종 추리를 끝내지 못했으면(증거를 못 모아 단계를 못 채움 등) 풀지 못한 것으로 센다
    res.ending, res.success = (st.ending if st.ending != "none" else "unfinished"), st.ending == "success"
    res.days, res.seconds, res.total_calls = st.day, time.perf_counter() - t0, calls()
    return res


async def _accuse(svc: Any, gid: str, res: DetectiveResult, mem: Memory) -> None:
    """지목 → (틀리면 한 번 물리고 다시) → 단계별 증거 제시. 한 판에 지목은 최대 2번."""
    banned: set[str] = set()
    for attempt in range(2):
        view = svc.view(gid)
        cands = [c for c in view.characters if c.id not in banned]
        if not cands:
            return
        ctx = observe(view, mem) + ("\n이미 아니라고 확인된 인물: " + ", ".join(sorted(banned)) if banned else "")
        v, fb = await svc.llm.structured(
            role="detective", bucket="detective", schema=DetectiveVerdict, system=VERDICT_SYSTEM, user=ctx,
            fake=lambda: _fake_verdict(view), fallback=lambda: DetectiveVerdict(accused_id=cands[0].id),
            validate=lambda x: [] if x.accused_id in {c.id for c in cands} else [f"없는 인물 id: {x.accused_id}"],
            game_id=gid, node="detective_verdict")
        res.detective_calls += 1
        res.fallbacks += int(fb)
        res.accusations.append(v.accused_id)
        res.log.append(f"지목 {v.accused_id}: {v.reasoning[:80]}")
        evs = [e async for e in svc.finale(gid, {"type": "start", "accused_id": v.accused_id})]
        st = svc.store.load_live(gid)
        pending = bool((st.finale or {}).get("pending_confirmation"))
        if attempt == 0:
            res.first_try = not pending
        if pending:  # 지목이 틀렸다는 반응(NPC 반박). 한 번은 물린다
            banned.add(v.accused_id)
            _ = [e async for e in svc.finale(gid, {"type": "retract"})]
            if attempt == 1:  # 두 번째도 틀리면 확정
                _ = [e async for e in svc.finale(gid, {"type": "start", "accused_id": v.accused_id})]
                _ = [e async for e in svc.finale(gid, {"type": "confirm"})]
            continue
        owned = {e.id for e in view.evidence}
        for stage in STAGES:
            eid = getattr(v, stage)
            if eid not in owned:
                res.log.append(f"{stage}: 가진 증거가 아님({eid or '없음'})")
                continue
            evs += [e async for e in svc.finale(gid, {"type": "present", "stage": stage, "evidence_id": eid})]
            if svc.store.load_live(gid).ending != "none":
                break
        res.errors += [e.get("message", "") for e in evs if e["type"] == "RUN_ERROR"]
        break
    st = svc.store.load_live(gid)
    if st.ending == "none" and st.phase == "finale":  # 증거가 모자라 단계를 못 채움 → 도주(범인이 버팀)로 끝낸다
        res.log.append("증거를 다 못 대 최종 추리를 마치지 못함")


def render(results: list[DetectiveResult]) -> str:
    n = len(results)
    win = sum(r.success for r in results)
    first = sum(r.first_try for r in results)
    lines = [f"판 {n}개 · 풀림 {win}개({win / n:.0%}) · 처음 지목이 맞음 {first}개({first / n:.0%}) · "
             f"탐정 호출 평균 {sum(r.detective_calls for r in results) / n:.0f}번 · 전체 호출 평균 "
             f"{sum(r.total_calls for r in results) / n:.0f}번" if n else "판 없음", "",
             "| # | 엔딩 | 지목 | 일 | 행동 | 걸음 | 무효 | 탐정 호출 | 전체 호출 | 대체 | 멈춤 |",
             "|--|--|--|--|--|--|--|--|--|--|--|"]
    for i, r in enumerate(results, 1):
        lines.append(f"| {i} | {r.ending} | {'→'.join(r.accusations) or '-'} | {r.days} | {r.actions} | {r.steps} | "
                     f"{r.invalid_steps} | {r.detective_calls} | {r.total_calls} | {r.fallbacks} | {r.stopped or '-'} |")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="탐정 자동 플레이 에이전트(풀이율). 진짜 모델은 --real이 있을 때만")
    ap.add_argument("--games", type=int, default=1)
    ap.add_argument("--theme", default="demo_db_deleted")
    ap.add_argument("--difficulty", choices=["easy", "normal", "hard"], default="normal")
    ap.add_argument("--max-steps", type=int, default=80)
    ap.add_argument("--max-calls", type=int, default=300, help="한 판의 LLM 호출 상한(넘으면 그 판을 멈춘다)")
    ap.add_argument("--real", action="store_true", help="진짜 모델 사용량이 드는 것을 알고 실행")
    args = ap.parse_args(argv)
    from server.llm.latency import _temp_service

    svc = _temp_service()
    if not svc.llm.fake_mode and not args.real:
        raise SystemExit("진짜 모델 연결이 켜져 있다. 사용량이 드니 --real을 붙여 다시 실행하라(풀이율은 한도 안에서만 잰다).")
    results = []
    for g in range(args.games):
        r = asyncio.run(play(svc, args.theme, max_steps=args.max_steps, max_calls=args.max_calls, difficulty=args.difficulty))
        results.append(r)
        print(f"[판 {g + 1}] {r.ending} 호출 {r.total_calls}번 {r.seconds:.0f}초" + (f" ({r.stopped})" if r.stopped else ""))
        svc.llm.tracer.records.clear()  # 다음 판의 호출 상한을 새로 센다
    print(render(results))


if __name__ == "__main__":
    main()
