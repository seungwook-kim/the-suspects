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
    "work_clothes": "practical work clothes",
    "teacher_smart": "smart casual teacher clothes, a cardigan over a collared shirt",
    "public_uniform": "a plain dark civil-service style uniform shirt without insignia or patches",
    "formal_gov": "formal conservative office clothes, a dark jacket and a plain shirt",
    "creative_casual": "stylish creative casual clothes, a light scarf or a neat jacket",
    "farm_clothes": "weathered practical farm work clothes and a plain work hat",
    "store_apron": "a plain store staff apron over a polo shirt",
    "hotel_uniform": "a plain hotel staff uniform with a vest and a blank name-tag-free collar", "office_lanyard": "office clothes with a blank white ID card on a plain lanyard",
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
        "The face and shoulders fill the frame, cropped at the upper chest, eyes in the upper third; "
        "only the head, neck and upper chest are visible, so trousers, shoes and hands are out of frame. "
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
        self._emo_jobs: dict[tuple[str, str, str], asyncio.Task] = {}  # (판, 인물, 표정) → 그리기 (끝나도 남겨 재시도 막음)
        self._base_files: dict[tuple[str, str], str] = {}  # (판, 인물) → 보관함의 기본 사진 (표정 사진 잇기용)

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
        """기본 사진이 빠진 사람이 있는지 (표정 사진은 그 감정이 처음 나올 때 그린다)."""
        base = self.urls(key)
        return any(i not in base for i in ids)

    @property
    def can_fill(self) -> bool:
        """새로 그리거나(그림 연결 켜짐) 보관함에서 꺼내 쓸 수 있는지."""
        return self.images.enabled or self.library is not None

    def start(self, key: str, people: list[dict], *, setting: str = "", game_id: str | None = None) -> None:
        """기본 사진 그리기 시작. people: [{id, role, age, gender, appearance}] — 공개 정보만. 이미 그리는 중이면 무시.
        이미 있는 그림은 건너뛰므로 다시 부르면 빠진 사람만 채운다. 한 판에 MAX_STARTS번까지(무한 반복 방지).
        새로 그릴 수 없으면(할당량 초과·실패) 보관함에서 비슷한 사람 사진(표정 사진 포함)을 꺼내 쓴다."""
        if not self.can_fill or self.pending(key) or self._starts.get(key, 0) >= MAX_STARTS:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 이벤트 루프 밖(동기 호출)에서는 그리지 않는다 → SVG
            return
        self._starts[key] = self._starts.get(key, 0) + 1
        self._tasks[key] = loop.create_task(self._draw_all(key, people, setting, game_id))

    def pending(self, key: str) -> bool:
        t = self._tasks.get(key)
        return bool(t and not t.done()) or any(k == key and not j.done() for (k, _, _), j in self._emo_jobs.items())

    async def wait(self, key: str) -> None:
        t = self._tasks.get(key)
        if t:
            await t
        jobs = [j for (k, _, _), j in self._emo_jobs.items() if k == key]
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)

    @staticmethod
    def _save(d: Path, name: str, img: bytes) -> None:
        tmp = d / f"{name}.tmp"
        tmp.write_bytes(img)
        tmp.replace(d / f"{name}.webp")  # 반쯤 쓴 파일이 서빙되지 않게

    async def _draw(self, prompt: str, seed: int, game_id: str | None, refs: list[bytes] | None = None) -> bytes | None:
        async with self._sem:
            if not self.images.enabled:  # 그사이 할당량이 끝났으면 남은 요청은 보내지 않는다
                return None
            raw = await self.images.generate(prompt, seed=seed, game_id=game_id, ref_images=refs)
        return compact(raw, max_size=(self.images.width, self.images.height),
                       quality=self.images.webp_quality) if raw else None

    @staticmethod
    def _base_path(d: Path, pid: str) -> Path | None:
        return next((d / f"{pid}.{e}" for e in EXTS if (d / f"{pid}.{e}").exists()), None)

    def _reuse(self, key: str, d: Path, p: dict, used: set[str]) -> bool:
        """보관함에서 비슷한 사람(같은 직업군·성별, 가까운 나이) 사진을 꺼내 이 판의 사진으로 쓴다. 표정 사진도 함께."""
        if self.library is None:
            return False
        hit = self.library.pick(p, exclude=used)
        if not hit:
            return False
        rec, emos = hit
        used.add(rec["file"])
        self._save(d, p["id"], (self.library.root / rec["file"]).read_bytes())
        for emo, path in emos.items():
            self._save(d, f"{p['id']}--{emo}", path.read_bytes())
        self._base_files[(key, p["id"])] = rec["file"]
        return True

    async def _draw_all(self, key: str, people: list[dict], setting: str, game_id: str | None) -> None:
        d = self._dir(key)
        d.mkdir(parents=True, exist_ok=True)
        used: set[str] = set()  # 이 판에서 이미 꺼내 쓴 보관함 사진 (같은 얼굴 두 번 금지)

        async def one(p: dict) -> None:
            pid = p["id"]
            if not _SAFE.match(pid) or self._base_path(d, pid):
                return
            img = None
            if self.images.enabled:
                prompt = portrait_prompt(role=p["role"], age=p["age"], gender=p["gender"],
                                         appearance=p.get("appearance") or {}, setting=setting)
                seed = random.randrange(2**31)
                img = await self._draw(prompt, seed, game_id)
                if img:
                    self._save(d, pid, img)
                    if self.library is not None:  # 사건·판·인물 id 없이 공개 외모 정보만
                        self._base_files[(key, pid)] = self.library.add(
                            img, "webp", person=p, prompt=prompt, provider=self.images.provider,
                            model=self.images.model, seed=seed)["file"]
            if not img:
                self._reuse(key, d, p, used)
            elif self.images.emotion_mode == "eager":  # 설정으로 표정까지 미리 그리기
                await asyncio.gather(*(self._draw_emotion(key, p, e, game_id) for e in self.images.emotions),
                                     return_exceptions=True)

        await asyncio.gather(*(one(p) for p in people), return_exceptions=True)

    def want_emotions(self, key: str, wants: list[tuple[dict, str]], *, game_id: str | None = None) -> None:
        """지금 나온 감정의 표정 사진이 없으면 그것만 그린다(감정이 처음 나올 때, 한 장 약 7~10초).
        그동안 화면은 기본 사진 + 효과. 사람·표정마다 한 번만 시도한다."""
        if not self.images.enabled or not _SAFE.match(key):
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        d = self.root / key
        for p, emo in wants:
            jk = (key, p["id"], emo)
            if (emo not in EMOTION_EN or emo not in self.images.emotions or jk in self._emo_jobs
                    or not _SAFE.match(p["id"]) or (d / f"{p['id']}--{emo}.webp").exists()
                    or not self._base_path(d, p["id"])):
                continue
            self._emo_jobs[jk] = loop.create_task(self._draw_emotion(key, p, emo, game_id))

    async def _draw_emotion(self, key: str, p: dict, emo: str, game_id: str | None) -> None:
        """기본 사진을 참조로 넣어 같은 얼굴에 표정만 바꿔 그린다."""
        d = self._dir(key)
        pid = p["id"]
        base_path = self._base_path(d, pid)
        if not base_path or (d / f"{pid}--{emo}.webp").exists():
            return
        prompt, seed = expression_prompt(emo), random.randrange(2**31)
        img = await self._draw(prompt, seed, game_id, [ref_image(base_path.read_bytes())])
        if not img:
            return
        self._save(d, f"{pid}--{emo}", img)
        if self.library is not None:
            self.library.add(img, "webp", person=p, prompt=prompt, provider=self.images.provider,
                             model=self.images.model, seed=seed, kind="emotion", emotion=emo,
                             base_file=self._base_files.get((key, pid)))

    def keep_for_history(self, key: str, people: list[dict], dest: Path,
                         size: tuple[int, int] = (180, 240), quality: int = 80) -> dict[str, str]:
        """클리어 기록(결과 카드)용으로 그 판 인물의 기본 사진을 작은 썸네일로 남긴다: 인물 id → 파일 이름.
        판 사진 폴더는 클리어하면 지우지만, 결과 카드·공유 이미지는 그 뒤에도 실제 사진을 보여 준다(사용자 결정 2026-10-15).
        그 판 사진이 없는 인물은 보관함의 비슷한 사람 사진(이 판에서 안 쓴 것)으로 채운다. 그래도 없으면 빠진다(코드로 그린 얼굴).
        people: [{id, role, age, gender, appearance}] — 공개 정보만. 파일 이름은 순번만 쓴다(인물 id 같은 사건 내부 값을 남기지 않음)."""
        if not _SAFE.match(key):
            return {}
        d = self.root / key
        used = {f for (k, _), f in self._base_files.items() if k == key}  # 이 판이 이미 쓴 보관함 사진(같은 얼굴 두 번 금지)
        out: dict[str, str] = {}
        for i, p in enumerate(people):
            pid = p["id"]
            src = self._base_path(d, pid) if _SAFE.match(pid) else None
            if src is None and self.library is not None:
                hit = self.library.pick(p, exclude=used)
                if hit:
                    used.add(hit[0]["file"])
                    src = self.library.root / hit[0]["file"]
            if src is None:
                continue
            img = compact(src.read_bytes(), max_size=size, quality=quality)
            if not img:
                continue
            dest.mkdir(parents=True, exist_ok=True)
            name = f"{i}.webp"
            (dest / name).write_bytes(img)
            out[pid] = name
        return out

    def delete(self, key: str) -> None:
        """판 그림만 지운다. 보관함 사진은 남는다."""
        t = self._tasks.pop(key, None)
        self._starts.pop(key, None)
        for jk in [jk for jk in self._emo_jobs if jk[0] == key]:
            j = self._emo_jobs.pop(jk)
            if not j.done():
                j.cancel()
        for bk in [bk for bk in self._base_files if bk[0] == key]:
            self._base_files.pop(bk)
        if t and not t.done():
            t.cancel()
        if _SAFE.match(key):
            shutil.rmtree(self.root / key, ignore_errors=True)
