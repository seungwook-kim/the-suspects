"""응답 지연 측정 (PRD §17.1 응답 지연, §17.5 개선 기록).

호출 기록(Tracer JSONL, 기본 var/traces.jsonl)으로 두 가지를 낸다.
1. 요약: 역할별 지연 p50·p95·최대와 출력 토큰, 질문 1개 단위(질문→답) 지연.
   질문 1개 = 앞선 LLM 라우터·검색 + 인물 답 + 뒤따른 게임 마스터 LLM 검사.
2. 다시 보내기(replay): 기록된 요청(개발 모드는 지시문·질문 원문을 남김)을 지금 모델 설정으로 다시 보내 잰다.
   설정·프롬프트를 바꾼 뒤 같은 요청으로 전후를 비교하는 용도. 진짜 모델을 부르므로 사용량이 든다.

결과는 evals/reports/ 보고서에 붙일 수 있는 마크다운 표로도 낸다.

추천 질문 답 미리 만들기(server/game/speculative.py)와 함께 볼 때:
- node가 "…:speculative"인 호출은 미리 만든 호출이라 질문 단위 지연에서 뺀다(플레이어가 기다리지 않음).
- model "prepared"는 미리 만든 답을 꺼내 쓴 기록이다. 지연 = 그 답이 끝나기를 기다린 시간.
- role "speculative" 기록(준비 1번마다 미리 만든 수·쓴 수)으로 적중률을 낸다(PRD §17.1 추측 생성 적중률).

  uv run python -m server.llm.latency --since "2026-10-14 13:40" --until "2026-10-14 13:58"
  uv run python -m server.llm.latency --replay 4 --roles npc     # 최근 인물 답 요청 4개 다시 보내기
  uv run python -m server.llm.latency --replay 4 --roles npc --thinking off   # 같은 요청을 생각 끄고
  uv run python -m server.llm.latency --speculative 2            # 칩 답 미리 만들기 효과 (A·B·C 방식 2번씩)
  uv run python -m server.llm.latency --stream-check 3           # 직접 쓴 질문의 첫 문장·전체 시간 (첫 문장부터 보여 주기 끔/켬)

첫 문장부터 보여 주기(server/agents/npc.py answer_stream): 인물 답 호출 기록의 extra.first_text_s = 그 호출을 시작해
첫 문장을 내보내기까지 걸린 시간. 질문 단위 "첫 문장" = 앞선 라우터·검색 + first_text_s (없으면 답이 다 끝난 시각).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

ANSWER_ROLES = ("npc", "npc_hard", "npc_minor", "small_talk")  # 플레이어가 기다리는 인물 답
BEFORE_ANSWER = ("router", "retrieval")  # 답 앞에 도는 단계
AFTER_ANSWER = ("gm_check",)  # 답 뒤에 도는 단계(조건부)
TARGET_P50_S, TARGET_P95_S = 3.0, 6.0  # PRD §17.1


def load_records(path: str | Path, *, since: float | None = None, until: float | None = None,
                 include_fake: bool = False) -> list[dict]:
    """호출 기록을 읽는다. 쓰다 끊긴 줄은 건너뛴다. 가짜 LLM·그림 호출은 기본으로 뺀다."""
    out = []
    p = Path(path)
    if not p.is_file():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("bucket") == "image" or (not include_fake and r.get("model") == "fake"):
            continue
        if (since is not None and r["ts"] < since) or (until is not None and r["ts"] >= until):
            continue
        out.append(r)
    return out


def percentile(values: Iterable[float], p: float) -> float:
    """가장 가까운 순위 방식 백분위수. 값이 없으면 0."""
    v = sorted(values)
    if not v:
        return 0.0
    return v[max(0, math.ceil(p / 100 * len(v)) - 1)]


def questions(records: list[dict]) -> list[dict]:
    """기록 순서대로 질문 단위로 묶는다: {total, first, answer, before, after, role, routed, streamed, prepared}.
    시각은 호출 기록의 끝 시각(ts)과 지연으로 구간을 만들어 계산한다(동시에 돈 단계는 겹친 만큼 뺀다).
    - 라우터와 인물 답을 동시에 돌린 경우(애매한 질문): 답이 라우터보다 먼저 끝나 라우터 기록이 뒤에 오면
      그 라우터는 앞 질문에 붙인다. 첫 문장은 라우터 판정이 끝나야 보이므로 둘 중 늦은 쪽.
    - 판(game_id)이 바뀌면 앞서 쌓인 라우터·검색은 버린다."""
    out: list[dict] = []
    pend: list[dict] = []  # 답 앞에 쌓인 라우터·검색 기록
    for r in records:
        role, game = r.get("role"), r.get("game_id")
        if _speculative(r):  # 미리 만든 호출은 플레이어가 기다리지 않았다
            continue
        if pend and pend[-1].get("game_id") != game:
            pend = []
        r_start, r_end = r["ts"] - r["latency_s"], r["ts"]
        if role in BEFORE_ANSWER:
            last = out[-1] if out else None
            if last and last["game_id"] == game and r_start < last["_end"]:
                _merge_before(last, r)  # 답과 겹쳐 돈 라우터·검색(답보다 늦게 끝남): 앞 질문의 것
            else:
                pend.append(r)
        elif role in ANSWER_ROLES:
            first = (r.get("extra") or {}).get("first_text_s")
            q = {"role": role, "answer": r["latency_s"], "after": 0.0, "routed": False,
                 "output_tokens": r.get("output_tokens", 0), "streamed": first is not None,
                 "game_id": game, "prepared": r.get("model") == "prepared",
                 "_start": r_start, "_end": r_end, "_shown": r_start + first if first is not None else r_end}
            for b in pend:
                _merge_before(q, b)
            pend = []
            _finish(q)
            out.append(q)
        elif role in AFTER_ANSWER and out and out[-1]["game_id"] == game:
            q = out[-1]
            q["after"] += r["latency_s"]
            q["_end"] = max(q["_end"], r_end)
            if not q["streamed"]:  # 실시간이면 검사는 문장을 내보내는 중에 끝났다
                q["_shown"] = max(q["_shown"], r_end)
            _finish(q)
    for q in out:
        for k in ("_start", "_end", "_shown"):
            q.pop(k, None)
    return out


def _merge_before(q: dict, b: dict) -> None:
    b_start, b_end = b["ts"] - b["latency_s"], b["ts"]
    q["_start"] = min(q["_start"], b_start)
    q["_end"] = max(q["_end"], b_end)
    if b.get("role") == "router":
        q["routed"] = True
        q["_shown"] = max(q["_shown"], b_end)  # 판정이 끝나야 답이 화면에 나간다
    _finish(q)


def _finish(q: dict) -> None:
    q["total"] = round(q["_end"] - q["_start"], 3)
    q["first"] = round(q["_shown"] - q["_start"], 3)
    q["before"] = round(max(0.0, q["total"] - q["answer"] - q["after"]), 3)


def _stats(values: list[float]) -> dict:
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95),
            "max": max(values) if values else 0.0}


def _speculative(r: dict) -> bool:
    return (r.get("node") or "").endswith(":speculative")


def _role_name(r: dict) -> str:
    if _speculative(r):
        return f"{r['role']} (미리 만듦)"
    if r.get("model") == "prepared":
        return f"{r['role']} (미리 만든 답 사용)"
    return r["role"]


def summarize(records: list[dict]) -> dict:
    by_role: dict[str, dict] = {}
    shows = [r for r in records if r.get("role") == "speculative"]
    for r in records:
        if r.get("role") == "speculative":
            continue
        b = by_role.setdefault(_role_name(r), {"lat": [], "out": [], "fallbacks": 0})
        b["lat"].append(r["latency_s"])
        b["out"].append(r.get("output_tokens", 0))
        b["fallbacks"] += bool(r.get("fallback_used"))
    roles = {k: {**_stats(v["lat"]), "out_p50": percentile(v["out"], 50), "fallbacks": v["fallbacks"]}
             for k, v in sorted(by_role.items())}
    qs = questions(records)
    totals = [q["total"] for q in qs]
    pairs = [(int((r.get("extra") or {}).get("prepared", 0)), int((r.get("extra") or {}).get("used", 0))) for r in shows]
    prepared, used = sum(p for p, _ in pairs), sum(u for _, u in pairs)
    made = [u for p, u in pairs if p > 0]
    return {
        "roles": roles,
        "questions": {**_stats(totals), "over_target": sum(1 for t in totals if t > TARGET_P95_S),
                      "routed": sum(1 for q in qs if q["routed"]), "prepared": sum(1 for q in qs if q["prepared"]),
                      "first_p50": percentile([q["first"] for q in qs], 50),
                      "first_p95": percentile([q["first"] for q in qs], 95),
                      "streamed": sum(1 for q in qs if q["streamed"])},
        "speculative": {"shows": len(shows), "prepared": prepared, "used": used,
                        "hit_rate": sum(1 for u in made if u > 0) / len(made) if made else None,  # F.15 (D-60)
                        "discard_rate": 1 - used / prepared if prepared else None},
    }


def render_markdown(s: dict, title: str = "응답 지연") -> str:
    q = s["questions"]
    lines = [f"### {title}", "",
             f"질문→답 {q['n']}개: p50 {q['p50']:.1f}초 · p95 {q['p95']:.1f}초 · 최대 {q['max']:.1f}초 "
             f"(목표 {TARGET_P50_S:.0f}초/{TARGET_P95_S:.0f}초) · {TARGET_P95_S:.0f}초 넘음 {q['over_target']}개 · "
             f"LLM 라우터 {q['routed']}번 · 미리 만든 답 사용 {q['prepared']}개",
             f"첫 문장까지 p50 {q['first_p50']:.1f}초 · p95 {q['first_p95']:.1f}초 (첫 문장부터 보여 준 답 {q['streamed']}개)", "",
             "| 역할 | 호출 | p50 | p95 | 최대 | 출력 토큰 p50 | 대체 동작 |", "|:--|--:|--:|--:|--:|--:|--:|"]
    for role, r in s["roles"].items():
        lines.append(f"| {role} | {r['n']} | {r['p50']:.1f} | {r['p95']:.1f} | {r['max']:.1f} | "
                     f"{r['out_p50']:.0f} | {r['fallbacks']} |")
    sp = s.get("speculative") or {}
    if sp.get("shows"):
        def pct(v):
            return f"{v * 100:.0f}%" if v is not None else "-"

        lines += ["", f"추천 질문 답 미리 만들기: 준비 {sp['shows']}번 · 적중률 {pct(sp['hit_rate'])}(하나라도 쓴 준비, "
                      f"목표 50% 이상) · 미리 만든 답 {sp['prepared']}개 중 {sp['used']}개 사용, 버린 비율 {pct(sp['discard_rate'])}"]
    return "\n".join(lines) + "\n"


def _schema_for(role: str) -> type[BaseModel] | None:
    from server.schemas import NPCReply, RouterOutput

    if role in ANSWER_ROLES:
        return NPCReply
    if role == "router":
        return RouterOutput
    if role == "gm_check":
        from server.game.service import GMCheck  # 무거운 모듈이라 필요할 때만

        return GMCheck
    return None


def split_prompt(prompt: str) -> tuple[str, str]:
    """기록의 prompt("[system]\\n…\\n[user]\\n…")를 지시문과 사용자 글로 나눈다."""
    system, _, user = prompt.removeprefix("[system]\n").partition("\n[user]\n")
    return system, user


async def replay(client: Any, records: list[dict], *, roles: Iterable[str] = ANSWER_ROLES, limit: int = 4) -> list[dict]:
    """기록된 요청 중 roles에 해당하는 최근 limit개를 지금 모델 설정으로 하나씩 다시 보낸다.
    결과: {role, before_s(기록된 지연), after_s, out_before, out_after, fallback, text(다시 받은 답)}."""
    roles = tuple(roles)
    picked = [r for r in records if r.get("role") in roles and r.get("prompt") and _schema_for(r["role"])][-limit:]
    out = []
    for r in picked:
        schema = _schema_for(r["role"])
        system, user = split_prompt(r["prompt"])
        t0 = time.perf_counter()
        res, fb = await client.structured(role=r["role"], bucket=r.get("bucket", "npc"), schema=schema, system=system,
                                        user=user, fake=lambda s=schema: _fake(s), fallback=lambda s=schema: _fake(s),
                                        node="latency_replay")
        rec = client.tracer.records[-1]
        out.append({"role": r["role"], "before_s": r["latency_s"], "after_s": time.perf_counter() - t0,
                    "out_before": r.get("output_tokens", 0), "out_after": rec.output_tokens, "fallback": fb,
                    "text": getattr(res, "text", "")})
    return out


def _fake(schema: type[BaseModel]) -> BaseModel:
    from server.schemas import NPCReply, RouterOutput

    if schema is NPCReply:
        return NPCReply(text="(측정용 가짜 답)")
    if schema is RouterOutput:
        return RouterOutput(kind="investigate", via="llm")
    return schema.model_validate({"ok": True})


def render_replay(rows: list[dict]) -> str:
    lines = ["| 역할 | 기록 | 다시 보냄 | 출력 토큰(기록→다시) | 대체 동작 | 다시 받은 답 |", "|:--|--:|--:|--:|:--|:--|"]
    for r in rows:
        text = (r.get("text") or "").replace("|", "/").replace("\n", " ")
        lines.append(f"| {r['role']} | {r['before_s']:.1f}초 | {r['after_s']:.1f}초 | "
                     f"{r['out_before']}→{r['out_after']} | {'예' if r['fallback'] else ''} | {text} |")
    return "\n".join(lines) + "\n"


async def measure_speculative(svc: Any, *, rounds: int = 2, read_s: float = 8.0, settle_s: float = 1.0,
                              theme: str = "demo_db_deleted") -> list[dict]:
    """칩 질문을 세 방식으로 누르고 플레이어가 기다린 시간(act() 전체)을 잰다. 매번 새 판의 같은 첫 질문.
    A: 미리 만들기 없이 / B: 미리 만들기 시작 직후 누름 / C: read_s초(답을 읽는 시간) 뒤 누름."""
    rows = []
    for _ in range(rounds):
        for mode in ("A", "B", "C"):
            game_id, _ = svc.new_game(theme, {"difficulty": "normal"})
            chip = next((c for c in svc.view(game_id).chips if c.kind == "ask"), None)
            if chip is None:
                continue
            if mode != "A":
                await svc.prepare(game_id, chip.target_npc)
                if mode == "C":
                    await asyncio.sleep(read_s)
            t0 = time.perf_counter()
            evs = [e async for e in svc.act(game_id, {"type": "chip", "chip_id": chip.id})]
            rows.append({"mode": mode, "wait_s": time.perf_counter() - t0,
                         "error": any(e["type"] == "RUN_ERROR" for e in evs)})
            svc.spec.forget(game_id)
            await asyncio.sleep(settle_s)  # 버린 미리 만들기 호출이 다음 측정과 겹치지 않게
    return rows


def render_speculative(rows: list[dict], read_s: float) -> str:
    names = {"A": "미리 만들기 없음", "B": "미리 만들기 직후 누름", "C": f"{read_s:.0f}초 읽고 누름"}
    lines = ["| 방식 | 횟수 | 기다린 시간 p50 | 최대 | 오류 |", "|:--|--:|--:|--:|--:|"]
    for m, name in names.items():
        ws = [r["wait_s"] for r in rows if r["mode"] == m]
        if ws:
            lines.append(f"| {m}. {name} | {len(ws)} | {percentile(ws, 50):.1f}초 | {max(ws):.1f}초 | "
                         f"{sum(r['error'] for r in rows if r['mode'] == m)} |")
    return "\n".join(lines) + "\n"


def _ts(text: str | None) -> float | None:
    return time.mktime(time.strptime(text, "%Y-%m-%d %H:%M")) if text else None


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="응답 지연 측정 (호출 기록 요약 / 기록된 요청 다시 보내기)")
    ap.add_argument("--traces", default="var/traces.jsonl")
    ap.add_argument("--since", help='"YYYY-MM-DD HH:MM" (로컬 시각)')
    ap.add_argument("--until", help='"YYYY-MM-DD HH:MM" (로컬 시각)')
    ap.add_argument("--replay", type=int, default=0, help="다시 보낼 요청 수 (0이면 요약만). 진짜 모델 사용량이 든다")
    ap.add_argument("--roles", default=",".join(ANSWER_ROLES), help="다시 보낼 역할(쉼표로 구분)")
    ap.add_argument("--thinking", choices=("default", "off"), default="default",
                    help="다시 보낼 때 그 역할들의 생각(추론)을 끈다(프로필의 thinking_off 방법)")
    ap.add_argument("--speculative", type=int, default=0,
                    help="칩 답 미리 만들기 효과를 N번씩 잰다(임시 폴더의 새 판, 그림 끔). 진짜 모델 사용량이 든다")
    ap.add_argument("--read", type=float, default=8.0, help="--speculative C 방식의 읽는 시간(초)")
    ap.add_argument("--stream-check", type=int, default=0,
                    help="직접 쓴 질문의 첫 대사 조각·끝 시간을 N번씩 잰다(첫 문장부터 보여 주기 끔/켬). 진짜 모델 사용량이 든다")
    ap.add_argument("--question", help="--stream-check에 쓸 질문 (기본: 어젯밤 사건 시각쯤 어디 계셨어요?)")
    args = ap.parse_args(argv)
    if args.stream_check:
        _run_stream(args.stream_check, args.question)
        return
    if args.speculative:
        _run_speculative(args.speculative, args.read)
        return

    records = load_records(args.traces, since=_ts(args.since), until=_ts(args.until))
    print(render_markdown(summarize(records)))
    if args.replay:
        from dotenv import load_dotenv

        from server.llm.client import LLMClient
        from server.llm.tracing import Tracer

        load_dotenv()
        client = LLMClient(tracer=Tracer())  # 다시 보낸 호출은 var/traces.jsonl에 섞지 않는다
        if args.thinking == "off":
            for role in args.roles.split(","):
                prof = client.cfg["profiles"].setdefault(client.profile, {})
                prof.setdefault("roles", {}).setdefault(role, dict(client.role_config(role)))["thinking"] = "off"
        print(f"다시 보내기: 프로필 {client.profile}, 방식 {client.provider}" + (" (가짜 LLM)" if client.fake_mode else ""))
        rows = asyncio.run(replay(client, records, roles=args.roles.split(","), limit=args.replay))
        print(render_replay(rows))


async def measure_stream(svc: Any, *, rounds: int = 3, question: str = "어젯밤 사건 시각쯤 어디 계셨어요?",
                         theme: str = "demo_db_deleted", settle_s: float = 1.0) -> list[dict]:
    """직접 쓴 질문 하나를 보내 첫 대사 조각과 행동 끝까지의 시간을 잰다. 첫 문장부터 보여 주기를 끔/켬 번갈아.
    매번 새 판의 같은 인물(처음 장소에 있는 첫 사람)에게 같은 질문."""
    rows = []
    base = svc.cfg
    for _ in range(rounds):
        for stream in (False, True):
            svc.cfg = base.model_copy(update={"speed": base.speed.model_copy(update={"stream_npc_answers": stream})})
            game_id, view = svc.new_game(theme, {"difficulty": "normal"})
            npc = next(c for c in view.characters if c.location_id == view.player_location)
            t0, first = time.perf_counter(), None
            evs = []
            async for e in svc.act(game_id, {"type": "ask", "npc_id": npc.id, "text": question}):
                evs.append(e)
                if first is None and e["type"] == "TEXT_MESSAGE_CONTENT":
                    first = time.perf_counter() - t0
            total = time.perf_counter() - t0
            rows.append({"stream": stream, "first_s": first if first is not None else total, "total_s": total,
                         "error": any(e["type"] == "RUN_ERROR" for e in evs),
                         "text": "".join(e.get("delta", "") for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT")})
            await asyncio.sleep(settle_s)
    svc.cfg = base
    return rows


def render_stream(rows: list[dict]) -> str:
    lines = ["| 방식 | 횟수 | 첫 대사 조각 p50 | 최대 | 행동 끝 p50 | 오류 |", "|:--|--:|--:|--:|--:|--:|"]
    for stream, name in ((False, "다 만든 뒤 보여 줌(전)"), (True, "첫 문장부터 보여 줌(후)")):
        rs = [r for r in rows if r["stream"] == stream]
        if rs:
            f, t = [r["first_s"] for r in rs], [r["total_s"] for r in rs]
            lines.append(f"| {name} | {len(rs)} | {percentile(f, 50):.1f}초 | {max(f):.1f}초 | "
                         f"{percentile(t, 50):.1f}초 | {sum(r['error'] for r in rs)} |")
    return "\n".join(lines) + "\n"


def _temp_service():
    import os
    import tempfile

    from dotenv import load_dotenv

    load_dotenv()
    os.environ["CLOUDFLARE_API_TOKEN"] = os.environ["CLOUDFLARE_ACCOUNT_ID"] = ""  # 그림은 그리지 않는다
    from server.game.service import GameService

    svc = GameService(Path(tempfile.mkdtemp(prefix="latency_")), in_memory=True)
    print(f"모델 연결: 프로필 {svc.llm.profile}, 방식 {svc.llm.provider}" + (" (가짜 LLM)" if svc.llm.fake_mode else "")
          + (", 실시간 출력 가능" if svc.llm.can_stream else ""))
    return svc


def _run_stream(rounds: int, question: str | None = None) -> None:
    svc = _temp_service()
    q = question or "어젯밤 사건 시각쯤 어디 계셨어요?"
    print(f"질문: {q} (시맨틱 분류: {svc.router.classify(q).via})")
    rows = asyncio.run(measure_stream(svc, rounds=rounds, question=q))
    print(render_stream(rows))
    for r in rows:
        print(f"- {'후' if r['stream'] else '전'} 첫 {r['first_s']:.1f}초 / 끝 {r['total_s']:.1f}초: {r['text'][:60]}")
    print()
    print(render_markdown(summarize([r.__dict__ for r in svc.llm.tracer.records]), title="이번 측정 호출 기록"))


def _run_speculative(rounds: int, read_s: float) -> None:
    import os
    import tempfile

    from dotenv import load_dotenv

    load_dotenv()
    os.environ["CLOUDFLARE_API_TOKEN"] = os.environ["CLOUDFLARE_ACCOUNT_ID"] = ""  # 그림은 그리지 않는다
    from server.game.service import GameService

    svc = GameService(Path(tempfile.mkdtemp(prefix="latency_spec_")), in_memory=True)
    print(f"모델 연결: 프로필 {svc.llm.profile}, 방식 {svc.llm.provider}" + (" (가짜 LLM)" if svc.llm.fake_mode else ""))
    rows = asyncio.run(measure_speculative(svc, rounds=rounds, read_s=read_s))
    print(render_speculative(rows, read_s))
    print(render_markdown(summarize([r.__dict__ for r in svc.llm.tracer.records]), title="이번 측정 호출 기록"))


if __name__ == "__main__":
    main()
