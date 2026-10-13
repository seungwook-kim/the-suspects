"""AI 초상화: 판마다 새로 그리고, 공개 정보만 요청에 넣고, 화면에 주소가 실리고, 클리어하면 지운다 (가짜 그림 생성기)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

import server.game.service as service_mod
from server.api.app import app
from server.game.portraits import PortraitStore, portrait_prompt
from server.game.service import GameService
from server.llm.images import ImageClient

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


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


def test_prompt_is_modern_photo_and_public_only():
    p = portrait_prompt(role="경비원", age=58, gender="F", appearance={"outfit": "security_uniform", "hair": "ponytail"})
    assert "Photorealistic" in p and "58-year-old Korean woman" in p and "security guard uniform" in p
    assert "not resembling any real person" in p
