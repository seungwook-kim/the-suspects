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
MAX_STARTS = 2  # 처음 1번 + 빠진 그림 다시 그리기 1번 (서버 재시작으로 끊긴 경우 등)

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


def _look(table: dict[str, str], value: object, default: str) -> str:
    """정해진 값(생성 사건)이면 영어 묘사, 자유 서술(기본 사건의 "남색 경비복과 모자" 등)이면 그대로 넣는다.
    그림 모델의 글 해석기는 한국어도 읽는다(2026-10-13 확인: 자유 서술을 버리면 경비원이 평상복으로 그려짐)."""
    if isinstance(value, str) and value in table:
        return table[value]
    return value.strip() if isinstance(value, str) and value.strip() else default


def portrait_prompt(*, role: str, age: int, gender: str, appearance: dict, setting: str = "") -> str:
    who = {"M": "man", "F": "woman"}.get(gender, "person")
    look = [_look(OUTFIT_EN, appearance.get("outfit"), "casual clothes"),
            _look(HAIR_EN, appearance.get("hair"), "natural hair"),
            _look(ACCESSORY_EN, appearance.get("accessory"), ""),
            _look({}, appearance.get("build"), "")]
    extra = "".join(f", {x}" for x in look[2:] if x)
    return (
        f"Photorealistic close-up head-and-shoulders portrait photo of a fictional {age}-year-old Korean {who} "
        f"who works as {role}, wearing {look[0]}, with {look[1]}{extra}. "
        "The face and shoulders fill the frame, cropped at the chest, eyes in the upper third. "
        "Relaxed neutral expression with closed lips, looking straight at the camera, natural soft daylight, "
        f"modern present-day South Korea, softly blurred background{(' suggesting ' + setting) if setting else ''}. "
        "An ordinary-looking person, not a celebrity and not resembling any real person. "
        "Clothing is plain and unmarked with no name tags, patches, logos or lettering; the background has no signs. "
        "No text, no watermark, no dramatic lighting."
    )


# 표정 사진: 기본 사진을 참조로 넣고 표정만 바꿔 그린다 (같은 얼굴 유지, 2026-10-13 사용자 요청)
EMOTION_EN = {
    "nervous": "a tense, nervous expression: lips pressed together, eyebrows slightly raised, eyes glancing to the side",
    "flustered": "a flustered, startled expression: eyes wide open, eyebrows raised high, mouth slightly open, "
                 "a drop of sweat on the forehead",
    "angry": "an angry expression: furrowed brows, glaring eyes, clenched jaw, tight lips",
    "sad": "a sad expression: drooping eyebrows, downcast eyes, the corners of the mouth turned down",
    "happy": "a warm, relieved smile with eyes crinkling at the corners",
}


def expression_prompt(emotion: str) -> str:
    return (
        "Edit this photo. It must stay the exact same person: identical face, identity, age, skin, hairstyle, "
        "clothing, accessories, background, lighting, camera angle and framing. "
        f"Change only the facial expression to {EMOTION_EN[emotion]}. "
        "Photorealistic, natural and subtle, no text, no watermark."
    )


def ref_image(webp: bytes, max_size: tuple[int, int] = (378, 504)) -> bytes:
    """참조로 넣을 기본 사진: 512×512보다 작게 줄여 JPEG로 (Cloudflare 참조 사진 제한)."""
    im = Image.open(io.BytesIO(webp)).convert("RGB")
    im.thumbnail(max_size, Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


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
        self._starts: dict[str, int] = {}  # 판마다 그리기 시작 횟수 (빠진 그림 다시 그리기 상한용)

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

    def _files(self, key: str) -> list[Path]:
        d = self.root / key if _SAFE.match(key) else None
        if d is None or not d.is_dir():
            return []
        return [p for p in d.iterdir() if p.suffix[1:] in EXTS]

    @staticmethod
    def _url(key: str, p: Path) -> str:
        return f"/api/portraits/{key}/{p.name}?v={int(p.stat().st_mtime)}"

    def urls(self, key: str) -> dict[str, str]:
        """기본(무표정) 사진: 인물 id → 주소."""
        return {p.stem: self._url(key, p) for p in self._files(key) if "--" not in p.stem}

    def emotion_urls(self, key: str) -> dict[str, dict[str, str]]:
        """표정 사진: 인물 id → {표정: 주소}. 파일 이름은 <인물 id>--<표정>.webp."""
        out: dict[str, dict[str, str]] = {}
        for p in self._files(key):
            pid, sep, emo = p.stem.partition("--")
            if sep and emo in EMOTION_EN:
                out.setdefault(pid, {})[emo] = self._url(key, p)
        return out

    def missing(self, key: str, ids: list[str]) -> bool:
        """기본 사진이나 설정된 표정 사진 중 빠진 게 있는지."""
        base, emos = self.urls(key), self.emotion_urls(key)
        return any(i not in base or any(e not in emos.get(i, {}) for e in self.images.emotions) for i in ids)

    def start(self, key: str, people: list[dict], *, setting: str = "", game_id: str | None = None) -> None:
        """people: [{id, role, age, gender, appearance}] — 공개 정보만. 이미 그리는 중이면 무시.
        이미 있는 그림은 건너뛰므로 다시 부르면 빠진 사람만 그린다. 한 판에 MAX_STARTS번까지(계속 실패할 때 무한 반복 방지)."""
        if not self.enabled or self.pending(key) or self._starts.get(key, 0) >= MAX_STARTS:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 이벤트 루프 밖(동기 호출)에서는 그리지 않는다 → SVG
            return
        self._starts[key] = self._starts.get(key, 0) + 1
        self._tasks[key] = loop.create_task(self._draw_all(key, people, setting, game_id))

    def pending(self, key: str) -> bool:
        t = self._tasks.get(key)
        return bool(t and not t.done())

    async def wait(self, key: str) -> None:
        t = self._tasks.get(key)
        if t:
            await t

    async def _draw_all(self, key: str, people: list[dict], setting: str, game_id: str | None) -> None:
        d = self._dir(key)
        d.mkdir(parents=True, exist_ok=True)

        def save(name: str, img: bytes) -> None:
            tmp = d / f"{name}.tmp"
            tmp.write_bytes(img)
            tmp.replace(d / f"{name}.webp")  # 반쯤 쓴 파일이 서빙되지 않게

        async def draw(prompt: str, seed: int, refs: list[bytes] | None = None) -> bytes | None:
            async with self._sem:
                if not self.images.enabled:  # 그사이 할당량이 끝났으면 남은 요청은 보내지 않는다
                    return None
                raw = await self.images.generate(prompt, seed=seed, game_id=game_id, ref_images=refs)
            return compact(raw, max_size=(self.images.width, self.images.height),
                           quality=self.images.webp_quality) if raw else None

        async def one(p: dict) -> None:
            pid = p["id"]
            if not _SAFE.match(pid):
                return
            # 1) 기본(무표정) 사진 — 이미 있으면 그대로 쓴다(빠진 그림 다시 그리기)
            base_path = next((d / f"{pid}.{e}" for e in EXTS if (d / f"{pid}.{e}").exists()), None)
            seed, base_file = random.randrange(2**31), None
            if base_path:
                base = base_path.read_bytes()
            else:
                prompt = portrait_prompt(role=p["role"], age=p["age"], gender=p["gender"],
                                         appearance=p.get("appearance") or {}, setting=setting)
                img = await draw(prompt, seed)
                if not img:
                    return
                save(pid, img)
                base = img
                if self.library is not None:  # 사건·판·인물 id 없이 공개 외모 정보만
                    base_file = self.library.add(img, "webp", person=p, prompt=prompt, provider=self.images.provider,
                                                 model=self.images.model, seed=seed)["file"]

            # 2) 표정 사진 — 기본 사진을 참조로 넣어 같은 얼굴에 표정만 바꾼다 (한 장 약 10초)
            ref = ref_image(base)

            async def emotion(emo: str) -> None:
                if (d / f"{pid}--{emo}.webp").exists():
                    return
                prompt = expression_prompt(emo)
                img = await draw(prompt, seed, [ref])
                if not img:
                    return
                save(f"{pid}--{emo}", img)
                if self.library is not None:
                    self.library.add(img, "webp", person=p, prompt=prompt, provider=self.images.provider,
                                     model=self.images.model, seed=seed, kind="emotion", emotion=emo,
                                     base_file=base_file)

            await asyncio.gather(*(emotion(e) for e in self.images.emotions if e in EMOTION_EN),
                                 return_exceptions=True)

        await asyncio.gather(*(one(p) for p in people), return_exceptions=True)

    def delete(self, key: str) -> None:
        """판 그림만 지운다. 보관함 사진은 남는다."""
        t = self._tasks.pop(key, None)
        self._starts.pop(key, None)
        if t and not t.done():
            t.cancel()
        if _SAFE.match(key):
            shutil.rmtree(self.root / key, ignore_errors=True)
