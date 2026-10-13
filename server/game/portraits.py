"""인물 초상화 (AI, 실사 사진 느낌 — 2026-10-13 사용자 결정).

- 판마다 새로 그린다(얼굴 재사용 없음). 판 그림: var/portraits/<key>/<인물 id>.webp. 클리어하면 폴더째 삭제.
  key = 자유 주제 사건이면 case_id(사건 생성 중 브리핑 단계에서 미리 그리기 시작), 기본 주제면 game_id.
- 경량화(2026-10-13 사용자 결정): 480×640으로 그려 WebP로 압축한다(장당 약 15KB). 화면 최대 표시 폭 230px의 2배.
  한 판의 인물을 한꺼번에 그린다(설정 concurrency, 기본 7). 시간은 대부분 공급자 쪽 대기라 동시에 보내야 빠르다.
- 사진 보관함(portrait_library.py): 그린 사진은 클리어해도 직업군별로 남긴다(나중에 검사·보정·재활용용).
- 그림 요청에는 역할·나이·성별·옷·머리만 넣는다. 범인 여부·비밀·성격은 넣지 않는다(PRD §3.6, 검수 규칙 7).
- 그림이 없거나 늦으면 화면은 절차적 SVG로 대신 그린다.
"""

from __future__ import annotations

import asyncio
import io
import random
import re
import shutil
from pathlib import Path

from PIL import Image

from server.game.portrait_library import PortraitLibrary
from server.llm.images import ImageClient

_SAFE = re.compile(r"^[A-Za-z0-9_\-]+$")
EXTS = ("png", "jpg", "webp")

# 옷과 소품은 글자가 없는 민무늬로 묘사한다 (이름표·패치·사원증에 엉터리 글자가 찍히는 것 방지, 2026-10-13 시안 1차)
OUTFIT_EN = {
    "suit": "a dark business suit", "casual": "casual everyday clothes", "hoodie": "a plain hoodie",
    "cleaner_uniform": "a plain cleaning staff uniform", "security_uniform": "a plain navy security guard uniform shirt",
    "chef": "a plain white chef's jacket", "doctor": "a plain white doctor's coat",
    "delivery": "a plain delivery worker's jacket", "school_uniform": "a Korean school uniform",
    "work_clothes": "practical work clothes", "office_lanyard": "office clothes with a blank white ID card on a plain lanyard",
}
HAIR_EN = {
    "short": "short hair", "side": "side-parted hair", "long": "long hair", "bun": "hair tied in a bun",
    "curly": "curly hair", "buzz": "a buzz cut", "ponytail": "a ponytail", "bald": "a bald head",
}
ACCESSORY_EN = {"glasses": "wearing glasses", "cap": "wearing a plain cap", "badge": "with a blank ID badge",
                "radio": "with a two-way radio clipped on", "apron": "wearing a plain apron", "laptop": "", "mop": ""}


def portrait_prompt(*, role: str, age: int, gender: str, appearance: dict, setting: str = "") -> str:
    who = {"M": "man", "F": "woman"}.get(gender, "person")
    look = [OUTFIT_EN.get(appearance.get("outfit", ""), "casual clothes"),
            HAIR_EN.get(appearance.get("hair", ""), "natural hair")]
    if acc := ACCESSORY_EN.get(appearance.get("accessory", "")):
        look.append(acc)
    return (
        f"Photorealistic close-up head-and-shoulders portrait photo of a fictional {age}-year-old Korean {who} "
        f"who works as {role}, wearing {look[0]}, with {look[1]}{', ' + look[2] if len(look) > 2 else ''}. "
        "The face and shoulders fill the frame, cropped at the chest, eyes in the upper third. "
        "Relaxed neutral expression with closed lips, looking straight at the camera, natural soft daylight, "
        f"modern present-day South Korea, softly blurred background{(' suggesting ' + setting) if setting else ''}. "
        "An ordinary-looking person, not a celebrity and not resembling any real person. "
        "Clothing is plain and unmarked with no name tags, patches, logos or lettering; the background has no signs. "
        "No text, no watermark, no dramatic lighting."
    )


def compact(data: bytes, *, max_size: tuple[int, int], quality: int) -> bytes | None:
    """받은 그림을 최대 크기 안으로 줄이고 WebP로 압축한다. 그림이 아니면 None (저장하지 않음)."""
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None
    im = im.convert("RGB")  # 메타데이터·투명도 버림
    im.thumbnail(max_size, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


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
    def __init__(self, root: Path, images: ImageClient, concurrency: int | None = None,
                 library: PortraitLibrary | None = None) -> None:
        self.root = root
        self.images = images
        self.library = library
        self._sem = asyncio.Semaphore(concurrency or images.concurrency)
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
                raw = await self.images.generate(prompt, seed=seed, game_id=game_id)
            img = compact(raw, max_size=(self.images.width, self.images.height),
                          quality=self.images.webp_quality) if raw else None
            if not img:
                return
            tmp = d / f"{p['id']}.tmp"
            tmp.write_bytes(img)
            tmp.replace(d / f"{p['id']}.webp")  # 반쯤 쓴 파일이 서빙되지 않게
            if self.library is not None:  # 사건·판·인물 id 없이 공개 외모 정보만
                self.library.add(img, "webp", person=p, prompt=prompt, provider=self.images.provider,
                                 model=self.images.model, seed=seed)

        await asyncio.gather(*(one(p) for p in people), return_exceptions=True)

    def delete(self, key: str) -> None:
        """판 그림만 지운다. 보관함 사진은 남는다."""
        t = self._tasks.pop(key, None)
        if t and not t.done():
            t.cancel()
        if _SAFE.match(key):
            shutil.rmtree(self.root / key, ignore_errors=True)
