"""추천 질문 답 미리 만들기 (PRD §14.1 추측 생성, 부록 F.15) — 가짜 LLM으로."""

import asyncio

import pytest

from server.game.service import GameService
from server.rules.speculative import SpeculativeStats


@pytest.fixture
def svc(tmp_path):
    return GameService(tmp_path, in_memory=True)


async def collect(gen):
    return [e async for e in gen]


def texts(events):
    return "".join(e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")


async def settle(svc, game_id):
    show = svc.spec._shows.get(game_id)
    if show:
        await asyncio.gather(*show.tasks.values(), return_exceptions=True)


def ask_chip(svc, game_id):
    view = svc.view(game_id)
    return next(c for c in view.chips if c.kind == "ask")


def answer_calls(records):
    """플레이어를 기다리게 한 인물 답 호출 (미리 만든 호출과 꺼내 쓴 기록 제외)."""
    return [r for r in records if r.node == "npc" and r.model != "code"]


async def test_prepared_chip_answer_is_used_without_new_answer_call(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    chip = ask_chip(svc, game_id)
    assert (await svc.prepare(game_id, chip.target_npc))["prepared"] >= 1
    await settle(svc, game_id)
    spec_calls = [r for r in svc.llm.tracer.records if (r.node or "").endswith(":speculative")]
    assert spec_calls, "미리 만든 호출은 꼬리표를 달고 기록된다"

    n = len(svc.llm.tracer.records)
    evs = await collect(svc.act(game_id, {"type": "chip", "chip_id": chip.id}))
    new = svc.llm.tracer.records[n:]
    assert not [e for e in evs if e["type"] == "RUN_ERROR"]
    assert not answer_calls(new), "미리 만든 답이 있으면 인물 답을 다시 부르지 않는다"
    assert any(r.model == "prepared" and r.node == "npc_prepared" for r in new)
    assert texts(evs).strip()

    state = svc.store.load_live(game_id)
    assert state.question_count == 1 and len(state.notebook.statements) == 1  # 뒤처리는 실제로 누를 때
    stats = SpeculativeStats.model_validate(state.director_state["speculative"])
    assert stats.shows[-1][1] == 1  # 이번 준비분에서 1개 썼다


async def test_prepare_does_not_change_game_state(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    before = svc.store.load_live(game_id).model_dump_json()
    mems = len(svc.rag.load_memories(svc.cases["demo_db_deleted"].case_id, svc.store.load_live(game_id).slot_id))
    chip = ask_chip(svc, game_id)
    await svc.prepare(game_id, chip.target_npc)
    await settle(svc, game_id)
    after = svc.store.load_live(game_id)
    assert after.model_dump_json() == before
    assert len(svc.rag.load_memories(svc.cases["demo_db_deleted"].case_id, after.slot_id)) == mems  # 한 말 기억 없음


async def test_other_action_discards_prepared_answers_and_records_miss(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    chip = ask_chip(svc, game_id)
    started = (await svc.prepare(game_id, chip.target_npc))["prepared"]
    await settle(svc, game_id)
    await collect(svc.act(game_id, {"type": "investigate"}))  # 칩을 누르지 않고 다른 행동
    stats = SpeculativeStats.model_validate(svc.store.load_live(game_id).director_state["speculative"])
    assert stats.shows == [(started, 0)]

    n = len(svc.llm.tracer.records)
    chip2 = ask_chip(svc, game_id)  # 새 상태의 칩 → 미리 만든 답 없음 → 평소처럼 만든다
    await collect(svc.act(game_id, {"type": "chip", "chip_id": chip2.id}))
    assert answer_calls(svc.llm.tracer.records[n:])


async def test_prepare_same_state_once_and_skips_when_not_possible(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    chip = ask_chip(svc, game_id)
    assert (await svc.prepare(game_id, chip.target_npc))["prepared"] >= 1
    assert (await svc.prepare(game_id, chip.target_npc))["prepared"] == 0  # 같은 상태·같은 인물은 한 번만
    await settle(svc, game_id)

    case = svc.cases["demo_db_deleted"]
    state = svc.store.load_live(game_id)
    away = next(c.id for c in case.characters if c.id in state.npc_states
                and state.npc_states[c.id].location_id != state.player_location)
    assert (await svc.prepare(game_id, away))["prepared"] == 0  # 여기 없는 사람

    state.director_state["speculative"] = SpeculativeStats(disabled=True).model_dump(mode="json")
    svc.store.save_live(state)
    svc.spec.forget(game_id)
    assert (await svc.prepare(game_id, chip.target_npc))["prepared"] == 0  # 적중률이 낮아 꺼진 판


async def test_load_forgets_prepared_answers(svc):
    game_id, _ = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    slot = svc.save(game_id, "a")["slot_id"]
    chip = ask_chip(svc, game_id)
    await svc.prepare(game_id, chip.target_npc)
    await settle(svc, game_id)
    svc.load(game_id, slot)
    assert svc.spec.active(game_id) is None
