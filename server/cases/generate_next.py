"""상황 목록에서 사건을 하나씩 만든다 (토큰 안전 장치가 붙은 입구, 2026-10-26).

  uv run python -m server.cases.generate_next --dry-run           # 다음에 만들 상황과 보낼 글만 보여 준다(모델 호출 없음)
  uv run python -m server.cases.generate_next --confirm           # 진짜로 만든다(하루 1건, 사용량이 든다)

- --confirm이 없으면 어떤 경우에도 모델을 부르지 않는다(--dry-run이 기본 동작과 같다).
- 하루 1건: var/generate_next_state.json 에 오늘 시도를 먼저 적는다(실패해도 하루 한 번만 시도한다).
- 가짜 LLM(모델 연결이 꺼진 상태)이면 만들지 않는다. 가짜 사건을 data/cases에 저장하면 평가가 오염된다.
- 결제가 생기는 우회(API 키·추가 사용량)는 쓰지 않는다. 한도에 걸리면 멈추고 내일 다시 한다.
- 저장 위치: data/cases/sit_<상황id>_<날짜>.json (게임 서버가 시작 때 읽는 기본 사건 목록에 들어간다).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from server.cases import situations as S
from server.cases.loader import DEFAULT_CASE_DIR, PROJECT_ROOT

STATE_PATH = PROJECT_ROOT / "var" / "generate_next_state.json"
MAX_PER_DAY = 1
# 어림값(var/traces.jsonl에 남은 진짜 생성 2건의 평균): 호출 12~15번, 입력 약 4만 + 출력 약 1.5만 토큰. 검수 재시도가 있으면 늘어난다.
ESTIMATE = {"calls": "12~15", "input_tokens": 40_000, "output_tokens": 15_000}


def _today() -> str:
    return time.strftime("%Y%m%d")


def _read_state(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def attempts_today(path: Path = STATE_PATH, today: str | None = None) -> int:
    st = _read_state(path)
    return int((st.get("by_day") or {}).get(today or _today(), 0))


def _bump(path: Path, today: str, note: dict[str, Any]) -> None:
    st = _read_state(path)
    by_day = st.setdefault("by_day", {})
    by_day[today] = int(by_day.get(today, 0)) + 1
    st.setdefault("log", []).append({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **note})
    st["log"] = st["log"][-50:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def make_plan(situation_id: str | None = None, *, play_minutes: int = 40, runs_file: str | Path | None = S.RUNS_FILE,
              case_dir: str | Path | None = None, data: dict | None = None, today: str | None = None, seed: int | None = None) -> dict:
    """무엇을 만들지 정한다(코드뿐). 반환: situation, case_id, theme_text, options, prompt(개념 단계에서 모델에 보낼 글)."""
    from server.cases.generate.plan import draw
    from server.cases.generate.writer import concept_prompt

    data = data or S.load_situations()
    problems = S.validate(data)
    if problems:
        raise ValueError("상황 목록에 문제가 있다: " + "; ".join(problems[:3]))
    if situation_id:
        sit = S.by_id(data).get(situation_id)
        if sit is None:
            raise KeyError(f"모르는 상황 id: {situation_id}")
    else:
        sit = S.next_to_generate(data, runs_file, case_dir)
    case_id = f"{S.CASE_PREFIX}{sit['id']}_{today or _today()}"
    text = S.theme_text(sit)
    options = {"play_minutes": play_minutes, "cast_hint": S.cast_hint(sit)}
    plan = draw(case_id, text, options, seed)
    system, user = concept_prompt(plan)
    return {"situation": sit, "case_id": case_id, "theme_text": text, "options": options, "seed": seed,
            "people": len(plan.people), "prompt": {"system": system, "user": user}}


def render_plan(p: dict, *, state_path: Path = STATE_PATH, today: str | None = None) -> str:
    sit = p["situation"]
    out = [f"다음에 만들 상황: {sit['name']} ({sit['id']})", f"사건 id: {p['case_id']}", f"사건 씨앗: {p['theme_text']}",
           f"인원: {p['people']}명 (후보 {len(sit['roles'])}명 중 선택), 플레이 시간 {p['options']['play_minutes']}분",
           f"어림 사용량(추정): 호출 {ESTIMATE['calls']}번, 입력 약 {ESTIMATE['input_tokens']:,} + 출력 약 {ESTIMATE['output_tokens']:,} 토큰",
           f"오늘 시도: {attempts_today(state_path, today)}/{MAX_PER_DAY}건", "",
           "[1단계 모델에 보낼 글 - system]", p["prompt"]["system"], "", "[1단계 - user]", p["prompt"]["user"], "",
           "[3단계(인물)에 덧붙는 등장 후보 직업 안내]", p["options"]["cast_hint"]]
    return "\n".join(out)


async def generate(p: dict, llm: Any, *, case_dir: Path, state_path: Path, today: str | None = None) -> str:
    """진짜 생성. 오늘 한도를 먼저 쓰고 부른다. 결과 문구를 돌려준다."""
    from server.cases.generate import generate_case

    today = today or _today()
    if attempts_today(state_path, today) >= MAX_PER_DAY:
        return f"오늘은 이미 {MAX_PER_DAY}건 시도했다. 내일 다시 한다."
    _bump(state_path, today, {"case_id": p["case_id"], "situation": p["situation"]["id"]})
    res = await generate_case(llm, p["case_id"], p["theme_text"], p["options"], seed=p.get("seed"))
    if res.outcome != "ok" or res.case is None:
        return f"만들지 못했다({res.outcome}): {res.message} {'; '.join(res.problems[:3])}"
    case_dir.mkdir(parents=True, exist_ok=True)
    out = case_dir / f"{p['case_id']}.json"
    out.write_text(res.case.model_dump_json(indent=2), encoding="utf-8")
    return f"저장했다: {out}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="상황 목록에서 사건 하나 만들기(하루 1건 상한). --confirm 없이는 모델을 부르지 않는다")
    ap.add_argument("--dry-run", action="store_true", help="다음 상황과 보낼 글만 보여 준다")
    ap.add_argument("--confirm", action="store_true", help="진짜로 만든다(사용량이 드는 것을 알고 실행)")
    ap.add_argument("--situation", help="상황 id를 직접 고른다(기본: 사건이 가장 적은 상황)")
    ap.add_argument("--play-minutes", type=int, choices=[20, 40, 60], default=40)
    args = ap.parse_args(argv)
    p = make_plan(args.situation, play_minutes=args.play_minutes)
    print(render_plan(p))
    if not args.confirm:
        print("\n(모델을 부르지 않았다. 만들려면 --confirm)")
        return
    if args.dry_run:
        raise SystemExit("--dry-run 과 --confirm 은 함께 쓸 수 없다")
    if attempts_today(STATE_PATH) >= MAX_PER_DAY:
        raise SystemExit(f"오늘은 이미 {MAX_PER_DAY}건 시도했다. 내일 다시 한다(한도가 풀릴 때까지 기다리고 결제로 우회하지 않는다).")
    from dotenv import load_dotenv

    load_dotenv()
    import os

    os.environ["CLOUDFLARE_API_TOKEN"] = os.environ["CLOUDFLARE_ACCOUNT_ID"] = ""  # 그림은 그리지 않는다
    from server.llm.client import LLMClient

    llm = LLMClient()
    if llm.fake_mode:
        raise SystemExit("모델 연결이 꺼져 있다(가짜 LLM). 가짜 사건을 저장하지 않는다.")
    print(asyncio.run(generate(p, llm, case_dir=DEFAULT_CASE_DIR, state_path=STATE_PATH)))


if __name__ == "__main__":
    main()
