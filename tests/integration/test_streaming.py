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


async def test_discarded_preparation_stops_the_model_call(tmp_path):
    """다른 행동을 하면 미리 만들던 답은 버리고, 실시간 호출을 취소해 모델 생성도 멈춘다(사용량 절약)."""
    svc = GameService(tmp_path, in_memory=True)

    class Hang:
        can_stream = True

        def __init__(self, inner):
            self.inner, self.started, self.cancelled = inner, 0, 0

        def __getattr__(self, name):
            return getattr(self.inner, name)

        async def structured_stream(self, **_):
            self.started += 1
            try:
                await asyncio.Event().wait()  # 끝나지 않는 생성
            except asyncio.CancelledError:
                self.cancelled += 1
                raise

    svc.llm = Hang(svc.llm)
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    chip = ask_chip(svc, game_id)
    assert (await svc.prepare(game_id, chip.target_npc))["prepared"] >= 1
    await asyncio.sleep(0.05)
    assert svc.llm.started >= 1
    await asyncio.wait_for(_collect(svc.act(game_id, {"type": "investigate"})), timeout=5)
    await asyncio.sleep(0.05)
    assert svc.llm.cancelled == svc.llm.started  # 버린 준비분은 모두 취소됐다


class SlowRouter:
    """LLM 라우터는 gate가 열릴 때까지 늦게 답하고, 인물 답은 실시간으로 바로 쓰는 가짜 모델."""

    can_stream = True

    def __init__(self, inner, kind):
        self.inner, self.kind, self.gate = inner, kind, asyncio.Event()
        self.streaming = asyncio.Event()  # 인물 답을 쓰기 시작했다
        self.router_done = False
        self.stream_started_before_router = None
        self.stream_cancelled = False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def structured(self, **kw):
        if kw["role"] == "router":
            await self.gate.wait()
            self.router_done = True
            from server.schemas import RouterOutput
            return RouterOutput(kind=self.kind, via="llm"), False
        return await self.inner.structured(**kw)

    async def structured_stream(self, *, schema, on_partial, **_):
        if self.stream_started_before_router is None:
            self.stream_started_before_router = not self.router_done
        raw = ""
        self.streaming.set()
        try:
            for c in CHUNKS:
                raw += c
                await on_partial(raw)
                await asyncio.sleep(0.01)
            self.gate.set()  # 답을 다 쓴 뒤에야 라우터가 끝난다(라우터가 더 느린 경우)
            await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.stream_cancelled = True
            raise
        m = re.search(r"\{.*\}", raw, re.S)
        return schema.model_validate_json(m.group(0)), raw


AMBIGUOUS = "확실해요?"


async def test_ambiguous_question_answer_runs_alongside_router(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    assert svc.router.classify(AMBIGUOUS).via == "llm"  # 시맨틱으로는 애매한 문장
    svc.llm = SlowRouter(svc.llm, "investigate")
    game_id, view = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    npc = next(c for c in view.characters if c.location_id == view.player_location)
    evs = await asyncio.wait_for(_collect(svc.act(game_id, {"type": "ask", "npc_id": npc.id, "text": AMBIGUOUS})), 5)
    assert svc.llm.stream_started_before_router  # 라우터를 기다리지 않고 답을 시작했다
    text = "".join(e.get("delta", "") for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert text == "그날은 집에 있었어요. 혼자서요. 그게 다예요."
    assert svc.store.load_live(game_id).notebook.statements[-1].content == text


async def test_early_answer_is_dropped_when_router_says_small_talk(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    svc.llm = SlowRouter(svc.llm, "small_talk")

    async def open_soon():
        await svc.llm.streaming.wait()  # 답을 쓰기 시작한 뒤, 다 나오기 전에 라우터가 잡담으로 판정
        svc.llm.gate.set()

    game_id, view = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    npc = next(c for c in view.characters if c.location_id == view.player_location)
    opener = asyncio.ensure_future(open_soon())
    evs = await asyncio.wait_for(_collect(svc.act(game_id, {"type": "ask", "npc_id": npc.id, "text": AMBIGUOUS})), 5)
    await opener
    text = "".join(e.get("delta", "") for e in evs if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert svc.llm.stream_cancelled and "집에 있었어요" not in text  # 먼저 만들던 수사 답은 화면에 안 나간다
    assert text  # 잡담 답(가짜 LLM)이 나갔다
