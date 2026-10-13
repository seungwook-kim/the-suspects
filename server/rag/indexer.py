"""사건 원본(CaseBible)을 저장소에 색인한다 (PRD §11.4.6: 사건 생성 시 색인).

- 문서 -> 청킹 -> 청크 (Contextual Retrieval 옵션)
- 증거 -> 증거 청크 1개씩 (`ev:<id>`)
- 초기 기억 -> slot_id를 대상 슬롯으로 바꿔 저장
- 정형 기록 -> records 테이블 (청킹·임베딩 없음)
`slot_id="__template__"`로 색인해 두고 게임 시작 때 `store.copy_slot`으로 복사하는 흐름을 지원한다.
"""

from __future__ import annotations

from server.rag.chunking import chunk_document, chunk_evidence
from server.rag.store import RagStore
from server.schemas import CaseBible


def index_case(
    store: RagStore,
    case: CaseBible,
    slot_id: str,
    *,
    contextual: bool = True,
    documents: bool = True,
    evidence: bool = True,
    memories: bool = True,
    records: bool = True,
    max_tokens: int = 400,
    window_minutes: int = 10,
) -> dict[str, int]:
    counts = {"chunks": 0, "memories": 0, "records": 0}
    chunks = []
    if documents:
        for doc in case.documents:
            chunks.extend(
                chunk_document(
                    doc, case.case_id, slot_id, max_tokens=max_tokens, window_minutes=window_minutes,
                    contextual=contextual,
                )
            )
    if evidence:
        chunks.extend(chunk_evidence(ev, case.case_id, slot_id, contextual=contextual) for ev in case.evidence)
    if chunks:
        store.add_chunks(chunks)
        counts["chunks"] = len(chunks)
    if memories and case.initial_memories:
        docs = [m.model_copy(update={"case_id": case.case_id, "slot_id": slot_id}) for m in case.initial_memories]
        store.add_memories(docs)
        counts["memories"] = len(docs)
    if records and case.records:
        counts["records"] = store.add_records(case.case_id, slot_id, case.records)
    return counts
