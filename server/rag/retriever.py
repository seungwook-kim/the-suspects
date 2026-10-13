"""하이브리드 검색: BM25 키워드 + 임베딩 벡터, 권한 필터는 검색 단계에서 강제.

핵심 규칙 (AGENTS.md 규칙 5, PRD §11.4)
- 후보를 모으는 단계에서 `access.can_see`로 걸러낸 뒤에만 점수를 계산한다.
  권한 밖 문서는 BM25 통계(IDF)와 벡터 점수에도 들어가지 않는다. 사후 필터가 아니다.
- scope "npc:<id>": 그 NPC가 볼 수 있는 것(visibility에 "public" 또는 "npc:<id>")만.
- scope "player": 플레이어 공개분 + 플레이어가 가진 영장으로 열린 것만.
- `allowed_ids`는 권한을 넓히지 못하고 좁히기만 한다(예: 플레이어가 아직 발견하지 못한 증거 제외).
- 점수 = relevance_weight*관련도 + recency_weight*최신성 + importance_weight*중요도 (Generative Agents 방식).
  기본값은 관련도만 쓴다. 가중치는 규칙 엔진 설정을 모르므로 전부 인자로 받는다.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
from rank_bm25 import BM25Okapi

from server.rag.access import can_see, can_see_record, validate_scope
from server.rag.chunking import is_parent
from server.rag.store import RagStore, chunk_index_text, memory_index_text
from server.rag.tokenize import tokenize
from server.schemas import RetrievalHit, Warrant


@dataclass
class _Cand:
    id: str
    kind: str  # memory | chunk | record
    content: str
    tokens: list[str]
    vec: np.ndarray | None
    game_time: int | None
    importance: float
    meta: dict = field(default_factory=dict)


@dataclass
class _Index:
    cands: list[_Cand]
    bm25: BM25Okapi | None
    matrix: np.ndarray | None  # (n, dim), 벡터 없는 후보는 0행


class HybridRetriever:
    def __init__(
        self,
        store: RagStore,
        *,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
        relevance_weight: float = 1.0,
        recency_weight: float = 0.0,
        importance_weight: float = 0.0,
        recency_half_life: float = 360.0,
    ) -> None:
        self.store = store
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.relevance_weight = relevance_weight
        self.recency_weight = recency_weight
        self.importance_weight = importance_weight
        self.recency_half_life = recency_half_life
        self._cache: dict[tuple, tuple[int, _Index]] = {}

    # ------------------------------------------------------------------ 후보 수집 (권한 필터)
    def _collect(
        self, case_id: str, slot_id: str, scope: str, warrants: Sequence[Warrant], kinds: Collection[str],
        include_parents: bool,
    ) -> list[_Cand]:
        cands: list[_Cand] = []
        if "memory" in kinds:
            for doc, vec in self.store.load_memories(case_id, slot_id):
                if not can_see(doc.visibility, scope, warrants):
                    continue
                importance = 1.0 if doc.is_key_evidence else 0.8 if doc.is_first_testimony else 0.4 + 0.3 * doc.confidence
                cands.append(
                    _Cand(
                        id=doc.id, kind="memory", content=doc.content, tokens=tokenize(memory_index_text(doc)),
                        vec=vec, game_time=doc.game_time, importance=importance,
                        meta={
                            "owner": doc.owner, "doc_type": doc.doc_type, "confidence": doc.confidence,
                            "source": doc.source, "source_npc": doc.source_npc, "evidence_id": doc.evidence_id,
                            "is_first_testimony": doc.is_first_testimony, "game_time": doc.game_time,
                        },
                    )
                )
        if "chunk" in kinds:
            for chunk, vec in self.store.load_chunks(case_id, slot_id, "case"):
                if not can_see(chunk.visibility, scope, warrants):
                    continue
                if is_parent(chunk) and not include_parents:
                    continue
                is_key = bool((chunk.kb_meta or {}).get("is_key"))
                cands.append(
                    _Cand(
                        id=chunk.chunk_id, kind="chunk", content=chunk.content,
                        tokens=tokenize(chunk_index_text(chunk)), vec=vec, game_time=chunk.game_time,
                        importance=1.0 if is_key else 0.3,
                        meta={
                            "doc_id": chunk.doc_id, "doc_title": chunk.doc_title, "section_path": chunk.section_path,
                            "chunk_strategy": chunk.chunk_strategy, "parent_id": chunk.parent_id,
                            "speaker": chunk.speaker, "time_window": chunk.time_window, "context": chunk.context,
                            "evidence_id": (chunk.kb_meta or {}).get("evidence_id"),
                        },
                    )
                )
        if "record" in kinds:
            for row in self.store.load_all_records(case_id, slot_id):
                if not can_see_record(row, scope, warrants):
                    continue
                text = f"{row.system} {row.person_id or ''} {row.location_id or ''} {row.detail}"
                cands.append(
                    _Cand(
                        id=row.id, kind="record", content=row.detail, tokens=tokenize(text), vec=None,
                        game_time=row.time, importance=0.5,
                        meta={
                            "system": row.system, "person_id": row.person_id, "location_id": row.location_id,
                            "time": row.time, "evidence_id": row.evidence_id,
                        },
                    )
                )
        return cands

    def _index(
        self, case_id: str, slot_id: str, scope: str, warrants: Sequence[Warrant], kinds: Collection[str],
        include_parents: bool,
    ) -> _Index:
        # 영장은 접근 범위를 바꾸므로 캐시 키에 넣는다.
        wkey = tuple(sorted((w.system, w.target_id, w.from_time, w.to_time) for w in warrants))
        key = (case_id, slot_id, scope, wkey, tuple(sorted(kinds)), include_parents)
        hit = self._cache.get(key)
        if hit and hit[0] == self.store.version:
            return hit[1]
        cands = self._collect(case_id, slot_id, scope, warrants, kinds, include_parents)
        bm25 = BM25Okapi([c.tokens or ["_"] for c in cands]) if cands else None
        matrix = None
        dim = self.store.embedder.dim if self.store.embedder else None
        if cands and dim and any(c.vec is not None for c in cands):
            matrix = np.stack([c.vec if c.vec is not None else np.zeros(dim, dtype=np.float32) for c in cands])
        idx = _Index(cands, bm25, matrix)
        self._cache[key] = (self.store.version, idx)
        return idx

    # ------------------------------------------------------------------ 검색
    def search(
        self,
        query: str,
        *,
        case_id: str,
        slot_id: str,
        scope: str,
        warrants: Iterable[Warrant] | None = None,
        k: int = 5,
        kinds: Collection[str] = ("memory", "chunk"),
        now: int | None = None,
        include_parents: bool = False,
        expand_parent: bool = True,
        allowed_ids: Collection[str] | None = None,
        bm25_weight: float | None = None,
        vector_weight: float | None = None,
    ) -> list[RetrievalHit]:
        validate_scope(scope)
        if not case_id or not slot_id:
            raise ValueError("case_id와 slot_id가 필요하다")
        wlist = list(warrants or [])
        idx = self._index(case_id, slot_id, scope, wlist, kinds, include_parents)
        if not idx.cands:
            return []
        wb = self.bm25_weight if bm25_weight is None else bm25_weight
        wv = self.vector_weight if vector_weight is None else vector_weight

        q_tokens = tokenize(query)
        bm = np.asarray(idx.bm25.get_scores(q_tokens), dtype=np.float64) if idx.bm25 and q_tokens else np.zeros(len(idx.cands))
        bm = np.clip(bm, 0, None)
        if bm.max() > 0:
            bm = bm / bm.max()
        vs = np.zeros(len(idx.cands))
        if idx.matrix is not None and self.store.embedder is not None and wv > 0:
            q_vec = self.store.embedder.embed_one(query)
            vs = np.clip(idx.matrix @ q_vec, 0, None).astype(np.float64)
            if vs.max() > 0:
                vs = vs / vs.max()
        if idx.matrix is None:  # 벡터가 없으면 키워드만
            wb, wv = 1.0, 0.0
        rel = (wb * bm + wv * vs) / (wb + wv) if (wb + wv) > 0 else bm

        scored: list[tuple[float, int]] = []
        for i, c in enumerate(idx.cands):
            if allowed_ids is not None and c.id not in allowed_ids and c.meta.get("evidence_id") not in allowed_ids:
                continue
            if rel[i] <= 0:
                continue
            score = self.relevance_weight * float(rel[i])
            if self.recency_weight and now is not None:
                gt = c.game_time if c.game_time is not None else now
                score += self.recency_weight * math.exp(-max(0, now - gt) / self.recency_half_life)
            if self.importance_weight:
                score += self.importance_weight * c.importance
            scored.append((score, i))
        scored.sort(key=lambda x: (-x[0], idx.cands[x[1]].id))

        hits: list[RetrievalHit] = []
        for score, i in scored[:k]:
            c = idx.cands[i]
            meta = {**c.meta, "relevance": float(rel[i])}
            if expand_parent and c.kind == "chunk" and c.meta.get("parent_id"):
                parent = self.store.get_chunk(case_id, slot_id, c.meta["parent_id"])
                if parent is not None and can_see(parent.visibility, scope, wlist):  # 부모도 권한 검사
                    meta["parent_content"] = parent.content
            hits.append(RetrievalHit(id=c.id, kind=c.kind, content=c.content, score=score, meta=meta))  # type: ignore[arg-type]
        return hits
