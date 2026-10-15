"""클리어 기록(결과 카드)의 인물 사진: 클리어하면 판 사진은 지우고, 결과 카드용 작은 사본만 남는다 (사용자 결정 2026-10-15)."""

import io

from fastapi.testclient import TestClient
from PIL import Image

import server.game.service as service_mod
from server.game.portrait_library import PortraitLibrary
from server.api.app import app
from server.game.service import GameService


def _photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (480, 640), (120, 90, 60)).save(buf, "WEBP")
    return buf.getvalue()


def test_clear_keeps_small_photo_copies_for_result_card(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    service_mod._SERVICE = svc
    try:
        game_id, view = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
        st = svc.store.load_live(game_id)
        key = svc._portrait_key(st)
        d = svc.portraits.root / key
        d.mkdir(parents=True)
        shown = [c for c in view.characters]
        for c in shown[:-1]:  # 마지막 사람은 사진이 없는 경우
            (d / f"{c.id}.webp").write_bytes(_photo())
        st.ending = "success"
        svc.store.save_live(st)

        hist = svc.clear(game_id)["history"]
        urls = [c.get("portrait_url") for c in hist["characters"]]
        assert sum(1 for u in urls if u) == len(shown) - 1 and urls.count(None) == 1
        assert not d.exists()  # 판 사진 폴더는 지웠다
        with TestClient(app) as client:
            r = client.get(next(u for u in urls if u))
            assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
            im = Image.open(io.BytesIO(r.content))
            assert im.size == (180, 240)  # 결과 카드용 작은 사본
            assert client.get(f"/api/history/{hist['id']}/photos/../../game.sqlite3").status_code == 404
            assert client.get("/api/history/h_xx/photos/0.webp").status_code == 404
        assert all(game_id not in (u or "") for u in urls)  # 주소에 판 id가 없다
    finally:
        service_mod._SERVICE = None


def test_missing_photo_is_filled_from_library(tmp_path):
    """그 판 사진이 없는 인물은 보관함의 비슷한 사람 사진으로 썸네일을 남긴다(같은 사진을 두 사람에게 쓰지 않음)."""
    svc = GameService(tmp_path, in_memory=True)
    svc.portraits.library = PortraitLibrary(tmp_path / "lib")
    game_id, view = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    st = svc.store.load_live(game_id)
    case = svc.cases["demo_db_deleted"]
    lone = next(c for c in case.characters if c.id == view.characters[0].id)
    person = svc._public_people([lone])[0]
    svc.portraits.library.add(_photo(), "webp", person=person, prompt="p", provider="x", model="m", seed=1)
    st.ending = "success"
    svc.store.save_live(st)

    chars = svc.clear(game_id)["history"]["characters"]
    filled = [c for c in chars if c.get("portrait_url")]
    assert len(filled) == 1  # 보관함 사진 1장 → 비슷한 한 사람만(같은 직업군·성별, 가까운 나이)
    who = next(c for c in case.characters if c.name == filled[0]["name"])
    assert who.gender == lone.gender and abs(who.age - lone.age) <= 12
    assert len(list((svc.history_photos).rglob("*.webp"))) == 1

