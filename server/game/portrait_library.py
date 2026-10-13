"""사진 보관함: 그린 초상화를 직업군·성별·나이대별로 쌓아 둔다 (2026-10-13 사용자 결정).

- 위치: var/portrait_library/<직업군>/<성별>_<나이대>/<uuid>.webp, 목록은 index.jsonl(한 줄에 한 장).
- 직업군은 옷차림(appearance.outfit)으로 정한다. 사건마다 직업 이름은 달라도("아파트 경비원", "건물 보안요원")
  옷차림이 같으면 같은 사진을 그대로 쓸 수 있어서다.
- 사건·판·인물 id는 적지 않는다(사건 데이터 삭제 규칙과 분리). 공개 외모 정보·요청 문구·모델·시드만 적는다.
- 재활용(find)은 아직 게임에 연결하지 않았다. 지금은 판마다 새로 그리고 보관함에 쌓기만 한다.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

# 옷차림 → (폴더 이름, 직업군)
JOB_GROUPS: dict[str, tuple[str, str]] = {
    "suit": ("office", "사무·관리직"),
    "office_lanyard": ("office", "사무·관리직"),
    "security_uniform": ("security", "경비·보안직"),
    "cleaner_uniform": ("cleaning", "미화·청소직"),
    "chef": ("culinary", "조리·요식업"),
    "doctor": ("medical", "의료직"),
    "delivery": ("delivery", "배달·운송직"),
    "school_uniform": ("student", "학생"),
    "work_clothes": ("field", "현장·기술직"),
}
GENERAL = ("general", "일반·기타")  # casual, hoodie, 그 밖의 옷


def job_group(outfit: str | None) -> str:
    return JOB_GROUPS.get(outfit or "", GENERAL)[0]


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
            seed: int | None, kind: str = "base") -> dict:
        appearance = person.get("appearance") or {}
        group = job_group(appearance.get("outfit"))
        sub = self.root / group / _bucket(person["gender"], person["age"])
        sub.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        (sub / name).write_bytes(img)
        rec = {
            "file": f"{group}/{sub.name}/{name}", "group": group, "kind": kind, "created_at": round(time.time(), 3),
            "provider": provider, "model": model, "seed": seed,
            "role": person["role"], "age": person["age"], "gender": person["gender"],
            "appearance": appearance, "prompt": prompt,
        }
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

    def find(self, *, outfit: str | None, gender: str, age: int, max_age_gap: int = 6,
             exclude: set[str] | frozenset[str] = frozenset(), kind: str = "base") -> list[dict]:
        """재활용 후보: 같은 옷차림·성별, 나이 차이 max_age_gap 이하. 나이가 가까운 순."""
        hits = [r for r in self.records()
                if r.get("kind") == kind and r["gender"] == gender
                and (r.get("appearance") or {}).get("outfit") == outfit
                and abs(r["age"] - age) <= max_age_gap and r["file"] not in exclude
                and (self.root / r["file"]).is_file()]
        return sorted(hits, key=lambda r: abs(r["age"] - age))
