"""인물 초상화 (AI, 실사 사진 느낌 — 2026-10-13 사용자 결정).

- 판마다 새로 그린다(얼굴 재사용 없음). 저장: var/portraits/<key>/<인물 id>.png. 클리어하면 폴더째 삭제.
  key = 자유 주제 사건이면 case_id(사건 생성 중 브리핑 단계에서 미리 그리기 시작), 기본 주제면 game_id.
- 그림 요청에는 역할·나이·성별·옷·머리만 넣는다. 범인 여부·비밀·성격은 넣지 않는다(PRD §3.6, 검수 규칙 7).
- 그림이 없거나 늦으면 화면은 절차적 SVG로 대신 그린다.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from server.llm.images import ImageClient

_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")

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


class PortraitStore:
    def __init__(self, root: Path, images: ImageClient, concurrency: int = 3) -> None:
        self.root = root
        self.images = images
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
        """서빙용 경로 (경로 조작 방지: 영문·숫자·_- 이름 + .png만)."""
        stem, dot, ext = filename.rpartition(".")
        if not dot or ext != "png" or not _SAFE.match(stem) or not _SAFE.match(key):
            return None
        p = self._dir(key) / filename
        return p if p.is_file() else None

    def urls(self, key: str) -> dict[str, str]:
        d = self.root / key if _SAFE.match(key) else None
        if d is None or not d.is_dir():
            return {}
        return {p.stem: f"/api/portraits/{key}/{p.name}?v={int(p.stat().st_mtime)}" for p in d.glob("*.png")}

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
            if (d / f"{p['id']}.png").exists():
                return
            async with self._sem:
                img = await self.images.generate(
                    portrait_prompt(role=p["role"], age=p["age"], gender=p["gender"], appearance=p.get("appearance") or {},
                                    setting=setting), game_id=game_id)
            if img and _SAFE.match(p["id"]):
                tmp = d / f"{p['id']}.tmp"
                tmp.write_bytes(img)
                tmp.replace(d / f"{p['id']}.png")  # 반쯤 쓴 파일이 서빙되지 않게

        await asyncio.gather(*(one(p) for p in people), return_exceptions=True)

    def delete(self, key: str) -> None:
        t = self._tasks.pop(key, None)
        if t and not t.done():
            t.cancel()
        if _SAFE.match(key):
            shutil.rmtree(self.root / key, ignore_errors=True)
