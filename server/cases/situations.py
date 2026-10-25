"""상황 목록(data/situations.yaml): 탐정 평가가 여러 무대·직업 구성으로 돌도록 하는 입력 (2026-10-26).

- 상황 하나 = 무대 + 사건 씨앗 한 줄 + 등장 후보 직업 8~12명. 직업마다 사진 직업군(var/portrait_library)과 성별·나이대.
- load/validate: 파일 검사(직업군 이름, 인원, 중복 id).
- next_situation(runs_file): 가장 오래전에 평가한(안 한 것 먼저) 상황.
- rotation_case(presets, runs_file): --theme rotate 용. 사건이 실제로 있는 상황 중에서 고른다.
- python -m server.cases.situations --report: 상황별 사건 수, 직업군 x 성별 필요량 대 보관함 재고.
LLM·네트워크를 쓰지 않는다.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from server.cases.loader import DEFAULT_CASE_DIR, PROJECT_ROOT
from server.game.portrait_library import GROUP_NAMES

SITUATIONS_PATH = PROJECT_ROOT / "data" / "situations.yaml"
LIBRARY_DIR = PROJECT_ROOT / "var" / "portrait_library"
RUNS_FILE = PROJECT_ROOT / "var" / "detective_runs.jsonl"
CASE_PREFIX = "sit_"  # 생성한 사건 id: sit_<상황 id>_<날짜>
ROSTER_MIN, ROSTER_MAX = 8, 12
GENDERS = ("M", "F", "any")
IMAGE_EXT = {".webp", ".png", ".jpg", ".jpeg"}


def load_situations(path: str | Path | None = None) -> dict[str, Any]:
    with open(path or SITUATIONS_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or not isinstance(data.get("situations"), list):
        raise ValueError("situations.yaml 최상위에 situations 목록이 있어야 한다")
    data.setdefault("proposed_groups", {})
    return data


def validate(data: dict[str, Any]) -> list[str]:
    """문제 문장 목록(비면 통과)."""
    problems: list[str] = []
    proposed = data.get("proposed_groups") or {}
    for g in proposed:
        if g in GROUP_NAMES:
            problems.append(f"proposed_groups의 {g}는 이미 있는 직업군이다")
    seen: set[str] = set()
    for s in data["situations"]:
        sid = s.get("id")
        if not sid or not str(sid).replace("_", "").isalnum():
            problems.append(f"상황 id가 없거나 이상하다: {sid!r}")
            continue
        if sid in seen:
            problems.append(f"상황 id 중복: {sid}")
        seen.add(sid)
        for key in ("name", "incident"):
            if not str(s.get(key) or "").strip():
                problems.append(f"{sid}: {key}가 비었다")
        roles = s.get("roles") or []
        if not ROSTER_MIN <= len(roles) <= ROSTER_MAX:
            problems.append(f"{sid}: 직업이 {len(roles)}명 ({ROSTER_MIN}~{ROSTER_MAX}명이어야 한다)")
        titles: set[str] = set()
        for r in roles:
            title = str(r.get("role") or "").strip()
            if not title:
                problems.append(f"{sid}: role 이름이 빈 줄이 있다")
                continue
            if title in titles:
                problems.append(f"{sid}: 직업 이름 중복 {title}")
            titles.add(title)
            g, new = r.get("group"), r.get("needs_new_group")
            if bool(g) == bool(new):
                problems.append(f"{sid}/{title}: group 또는 needs_new_group 중 하나만 써야 한다")
            elif g and g not in GROUP_NAMES:
                problems.append(f"{sid}/{title}: 모르는 직업군 {g}")
            elif new and new not in proposed:
                problems.append(f"{sid}/{title}: needs_new_group {new}가 proposed_groups에 없다")
            if r.get("gender") not in GENDERS:
                problems.append(f"{sid}/{title}: gender는 {GENDERS} 중 하나")
            age = r.get("age")
            if not (isinstance(age, list) and len(age) == 2 and all(isinstance(a, int) for a in age) and 10 <= age[0] <= age[1] <= 90):
                problems.append(f"{sid}/{title}: age는 [최소, 최대] 정수 두 개")
            if not str(r.get("hook") or "").strip():
                problems.append(f"{sid}/{title}: hook이 비었다")
    return problems


def by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {s["id"]: s for s in data["situations"]}


# ------------------------------------------------------------------ 사건 <-> 상황
def setting_of(case_id: str, data: dict[str, Any] | None = None) -> str | None:
    """사건 id가 어느 상황의 것인지. 상황 목록에 없으면 None."""
    data = data or load_situations()
    for s in data["situations"]:
        if s.get("existing_case") == case_id:
            return s["id"]
    best = None
    for s in data["situations"]:
        if case_id.startswith(f"{CASE_PREFIX}{s['id']}_") and (best is None or len(s["id"]) > len(best)):
            best = s["id"]
    return best


def case_counts(data: dict[str, Any], case_dir: str | Path | None = None) -> Counter:
    d = Path(case_dir or DEFAULT_CASE_DIR)
    ids = [p.stem for p in d.glob("*.json")] if d.is_dir() else []
    return Counter(sid for sid in (setting_of(c, data) for c in ids) if sid)


def _last_seen(runs_file: str | Path | None, data: dict[str, Any]) -> dict[str, int]:
    """상황 id -> 평가 기록에서 마지막으로 나온 줄 번호(없으면 -1)."""
    last = {s["id"]: -1 for s in data["situations"]}
    try:
        lines = Path(runs_file).read_text(encoding="utf-8").splitlines() if runs_file else []
    except OSError:
        lines = []
    for i, line in enumerate(lines):
        try:
            theme = json.loads(line).get("theme") or ""
        except ValueError:
            continue
        sid = setting_of(theme, data)
        if sid:
            last[sid] = i
    return last


def next_situation(runs_file: str | Path | None = None, data: dict[str, Any] | None = None,
                   only_with_cases: bool = False, case_dir: str | Path | None = None) -> dict[str, Any]:
    """가장 오래전에 평가한(안 한 것 먼저) 상황. 같으면 목록 앞쪽."""
    data = data or load_situations()
    last = _last_seen(runs_file, data)
    cands = data["situations"]
    if only_with_cases:
        have = case_counts(data, case_dir)
        cands = [s for s in cands if have[s["id"]] > 0]
        if not cands:
            raise LookupError("사건이 있는 상황이 없다")
    order = {s["id"]: i for i, s in enumerate(data["situations"])}
    return min(cands, key=lambda s: (last[s["id"]], order[s["id"]]))


def next_to_generate(data: dict[str, Any] | None = None, runs_file: str | Path | None = None,
                     case_dir: str | Path | None = None) -> dict[str, Any]:
    """사건이 가장 적은 상황(같으면 평가를 오래 안 한 것, 그다음 목록 앞쪽)."""
    data = data or load_situations()
    have, last = case_counts(data, case_dir), _last_seen(runs_file, data)
    order = {s["id"]: i for i, s in enumerate(data["situations"])}
    return min(data["situations"], key=lambda s: (have[s["id"]], last[s["id"]], order[s["id"]]))


def rotation_case(presets: list[str], runs_file: str | Path | None = None, data: dict[str, Any] | None = None) -> str:
    """--theme rotate: 실제로 사건이 있는 것 중 가장 오래전에 평가한 상황의 사건.
    상황 목록에 없는 사건은 그 사건 하나를 한 상황으로 친다. 같은 상황에 사건이 여럿이면 그중 오래 안 돌린 것."""
    if not presets:
        raise LookupError("사건이 없다")
    data = data or load_situations()
    rows: list[str] = []
    try:
        for line in Path(runs_file).read_text(encoding="utf-8").splitlines() if runs_file else []:
            try:
                rows.append(json.loads(line).get("theme") or "")
            except ValueError:
                rows.append("")
    except OSError:
        pass
    last_case = {c: -1 for c in presets}
    for i, t in enumerate(rows):
        if t in last_case:
            last_case[t] = i
    key = {c: setting_of(c, data) or f"case:{c}" for c in presets}
    last_group: dict[str, int] = {}
    for c in presets:
        last_group[key[c]] = max(last_group.get(key[c], -1), last_case[c])
    return min(presets, key=lambda c: (last_group[key[c]], last_case[c], presets.index(c)))


# ------------------------------------------------------------------ 등장 후보를 작가에게 주는 글
def outfit_for(group: str | None, age_hi: int) -> str:
    if group == "student":
        return "school_uniform" if age_hi <= 19 else "casual"
    if group in ("security", "cleaning", "culinary", "medical", "delivery", "field"):
        return {"security": "security_uniform", "cleaning": "cleaner_uniform", "culinary": "chef", "medical": "doctor",
                "delivery": "delivery", "field": "work_clothes"}[group]
    if group == "office":
        return "suit"
    return "casual"


def cast_hint(situation: dict[str, Any]) -> str:
    g_ko = {"M": "남", "F": "여", "any": "남녀 무관"}
    lines = []
    for r in situation["roles"]:
        lines.append(f"- {r['role']} ({g_ko[r['gender']]}, {r['age'][0]}~{r['age'][1]}세, "
                     f"outfit={outfit_for(r.get('group'), r['age'][1])}): {r['hook']}")
    return "\n".join(lines)


def theme_text(situation: dict[str, Any]) -> str:
    return f"{situation['name']} — {situation['incident']}"


# ------------------------------------------------------------------ 사진 보관함 재고와 부족분
def stock(library: str | Path | None = None) -> dict[tuple[str, str, str], int]:
    """(직업군, 성별, 나이대) -> 사진 수."""
    root = Path(library or LIBRARY_DIR)
    out: Counter = Counter()
    if root.is_dir():
        for f in root.glob("*/*/*/*"):
            if f.suffix.lower() in IMAGE_EXT:
                out[(f.parts[-4], f.parts[-3], f.parts[-2])] += 1
    return dict(out)


def needed(data: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    """(직업군, 성별) -> {roles: 필요한 직업 수, bands: 필요한 나이대 집합}. any는 남·여 둘 다 센다."""
    need: dict[tuple[str, str], dict[str, Any]] = {}
    for s in data["situations"]:
        for r in s["roles"]:
            grp = r.get("group") or f"new:{r['needs_new_group']}"
            for g in (("M", "F") if r["gender"] == "any" else (r["gender"],)):
                e = need.setdefault((grp, g), {"roles": 0, "bands": set()})
                e["roles"] += 1
                e["bands"].update(f"{b}s" for b in range(r["age"][0] // 10 * 10, r["age"][1] // 10 * 10 + 1, 10))
    return need


def gaps(data: dict[str, Any], library: str | Path | None = None) -> dict[str, list]:
    """missing: 사진이 한 장도 없는 (직업군, 성별) / thin_bands: 상자는 있지만 필요한 나이대가 빈 것 / new: 새 상자가 필요한 것."""
    st = stock(library)
    need = needed(data)
    out: dict[str, list] = {"missing": [], "thin_bands": [], "new": []}
    for (grp, g), e in sorted(need.items()):
        if grp.startswith("new:"):
            out["new"].append((grp[4:], g, e["roles"]))
            continue
        total = sum(n for (sg, sx, _), n in st.items() if sg == grp and sx == g)
        if total == 0:
            out["missing"].append((grp, g, e["roles"]))
            continue
        have_bands = {b for (sg, sx, b), n in st.items() if sg == grp and sx == g and n}
        lack = sorted(e["bands"] - have_bands)
        if lack:
            out["thin_bands"].append((grp, g, lack))
    return out


def report(data: dict[str, Any] | None = None, library: str | Path | None = None, case_dir: str | Path | None = None) -> str:
    data = data or load_situations()
    problems = validate(data)
    have = case_counts(data, case_dir)
    out = [f"상황 {len(data['situations'])}개 (검사 문제 {len(problems)}건)"]
    out += [f"  ! {p}" for p in problems]
    out.append("")
    out.append("상황별 사건 수 / 등장 후보 수")
    for s in data["situations"]:
        out.append(f"  {s['id']:<14} {s['name']:<14} 사건 {have[s['id']]}개  후보 {len(s['roles'])}명")
    st, need = stock(library), needed(data)
    out += ["", "직업군 x 성별: 필요한 직업 수 / 보관함 사진 수 (부족이면 *)"]
    out.append(f"  {'직업군':<22}{'남 필요/재고':>14}{'여 필요/재고':>14}")
    groups = sorted({g for g, _ in need}, key=lambda g: (g.startswith("new:"), g))
    for grp in groups:
        cells = []
        for sx in ("M", "F"):
            n = need.get((grp, sx), {}).get("roles", 0)
            have_n = 0 if grp.startswith("new:") else sum(c for (sg, x, _), c in st.items() if sg == grp and x == sx)
            mark = "*" if n and have_n == 0 else " "
            cells.append(f"{n:>5}/{have_n:<5}{mark}")
        label = (grp[4:] + " (새 상자)") if grp.startswith("new:") else grp
        out.append(f"  {label:<22}{cells[0]:>14}{cells[1]:>14}")
    gp = gaps(data, library)
    out += ["", f"부족 요약: 사진 없는 기존 상자 {len(gp['missing'])}칸, 나이대가 빈 칸 {len(gp['thin_bands'])}칸, 새 상자 필요 {len({n for n, _, _ in gp['new']})}종"]
    for grp, sx, n in gp["missing"]:
        out.append(f"  없음  {grp}/{sx} (필요 직업 {n}개)")
    for grp, sx, lack in gp["thin_bands"]:
        out.append(f"  나이대 빈 곳  {grp}/{sx}: {', '.join(lack)}")
    new_names = data.get("proposed_groups") or {}
    for name in sorted({n for n, _, _ in gp["new"]}):
        out.append(f"  새 상자 제안  {name} ({new_names.get(name, '')}): " + ", ".join(f"{sx} {n}개" for nm, sx, n in gp["new"] if nm == name))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="상황 목록 검사·보고. 모델은 부르지 않는다")
    ap.add_argument("--report", action="store_true", help="상황별 사건 수와 사진 직업군 부족분을 출력")
    ap.add_argument("--next", action="store_true", help="평가 기록 기준으로 다음 상황 하나")
    ap.add_argument("--runs", default=str(RUNS_FILE))
    args = ap.parse_args(argv)
    data = load_situations()
    if args.next:
        print(next_situation(args.runs, data)["id"])
        return
    print(report(data))
    if validate(data):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
