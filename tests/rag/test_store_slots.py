import pytest

from server.rag.embedding import HashEmbedding
from server.rag.indexer import index_case
from server.rag.records import search_records
from server.rag.relations import RelationGraph
from server.rag.store import TEMPLATE_SLOT, MissingSlotError, RagStore
from server.schemas import Chunk, MemoryDoc, RecordRow
CASE_ID = "demo_db_deleted"
SLOT = "slot_test_1"


def mem(**kw):
    base = dict(id="m1", case_id=CASE_ID, slot_id=SLOT, owner="npc_chu", visibility=["npc:npc_chu"],
                doc_type="observation", content="내용", game_time=1)
    base.update(kw)
    return MemoryDoc(**base)


def test_memory_without_ids_rejected():
    s = RagStore()
    for bad in ({"slot_id": ""}, {"case_id": ""}, {"slot_id": "  "}):
        with pytest.raises(MissingSlotError):
            s.add_memory(mem(**bad))
    assert s.count_slot(SLOT) == 0


def test_batch_with_one_bad_item_stores_nothing():
    s = RagStore()
    with pytest.raises(MissingSlotError):
        s.add_memories([mem(id="a"), mem(id="b", slot_id="")])
    assert s.count_slot(SLOT) == 0


def test_chunk_and_records_and_relations_require_ids():
    s = RagStore()
    chunk = Chunk(chunk_id="c1", doc_id="d", collection="case", doc_title="t", chunk_strategy="x", content="내용",
                  case_id=CASE_ID, slot_id=None)
    with pytest.raises(MissingSlotError):
        s.add_chunk(chunk)
    with pytest.raises(MissingSlotError):
        s.add_records("", SLOT, [RecordRow(id="r", system="cctv", time=1, detail="x")])
    with pytest.raises(MissingSlotError):
        s.add_records(CASE_ID, "", [RecordRow(id="r", system="cctv", time=1, detail="x")])
    g = RelationGraph(s)
    with pytest.raises(MissingSlotError):
        g.record_fact(CASE_ID, "", "f", "x")
    with pytest.raises(MissingSlotError):
        g.record_knowledge("", SLOT, "f", "npc_chu", 1)


def test_kb_collection_is_exempt():
    s = RagStore()
    s.add_chunk(Chunk(chunk_id="kb1", doc_id="law1", collection="kb_law", doc_title="형법", chunk_strategy="article",
                      content="제366조 재물손괴"))
    assert len(s.load_chunks(None, None, "kb_law")) == 1


def test_delete_slot_leaves_zero_rows(case):
    s = RagStore(embedder=HashEmbedding())
    index_case(s, case, SLOT)
    RelationGraph(s).seed_from_case(case, SLOT)
    assert s.count_slot(SLOT) > 0
    counts = s.delete_slot(SLOT)
    assert counts["memories"] > 0 and counts["chunks"] > 0 and counts["records"] > 0
    assert s.count_slot(SLOT) == 0
    assert s.load_memories(CASE_ID, SLOT) == []
    assert s.load_chunks(CASE_ID, SLOT) == []
    assert s.load_all_records(CASE_ID, SLOT) == []
    assert search_records(s, "cctv", 0, 3000, case_id=CASE_ID, slot_id=SLOT) == []
    assert RelationGraph(s).who_knows(CASE_ID, SLOT, "bc_backup_restored") == []


def test_delete_slot_does_not_touch_other_slots(case):
    s = RagStore(embedder=HashEmbedding())
    index_case(s, case, "a")
    index_case(s, case, "b")
    before = s.count_slot("b")
    s.delete_slot("a")
    assert s.count_slot("a") == 0 and s.count_slot("b") == before


def test_template_copy_to_slot(case):
    s = RagStore(embedder=HashEmbedding())
    index_case(s, case, TEMPLATE_SLOT)
    s.copy_slot(TEMPLATE_SLOT, "game_1")
    assert s.count_slot("game_1") == s.count_slot(TEMPLATE_SLOT) > 0
    docs = s.load_memories(CASE_ID, "game_1")
    assert docs and all(d.slot_id == "game_1" for d, _ in docs)
    chunks = s.load_chunks(CASE_ID, "game_1")
    assert chunks and all(c.slot_id == "game_1" for c, _ in chunks)
    assert all(v is not None for _, v in docs)  # 임베딩도 같이 복사


def test_copy_overwrites_and_save_diverges(case):
    s = RagStore(embedder=HashEmbedding())
    index_case(s, case, TEMPLATE_SLOT)
    s.copy_slot(TEMPLATE_SLOT, "game_1")
    s.add_memory(mem(id="extra", slot_id="game_1"))
    s.copy_slot("game_1", "save_1")  # 저장
    assert {d.id for d, _ in s.load_memories(CASE_ID, "save_1")} >= {"extra"}
    s.delete_slot("game_1")
    assert s.count_slot("save_1") > 0
    s.copy_slot(TEMPLATE_SLOT, "save_1")  # 덮어쓰기
    assert "extra" not in {d.id for d, _ in s.load_memories(CASE_ID, "save_1")}
    with pytest.raises(ValueError):
        s.copy_slot(TEMPLATE_SLOT, "save_1", overwrite=False)


def test_file_backed_store(tmp_path, case):
    path = str(tmp_path / "rag.sqlite")
    s = RagStore(path, embedder=HashEmbedding())
    index_case(s, case, SLOT)
    n = s.count_slot(SLOT)
    s.close()
    s2 = RagStore(path)
    assert s2.count_slot(SLOT) == n
    s2.close()


def test_update_confidence(store):
    assert store.update_memory_confidence(CASE_ID, SLOT, "mem_dowon_03", 0.3)
    docs = {d.id: d for d, _ in store.load_memories(CASE_ID, SLOT)}
    assert docs["mem_dowon_03"].confidence == 0.3
