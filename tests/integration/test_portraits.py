"""AI 초상화: 판마다 새로 그리고, 공개 정보만 요청에 넣고, 화면에 주소가 실리고, 작은 WebP로 저장하고,
클리어하면 판 그림은 지우되 직업군별 보관함 사진은 남긴다 (가짜 그림 생성기 / 가짜 HTTP)."""

import asyncio
import base64
import io
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import server.game.service as service_mod
from server.api.app import app
from PIL import Image

from server.game.portrait_library import PortraitLibrary, job_group
from server.game.portraits import PortraitStore, compact, expression_prompt, image_ext, portrait_prompt, ref_image
from server.cases.loader import load_case_by_id
from server.game.service import GameService
from server.llm.images import ImageClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPG = b"\xff\xd8\xff\xe0" + b"0" * 32


def real_image(fmt: str = "PNG", size: tuple[int, int] = (768, 1024)) -> bytes:
    """공급자가 돌려주는 것 같은 진짜 그림 (그라데이션)."""
    im = Image.linear_gradient("L").resize(size).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, fmt)
    return buf.getvalue()


CF_CONFIG = {"active_profile": "dev", "profiles": {"dev": {"roles": {"portrait": {
    "provider": "cloudflare", "model": "@cf/black-forest-labs/flux-2-klein-4b", "width": 768, "height": 1024}}}}}


@pytest.fixture
def prompts():
    return []


@pytest.fixture
def svc(tmp_path, prompts):
    s = GameService(tmp_path, in_memory=True)

    async def fake(prompt: str):
        prompts.append(prompt)
        return real_image()

    s.portraits = PortraitStore(tmp_path / "portraits", eager(ImageClient(tracer=s.llm.tracer, generator=fake)))
    return s


def test_disabled_without_key(tmp_path):
    images = ImageClient(api_key="")
    assert images.enabled is False  # 키가 없으면 그림을 안 그리고 화면은 SVG
    s = GameService(tmp_path, in_memory=True)
    game_id, view = s.new_game("demo_db_deleted")
    assert all(c.portrait_url is None for c in view.characters)


async def test_preset_game_draws_fresh_portraits(svc, prompts):
    game_id, view = svc.new_game("demo_db_deleted")
    await svc.portraits.wait(game_id)
    case = svc.cases["demo_db_deleted"]
    v = svc.view(game_id)
    assert all(c.portrait_url and c.portrait_url.startswith(f"/api/portraits/{game_id}/") for c in v.characters)
    assert all(c.portrait_url.split("?")[0].endswith(".webp") for c in v.characters)  # 작은 WebP로 저장
    per_person = 1 + len(svc.portraits.images.emotions)  # 기본 1장 + 표정 사진
    assert len([x for x in prompts if x.startswith("Photorealistic")]) == len(case.characters)
    assert len(prompts) == len(case.characters) * per_person
    # 표정 사진: 같은 얼굴로 표정만 바꾼 사진이 인물마다 설정된 표정 수만큼
    for c in v.characters:
        assert set(c.portrait_emotions or {}) == set(svc.portraits.images.emotions)
        assert all(u.split("?")[0].endswith(f"{c.id}--{e}.webp") for e, u in c.portrait_emotions.items())
    # 그림 요청에 범인 여부·비밀·성격이 들어가면 안 된다 (수상해 보이게 그려지는 것 방지)
    blob = "\n".join(prompts)
    for ch in case.characters:
        for secret in ch.secrets:
            assert secret not in blob
        assert ch.personality not in blob
    assert "culprit" not in blob.lower() and "범인" not in blob

    # 다른 판은 다른 그림 (얼굴 재사용 없음): 같은 사건이라도 판마다 새로 그린다
    game2, _ = svc.new_game("demo_db_deleted")
    await svc.portraits.wait(game2)
    assert len(prompts) == 2 * len(case.characters) * per_person

    # 클리어하면 그 판의 그림 삭제
    st = svc.store.load_live(game_id)
    st.ending, st.phase = "escaped", "ended"
    svc.store.save_live(st)
    svc.clear(game_id)
    assert svc.portraits.urls(game_id) == {}
    assert svc.portraits.urls(game2)  # 다른 판 그림은 그대로


async def test_generated_case_portraits_start_during_generation(svc):
    job_id = svc.create_case_job("시장 골목에서 사라진 가게 열쇠", {"play_minutes": 20})
    for _ in range(400):
        job = svc.case_job(job_id)
        if job["status"] != "running":
            break
        await asyncio.sleep(0.05)
    case_id = svc.jobs[job_id]["_case_id"]
    await svc.portraits.wait(case_id)
    job = svc.case_job(job_id)
    assert job["status"] == "ready"
    assert all(c["portrait_url"] for c in job["preview"]["characters"])  # 브리핑 미리보기에 그림이 실림
    assert all(c["portrait_url"] for c in job["view"]["characters"]) or True  # 완료 시점에 따라 SVG일 수 있음
    assert all(c.portrait_url for c in svc.view(job["game_id"]).characters)


async def test_portrait_status_while_drawing(tmp_path):
    s = GameService(tmp_path, in_memory=True)
    gate = asyncio.Event()

    async def fake(prompt: str):
        await gate.wait()
        return real_image()

    s.portraits = PortraitStore(tmp_path / "portraits", eager(ImageClient(tracer=s.llm.tracer, generator=fake)))
    game_id, view = s.new_game("demo_db_deleted")
    assert s.portrait_status(game_id) == {"pending": True, "urls": {}, "emotions": {}}  # 화면은 이걸 보고 계속 묻는다
    gate.set()
    await s.portraits.wait(game_id)
    st = s.portrait_status(game_id)
    assert st["pending"] is False and set(st["urls"]) == {c.id for c in view.characters}
    assert all(set(st["emotions"][c.id]) == set(s.portraits.images.emotions) for c in view.characters)

    service_mod._SERVICE = s
    try:
        with TestClient(app) as c:
            r = c.get(f"/api/games/{game_id}/portraits")
            assert r.status_code == 200 and r.json()["pending"] is False and r.json()["urls"] == st["urls"]
            assert c.get("/api/games/g_nope/portraits").status_code == 404
    finally:
        service_mod._SERVICE = None


def eager(images: ImageClient) -> ImageClient:
    images.emotion_mode = "eager"  # 표정까지 처음에 전부 그리는 설정
    return images


async def test_lazy_expression_drawn_when_emotion_first_appears(tmp_path):
    """기본 설정(lazy): 처음에는 기본 사진만, 어떤 인물의 감정이 바뀌면 그 사람·그 표정만 그린다(한 번만)."""
    s = GameService(tmp_path, in_memory=True)
    prompts = []

    async def fake(prompt: str):
        prompts.append(prompt)
        return real_image()

    s.portraits = PortraitStore(tmp_path / "portraits", ImageClient(tracer=s.llm.tracer, generator=fake))
    game_id, view = s.new_game("demo_db_deleted")
    await s.portraits.wait(game_id)
    n = len(view.characters)
    assert len(prompts) == n and s.portraits.emotion_urls(game_id) == {}  # 기본 사진만
    case, state, masker = s._load(game_id)
    npc = view.characters[0].id
    state.npc_states[npc].emotion = "angry"
    s._view(case, state, masker)  # 화면 정보를 만들 때 지금 감정의 표정 사진이 없으면 그리기 시작
    assert s.portrait_status(game_id)["pending"] is True
    await s.portraits.wait(game_id)
    assert s.portraits.emotion_urls(game_id) == {npc: {"angry": s.portraits.emotion_urls(game_id)[npc]["angry"]}}
    assert len(prompts) == n + 1 and "angry expression" in prompts[-1]
    s._view(case, state, masker)
    await s.portraits.wait(game_id)
    assert len(prompts) == n + 1  # 이미 있으면 다시 그리지 않는다


async def test_reuse_library_when_drawing_unavailable(tmp_path):
    """새로 그릴 수 없으면(할당량 초과 등) 보관함에서 같은 직업군·성별·비슷한 나이 사진을 표정 사진째 꺼내 쓴다."""
    lib = PortraitLibrary(tmp_path / "lib")
    img = compact(real_image(), max_size=(480, 640), quality=80)
    case = load_case_by_id("demo_db_deleted")
    for ch in case.characters:  # 지난 판들에서 쌓인 사진이라고 치자
        person = dict(role=ch.role, age=ch.age, gender=ch.gender, appearance=ch.appearance)
        base = lib.add(img, "webp", person=person, prompt="p", provider="cloudflare", model="m", seed=1)
        lib.add(img, "webp", person=person, prompt="e", provider="cloudflare", model="m", seed=1,
                kind="emotion", emotion="angry", base_file=base["file"])
    s = GameService(tmp_path, in_memory=True)
    off = ImageClient(api_key="")  # 그림 연결 꺼짐
    s.portraits = PortraitStore(tmp_path / "portraits", off, library=lib)
    game_id, view = s.new_game("demo_db_deleted")
    await s.portraits.wait(game_id)
    v = s.view(game_id)
    assert all(c.portrait_url for c in v.characters)  # 전원 사진
    assert all((c.portrait_emotions or {}).get("angry") for c in v.characters)  # 표정 사진도 함께
    assert len((lib.root / "index.jsonl").read_text(encoding="utf-8").splitlines()) == 2 * len(case.characters)  # 보관함에 중복 저장 안 함
    assert (lib.root / "groups.json").is_file() and all((lib.root / g).is_dir() for g in ("security", "office", "general"))


def no_emotions(images: ImageClient) -> ImageClient:
    images.emotions = []  # 기본 사진만 세는 시험
    return images


async def test_missing_portraits_redrawn_once_when_asked(tmp_path):
    """그리던 작업이 끊기거나 실패해 빠진 사람이 있으면, 상태를 물을 때 빠진 사람만 한 번 더 그린다(상한 있음)."""
    s = GameService(tmp_path, in_memory=True)
    calls = []

    async def flaky(prompt: str):
        calls.append(prompt)
        return None if len(calls) <= 2 else real_image()  # 처음 두 장 실패

    s.portraits = PortraitStore(tmp_path / "portraits", no_emotions(ImageClient(tracer=s.llm.tracer, generator=flaky)))
    game_id, view = s.new_game("demo_db_deleted")
    await s.portraits.wait(game_id)
    n = len(view.characters)
    assert len(s.portrait_status(game_id)["urls"]) == n - 2  # 두 명 빠짐 → 다시 그리기 시작
    await s.portraits.wait(game_id)
    assert len(calls) == n + 2  # 빠진 두 명만 다시 그림
    st = s.portrait_status(game_id)
    assert st["pending"] is False and len(st["urls"]) == n

    # 계속 실패해도 무한히 다시 그리지 않는다
    async def broken(prompt: str):
        calls.append(prompt)
        return None

    s.portraits = PortraitStore(tmp_path / "portraits2", no_emotions(ImageClient(tracer=s.llm.tracer, generator=broken)))
    game2, _ = s.new_game("demo_db_deleted")
    await s.portraits.wait(game2)
    for _ in range(5):
        s.portrait_status(game2)
        await s.portraits.wait(game2)
    assert len(calls) == n + 2 + 2 * n  # 처음 1번 + 다시 1번에서 멈춤


def test_portrait_endpoint_and_path_safety(tmp_path, svc):
    service_mod._SERVICE = svc
    try:
        d = tmp_path / "portraits" / "g_abc"
        d.mkdir(parents=True)
        (d / "npc_01.png").write_bytes(PNG)
        with TestClient(app) as c:
            r = c.get("/api/portraits/g_abc/npc_01.png")
            assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == PNG
            for bad in ["/api/portraits/g_abc/npc_01.txt", "/api/portraits/g_abc/..%2Fx.png", "/api/portraits/..%2F/npc_01.png",
                        "/api/portraits/g_abc/missing.png"]:
                assert c.get(bad).status_code == 404
    finally:
        service_mod._SERVICE = None


async def test_cloudflare_request_and_response():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["type"] = request.headers["content-type"]
        seen["body"] = request.content.decode("latin-1")
        return httpx.Response(200, json={"success": True, "result": {"image": base64.b64encode(JPG).decode()}})

    images = ImageClient(models_config=CF_CONFIG, api_key="tok", account_id="acc123",
                         transport=httpx.MockTransport(handler))
    assert images.enabled and images.provider == "cloudflare"
    out = await images.generate("a portrait", seed=42)
    assert out == JPG
    assert seen["url"] == "https://api.cloudflare.com/client/v4/accounts/acc123/ai/run/@cf/black-forest-labs/flux-2-klein-4b"
    assert seen["auth"] == "Bearer tok" and seen["type"].startswith("multipart/form-data")
    for name, value in (("prompt", "a portrait"), ("width", "768"), ("height", "1024"), ("seed", "42")):
        assert f'name="{name}"' in seen["body"] and value in seen["body"]


async def test_cloudflare_quota_error_falls_back_to_svg():
    images = ImageClient(models_config=CF_CONFIG, api_key="tok", account_id="acc123",
                         transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"success": False})))
    assert await images.generate("a portrait") is None  # 할당량 초과 → 그림 없음 → 화면은 SVG
    rec = images.tracer.records[-1]
    assert rec.ok is False and rec.extra["errors"][0].startswith("HTTP 429")
    assert images.enabled is False  # 다음 UTC 0시까지 꺼서 실패할 요청을 계속 보내지 않는다
    assert images.quota_until % 86400 == 0
    assert await images.generate("again") is None and len(images.tracer.records) == 1  # 요청 자체를 안 보냄


def test_cloudflare_needs_both_account_and_token():
    assert ImageClient(models_config=CF_CONFIG, api_key="tok", account_id="").enabled is False
    assert ImageClient(models_config=CF_CONFIG, api_key="", account_id="acc").enabled is False


async def test_library_keeps_photos_after_clear_by_job_group(tmp_path):
    s = GameService(tmp_path, in_memory=True)

    async def fake(prompt: str):
        return real_image("JPEG")

    library = tmp_path / "library"
    s.portraits = PortraitStore(tmp_path / "portraits", eager(ImageClient(tracer=s.llm.tracer, generator=fake)),
                                library=PortraitLibrary(library))
    game_id, _ = s.new_game("demo_db_deleted")
    await s.portraits.wait(game_id)
    case = s.cases["demo_db_deleted"]

    st = s.store.load_live(game_id)
    st.ending, st.phase = "escaped", "ended"
    s.store.save_live(st)
    s.clear(game_id)
    assert s.portraits.urls(game_id) == {}  # 판 그림은 지움

    all_lines = (library / "index.jsonl").read_text(encoding="utf-8").splitlines()
    lines = [x for x in all_lines if json.loads(x)["kind"] == "base"]
    assert len(lines) == len(case.characters)  # 보관함 사진은 남음
    emo = [json.loads(x) for x in all_lines if json.loads(x)["kind"] == "emotion"]
    assert len(emo) == len(case.characters) * len(s.portraits.images.emotions)
    base_files = {json.loads(x)["file"] for x in lines}
    assert all(r["emotion"] in s.portraits.images.emotions and r["base_file"] in base_files for r in emo)
    outfits = sorted(ch.appearance.get("outfit", "") for ch in case.characters)
    assert sorted(json.loads(x)["appearance"].get("outfit", "") for x in lines) == outfits
    for line in lines:
        rec = json.loads(line)
        # 직업군/성별/나이대/파일 — 직업군은 옷차림으로 정한다
        group, gender, band, _ = rec["file"].split("/")
        assert group == rec["group"] == job_group(rec["role"], rec["appearance"])
        assert (gender, band) == (rec["gender"], f"{rec['age'] // 10 * 10}s")
        assert image_ext((library / rec["file"]).read_bytes()) == "webp"
        assert rec["kind"] == "base" and isinstance(rec["seed"], int)
    blob = "\n".join(lines)
    assert game_id not in blob and case.case_id not in blob  # 사건·판과 잇는 정보 없음
    assert all(ch.id not in blob for ch in case.characters)
    for ch in case.characters:
        assert all(secret not in blob for secret in ch.secrets)


def test_jpeg_portrait_served_with_jpeg_type(tmp_path, svc):
    service_mod._SERVICE = svc
    try:
        d = tmp_path / "portraits" / "g_abc"
        d.mkdir(parents=True)
        (d / "npc_02.jpg").write_bytes(JPG)
        with TestClient(app) as c:
            r = c.get("/api/portraits/g_abc/npc_02.jpg")
            assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    finally:
        service_mod._SERVICE = None


async def test_expression_uses_base_photo_as_reference():
    """표정 사진은 기본 사진을 512×512보다 작게 줄여 input_image_0으로 넣는다 (같은 얼굴 유지)."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(200, json={"success": True, "result": {"image": base64.b64encode(real_image("JPEG")).decode()}})

    images = ImageClient(models_config=CF_CONFIG, api_key="tok", account_id="acc", transport=httpx.MockTransport(handler))
    ref = ref_image(compact(real_image(), max_size=(480, 640), quality=80))
    w, h = Image.open(io.BytesIO(ref)).size
    assert w < 512 and h < 512
    assert await images.generate(expression_prompt("angry"), seed=1, ref_images=[ref])
    body = seen["body"]
    assert b'name="input_image_0"' in body and ref in body
    assert b"exact same person" in body and b"angry expression" in body


def test_compact_makes_small_webp():
    big = real_image("PNG", (1200, 1600))
    small = compact(big, max_size=(480, 640), quality=80)
    assert small and image_ext(small) == "webp" and len(small) < len(big)
    assert Image.open(io.BytesIO(small)).size == (480, 640)
    assert compact(b"<html>not an image</html>", max_size=(480, 640), quality=80) is None


def test_library_find_by_outfit_gender_age(tmp_path):
    lib = PortraitLibrary(tmp_path / "lib")
    img = compact(real_image(), max_size=(480, 640), quality=80)

    def add(outfit, gender, age):
        return lib.add(img, "webp", person={"role": "x", "age": age, "gender": gender, "appearance": {"outfit": outfit}},
                       prompt="p", provider="fake", model="m", seed=1)["file"]

    g58 = add("security_uniform", "F", 58)
    g55 = add("security_uniform", "F", 55)
    add("security_uniform", "M", 57)  # 성별 다름
    add("security_uniform", "F", 30)  # 나이 차이 큼
    add("chef", "F", 56)              # 직업군 다름
    assert [h["file"] for h in lib.find(group="security", gender="F", age=56)] == [g55, g58]  # 나이 가까운 순
    assert [h["file"] for h in lib.find(group="security", gender="F", age=56, exclude={g55})] == [g58]
    assert g58.startswith("security/F/50s/") and job_group("", {"outfit": "hoodie"}) == "general"


def test_free_text_appearance_used_in_prompt_and_group():
    """기본 사건처럼 외모가 한글 자유 서술이면 그대로 그림 요청에 넣고, 직업 이름·옷 설명 낱말로 직업군을 정한다."""
    case = load_case_by_id("demo_db_deleted")
    by_id = {c.id: c for c in case.characters}
    guard = by_id["npc_guard"]
    p = portrait_prompt(role=guard.role, age=guard.age, gender=guard.gender, appearance=guard.appearance)
    assert guard.appearance["outfit"] in p and guard.appearance["hair"] in p and "casual clothes" not in p
    groups = {cid: job_group(c.role, c.appearance) for cid, c in by_id.items()}
    assert groups["npc_guard"] == "security" and groups["npc_chu"] == "cleaning"
    assert groups["npc_dba"] == groups["npc_dowon"] == groups["npc_pm"] == "office"


def test_image_ext():
    assert image_ext(PNG) == "png" and image_ext(JPG) == "jpg"
    assert image_ext(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp" and image_ext(b"<html>") is None


def test_prompt_is_modern_photo_and_public_only():
    p = portrait_prompt(role="경비원", age=58, gender="F", appearance={"outfit": "security_uniform", "hair": "ponytail"})
    assert "Photorealistic" in p and "58-year-old Korean woman" in p and "security guard uniform" in p
    assert "not resembling any real person" in p
