"""인물 초상화 (AI, 실사 사진 느낌 — 2026-10-13 사용자 결정).

- 판마다 새로 그린다(얼굴 재사용 없음). 판 그림: var/portraits/<key>/<인물 id>.<png|jpg|webp>. 클리어하면 폴더째 삭제.
  key = 자유 주제 사건이면 case_id(사건 생성 중 브리핑 단계에서 미리 그리기 시작), 기본 주제면 game_id.
- 사진 보관함(var/portrait_library): 그린 사진은 클리어해도 남긴다(나중에 검사·보정·재사용용, 2026-10-13 사용자 결정).
  보관함에는 사건·판 id를 적지 않는다. 공개 외모 정보와 요청 문구, 모델, 시드만 index.jsonl에 적는다.
- 그림 요청에는 역할·나이·성별·옷·머리만 넣는다. 범인 여부·비밀·성격은 넣지 않는다(PRD §3.6, 검수 규칙 7).
- 그림이 없거나 늦으면 화면은 절차적 SVG로 대신 그린다.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
import shutil
import time
import uuid
from pathlib import Path

from server.llm.images import ImageClient

_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")
EXTS = ("png", "jpg", "webp")

OUTFIT_EN = {
    "suit": "a dark business suit", "casual": "casual everyday clothes", "hoodie": "a plain hoodie",
    "cleaner_uniform": "a cleaning staff uniform", "security_uniform": "a security guard uniform",
    "chef": "a chef's white jacket", "doctor": "a white doctor's coat", "delivery": "a delivery worker's jacket",
    "school_uniform": "a Korean school uniform", "work_clothes": "practical work clothes",
    "office_lanyard": "office clothes with an ID lanyard",
}
HAIR_EN = {
    "short": "short hair", "side": "side-parted hair", "long": "long hair", "bun": "hair tied in a bun",
    "curly": "curly hair", "buzz": "a buzz cut", "ponytail": "a ponytail", "bald": "a bald head",
}
ACCESSORY_EN = {"glasses": "wearing glasses", "cap": "wearing a cap", "badge": "with a name badge",
                "radio": "with a two-way radio clipped on", "apron": "wearing an apron", "laptop": "", "mop": ""}


def portrait_prompt(*, role: str, age: int, gender: str, appearance: dict, setting: str = "") -> str:
    who = {"M": "man", "F": "woman"}.get(gender, "person")
    look = [OUTFIT_EN.get(appearance.get("outfit", ""), "casual clothes"),
            HAIR_EN.get(appearance.get("hair", ""), "natural hair")]
    if acc := ACCESSORY_EN.get(appearance.get("accessory", "")):
        look.append(acc)
    return (
        f"Photorealistic upper-body portrait photo of a fictional {age}-year-old Korean {who} who works as {role}, "
        f"wearing {look[0]}, with {look[1]}{', ' + look[2] if len(look) > 2 else ''}. "
        "Calm neutral expression, looking at the camera, natural soft daylight, modern present-day South Korea, "
        f"plain softly blurred background{(' suggesting ' + setting) if setting else ''}, 3:4 vertical framing, head and shoulders centered. "
        "An ordinary-looking person, not a celebrity and not resembling any real person. "
        "No text, no watermark, no logo, no dramatic lighting."
    )


def image_ext(data: bytes) -> str | None:
    """파일 머리로 형식 판별 (공급자마다 PNG·JPEG·WebP로 돌려준다)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


class PortraitStore:
    def __init__(self, root: Path, images: ImageClient, concurrency: int = 3, library: Path | None = None) -> None:
        self.root = root
        self.images = images
        self.library = library
        self._sem = asyncio.Semaphore(concurrency)
        self._tasks: dict[str, asyncio.Task] = {}

    @property
    def enabled(self) -> bool:
        return self.images.enabled

    def _dir(self, key: str) -> Path:
        if not _SAFE.match(key):
            raise ValueError("bad key")
        return self.root / key

    def path(self, key: str, filename: str) -> Path | None:
        """서빙용 경로 (경로 조작 방지: 영문·숫자·_- 이름 + 그림 확장자만)."""
        stem, dot, ext = filename.rpartition(".")
        if not dot or ext not in EXTS or not _SAFE.match(stem) or not _SAFE.match(key):
            return None
        p = self._dir(key) / filename
        return p if p.is_file() else None

    def urls(self, key: str) -> dict[str, str]:
        d = self.root / key if _SAFE.match(key) else None
        if d is None or not d.is_dir():
            return {}
        return {p.stem: f"/api/portraits/{key}/{p.name}?v={int(p.stat().st_mtime)}"
                for p in d.iterdir() if p.suffix[1:] in EXTS}

    def start(self, key: str, people: list[dict], *, setting: str = "", game_id: str | None = None) -> None:
        """people: [{id, role, age, gender, appearance}] — 공개 정보만. 이미 그리는 중이면 무시."""
        if not self.enabled or key in self._tasks:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 이벤트 루프 밖(동기 호출)에서는 그리지 않는다 → SVG
            return
        self._tasks[key] = loop.create_task(self._draw_all(key, people, setting, game_id))

    async def wait(self, key: str) -> None:
        t = self._tasks.get(key)
        if t:
            await t

    async def _draw_all(self, key: str, people: list[dict], setting: str, game_id: str | None) -> None:
        d = self._dir(key)
        d.mkdir(parents=True, exist_ok=True)

        async def one(p: dict) -> None:
            if not _SAFE.match(p["id"]) or any((d / f"{p['id']}.{e}").exists() for e in EXTS):
                return
            prompt = portrait_prompt(role=p["role"], age=p["age"], gender=p["gender"],
                                     appearance=p.get("appearance") or {}, setting=setting)
            seed = random.randrange(2**31)
            async with self._sem:
                img = await self.images.generate(prompt, seed=seed, game_id=game_id)
            ext = image_ext(img) if img else None
            if not ext:
                return
            tmp = d / f"{p['id']}.tmp"
            tmp.write_bytes(img)
            tmp.replace(d / f"{p['id']}.{ext}")  # 반쯤 쓴 파일이 서빙되지 않게
            self._archive(img, ext, p, prompt, seed)

        await asyncio.gather(*(one(p) for p in people), return_exceptions=True)

    def _archive(self, img: bytes, ext: str, person: dict, prompt: str, seed: int) -> None:
        """사진 보관함에 한 장 더 남긴다. 사건·판과 잇는 정보(case_id, game_id, 인물 id)는 적지 않는다."""
        if self.library is None:
            return
        now = time.time()
        sub = self.library / time.strftime("%Y-%m", time.localtime(now))
        sub.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex}.{ext}"
        (sub / name).write_bytes(img)
        rec = {
            "file": f"{sub.name}/{name}", "kind": "base", "created_at": round(now, 3),
            "provider": self.images.provider, "model": self.images.model, "seed": seed,
            "role": person["role"], "age": person["age"], "gender": person["gender"],
            "appearance": person.get("appearance") or {}, "prompt": prompt,
        }
        with (self.library / "index.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def delete(self, key: str) -> None:
        """판 그림만 지운다. 보관함 사진은 남는다."""
        t = self._tasks.pop(key, None)
        if t and not t.done():
            t.cancel()
        if _SAFE.match(key):
            shutil.rmtree(self.root / key, ignore_errors=True)
