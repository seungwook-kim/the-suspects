"""사진 보관함: 그린 초상화를 직업군·성별·나이대별로 쌓아 둔다 (2026-10-13 사용자 결정).

- 위치: var/portrait_library/<직업군>/<성별>_<나이대>/<uuid>.webp, 목록은 index.jsonl(한 줄에 한 장).
- 직업군: 옷차림이 정해진 값(생성 사건)이면 그 값으로, 자유 서술(기본 사건)이면 직업 이름·옷 설명의 낱말로 정한다.
- 게임에서 그린 사진뿐 아니라 개발 중 시안·시험으로 그린 사진도 넣는다(source="design", 사용자 요청).
- 사건·판·인물 id는 적지 않는다(사건 데이터 삭제 규칙과 분리). 공개 외모 정보·요청 문구·모델·시드만 적는다.
- 재활용(find)은 아직 게임에 연결하지 않았다. 지금은 판마다 새로 그리고 보관함에 쌓기만 한다.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

# 직업군 폴더 → 이름
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


class PortraitLibrary:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def index_path(self) -> Path:
        return self.root / "index.jsonl"

    def add(self, img: bytes, ext: str, *, person: dict, prompt: str, provider: str, model: str,
            seed: int | None, kind: str = "base", source: str = "game", note: str = "") -> dict:
        """person: {role, age, gender, appearance}. source: game(게임 중) | design(개발 중 시안·시험)."""
        appearance = person.get("appearance") or {}
        group = job_group(person["role"], appearance)
        sub = self.root / group / _bucket(person["gender"], person["age"])
        sub.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        (sub / name).write_bytes(img)
        rec = {
            "file": f"{group}/{sub.name}/{name}", "group": group, "kind": kind, "source": source,
            "created_at": round(time.time(), 3), "provider": provider, "model": model, "seed": seed,
            "role": person["role"], "age": person["age"], "gender": person["gender"],
            "appearance": appearance, "prompt": prompt,
        }
        if note:
            rec["note"] = note
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
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
        """재활용 후보: 같은 직업군·성별, 나이 차이 max_age_gap 이하. 나이가 가까운 순.
        더 맞추려면 결과의 appearance(옷·머리)로 한 번 더 고른다."""
        hits = [r for r in self.records()
                if r.get("kind") == kind and r.get("group") == group and r["gender"] == gender
                and abs(r["age"] - age) <= max_age_gap and r["file"] not in exclude
                and (self.root / r["file"]).is_file()]
        return sorted(hits, key=lambda r: abs(r["age"] - age))

    def regroup(self) -> int:
        """분류 규칙이 바뀌었을 때 기존 사진을 새 직업군 폴더로 옮기고 목록을 다시 쓴다. 옮긴 장 수."""
        moved, recs = 0, self.records()
        for r in recs:
            group = job_group(r["role"], r.get("appearance"))
            if group == r.get("group") and r["file"].startswith(f"{group}/"):
                continue
            src = self.root / r["file"]
            dst = self.root / group / _bucket(r["gender"], r["age"]) / src.name
            if src.is_file():
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)
                moved += 1
            r["group"], r["file"] = group, f"{group}/{dst.parent.name}/{dst.name}"
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
        tmp.replace(self.index_path)
        return moved
