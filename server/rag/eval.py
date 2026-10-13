"""검색 정답 세트 자동 생성(PRD §17.3)과 Recall@k, MRR 계산.

사건 원본에는 "어떤 질문에 어떤 문서가 나와야 하는가"가 이미 들어 있다.
증거, 문서 청크, NPC 초기 기억에서 질문 템플릿으로 질문을 만들고 정답 id(증거 청크 `ev:<id>`, 청크 id, 기억 id)를 붙인다.
정형 기록은 SQL 도구 대상이라 이 검색 평가에는 넣지 않는다(`records_tool_check` 참고).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from server.rag.chunking import chunk_document, is_parent
from server.rag.records import search_records
from server.rag.retriever import HybridRetriever
from server.schemas import CaseBible, RetrievalGold, Warrant

_SENT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.replace("\n", " ")) if len(s.strip()) >= 12]


def _snippet(text: str, rng: random.Random, max_len: int = 40) -> str:
    sents = _sentences(text) or [text]
    s = rng.choice(sents)
    return s[:max_len].rstrip()


def _player_scope_for(visibility: list[str]) -> str | None:
    if any(v in ("player", "public") or v.startswith("warrant:") for v in visibility):
        return "player"
    npcs = [v for v in visibility if v.startswith("npc:")]
    return npcs[0] if npcs else None


def generate_gold(case: CaseBible, *, seed: int = 7, max_per_source: int = 60) -> list[RetrievalGold]:
    """사건 원본에서 검색 정답 세트를 만든다. 같은 seed면 항상 같은 결과."""
    rng = random.Random(seed)
    gold: list[RetrievalGold] = []

    for ev in case.evidence:
        scope = _player_scope_for(ev.visibility)
        if scope is None:
            continue
        ids = [f"ev:{ev.id}"]
        gold.append(RetrievalGold(question=f"{ev.name}에 대해 알려 주세요", relevant_ids=ids, asker_scope=scope))
        gold.append(RetrievalGold(question=f"'{_snippet(ev.content, rng)}' 이런 내용이 있나요?", relevant_ids=ids, asker_scope=scope))

    for doc in case.documents:
        scope = _player_scope_for(doc.visibility)
        if scope is None:
            continue
        chunks = [c for c in chunk_document(doc, case.case_id, "__eval__") if not is_parent(c)]
        for c in chunks[:max_per_source]:
            if c.chunk_strategy == "chat_window" and c.time_window:
                h, m = divmod(c.time_window[0] % 1440, 60)
                gold.append(RetrievalGold(
                    question=f"{h}시 {m:02d}분 무렵 {c.speaker}가 메신저에 뭐라고 썼나요?", relevant_ids=[c.chunk_id], asker_scope=scope))
            else:
                head = c.section_path or doc.title
                gold.append(RetrievalGold(
                    question=f"{doc.title}의 '{head}' 부분에는 무슨 내용이 있나요?", relevant_ids=[c.chunk_id], asker_scope=scope))
                gold.append(RetrievalGold(
                    question=f"'{_snippet(c.content, rng)}' 라는 내용은 어디에 나오나요?", relevant_ids=[c.chunk_id], asker_scope=scope))

    for mem in case.initial_memories:
        if mem.owner == "public":
            continue
        gold.append(RetrievalGold(
            question=f"'{_snippet(mem.content, rng)}' 이 일을 기억하나요?", relevant_ids=[mem.id], asker_scope=f"npc:{mem.owner}"))
    return gold


# --------------------------------------------------------------------------------- 지표
def recall_at_k(ranked: list[list[str]], golds: list[RetrievalGold], k: int) -> float:
    """질문마다 정답 중 상위 k개 안에 든 비율의 평균."""
    if not golds:
        return 0.0
    total = 0.0
    for ids, g in zip(ranked, golds):
        rel = set(g.relevant_ids)
        total += len(rel & set(ids[:k])) / len(rel) if rel else 0.0
    return total / len(golds)


def mrr(ranked: list[list[str]], golds: list[RetrievalGold]) -> float:
    """첫 정답의 순위 역수 평균."""
    if not golds:
        return 0.0
    total = 0.0
    for ids, g in zip(ranked, golds):
        rel = set(g.relevant_ids)
        for rank, i in enumerate(ids, start=1):
            if i in rel:
                total += 1.0 / rank
                break
    return total / len(golds)


@dataclass
class EvalReport:
    n: int
    k: int
    recall_at_k: float
    mrr: float
    by_scope: dict[str, dict[str, float]] = field(default_factory=dict)
    misses: list[str] = field(default_factory=list)  # 정답이 상위 k에 없던 질문


def evaluate_retriever(
    retriever: HybridRetriever,
    golds: list[RetrievalGold],
    *,
    case_id: str,
    slot_id: str,
    warrants: list[Warrant] | None = None,
    k: int = 5,
    **search_kwargs,
) -> EvalReport:
    ranked: list[list[str]] = []
    for g in golds:
        hits = retriever.search(
            g.question, case_id=case_id, slot_id=slot_id, scope=g.asker_scope, warrants=warrants, k=k, **search_kwargs)
        ranked.append([h.id for h in hits])
    misses = [g.question for ids, g in zip(ranked, golds) if not set(g.relevant_ids) & set(ids[:k])]
    by_scope: dict[str, dict[str, float]] = {}
    for kind in ("player", "npc"):
        idx = [i for i, g in enumerate(golds) if g.asker_scope.split(":")[0] == kind]
        if idx:
            sg = [golds[i] for i in idx]
            sr = [ranked[i] for i in idx]
            by_scope[kind] = {"n": float(len(idx)), "recall_at_k": recall_at_k(sr, sg, k), "mrr": mrr(sr, sg)}
    return EvalReport(len(golds), k, recall_at_k(ranked, golds, k), mrr(ranked, golds), by_scope, misses)


def records_tool_check(case: CaseBible, warrants: list[Warrant]) -> float:
    """정형 기록 도구 점검: evidence_id가 붙은 기록마다 (시스템, 인물, 시각 ±0) 조회로 그 행이 나오는 비율."""
    rows = [r for r in case.records if r.evidence_id]
    if not rows:
        return 0.0
    ok = 0
    for r in rows:
        found = search_records(case, r.system, r.time, r.time, person_id=r.person_id, location_id=r.location_id,
                               scope="player", warrants=warrants)
        ok += any(f.id == r.id for f in found)
    return ok / len(rows)
