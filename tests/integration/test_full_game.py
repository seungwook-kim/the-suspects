"""가짜 LLM으로 한 판을 처음부터 끝까지 (Phase 1 수용 기준).

- 사람이 한 판을 끝까지 플레이해 범인을 잡을 수 있다
- 클리어 후 사건 데이터 조회 0건, 클리어 이력만 남는다
- 클라이언트로 나가는 데이터에 비밀·내부 ID가 없다
"""

import json

import pytest

from server.game.masking import IdMasker
from server.game.service import GameService


@pytest.fixture
def svc(tmp_path):
    return GameService(tmp_path, in_memory=True)


async def collect(gen):
    return [e async for e in gen]


def texts(events):
    return "".join(e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")


def errors(events):
    return [e for e in events if e["type"] == "RUN_ERROR"]


async def investigate_all(svc, game_id, loc):
    await collect(svc.act(game_id, {"type": "move", "location_id": loc}))
    for _ in range(6):
        evs = await collect(svc.act(game_id, {"type": "investigate"}))
        if "더 찾을 만한 건 없어" in texts(evs) or errors(evs):
            break


async def end_day(svc, game_id):
    return await collect(svc.night(game_id))


async def test_full_game_success_and_clear(svc):
    game_id, view = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    case = svc.cases["demo_db_deleted"]
    assert view.phase == "briefing" and view.actions_total == svc.cfg.day_actions

    # 1일차: 로비를 조사하면 핵심 증거는 나중에 나온다
    first = await collect(svc.act(game_id, {"type": "investigate"}))
    state = svc.store.load_live(game_id)
    got = state.notebook.evidence_ids
    assert got and all(not next(e for e in case.evidence if e.id == g).is_key for g in got), "핵심 증거가 먼저 나오면 안 됨"
    assert state.phase == "day"

    # 칩으로 질문 (라우터 생략) → LLM 1회
    view = svc.view(game_id)
    if view.chips:
        n_before = len(svc.llm.tracer.records)
        evs = await collect(svc.act(game_id, {"type": "chip", "chip_id": view.chips[0].id}))
        assert not errors(evs)
        llm_calls = [r for r in svc.llm.tracer.records[n_before:] if r.model != "code"]
        assert len(llm_calls) <= 2  # NPC 1회 + (근거 없는 핵심 정보일 때만) 게임 마스터 1회

    # 말이 되는 순서로 플레이하는 봇: ① 장소를 여는 인물과 먼저 대화 ② 남은 증거가 있는 장소만 조사
    from server.game import content as C

    talk_unlockers = [l.unlock_condition.split(":", 1)[1] for l in case.locations
                      if l.unlock_condition and l.unlock_condition.startswith("talk:")]
    for _ in range(6):
        st = svc.store.load_live(game_id)
        if st.ending != "none":
            break
        for npc in talk_unlockers:
            st = svc.store.load_live(game_id)
            if npc in st.director_state.get("talked", []) or st.actions_left < 2:
                continue
            loc = st.npc_states[npc].location_id
            if loc in st.unlocked_locations:
                await collect(svc.act(game_id, {"type": "move", "location_id": loc}))
                await collect(svc.act(game_id, {"type": "ask", "npc_id": npc, "text": "어젯밤 일 좀 얘기해 주세요"}))
        for loc in list(svc.store.load_live(game_id).unlocked_locations):
            st = svc.store.load_live(game_id)
            if C.remaining_at(case, st, loc) == 0 or st.actions_left < 2:
                continue
            await collect(svc.act(game_id, {"type": "move", "location_id": loc}))
            while True:
                st = svc.store.load_live(game_id)
                if C.remaining_at(case, st, loc) == 0 or st.actions_left < 1:
                    break
                await collect(svc.act(game_id, {"type": "investigate"}))
        st = svc.store.load_live(game_id)
        if st.day >= st.max_days or all(C.remaining_at(case, st, l) == 0 for l in st.unlocked_locations) \
                and all(n in st.director_state.get("talked", []) for n in talk_unlockers):
            break
        await end_day(svc, game_id)

    state = svc.store.load_live(game_id)
    culprit = case.culprit_ids[0]
    owned = set(state.notebook.evidence_ids)
    masker = IdMasker(case, state.id_salt)
    # 최종 추리: 단계마다 맞는 증거를 고른다
    evs = await collect(svc.finale(game_id, {"type": "start", "accused_id": culprit}))
    assert not errors(evs)
    for stage in ("opportunity", "means", "motive"):
        ev = next((e for e in case.evidence if e.id in owned and stage in e.element_tags and culprit in e.linked_suspects), None)
        assert ev is not None, f"{stage} 단계 증거를 수사로 얻지 못함 (사건이 풀리지 않음)"
        evs = await collect(svc.finale(game_id, {"type": "present", "stage": stage, "evidence_id": masker.out("evidence", ev.id)}))
    state = svc.store.load_live(game_id)
    assert state.ending == "success"

    slots = svc.store.all_slot_ids(game_id)
    out = svc.clear(game_id)
    assert out["history"]["success"] and out["card"]["emoji_line"].endswith("✅")
    assert out["history"]["culprit"]["name"] == next(c.name for c in case.characters if c.id == culprit)
    for s in slots:
        assert svc.rag.count_slot(s) == 0  # 기억·청크·기록·관계 그래프 모두 삭제
    assert svc.store.count_case_rows(game_id) == 0
    assert len(svc.history()) == 1


async def test_client_payloads_have_no_secrets(svc):
    game_id, _ = svc.new_game("demo_db_deleted")
    case = svc.cases["demo_db_deleted"]
    payload = []
    payload.append(svc.view(game_id).model_dump_json())
    payload += [json.dumps(e, ensure_ascii=False) for e in await collect(svc.act(game_id, {"type": "investigate"}))]
    v = svc.view(game_id)
    npc_here = next((c.id for c in v.characters if c.location_id == v.player_location), None)
    if npc_here:
        payload += [json.dumps(e, ensure_ascii=False) for e in
                    await collect(svc.act(game_id, {"type": "ask", "npc_id": npc_here, "text": "어젯밤 11시쯤 어디 계셨어요?"}))]
    blob = "\n".join(payload)
    for ch in case.characters:
        for secret in ch.secrets:
            assert secret not in blob
    for lie in case.lie_ledger:
        assert lie.id not in blob and lie.truth not in blob
    assert case.trick not in blob
    for e in case.evidence:
        assert f'"{e.id}"' not in blob  # 내부 증거 ID 그대로 나가면 안 됨


async def test_sources_never_expose_npc_memory(svc):
    game_id, _ = svc.new_game("demo_db_deleted")
    case = svc.cases["demo_db_deleted"]
    culprit = case.culprit_ids[0]
    st = svc.store.load_live(game_id)
    await collect(svc.act(game_id, {"type": "move", "location_id": st.npc_states[culprit].location_id}))
    await collect(svc.act(game_id, {"type": "ask", "npc_id": culprit, "text": "어젯밤 사건 시각쯤 어디 계셨어요?"}))
    st = svc.store.load_live(game_id)
    stmt = st.notebook.statements[-1]
    blob = json.dumps(svc.sources(game_id, stmt.id), ensure_ascii=False)
    for m in case.initial_memories:
        if m.owner == culprit:
            assert m.content not in blob  # 범인의 진짜 기억 원문이 출처로 새면 안 됨


def test_player_search_only_returns_owned_evidence(svc):
    """플레이어 시점 검색은 수첩에 있는 증거 청크만 (ADR-0006)."""
    game_id, _ = svc.new_game("demo_db_deleted")
    case = svc.cases["demo_db_deleted"]
    ev = next(e for e in case.evidence if e.is_key and "player" in e.visibility)
    st = svc.store.load_live(game_id)

    def found(state):
        hits = svc._player_search(case, state, ev.content, k=10)
        return any(h.meta.get("evidence_id") == ev.id or h.id == f"ev:{ev.id}" for h in hits)

    assert not found(st)  # 아직 못 찾은 증거는 검색에도 안 나온다
    st.notebook.evidence_ids.append(ev.id)
    assert found(st)


async def test_cannot_present_unowned_or_forged(svc):
    game_id, _ = svc.new_game("demo_db_deleted")
    case = svc.cases["demo_db_deleted"]
    st = svc.store.load_live(game_id)
    npc = next(n for n, s in st.npc_states.items() if s.location_id == st.player_location)
    masker = IdMasker(case, st.id_salt)
    key = next(e.id for e in case.evidence if e.is_key)
    evs = await collect(svc.act(game_id, {"type": "present", "npc_id": npc, "evidence_id": masker.out("evidence", key)}))
    assert errors(evs)  # 아직 없는 증거
    evs = await collect(svc.act(game_id, {"type": "present", "npc_id": npc, "evidence_id": key}))
    assert errors(evs)  # 내부 ID를 그대로 보내는 위조


async def test_save_and_load_bundle(svc):
    game_id, _ = svc.new_game("demo_db_deleted")
    await collect(svc.act(game_id, {"type": "investigate"}))
    saved = svc.save(game_id, "테스트")
    before = svc.store.load_live(game_id).notebook.evidence_ids[:]
    await collect(svc.act(game_id, {"type": "investigate"}))
    assert len(svc.store.load_live(game_id).notebook.evidence_ids) > len(before)
    view = svc.load(game_id, saved["slot_id"])
    assert len(view.notebook.evidence_ids) == len(before)
    live = svc.store.load_live(game_id)
    assert svc.rag.count_slot(live.slot_id) > 0  # 기억도 같은 묶음으로 복원


async def test_move_costs_action_only_on_first_visit(svc):
    """처음 가는 장소만 행동 1(시간도 흐름), 가 본 장소로 다시 가면 행동·시간이 그대로다."""
    game_id, view = svc.new_game("demo_db_deleted", {"difficulty": "easy"})
    start = view.player_location
    assert view.visited_locations == [start]
    st = svc.store.load_live(game_id)
    nxt = next(l.id for l in svc.cases["demo_db_deleted"].locations if l.id in st.unlocked_locations and l.id != start)

    await collect(svc.act(game_id, {"type": "move", "location_id": nxt}))
    s1 = svc.store.load_live(game_id)
    assert s1.actions_left == st.actions_left - 1 and s1.clock > st.clock
    assert set(s1.visited_locations) == {start, nxt}

    evs = await collect(svc.act(game_id, {"type": "move", "location_id": start}))
    s2 = svc.store.load_live(game_id)
    assert not errors(evs)
    assert s2.player_location == start
    assert (s2.actions_left, s2.clock) == (s1.actions_left, s1.clock)

    # 행동을 다 써도 가 본 곳으로는 갈 수 있다
    svc.store.save_live(s2.model_copy(update={"actions_left": 0}))
    evs = await collect(svc.act(game_id, {"type": "move", "location_id": nxt}))
    assert not errors(evs) and svc.store.load_live(game_id).player_location == nxt
