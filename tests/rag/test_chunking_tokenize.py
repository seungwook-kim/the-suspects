from server.rag.chunking import chunk_document, chunk_evidence, is_parent
from server.rag.embedding import CachedEmbedding, HashEmbedding
from server.rag.tokenize import parse_times, tokenize


def doc(case, doc_id):
    return next(d for d in case.documents if d.id == doc_id)


def test_time_normalization():
    assert 23 * 60 + 5 in parse_times("23:05에 로그인")
    assert parse_times("밤 11시 5분") == [23 * 60 + 5]
    assert parse_times("오후 11시 반") == [23 * 60 + 30]
    assert parse_times("새벽 2시") == [120]
    assert parse_times("밤 12시") == [0]
    assert "@2305" in tokenize("밤 11시 5분쯤") and "@2305" in tokenize("23:05")
    assert "@h23" in tokenize("23:40")


def test_korean_tokens():
    toks = tokenize("추성만이 서버실에")
    assert "추성만" in toks and "서버" in toks and "버실" in toks


def test_hash_embedding_deterministic_and_normalized():
    e = HashEmbedding(64)
    a, b = e.embed(["서버실 카드"]), e.embed(["서버실 카드"])
    assert (a == b).all()
    assert abs(float((a[0] ** 2).sum()) - 1.0) < 1e-5
    assert float(e.embed(["서버실 출입카드"])[0] @ a[0]) > float(e.embed(["치킨 배달"])[0] @ a[0])


def test_embedding_cache():
    c = CachedEmbedding(HashEmbedding(64))
    c.embed(["가", "나", "가"])
    c.embed(["가", "나"])
    assert c.calls == 2


def test_manual_section_chunking_parent_child(case):
    chunks = chunk_document(doc(case, "doc_manual"), "c", "s")
    by_id = {c.chunk_id: c for c in chunks}
    parents = [c for c in chunks if is_parent(c)]
    assert parents, "긴 섹션(계정 관리)은 부모-자식으로 나뉘어야 한다"
    children = [c for c in chunks if c.parent_id]
    assert children and all(c.parent_id in by_id and is_parent(by_id[c.parent_id]) for c in children)
    # 깊숙한 단서가 자식 청크에 있다
    assert any("smchoo" in c.content for c in children)
    assert all(c.context.startswith("[") and "매뉴얼" in c.context for c in chunks)
    assert all(c.case_id == "c" and c.slot_id == "s" for c in chunks)
    # 짧은 섹션은 청크 1개
    assert by_id["doc_manual#s0"].parent_id is None
    assert any(c.section_path == "계정 관리".join(["3. ", ""]) for c in parents)


def test_chat_log_windows(case):
    chunks = [c for c in chunk_document(doc(case, "doc_chat"), "c", "s") if c.chunk_strategy == "chat_window"]
    assert chunks
    for c in chunks:
        assert c.time_window and c.time_window[1] - c.time_window[0] == 10 and c.speaker
        assert c.time_window[0] % 10 == 0
    w = next(c for c in chunks if "운영 DB 접속이 안 돼요" in c.content)
    assert w.time_window == (23 * 60 + 10, 23 * 60 + 20)
    assert "서도윤" in w.speaker and "한소라" in w.speaker


def test_minutes_one_chunk_per_agenda(case):
    d = doc(case, "doc_incident_meeting")
    chunks = chunk_document(d, "c", "s")
    assert len(chunks) == len(d.sections) and all(c.chunk_strategy == "agenda" for c in chunks)


def test_contextual_off_clears_context(case):
    chunks = chunk_document(doc(case, "doc_manual"), "c", "s", contextual=False)
    assert all(c.context == "" for c in chunks)


def test_evidence_chunk(case):
    ev = case.evidence[2]
    c = chunk_evidence(ev, "c", "s")
    assert c.chunk_id == f"ev:{ev.id}" and c.visibility == ev.visibility
