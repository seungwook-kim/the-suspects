"""사진 보관함(직군함): 그린 초상화를 직업군별 상자에 쌓아 둔다 (2026-10-13~14 사용자 결정).

- 위치: var/portrait_library/<직업군>/<성별>_<나이대>/<uuid>.webp
  - 직업군마다 상자 폴더와 그 상자의 목록(<직업군>/index.jsonl)이 있다. 나중에 직업군별로 DB에 나눠 넣기 쉽게.
  - 전체 목록 index.jsonl(모든 상자 합본)과 상자 이름표 groups.json도 둔다.
- 직업군: 옷차림이 정해진 값(생성 사건)이면 그 값으로, 자유 서술(기본 사건)이면 직업 이름·옷 설명의 낱말로 정한다.
- 기본 사진(kind=base)과 표정 사진(kind=emotion, emotion, base_file)을 함께 둔다.
- 게임에서 그린 사진뿐 아니라 개발 중 시안·시험 사진도 넣는다(source=design).
- 사건·판·인물 id는 적지 않는다(사건 데이터 삭제 규칙과 분리). 공개 외모 정보·요청 문구·모델·시드만 적는다.
- 재활용(pick): 그림을 새로 그릴 수 없을 때(할당량 초과·실패) 비슷한 사람 사진을 꺼내 쓴다.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

# 직업군 상자 폴더 → 이름
GROUP_NAMES: dict[str, str] = {
    "security": "경비·보안직", "cleaning": "미화·청소직", "medical": "의료직", "culinary": "조리·요식업",
    "delivery": "배달·운송직", "student": "학생", "field": "현장·기술직", "office": "사무·관리직", "general": "일반·기타",
}
# 정해진 옷차림 값 → 직업군
OUTFIT_GROUPS: dict[str, str] = {
    "suit": "office", "office_lanyard": "office", "security_uniform": "security", "cleaner_uniform": "cleaning",
    "chef": "culinary", "doctor": "medical", "delivery": "delivery", "school_uniform": "student", "work_clothes": "field",
}
# 자유 서술용 낱말 (앞에 있는 직업군이 우선: "청소원(시설관리 용역)"은 현장·기술이 아니라 미화)
KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("security", ("경비", "보안", "경호", "security", "guard")),
    ("cleaning", ("청소", "미화", "cleaner", "janitor")),
    ("medical", ("의사", "간호", "의료", "약사", "doctor", "nurse")),
    ("culinary", ("요리", "셰프", "조리", "주방", "바리스타", "chef", "cook")),
    ("delivery", ("배달", "택배", "퀵", "운송", "delivery", "courier")),
    ("student", ("학생", "교복", "student")),
    ("field", ("작업복", "현장", "정비", "설비", "기술자", "기사", "worker", "mechanic")),
    ("office", ("개발자", "매니저", "관리자", "회사원", "사원", "직원", "대리", "과장", "팀장", "기획", "디자이너",
                "정장", "와이셔츠", "블라우스", "재킷", "dba", "pm", "manager", "engineer", "developer")),
]
REUSE_AGE_GAP = 12  # 재활용할 때 나이 차이 상한


def job_group(role: str = "", appearance: dict | None = None) -> str:
    appearance = appearance or {}
    outfit = appearance.get("outfit") or ""
    if outfit in OUTFIT_GROUPS:
        return OUTFIT_GROUPS[outfit]
    text = f"{role} {outfit}".lower()
    for group, words in KEYWORDS:
        if any(w in text for w in words):
            return group
    return "general"


def age_band(age: int) -> str:
    return f"{min(max(age // 10 * 10, 10), 80)}s"


def _bucket(gender: str, age: int) -> str:
    return f"{gender if gender in ('M', 'F') else 'X'}_{age_band(age)}"


def _line(rec: dict) -> str:
    return json.dumps(rec, ensure_ascii=False) + "\n"


class PortraitLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def index_path(self) -> Path:
        return self.root / "index.jsonl"

    def ensure_boxes(self) -> None:
        """직업군 상자 폴더를 모두 만들고 이름표(groups.json)를 쓴다."""
        for g in GROUP_NAMES:
            (self.root / g).mkdir(parents=True, exist_ok=True)
        (self.root / "groups.json").write_text(json.dumps(GROUP_NAMES, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, img: bytes, ext: str, *, person: dict, prompt: str, provider: str, model: str,
            seed: int | None, kind: str = "base", source: str = "game", note: str = "",
            emotion: str | None = None, base_file: str | None = None) -> dict:
        """person: {role, age, gender, appearance}. source: game(게임 중) | design(개발 중 시안·시험).
        kind: base(무표정) | emotion(표정 사진, emotion·base_file로 기본 사진과 이어짐)."""
        appearance = person.get("appearance") or {}
        group = job_group(person["role"], appearance)
        if not (self.root / "groups.json").is_file():
            self.ensure_boxes()
        sub = self.root / group / _bucket(person["gender"], person["age"])
        sub.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        (sub / name).write_bytes(img)
        rec = {
            "file": f"{group}/{sub.name}/{name}", "group": group, "group_name": GROUP_NAMES[group], "kind": kind,
            "source": source, "created_at": round(time.time(), 3), "provider": provider, "model": model, "seed": seed,
            "role": person["role"], "age": person["age"], "gender": person["gender"],
            "appearance": appearance, "prompt": prompt,
        }
        if emotion:
            rec["emotion"] = emotion
        if base_file:
            rec["base_file"] = base_file
        if note:
            rec["note"] = note
        with self.index_path.open("a", encoding="utf-8") as f:  # 전체 목록
            f.write(_line(rec))
        with (self.root / group / "index.jsonl").open("a", encoding="utf-8") as f:  # 직업군 상자 목록
            f.write(_line(rec))
        return rec

    def records(self) -> list[dict]:
        if not self.index_path.is_file():
            return []
        out = []
        for line in self.index_path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:  # 쓰다 끊긴 줄은 건너뛴다
                continue
        return out

    def find(self, *, group: str, gender: str, age: int, max_age_gap: int = 6,
             exclude: set[str] | frozenset[str] = frozenset(), kind: str = "base") -> list[dict]:
        """후보: 같은 직업군·성별, 나이 차이 max_age_gap 이하. 나이가 가까운 순."""
        hits = [r for r in self.records()
                if r.get("kind") == kind and r.get("group") == group and r["gender"] == gender
                and abs(r["age"] - age) <= max_age_gap and r["file"] not in exclude
                and (self.root / r["file"]).is_file()]
        return sorted(hits, key=lambda r: abs(r["age"] - age))

    def pick(self, person: dict, exclude: set[str] | frozenset[str] = frozenset()) -> tuple[dict, dict[str, Path]] | None:
        """재활용할 사진 한 사람분: (기본 사진 기록, {표정: 파일}). 같은 직업 이름·옷차림이 같으면 우선, 그다음 나이가 가까운 순.
        글자 깨짐 같은 문제 표시(note)가 있는 사진과 이 판에서 이미 쓴 사진(exclude)은 고르지 않는다."""
        appearance = person.get("appearance") or {}
        group = job_group(person["role"], appearance)
        cands = [r for r in self.find(group=group, gender=person["gender"], age=person["age"],
                                      max_age_gap=REUSE_AGE_GAP, exclude=exclude) if not r.get("bad")]
        if not cands:
            return None
        outfit = appearance.get("outfit")
        emo_files: dict[str, dict[str, Path]] = {}
        for r in self.records():
            if r.get("kind") == "emotion" and r.get("emotion") and r.get("base_file") and (self.root / r["file"]).is_file():
                emo_files.setdefault(r["base_file"], {})[r["emotion"]] = self.root / r["file"]

        def score(r: dict) -> tuple:  # 작을수록 좋음
            return (r["role"] != person["role"], (r.get("appearance") or {}).get("outfit") != outfit,
                    -len(emo_files.get(r["file"], {})), abs(r["age"] - person["age"]), -r.get("created_at", 0))

        best = min(cands, key=score)
        return best, emo_files.get(best["file"], {})

    def flag_bad(self, files: dict[str, str]) -> int:
        """문제 있는 사진 표시(재활용 제외): {파일: 사유}. 표시한 장 수. 그 사진의 표정 사진도 함께 표시."""
        recs, n = self.records(), 0
        for r in recs:
            reason = files.get(r["file"]) or files.get(r.get("base_file") or "")
            if reason and not r.get("bad"):
                r["bad"], r["bad_reason"] = True, reason
                n += 1
        self._rewrite(recs)
        return n

    def _rewrite(self, recs: list[dict]) -> None:
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text("".join(_line(r) for r in recs), encoding="utf-8")
        tmp.replace(self.index_path)
        for g in GROUP_NAMES:  # 직업군 상자 목록 다시 쓰기
            (self.root / g).mkdir(parents=True, exist_ok=True)
            (self.root / g / "index.jsonl").write_text("".join(_line(r) for r in recs if r["group"] == g),
                                                       encoding="utf-8")

    def regroup(self) -> int:
        """분류 규칙·구조가 바뀌었을 때 기존 사진을 알맞은 직업군 상자로 옮기고 목록을 다시 쓴다. 옮긴 장 수.
        표정 사진의 base_file도 새 위치로 고친다."""
        self.ensure_boxes()
        moved, recs, renamed = 0, self.records(), {}
        for r in recs:
            group = job_group(r["role"], r.get("appearance"))
            new = f"{group}/{_bucket(r['gender'], r['age'])}/{Path(r['file']).name}"
            if new != r["file"]:
                src, dst = self.root / r["file"], self.root / new
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    src.replace(dst)
                    moved += 1
                renamed[r["file"]] = new
            r["file"], r["group"], r["group_name"] = new, group, GROUP_NAMES[group]
        for r in recs:
            if r.get("base_file") in renamed:
                r["base_file"] = renamed[r["base_file"]]
        self._rewrite(recs)
        return moved
