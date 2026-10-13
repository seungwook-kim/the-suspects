import pytest

from server.rag.eval import EvalReport, evaluate_retriever, generate_gold, mrr, recall_at_k, records_tool_check
from server.rag.indexer import index_case
from server.rag.records import search_records
from server.rag.relations import RelationGraph
from server.rag.retriever import HybridRetriever
from server.rag.embedding import HashEmbedding
from server.rag.store import RagStore
from server.schemas import RetrievalGold
CASE_ID = "demo_db_deleted"
SLOT = "slot_test_1"


def test_records_time_person_location_filters(case):
    rows = search_records(case, "access_log", 22 * 60, 24 * 60, scope="player")
    assert {r.id for r in rows} and all(22 * 60 <= r.time <= 24 * 60 for r in rows)
    assert any("YSJ-0412" in r.detail for r in rows)
    only = search_records(case, "access_log", 0, 3000, person_id="npc_hwang", scope="player")
    assert only and all(r.person_id == "npc_hwang" for r in only)
    srv = search_records(case, "server_log", 23 * 60, 23 * 60 + 45, location_id="loc_serverroom", scope="player")
    assert [r.time for r in srv] == sorted(r.time for r in srv)
    assert any("30분 공백" in r.detail for r in srv)


def test_records_param_validation(case):
    with pytest.raises(ValueError):
        search_records(case, "x'; DROP TABLE records;--", 0, 10)
    with pytest.raises(ValueError):
        search_records(case, "cctv", 10, 0)


def test_records_sql_injection_in_params(store):
    out = search_records(store, "cctv", 0, 3000, person_id="x' OR '1'='1", scope="player", case_id=CASE_ID, slot_id=SLOT)
    assert out == []
    assert store.load_all_records(CASE_ID, SLOT)  # 테이블은 멀쩡하다


def test_records_store_matches_memory_source(store, case, all_warrants):
    for system in ("access_log", "cctv", "server_log", "messenger", "call", "bank"):
        a = search_records(case, system, 0, 3000, scope="player", warrants=all_warrants, limit=500)
        b = search_records(store, system, 0, 3000, scope="player", warrants=all_warrants, case_id=CASE_ID, slot_id=SLOT, limit=500)
        assert [r.id for r in a] == [r.id for r in b]


def test_npc_records_scope(case):
    mine = search_records(case, "messenger", 0, 3000, scope="npc:npc_dba")
    assert mine and all(r.person_id == "npc_dba" for r in mine)


def test_relation_graph_and_knows_false(store, case):
    g = RelationGraph(store)
    g.seed_from_case(case, SLOT)
    claim = next(c for c in case.bluff_claims if c.id == "bc_backup_restored")
    assert g.knows_false("npc_dba", claim, case_id=CASE_ID, slot_id=SLOT)
    assert not g.knows_false("npc_chu", claim, case_id=CASE_ID, slot_id=SLOT)
    assert g.knows_false("npc_dba", "bc_backup_restored", case_id=CASE_ID, slot_id=SLOT)  # 그래프 경유
    # 사실이 참인 주장은 즉시 실패 대상이 아니다
    g.record_fact(CASE_ID, SLOT, "f_true", "진짜", is_true=True)
    g.record_knowledge(CASE_ID, SLOT, "f_true", "npc_dba", 10)
    assert not g.knows_false("npc_dba", "f_true", case_id=CASE_ID, slot_id=SLOT)


def test_relation_time_and_rumor_path(store):
    g = RelationGraph(store)
    g.record_fact(CASE_ID, SLOT, "f1", "윤석진이 카드를 빌려줬다")
    g.record_knowledge(CASE_ID, SLOT, "f1", "npc_guard", 100, from_who=None, via="direct")
    g.record_knowledge(CASE_ID, SLOT, "f1", "npc_dowon", 200, from_who="npc_guard", via="heard")
    g.record_knowledge(CASE_ID, SLOT, "f1", "npc_pm", 300, from_who="npc_dowon", via="rumor", distortion=1)
    assert [e.knower for e in g.who_knows(CASE_ID, SLOT, "f1")] == ["npc_guard", "npc_dowon", "npc_pm"]
    assert [e.knower for e in g.who_knows(CASE_ID, SLOT, "f1", at_time=250)] == ["npc_guard", "npc_dowon"]
    assert not g.knows(CASE_ID, SLOT, "npc_pm", "f1", at_time=299)
    assert [e.knower for e in g.trace_origin(CASE_ID, SLOT, "f1", "npc_pm")] == ["npc_pm", "npc_dowon", "npc_guard"]


def test_relations_copied_with_slot(store, case):
    g = RelationGraph(store)
    g.seed_from_case(case, SLOT)
    store.copy_slot(SLOT, "slot_copy")
    assert g.knows_false("npc_dba", "bc_backup_restored", case_id=CASE_ID, slot_id="slot_copy")


def test_metrics_basics():
    golds = [RetrievalGold(question="a", relevant_ids=["x"], asker_scope="player"),
             RetrievalGold(question="b", relevant_ids=["y"], asker_scope="player")]
    ranked = [["x", "z"], ["q", "w", "y"]]
    assert recall_at_k(ranked, golds, 1) == 0.5
    assert recall_at_k(ranked, golds, 3) == 1.0
    assert mrr(ranked, golds) == pytest.approx((1 + 1 / 3) / 2)


def test_gold_generation_and_eval(case, all_warrants):
    golds = generate_gold(case)
    assert len(golds) >= 50
    assert generate_gold(case) == golds  # 결정적
    assert all(g.relevant_ids and g.asker_scope for g in golds)
    store = RagStore(embedder=HashEmbedding(256))
    index_case(store, case, SLOT)
    report = evaluate_retriever(HybridRetriever(store), golds, case_id=CASE_ID, slot_id=SLOT, warrants=all_warrants, k=5)
    assert isinstance(report, EvalReport)
    assert report.n == len(golds) and 0 <= report.mrr <= 1
    assert report.recall_at_k >= 0.6, report.misses[:5]
    assert report.mrr >= 0.4
    print(f"\nRecall@5={report.recall_at_k:.3f} MRR={report.mrr:.3f} n={report.n} {report.by_scope}")


def test_contextual_comparison_runs(case, all_warrants):
    golds = generate_gold(case)
    out = {}
    for ctx in (True, False):
        s = RagStore(embedder=HashEmbedding(256))
        index_case(s, case, SLOT, contextual=ctx)
        r = evaluate_retriever(HybridRetriever(s), golds, case_id=CASE_ID, slot_id=SLOT, warrants=all_warrants)
        out[ctx] = (r.recall_at_k, r.mrr)
    print(f"\ncontextual on/off (Recall@5, MRR): {out}")
    assert out[True][0] >= 0.5 and out[False][0] >= 0.5


def test_records_tool_check(case, all_warrants):
    assert records_tool_check(case, all_warrants) == 1.0
