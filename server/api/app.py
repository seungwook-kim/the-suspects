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
from fastapi.responses import StreamingResponse
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
def new_game(req: NewGame) -> dict:
    try:
        game_id, view = _service().new_game(req.theme_id, req.options)
    except KeyError:
        raise HTTPException(404, "없는 주제입니다")
    return {"game_id": game_id, "view": view.model_dump(mode="json")}


@app.get("/api/games")
def list_games() -> list[dict]:
    return _service().list_games()


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


@app.post("/api/games/{game_id}/actions")
def act(game_id: str, action: dict) -> StreamingResponse:
    return _sse_response(_service().act(game_id, action))


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
