"""HTTP API 스모크 테스트 (엔드포인트 응답, SSE 이벤트 순서, 상태 변화분) — 의존성 표의 스모크 3종."""

import json

import pytest
from fastapi.testclient import TestClient

import server.game.service as service_mod
from server.api.app import app
from server.game.service import GameService


@pytest.fixture
def client(tmp_path):
    service_mod._SERVICE = GameService(tmp_path, in_memory=True)
    with TestClient(app) as c:
        yield c
    service_mod._SERVICE = None


def sse_events(resp) -> list[dict]:
    return [json.loads(line[6:]) for line in resp.text.splitlines() if line.startswith("data: ")]


def test_endpoints_and_stream(client):
    assert client.get("/api/health").json()["ok"] is True
    themes = client.get("/api/themes").json()
    assert themes and themes[0]["id"] == "demo_db_deleted"

    r = client.post("/api/games", json={"theme_id": "demo_db_deleted", "options": {"difficulty": "normal"}})
    assert r.status_code == 200
    game_id = r.json()["game_id"]
    view = r.json()["view"]
    assert view["actions_total"] == 12 and view["max_days"] >= 2

    resp = client.post(f"/api/games/{game_id}/actions", json={"type": "investigate"})
    assert resp.headers["content-type"].startswith("text/event-stream")
    evs = sse_events(resp)
    types = [e["type"] for e in evs]
    assert types[0] == "RUN_STARTED" and types[-1] == "RUN_FINISHED"
    assert "STATE_DELTA" in types  # 바뀐 부분만 전송
    delta = next(e for e in evs if e["type"] == "STATE_DELTA")["delta"]
    assert any(op["path"] == "/actions_left" for op in delta)

    assert client.get("/api/games").json()[0]["game_id"] == game_id
    assert client.post(f"/api/games/{game_id}/save", json={"slot_name": "a"}).status_code == 200
    assert len(client.get(f"/api/games/{game_id}/saves").json()) == 1

    night = sse_events(client.post(f"/api/games/{game_id}/night"))
    assert any(e.get("name") == "night_progress" for e in night)
    snap = next(e for e in night if e["type"] == "STATE_SNAPSHOT")["snapshot"]
    assert snap["day"] == 2 and snap["actions_left"] == 12


def test_bad_action_does_not_break_stream(client):
    game_id = client.post("/api/games", json={"theme_id": "demo_db_deleted"}).json()["game_id"]
    evs = sse_events(client.post(f"/api/games/{game_id}/actions", json={"type": "move", "location_id": "loc_nowhere"}))
    assert any(e["type"] == "RUN_ERROR" for e in evs) and evs[-1]["type"] == "RUN_FINISHED"
    evs = sse_events(client.post(f"/api/games/{game_id}/actions", json={"type": "teleport"}))
    assert evs[-1]["type"] == "RUN_FINISHED"
    assert client.get("/api/games/g_missing").status_code == 404
