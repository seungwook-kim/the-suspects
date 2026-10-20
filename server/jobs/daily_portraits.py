"""매일 하루치 초상화 쌓기 (2026-10-20 사용자 요청): 그날의 직업군 하나를 골라 그 직업군 인물 사진만 그려 사진 보관함에 넣는다.

- 배경 그림은 만들지 않는다. 인물 얼굴 사진만. 요청에는 판의 장소 설명을 넣지 않는다.
- 한 사람마다 기본 사진 1장 + 같은 얼굴의 표정 사진(설정 `emotions`, 기본 5종)을 함께 쌓는다(2026-10-20 사용자 요청).
  표정은 기본 사진을 참조로 넣어 그린다. 재활용할 때 표정 사진이 있는 얼굴이 우선이다(portrait_library.pick).
- 이미 보관함에 있는데 표정이 빠진 얼굴은 새 얼굴보다 먼저 채운다(2026-10-20 사용자 요청, 빠진 표정이 적은 얼굴부터).
  채울 게 없어지면 하루 장수 전부를 새 얼굴에 쓴다.
- 직업군은 마지막으로 돌린 지 가장 오래된 것, 같으면 보관함에 사진이 가장 적은 것. 그래서 매일 다른 직업군이 걸린다(새 얼굴용).
- Cloudflare 무료 할당량(하루 10,000 뉴런, 매일 00:00 UTC = 한국 09:00 초기화, 실측 하루 약 100장)을 쓴다.
  게임이 쓸 몫을 남기려고 하루 42장에서 멈춘다. 429(할당량 소진)가 나면 그 자리에서 멈춘다.
  무료 요금제에서는 한도를 넘어도 요금이 나가지 않는다.
- 사건·판·인물 id 없이 공개 외모 정보만 보관함에 적는다(source=daily). 범인 암시 없음.

  uv run python -m server.jobs.daily_portraits                 # 빈 표정 먼저 채우고, 남은 장수로 새 얼굴(표정 포함)
  uv run python -m server.jobs.daily_portraits --count 4 --group medical --no-backfill
  uv run python -m server.jobs.daily_portraits --dry-run       # 그림을 그리지 않고 계획만 본다

실행 기록: var/daily_portraits.jsonl (한 줄 = 한 번 실행). 오류는 var/daily_portraits.log.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import time
import traceback
from datetime import datetime
from pathlib import Path

from server.game.portrait_library import GROUP_NAMES, PortraitLibrary, job_group
from server.game.portraits import EMOTION_EN, compact, expression_prompt, portrait_prompt, ref_image
from server.llm.images import ImageClient
from server.llm.tracing import Tracer

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUDGET = 42  # 하루 최대 장수. 하루 한도(실측 약 100장)의 반 이하, 나머지는 게임이 쓴다. 새 얼굴 한 사람 = 기본 1장 + 표정 5장
CONCURRENCY = 3
MAX_CONSECUTIVE_FAILS = 5  # 할당량이 아닌 오류가 이어지면 멈춘다 (실패할 요청을 계속 보내지 않게)

# 직업군별 인물 재료. outfit은 portraits.OUTFIT_EN의 정해진 값이라 직업군이 옷차림으로 정해진다.
# 일반·기타는 직업 이름 낱말이 다른 직업군 낱말에 걸리지 않게 골랐다 (portrait_library.KEYWORDS 참고).
SPECS: dict[str, dict] = {
    "security": {"outfits": ["security_uniform"], "roles": ["경비원", "보안 요원", "야간 경비원", "건물 경비원"],
                 "ages": (28, 62), "accessories": ["", "cap", "radio", "badge"]},
    "cleaning": {"outfits": ["cleaner_uniform"], "roles": ["청소원", "미화원", "건물 청소 담당"],
                 "ages": (35, 68), "accessories": ["", "cap", "mop"]},
    "medical": {"outfits": ["doctor"], "roles": ["의사", "간호사", "약사", "병원 의료진"],
                "ages": (26, 60), "accessories": ["", "glasses", "badge"]},
    "culinary": {"outfits": ["chef"], "roles": ["요리사", "주방장", "바리스타", "식당 조리사"],
                 "ages": (23, 58), "accessories": ["", "apron", "cap"]},
    "delivery": {"outfits": ["delivery"], "roles": ["배달 기사", "택배 기사", "퀵서비스 기사"],
                 "ages": (24, 55), "accessories": ["", "cap"]},
    "student": {"outfits": ["school_uniform"], "roles": ["고등학생", "학생"],
                "ages": (15, 19), "accessories": ["", "glasses"]},
    "field": {"outfits": ["work_clothes"], "roles": ["설비 기술자", "정비 기사", "현장 작업자", "시설 정비 담당"],
              "ages": (28, 62), "accessories": ["", "cap", "glasses"]},
    "office": {"outfits": ["suit", "office_lanyard"], "roles": ["회사원", "팀장", "개발자", "기획자", "디자이너", "과장"],
               "ages": (25, 55), "accessories": ["", "glasses", "badge"]},
    "general": {"outfits": ["casual", "hoodie"], "roles": ["상점 주인", "프리랜서 작가", "동네 주민", "택시 운전사", "주부"],
                "ages": (22, 70), "accessories": ["", "glasses", "cap"]},
}
HAIR_M = ["short", "side", "buzz", "curly", "short", "side", "bald"]
HAIR_F = ["short", "long", "bun", "ponytail", "curly", "side", "long"]


def make_person(group: str, rng: random.Random) -> dict:
    spec = SPECS[group]
    gender = rng.choice(["M", "F"])
    hair = rng.choice(HAIR_M if gender == "M" else HAIR_F)
    if group == "student" and hair == "bald":
        hair = "short"
    person = {"role": rng.choice(spec["roles"]), "age": rng.randint(*spec["ages"]), "gender": gender,
              "appearance": {"outfit": rng.choice(spec["outfits"]), "hair": hair, "accessory": rng.choice(spec["accessories"])}}
    assert job_group(person["role"], person["appearance"]) == group, (group, person)  # 상자가 어긋나면 만들지 않는다
    return person


def read_runs(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def pick_group(runs: list[dict], library: PortraitLibrary) -> str:
    """마지막으로 돌린 지 가장 오래된 직업군(안 돌린 건 가장 먼저), 같으면 기본 사진이 가장 적은 것."""
    last = {g: 0.0 for g in GROUP_NAMES}
    for r in runs:
        if r.get("group") in last and r.get("made", 0) > 0:
            last[r["group"]] = max(last[r["group"]], r.get("ts", 0.0))
    have = {g: 0 for g in GROUP_NAMES}
    for rec in library.records():
        if rec.get("kind") == "base" and rec.get("group") in have:
            have[rec["group"]] += 1
    return min(GROUP_NAMES, key=lambda g: (last[g], have[g], g))


MAX_ATTEMPTS = 3  # 같은 (얼굴, 표정)을 이만큼 그려 보고도 안 되면 포기 (그림 모델의 출력 검사에 걸리는 조합이 있다)


def load_attempts(var_dir: Path) -> dict[str, int]:
    try:
        return {str(k): int(v) for k, v in json.loads((var_dir / "daily_portraits_attempts.json").read_text("utf-8")).items()}
    except (OSError, ValueError):
        return {}


def save_attempts(var_dir: Path, attempts: dict[str, int]) -> None:
    var_dir.mkdir(parents=True, exist_ok=True)
    (var_dir / "daily_portraits_attempts.json").write_text(json.dumps(attempts, ensure_ascii=False, indent=0), "utf-8")


def missing_emotions(library: PortraitLibrary, emotions: list[str],
                     attempts: dict[str, int] | None = None) -> list[tuple[dict, str]]:
    """보관함에 이미 있는 기본 사진 중 표정 사진이 빠진 (기본 사진, 표정) 목록.
    빠진 표정이 적은 얼굴부터(표정이 다 갖춰진 얼굴이 빨리 늘도록). 문제 표시(bad)나 파일이 없는 사진은 뺀다.
    attempts(얼굴|표정 → 실패 횟수)가 MAX_ATTEMPTS 이상인 조합은 뺀다."""
    attempts = attempts or {}
    have: dict[str, set[str]] = {}
    for r in library.records():
        if r.get("kind") == "emotion" and r.get("base_file") and (library.root / r["file"]).is_file():
            have.setdefault(r["base_file"], set()).add(r.get("emotion", ""))
    jobs: list[tuple[int, dict, list[str]]] = []
    for r in library.records():
        if r.get("kind") != "base" or r.get("bad") or not (library.root / r["file"]).is_file():
            continue
        miss = [e for e in emotions if e not in have.get(r["file"], set())
                and attempts.get(f"{r['file']}|{e}", 0) < MAX_ATTEMPTS]
        if miss:
            jobs.append((len(miss), r, miss))
    jobs.sort(key=lambda j: (j[0], j[1].get("created_at", 0)))
    return [(r, e) for _, r, miss in jobs for e in miss]


async def run(count: int, group: str | None, var_dir: Path, images: ImageClient, rng: random.Random,
              dry_run: bool = False, backfill: int = 0) -> dict:
    """count: 새로 그릴 사람 수. backfill: 이미 있는 얼굴에 표정을 채우는 데 쓸 최대 장수(새 얼굴보다 먼저)."""
    library = PortraitLibrary(var_dir / "portrait_library")
    log_path = var_dir / "daily_portraits.jsonl"
    group = group or pick_group(read_runs(log_path), library)
    if group not in SPECS:
        raise SystemExit(f"직업군 이름이 아니다: {group} (가능: {', '.join(SPECS)})")
    result = {"ts": round(time.time(), 3), "date": datetime.now().strftime("%Y-%m-%d"), "group": group,
              "group_name": GROUP_NAMES[group], "wanted": count, "made": 0, "emotions_made": 0,
              "backfilled": 0, "failed": 0, "stopped": ""}
    attempts = load_attempts(var_dir)
    todo = missing_emotions(library, [e for e in images.emotions if e in EMOTION_EN], attempts)[:max(backfill, 0)]
    if dry_run:
        result["stopped"] = "dry-run"
        result["backfill_planned"] = len(todo)
        result["sample"] = [make_person(group, rng) for _ in range(min(count, 3))]
        return result
    if not images.enabled:
        result["stopped"] = "image-disabled (키 없음 또는 할당량 소진)"
        _append(log_path, result)
        return result

    sem, fails = asyncio.Semaphore(CONCURRENCY), 0
    emotions = [e for e in images.emotions if e in EMOTION_EN]

    async def draw(prompt: str, seed: int, refs: list[bytes] | None = None) -> bytes | None:
        """한 장 그리기. 할당량이 끝났거나 연속 실패면 보내지 않고 None."""
        nonlocal fails
        async with sem:
            if result["stopped"] or not images.enabled:
                result["stopped"] = result["stopped"] or "quota"  # 429가 나면 images.enabled가 꺼진다
                return None
            raw = await images.generate(prompt, seed=seed, node="daily_portraits", ref_images=refs)
        img = compact(raw, max_size=(images.width, images.height), quality=images.webp_quality) if raw else None
        if not img:
            result["failed"] += 1
            fails += 1
            if fails >= MAX_CONSECUTIVE_FAILS and not result["stopped"]:
                result["stopped"] = f"{MAX_CONSECUTIVE_FAILS}회 연속 실패"
            return None
        fails = 0
        return img

    async def one() -> None:
        p, seed = make_person(group, rng), rng.randrange(2**31)
        prompt = portrait_prompt(role=p["role"], age=p["age"], gender=p["gender"], appearance=p["appearance"])
        base = await draw(prompt, seed)
        if not base:
            return
        rec = library.add(base, "webp", person=p, prompt=prompt, provider=images.provider, model=images.model,
                          seed=seed, source="daily")
        result["made"] += 1
        ref = ref_image(base)  # 표정은 이 얼굴을 참조로 넣어 같은 사람으로 그린다

        async def emotion(emo: str) -> None:
            eprompt, eseed = expression_prompt(emo), rng.randrange(2**31)
            img = await draw(eprompt, eseed, [ref])
            if img:
                library.add(img, "webp", person=p, prompt=eprompt, provider=images.provider, model=images.model,
                            seed=eseed, source="daily", kind="emotion", emotion=emo, base_file=rec["file"])
                result["emotions_made"] += 1
            elif not result["stopped"]:  # 그림 모델이 거른 조합 (할당량·연속 실패로 멈춘 건 세지 않음). 나중에 빈 표정으로 다시 시도
                attempts[f"{rec['file']}|{emo}"] = attempts.get(f"{rec['file']}|{emo}", 0) + 1

        await asyncio.gather(*(emotion(e) for e in emotions))

    refs: dict[str, bytes] = {}  # 기본 사진 파일 → 참조 사진 (같은 얼굴의 표정을 연달아 그릴 때 한 번만 읽는다)

    async def fill(base: dict, emo: str) -> None:
        """이미 있는 얼굴에 빠진 표정 하나를 채운다 (기본 사진을 참조로 넣어 같은 얼굴 유지)."""
        if base["file"] not in refs:
            refs[base["file"]] = ref_image((library.root / base["file"]).read_bytes())
        eprompt, eseed = expression_prompt(emo), rng.randrange(2**31)
        img = await draw(eprompt, eseed, [refs[base["file"]]])
        if img:
            person = {k: base[k] for k in ("role", "age", "gender", "appearance")}
            library.add(img, "webp", person=person, prompt=eprompt, provider=images.provider, model=images.model,
                        seed=eseed, source="daily", kind="emotion", emotion=emo, base_file=base["file"],
                        note="backfill")
            result["backfilled"] += 1
        elif not result["stopped"]:
            attempts[f"{base['file']}|{emo}"] = attempts.get(f"{base['file']}|{emo}", 0) + 1

    await asyncio.gather(*(fill(b, e) for b, e in todo), *(one() for _ in range(count)))  # 빈 표정이 먼저
    save_attempts(var_dir, attempts)
    _append(log_path, result)
    return result


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    from dotenv import load_dotenv

    load_dotenv(_ROOT / ".env")
    ap = argparse.ArgumentParser(description="오늘의 직업군 인물 사진(표정 포함)을 사진 보관함에 쌓는다")
    ap.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="하루에 그릴 최대 장수")
    ap.add_argument("--count", type=int, default=None, help="새로 그릴 사람 수 (비우면 빈 표정 채우고 남은 장수로 계산)")
    ap.add_argument("--no-backfill", action="store_true", help="이미 있는 얼굴의 빠진 표정을 먼저 채우지 않는다")
    ap.add_argument("--group", choices=list(SPECS), default=None, help="비우면 가장 오래 안 돌린 직업군")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    var_dir = _ROOT / "var"
    # 호출 기록은 따로 둔다(var/traces.jsonl은 게임·지연 측정용이라 섞지 않는다). 실패 사유를 여기서 본다
    images = ImageClient(tracer=Tracer(path=var_dir / "daily_portraits_calls.jsonl"))
    per_person = 1 + len([e for e in images.emotions if e in EMOTION_EN])
    backlog = 0 if a.no_backfill else len(missing_emotions(PortraitLibrary(var_dir / "portrait_library"),
                                                           [e for e in images.emotions if e in EMOTION_EN],
                                                           load_attempts(var_dir)))
    backfill = min(a.budget, backlog)
    count = a.count if a.count is not None else (a.budget - backfill) // per_person
    try:
        res = asyncio.run(run(count, a.group, var_dir, images, random.Random(), a.dry_run, backfill))
    except Exception:
        var_dir.mkdir(exist_ok=True)
        with (var_dir / "daily_portraits.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat()}\n{traceback.format_exc()}\n")
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["made"] > 0 or res["backfilled"] > 0 or res["stopped"] == "dry-run" else 1


if __name__ == "__main__":
    raise SystemExit(main())
