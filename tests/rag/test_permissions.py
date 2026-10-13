"""가장 중요한 테스트: 권한 필터가 새지 않는다."""

import pytest

from server.rag.access import can_see, can_see_record
from server.rag.records import search_records
from server.schemas import MemoryDoc, RecordRow, Warrant
CASE_ID = "demo_db_deleted"
SLOT = "slot_test_1"

KW = dict(case_id=CASE_ID, slot_id=SLOT)
NPC_IDS = ["npc_dowon", "npc_dba", "npc_yoon", "npc_hwang", "npc_chu", "npc_guard", "npc_pm"]


def test_npc_never_sees_other_npc_memories(retriever, case):
    by_owner = {}
    for m in case.initial_memories:
        by_owner.setdefault(m.owner, set()).add(m.id)
    for npc in NPC_IDS:
        others = set().union(*(ids for o, ids in by_owner.items() if o not in (npc, "public")))
        for q in ["카드 서버실 23:05 운영 DB 삭제", "추성만 윤석진 카드 탕비실", "백업 실패 알림", "비밀 숨겼다 기억", "담배 자리 비움"]:
            hits = retriever.search(q, scope=f"npc:{npc}", k=50, **KW)
            leaked = {h.id for h in hits} & others
            assert not leaked, f"{npc}가 남의 기억을 봤다: {leaked}"
            for h in hits:
                if h.kind == "memory":
                    assert h.meta["owner"] in (npc, "public")


def test_culprit_secret_only_for_culprit(retriever):
    q = "svc_legacy_bk 콘솔 로그인 운영 DB 삭제 감사 로그 서비스를 멈춰"
    chu_ids = {h.id for h in retriever.search(q, scope="npc:npc_chu", k=50, **KW)}
    assert any(i.startswith("mem_chu_") for i in chu_ids)
    for npc in NPC_IDS:
        if npc != "npc_chu":
            ids = {h.id for h in retriever.search(q, scope=f"npc:{npc}", k=50, **KW)}
            assert not any(i.startswith("mem_chu_") for i in ids)
    player = {h.id for h in retriever.search(q, scope="player", k=50, kinds=("memory", "chunk", "record"), **KW)}
    assert not any(i.startswith("mem_") and not i.startswith("mem_pub") for i in player)


def test_player_never_sees_npc_memories(retriever, case):
    mem_ids = {m.id for m in case.initial_memories if m.owner != "public"}
    for q in ["카드", "서버실", "추성만", "삭제"]:
        hits = retriever.search(q, scope="player", k=100, **KW)
        assert not ({h.id for h in hits} & mem_ids)


def test_player_cannot_see_warrant_call_without_warrant(store, retriever, case, all_warrants):
    call_rows = [r for r in case.records if "warrant:call" in r.visibility]
    assert call_rows
    call_ids = {r.id for r in call_rows}
    # 기록 조회
    for r in call_rows:
        got = search_records(case, "call", 0, 3000, scope="player", warrants=[])
        assert got == []
        got_sql = search_records(store, "call", 0, 3000, scope="player", warrants=[], case_id=CASE_ID, slot_id=SLOT)
        assert got_sql == []
    # 검색 (record 종류 포함)
    hits = retriever.search("대리운전 통화 서교동 기지국", scope="player", k=100, kinds=("memory", "chunk", "record"), **KW)
    assert not ({h.id for h in hits} & call_ids)
    # 증거 청크(E14)도 영장 없이는 안 나온다
    hits = retriever.search("윤석진 통화 기록 대리운전", scope="player", k=100, **KW)
    assert "ev:E14" not in {h.id for h in hits}
    # 다른 시스템(bank) 영장으로는 열리지 않는다
    bank_only = [w for w in all_warrants if w.system == "bank"]
    assert search_records(case, "call", 0, 3000, scope="player", warrants=bank_only) == []


def test_player_sees_warrant_records_with_matching_warrant(store, retriever, case, all_warrants):
    got = search_records(case, "call", 0, 3000, person_id="npc_yoon", scope="player", warrants=all_warrants)
    assert {r.id for r in got} and all(r.person_id == "npc_yoon" for r in got)
    got_sql = search_records(store, "call", 0, 3000, person_id="npc_yoon", scope="player", warrants=all_warrants,
                             case_id=CASE_ID, slot_id=SLOT)
    assert [r.id for r in got_sql] == [r.id for r in got]
    hits = retriever.search("윤석진 통화 기록 대리운전", scope="player", warrants=all_warrants, k=10, **KW)
    assert "ev:E14" in {h.id for h in hits}


def test_warrant_target_and_time_window_enforced(case):
    wrong_target = [Warrant(system="call", target_id="npc_dba", from_time=0, to_time=3000)]
    assert search_records(case, "call", 0, 3000, person_id="npc_yoon", scope="player", warrants=wrong_target) == []
    too_early = [Warrant(system="call", target_id="npc_yoon", from_time=0, to_time=600)]
    assert search_records(case, "call", 0, 3000, person_id="npc_yoon", scope="player", warrants=too_early) == []
    window = [Warrant(system="call", target_id="npc_yoon", from_time=1380, to_time=1390)]
    got = search_records(case, "call", 0, 3000, person_id="npc_yoon", scope="player", warrants=window)
    assert [r.time for r in got] == [1385]  # 23:05 한 건만


def test_npc_cannot_use_warrant_visibility(case):
    w = [Warrant(system="call", target_id="npc_yoon", from_time=0, to_time=3000)]
    for r in case.records:
        if r.visibility == ["warrant:call"]:
            assert not can_see_record(r, "npc:npc_chu", w)


def test_empty_visibility_is_invisible_everywhere(store, retriever):
    """기억 오염 시 원본은 id에 '#original', visibility=[]로 보존된다. 어떤 범위로도 나오면 안 된다."""
    secret = "봉황색 은밀한 원본기억 토큰 zzqx"
    store.add_memory(MemoryDoc(id="mem_chu_01#original", case_id=CASE_ID, slot_id=SLOT, owner="npc_chu", visibility=[],
                               doc_type="observation", content=secret, game_time=1000))
    store.add_records(CASE_ID, SLOT, [RecordRow(id="rec_hidden", system="cctv", time=1000, detail=secret, visibility=[])])
    for scope in ["player"] + [f"npc:{n}" for n in NPC_IDS]:
        hits = retriever.search(secret, scope=scope, k=100, kinds=("memory", "chunk", "record"), **KW)
        assert not any("zzqx" in h.content for h in hits), scope
        assert search_records(store, "cctv", 0, 3000, scope=scope, case_id=CASE_ID, slot_id=SLOT) is not None
        assert all(r.id != "rec_hidden" for r in
                   search_records(store, "cctv", 0, 3000, scope=scope, case_id=CASE_ID, slot_id=SLOT))
    assert not can_see([], "player") and not can_see([], "npc:npc_chu")


def test_invalid_scope_rejected(retriever):
    with pytest.raises(ValueError):
        retriever.search("카드", scope="gm", **KW)
    with pytest.raises(ValueError):
        retriever.search("카드", scope="npc:", **KW)


def test_allowed_ids_only_narrows(retriever):
    hits = retriever.search("서버실 출입카드 기록", scope="player", allowed_ids={"ev:E3"}, k=10, **KW)
    assert {h.id for h in hits} <= {"ev:E3"}
    # 허용 목록에 있어도 권한이 없으면 안 나온다
    hits = retriever.search("윤석진 통화 기록", scope="player", allowed_ids={"ev:E14"}, k=10, **KW)
    assert hits == []


def test_other_slot_data_invisible(store, retriever, case):
    from server.rag.indexer import index_case
    index_case(store, case, "slot_other")
    store.add_memory(MemoryDoc(id="mem_pub_zz", case_id=CASE_ID, slot_id="slot_other", owner="public", visibility=["public"],
                               doc_type="observation", content="다른슬롯전용 토큰 qqwwee", game_time=1))
    hits = retriever.search("다른슬롯전용 qqwwee", scope="player", k=50, **KW)
    assert not any("qqwwee" in h.content for h in hits)
