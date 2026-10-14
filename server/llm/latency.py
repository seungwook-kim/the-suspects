"""응답 지연 측정 (PRD §17.1 응답 지연, §17.5 개선 기록).

호출 기록(Tracer JSONL, 기본 var/traces.jsonl)으로 두 가지를 낸다.
1. 요약: 역할별 지연 p50·p95·최대와 출력 토큰, 질문 1개 단위(질문→답) 지연.
   질문 1개 = 앞선 LLM 라우터·검색 + 인물 답 + 뒤따른 게임 마스터 LLM 검사.
2. 다시 보내기(replay): 기록된 요청(개발 모드는 지시문·질문 원문을 남김)을 지금 모델 설정으로 다시 보내 잰다.
   설정·프롬프트를 바꾼 뒤 같은 요청으로 전후를 비교하는 용도. 진짜 모델을 부르므로 사용량이 든다.

결과는 evals/reports/ 보고서에 붙일 수 있는 마크다운 표로도 낸다.

  uv run python -m server.llm.latency --since "2026-10-14 13:40" --until "2026-10-14 13:58"
  uv run python -m server.llm.latency --replay 4 --roles npc     # 최근 인물 답 요청 4개 다시 보내기
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
    """기록 순서대로 질문 단위로 묶는다: {total, answer, before, after, role, routed}.
    판(game_id)이 바뀌면 앞서 쌓인 라우터·검색 시간은 버린다."""
    out: list[dict] = []
    pending, pending_game, routed = 0.0, None, False
    for r in records:
        role, game = r.get("role"), r.get("game_id")
        if game != pending_game:
            pending, routed, pending_game = 0.0, False, game
        if role in BEFORE_ANSWER:
            pending += r["latency_s"]
            routed = routed or role == "router"
        elif role in ANSWER_ROLES:
            out.append({"role": role, "answer": r["latency_s"], "before": pending, "after": 0.0, "routed": routed,
                        "total": pending + r["latency_s"], "output_tokens": r.get("output_tokens", 0),
                        "game_id": game})
            pending, routed = 0.0, False
        elif role in AFTER_ANSWER and out and out[-1]["game_id"] == game:
            out[-1]["after"] += r["latency_s"]
            out[-1]["total"] += r["latency_s"]
    return out


def _stats(values: list[float]) -> dict:
    return {"n": len(values), "p50": percentile(values, 50), "p95": percentile(values, 95),
            "max": max(values) if values else 0.0}


def summarize(records: list[dict]) -> dict:
    by_role: dict[str, dict] = {}
    for r in records:
        by_role.setdefault(r["role"], {"lat": [], "out": [], "fallbacks": 0})
        by_role[r["role"]]["lat"].append(r["latency_s"])
        by_role[r["role"]]["out"].append(r.get("output_tokens", 0))
        by_role[r["role"]]["fallbacks"] += bool(r.get("fallback_used"))
    roles = {k: {**_stats(v["lat"]), "out_p50": percentile(v["out"], 50), "fallbacks": v["fallbacks"]}
             for k, v in sorted(by_role.items())}
    qs = questions(records)
    totals = [q["total"] for q in qs]
    return {
        "roles": roles,
        "questions": {**_stats(totals), "over_target": sum(1 for t in totals if t > TARGET_P95_S),
                      "routed": sum(1 for q in qs if q["routed"])},
    }


def render_markdown(s: dict, title: str = "응답 지연") -> str:
    q = s["questions"]
    lines = [f"### {title}", "",
             f"질문→답 {q['n']}개: p50 {q['p50']:.1f}초 · p95 {q['p95']:.1f}초 · 최대 {q['max']:.1f}초 "
             f"(목표 {TARGET_P50_S:.0f}초/{TARGET_P95_S:.0f}초) · {TARGET_P95_S:.0f}초 넘음 {q['over_target']}개 · "
             f"LLM 라우터 {q['routed']}번", "",
             "| 역할 | 호출 | p50 | p95 | 최대 | 출력 토큰 p50 | 대체 동작 |", "|:--|--:|--:|--:|--:|--:|--:|"]
    for role, r in s["roles"].items():
        lines.append(f"| {role} | {r['n']} | {r['p50']:.1f} | {r['p95']:.1f} | {r['max']:.1f} | "
                     f"{r['out_p50']:.0f} | {r['fallbacks']} |")
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
    결과: {role, before_s(기록된 지연), after_s, out_before, out_after, fallback}."""
    roles = tuple(roles)
    picked = [r for r in records if r.get("role") in roles and r.get("prompt") and _schema_for(r["role"])][-limit:]
    out = []
    for r in picked:
        schema = _schema_for(r["role"])
        system, user = split_prompt(r["prompt"])
        t0 = time.perf_counter()
        _, fb = await client.structured(role=r["role"], bucket=r.get("bucket", "npc"), schema=schema, system=system,
                                        user=user, fake=lambda s=schema: _fake(s), fallback=lambda s=schema: _fake(s),
                                        node="latency_replay")
        rec = client.tracer.records[-1]
        out.append({"role": r["role"], "before_s": r["latency_s"], "after_s": time.perf_counter() - t0,
                    "out_before": r.get("output_tokens", 0), "out_after": rec.output_tokens, "fallback": fb})
    return out


def _fake(schema: type[BaseModel]) -> BaseModel:
    from server.schemas import NPCReply, RouterOutput

    if schema is NPCReply:
        return NPCReply(text="(측정용 가짜 답)")
    if schema is RouterOutput:
        return RouterOutput(kind="investigate", via="llm")
    return schema.model_validate({"ok": True})


def render_replay(rows: list[dict]) -> str:
    lines = ["| 역할 | 기록 | 다시 보냄 | 출력 토큰(기록→다시) | 대체 동작 |", "|:--|--:|--:|--:|:--|"]
    for r in rows:
        lines.append(f"| {r['role']} | {r['before_s']:.1f}초 | {r['after_s']:.1f}초 | "
                     f"{r['out_before']}→{r['out_after']} | {'예' if r['fallback'] else ''} |")
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
    args = ap.parse_args(argv)

    records = load_records(args.traces, since=_ts(args.since), until=_ts(args.until))
    print(render_markdown(summarize(records)))
    if args.replay:
        from dotenv import load_dotenv

        from server.llm.client import LLMClient
        from server.llm.tracing import Tracer

        load_dotenv()
        client = LLMClient(tracer=Tracer())  # 다시 보낸 호출은 var/traces.jsonl에 섞지 않는다
        print(f"다시 보내기: 프로필 {client.profile}, 방식 {client.provider}" + (" (가짜 LLM)" if client.fake_mode else ""))
        rows = asyncio.run(replay(client, records, roles=args.roles.split(","), limit=args.replay))
        print(render_replay(rows))


if __name__ == "__main__":
    main()
