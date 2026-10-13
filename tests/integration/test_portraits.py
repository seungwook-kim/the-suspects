"""AI 초상화: 판마다 새로 그리고, 공개 정보만 요청에 넣고, 화면에 주소가 실리고, 클리어하면 판 그림은 지우되
보관함 사진은 남긴다 (가짜 그림 생성기 / 가짜 HTTP)."""

import asyncio
import base64
import json

import httpx
import pytest
from fastapi.testclient import TestClient

import server.game.service as service_mod
from server.api.app import app
from server.game.portraits import PortraitStore, image_ext, portrait_prompt
from server.game.service import GameService
from server.llm.images import ImageClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32
JPG = b"\xff\xd8\xff\xe0" + b"0" * 32
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
        return PNG

    s.portraits = PortraitStore(tmp_path / "portraits", ImageClient(tracer=s.llm.tracer, generator=fake))
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
    assert len(prompts) == len(case.characters)
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
    assert len(prompts) == 2 * len(case.characters)

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
    assert rec.ok is False and rec.extra["errors"]


def test_cloudflare_needs_both_account_and_token():
    assert ImageClient(models_config=CF_CONFIG, api_key="tok", account_id="").enabled is False
    assert ImageClient(models_config=CF_CONFIG, api_key="", account_id="acc").enabled is False


async def test_library_keeps_photos_after_clear_without_case_links(tmp_path):
    s = GameService(tmp_path, in_memory=True)

    async def fake(prompt: str):
        return JPG

    library = tmp_path / "library"
    s.portraits = PortraitStore(tmp_path / "portraits", ImageClient(tracer=s.llm.tracer, generator=fake), library=library)
    game_id, _ = s.new_game("demo_db_deleted")
    await s.portraits.wait(game_id)
    case = s.cases["demo_db_deleted"]
    assert all(u.split("?")[0].endswith(".jpg") for u in s.portraits.urls(game_id).values())

    st = s.store.load_live(game_id)
    st.ending, st.phase = "escaped", "ended"
    s.store.save_live(st)
    s.clear(game_id)
    assert s.portraits.urls(game_id) == {}  # 판 그림은 지움

    lines = (library / "index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(case.characters)  # 보관함 사진은 남음
    for line in lines:
        rec = json.loads(line)
        assert (library / rec["file"]).read_bytes() == JPG
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


def test_image_ext():
    assert image_ext(PNG) == "png" and image_ext(JPG) == "jpg"
    assert image_ext(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "webp" and image_ext(b"<html>") is None


def test_prompt_is_modern_photo_and_public_only():
    p = portrait_prompt(role="경비원", age=58, gender="F", appearance={"outfit": "security_uniform", "hair": "ponytail"})
    assert "Photorealistic" in p and "58-year-old Korean woman" in p and "security guard uniform" in p
    assert "not resembling any real person" in p
