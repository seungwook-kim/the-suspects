"""인물 답을 첫 문장부터 보여 주기 — 행동이 끝나기 전에 대사 조각이 화면으로 나가는지 (가짜 실시간 모델로)."""

import asyncio
import re

import pytest

from server.game.service import GameService


class GatedStream:
    """첫 문장을 낸 뒤 gate가 열릴 때까지 기다리는 가짜 실시간 모델. 나머지는 원래(가짜 LLM) 연결로."""

    can_stream = True

    def __init__(self, inner, chunks):
        self.inner, self.chunks, self.gate, self.calls = inner, chunks, asyncio.Event(), 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def structured_stream(self, *, schema, on_partial, **_):
        self.calls += 1
        raw = ""
        for i, c in enumerate(self.chunks):
            raw += c
            if (await on_partial(raw)) is False:
                return None, raw
            if i == 1:
                await self.gate.wait()  # 첫 문장이 나간 뒤 멈춤
        m = re.search(r"\{.*\}", raw, re.S)
        return schema.model_validate_json(m.group(0)), raw


CHUNKS = ['{"emotion": "nervous", "text": "그날은 집에 있었어요.', " 혼자서요.", ' 그게 다예요."', ', "used_ids": []}']


@pytest.fixture
def svc(tmp_path):
    s = GameService(tmp_path, in_memory=True)
    s.llm = GatedStream(s.llm, CHUNKS)
    return s


def ask_chip(svc, game_id):
    return next(c for c in svc.view(game_id).chips if c.kind == "ask")


async def test_first_sentence_reaches_client_before_action_finishes(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    chip = ask_chip(svc, game_id)
    gen = svc.act(game_id, {"type": "chip", "chip_id": chip.id})
    seen = []

    async def until_first_text():
        async for ev in gen:
            seen.append(ev)
            if ev["type"] == "TEXT_MESSAGE_CONTENT":
                return ev

    first = await asyncio.wait_for(until_first_text(), timeout=5)  # 행동이 끝나기 전에 와야 한다(gate가 닫혀 있음)
    assert first["delta"] == "그날은 집에 있었어요."
    assert any(e.get("name") == "emotion" and e["value"]["emotion"] == "nervous" for e in seen)  # 표정이 먼저
    assert not any(e["type"] == "RUN_FINISHED" for e in seen)

    svc.llm.gate.set()
    rest = [e async for e in gen]
    text = first["delta"] + "".join(e["delta"] for e in rest if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert text == "그날은 집에 있었어요. 혼자서요. 그게 다예요."
    ends = [e for e in rest if e["type"] == "TEXT_MESSAGE_END" and e["messageId"] == first["messageId"]]
    assert len(ends) == 1 and rest[-1]["type"] == "RUN_FINISHED"
    state = svc.store.load_live(game_id)
    assert state.notebook.statements[-1].content == text  # 수첩에는 화면에 나간 글 그대로


async def test_streaming_can_be_turned_off_by_config(svc):
    svc.cfg = svc.cfg.model_copy(update={"speed": svc.cfg.speed.model_copy(update={"stream_npc_answers": False})})
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    chip = ask_chip(svc, game_id)
    evs = [e async for e in svc.act(game_id, {"type": "chip", "chip_id": chip.id})]
    assert svc.llm.calls == 0 and evs[-1]["type"] == "RUN_FINISHED"  # 평소 경로(가짜 LLM)로 답했다


async def test_present_evidence_reaction_streams_too(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    await asyncio.wait_for(_collect(svc.act(game_id, {"type": "investigate"})), timeout=5)
    view = svc.view(game_id)
    here = next(c for c in view.characters if c.location_id == view.player_location)
    svc.llm.gate.set()
    evs = await asyncio.wait_for(_collect(svc.act(game_id, {"type": "present", "npc_id": here.id,
                                                            "evidence_id": view.evidence[0].id})), timeout=5)
    assert svc.llm.calls == 1
    assert "그날은 집에 있었어요." in "".join(e.get("delta", "") for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT")


async def _collect(gen):
    return [e async for e in gen]
