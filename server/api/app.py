"""HTTP API (docs/api-contract.md).

- 클라이언트로는 PlayerView와 AG-UI 형식 SSE 이벤트만 나간다.
- 행동 처리 중 오류가 나도 스트림을 끊지 않고 RUN_ERROR 이벤트로 알린다(화면이 멈추지 않게).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from server.game.events import EventBuilder, sse
from server.storage.db import StorageError

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")


class NewGame(BaseModel):
    theme_id: str = "demo_db_deleted"
    options: dict | None = None


class SaveReq(BaseModel):
    slot_name: str | None = None


class LoadReq(BaseModel):
    slot_id: str


class PrepareReq(BaseModel):
    npc_id: str


def _service():
    from server.game.service import get_service

    return get_service()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _service()  # 시작할 때 사건·라우터 로드
    yield


app = FastAPI(title="The Suspects", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("THE_SUSPECTS_CORS", "http://localhost:5173").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _stream(gen: AsyncIterator[dict]) -> AsyncIterator[str]:
    eb = EventBuilder()
    try:
        async for ev in gen:
            yield sse(ev)
    except StorageError as e:
        yield sse(eb.run_error(str(e), code="not_found"))
    except Exception as e:  # 화면을 멈추지 않게 오류 이벤트로
        yield sse(eb.run_error(f"처리 중 문제가 생겼어요: {type(e).__name__}", code="internal"))
        if os.getenv("THE_SUSPECTS_MODE", "dev") == "dev":
            raise


def _sse_response(gen: AsyncIterator[dict]) -> StreamingResponse:
    return StreamingResponse(_stream(gen), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/health")
def health() -> dict:
    s = _service()
    return {"ok": True, "fake_llm": s.llm.fake_mode}


@app.get("/api/themes")
def themes() -> list[dict]:
    return _service().themes()


@app.post("/api/games")
async def new_game(req: NewGame) -> dict:
    # async: 초상화 그리기를 같은 이벤트 루프의 백그라운드 작업으로 시작하기 위해
    try:
        game_id, view = _service().new_game(req.theme_id, req.options)
    except KeyError:
        raise HTTPException(404, "없는 주제입니다")
    return {"game_id": game_id, "view": view.model_dump(mode="json")}


@app.get("/api/portraits/{key}/{filename}")
def portrait(key: str, filename: str) -> FileResponse:
    path = _service().portraits.path(key, filename)
    if path is None:
        raise HTTPException(404, "초상화가 없습니다")
    media = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}[path.suffix[1:]]
    return FileResponse(path, media_type=media, headers={"Cache-Control": "private, max-age=86400"})


@app.get("/api/history/{hid}/photos/{filename}")
def history_photo(hid: str, filename: str) -> FileResponse:
    """클리어 기록(결과 카드)의 인물 사진 사본."""
    path = _service().history_photo(hid, filename)
    if path is None:
        raise HTTPException(404, "사진이 없습니다")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "private, max-age=604800"})


@app.get("/api/games")
def list_games() -> list[dict]:
    return _service().list_games()


class NewCase(BaseModel):
    theme_text: str
    options: dict | None = None


@app.post("/api/cases", status_code=202)
async def create_case(req: NewCase) -> dict:
    """자유 주제 사건 생성 시작 (백그라운드, 1~3분). 진행 상황은 GET /api/cases/{job_id}."""
    try:
        return {"job_id": _service().create_case_job(req.theme_text, req.options)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/cases/{job_id}")
def case_job(job_id: str) -> dict:
    try:
        return _service().case_job(job_id)
    except KeyError:
        raise HTTPException(404, "없는 생성 작업입니다")


@app.get("/api/games/{game_id}/saves")
def list_saves(game_id: str) -> list[dict]:
    try:
        return _service().list_saves(game_id)
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.get("/api/games/{game_id}")
def get_view(game_id: str) -> dict:
    try:
        return _service().view(game_id).model_dump(mode="json")
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.get("/api/games/{game_id}/portraits")
async def portrait_status(game_id: str) -> dict:
    """그리는 중인 초상화 확인용: {pending, urls}. 화면은 pending 동안 몇 초마다 묻고 주소를 채운다.
    (async: 빠진 그림을 다시 그릴 때 이벤트 루프가 있어야 한다)"""
    try:
        return _service().portrait_status(game_id)
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.post("/api/games/{game_id}/actions")
def act(game_id: str, action: dict) -> StreamingResponse:
    return _sse_response(_service().act(game_id, action))


@app.post("/api/games/{game_id}/prepare")
async def prepare(game_id: str, req: PrepareReq) -> dict:
    """심문 중인 인물의 추천 질문 답을 미리 만들기 시작한다(PRD §14.1 추측 생성). 기다리지 않고 바로 돌아온다.
    (async: 미리 만들기를 같은 이벤트 루프의 백그라운드 작업으로 돌리기 위해)"""
    try:
        return await _service().prepare(game_id, req.npc_id)
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.post("/api/games/{game_id}/night")
def night(game_id: str) -> StreamingResponse:
    return _sse_response(_service().night(game_id))


@app.post("/api/games/{game_id}/finale")
def finale(game_id: str, step: dict) -> StreamingResponse:
    return _sse_response(_service().finale(game_id, step))


@app.post("/api/games/{game_id}/save")
def save(game_id: str, req: SaveReq) -> dict:
    try:
        return _service().save(game_id, req.slot_name)
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.post("/api/games/{game_id}/load")
def load(game_id: str, req: LoadReq) -> dict:
    try:
        return _service().load(game_id, req.slot_id).model_dump(mode="json")
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.get("/api/games/{game_id}/sources/{statement_id}")
def sources(game_id: str, statement_id: str) -> list[dict]:
    """수첩 진술의 출처 원문 (플레이어 권한 안의 것만)."""
    try:
        return _service().sources(game_id, statement_id)
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.post("/api/games/{game_id}/clear")
def clear(game_id: str) -> dict:
    try:
        return _service().clear(game_id)
    except StorageError as e:
        raise HTTPException(404, str(e))


@app.get("/api/history")
def history() -> list[dict]:
    return [h.model_dump(mode="json") for h in _service().history()]
