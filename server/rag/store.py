"""기억·청크·정형 기록·관계 그래프 저장소 (SQLite).

규칙 (AGENTS.md 규칙 9, PRD §11.4.6)
- 사건 데이터(기억, 사건 청크, 정형 기록, 관계 그래프)는 case_id와 slot_id 없이 저장하지 않는다
  (`MissingSlotError`). 예외는 지식 베이스 컬렉션(kb_job, kb_law)의 청크뿐이다.
- 세이브 슬롯 단위로 분리한다: `copy_slot`(저장·불러오기), `delete_slot`(슬롯 삭제·클리어).
- `slot_id="__template__"`는 사건 원본의 초기 기억을 담아 두는 슬롯이다. 게임 시작 시 `copy_slot`으로 복사한다.
- 모든 조회 메서드가 case_id와 slot_id를 필수 인자로 받아 다른 슬롯이 섞일 수 없다.
- 권한 필터(visibility)는 retriever.py/records.py가 후보를 모으는 단계에서 적용한다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Sequence

import numpy as np

from server.rag.embedding import EmbeddingProvider
from server.schemas import Chunk, MemoryDoc, RecordRow

TEMPLATE_SLOT = "__template__"
KB_COLLECTIONS = ("kb_job", "kb_law")
# 슬롯 id를 가진 테이블 (복사·삭제 대상)
SLOT_TABLES = ("memories", "chunks", "records", "rel_facts", "rel_edges")


class MissingSlotError(ValueError):
    """case_id 또는 slot_id가 없어 저장을 거부했다."""


def _require_ids(case_id: str | None, slot_id: str | None, what: str) -> None:
    if not case_id or not str(case_id).strip():
        raise MissingSlotError(f"{what}: case_id가 없어 저장을 거부한다")
    if not slot_id or not str(slot_id).strip():
        raise MissingSlotError(f"{what}: slot_id가 없어 저장을 거부한다")


def memory_index_text(doc: MemoryDoc) -> str:
    return doc.content + (" " + " ".join(doc.tags) if doc.tags else "")


def chunk_index_text(chunk: Chunk) -> str:
    """Contextual Retrieval: 문맥 설명을 앞에 붙여 색인한다."""
    return f"{chunk.context}\n{chunk.content}" if chunk.context else chunk.content


def _to_blob(vec: np.ndarray | None) -> bytes | None:
    return None if vec is None else np.asarray(vec, dtype=np.float32).tobytes()


def _from_blob(blob: bytes | None) -> np.ndarray | None:
    return None if blob is None else np.frombuffer(blob, dtype=np.float32)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    slot_id TEXT NOT NULL, id TEXT NOT NULL, case_id TEXT NOT NULL, owner TEXT NOT NULL,
    data TEXT NOT NULL, vec BLOB,
    PRIMARY KEY (slot_id, id)
);
CREATE TABLE IF NOT EXISTS chunks (
    slot_id TEXT NOT NULL, collection TEXT NOT NULL, chunk_id TEXT NOT NULL, case_id TEXT NOT NULL,
    parent_id TEXT, data TEXT NOT NULL, vec BLOB,
    PRIMARY KEY (slot_id, collection, chunk_id)
);
CREATE TABLE IF NOT EXISTS records (
    slot_id TEXT NOT NULL, id TEXT NOT NULL, case_id TEXT NOT NULL, system TEXT NOT NULL,
    time INTEGER NOT NULL, person_id TEXT, location_id TEXT, detail TEXT NOT NULL,
    visibility TEXT NOT NULL, evidence_id TEXT,
    PRIMARY KEY (slot_id, id)
);
CREATE INDEX IF NOT EXISTS idx_records_q ON records (slot_id, system, time);
CREATE TABLE IF NOT EXISTS rel_facts (
    slot_id TEXT NOT NULL, fact_id TEXT NOT NULL, case_id TEXT NOT NULL,
    content TEXT NOT NULL, is_true INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (slot_id, fact_id)
);
CREATE TABLE IF NOT EXISTS rel_edges (
    rid INTEGER PRIMARY KEY AUTOINCREMENT,
    slot_id TEXT NOT NULL, case_id TEXT NOT NULL, fact_id TEXT NOT NULL, knower TEXT NOT NULL,
    learned_at INTEGER NOT NULL, from_who TEXT, via TEXT NOT NULL DEFAULT 'direct',
    distortion INTEGER NOT NULL DEFAULT 0, believed TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_q ON rel_edges (slot_id, fact_id, knower);
"""


class RagStore:
    def __init__(self, path: str = ":memory:", embedder: EmbeddingProvider | None = None) -> None:
        self.path = path
        self.embedder = embedder
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.version = 0  # 쓰기마다 증가. 검색 캐시 무효화에 쓴다.
        with self.lock:
            self.conn.executescript(_SCHEMA)
            self.conn.commit()

    # ------------------------------------------------------------------ 공통
    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def _bump(self) -> None:
        self.version += 1

    def _embed(self, texts: list[str]) -> list[np.ndarray | None]:
        if self.embedder is None or not texts:
            return [None] * len(texts)
        return list(self.embedder.embed(texts))

    # ------------------------------------------------------------------ 기억
    def add_memory(self, doc: MemoryDoc) -> None:
        self.add_memories([doc])

    def add_memories(self, docs: Sequence[MemoryDoc]) -> None:
        for d in docs:  # 하나라도 ID가 없으면 전체 거부
            _require_ids(d.case_id, d.slot_id, f"memory {d.id}")
        vecs = self._embed([memory_index_text(d) for d in docs])
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO memories (slot_id, id, case_id, owner, data, vec) VALUES (?,?,?,?,?,?)",
                [
                    (d.slot_id, d.id, d.case_id, d.owner, d.model_dump_json(), _to_blob(v))
                    for d, v in zip(docs, vecs)
                ],
            )
            self.conn.commit()
            self._bump()

    def load_memories(self, case_id: str, slot_id: str) -> list[tuple[MemoryDoc, np.ndarray | None]]:
        _require_ids(case_id, slot_id, "load_memories")
        with self.lock:
            rows = self.conn.execute(
                "SELECT data, vec FROM memories WHERE case_id=? AND slot_id=?", (case_id, slot_id)
            ).fetchall()
        return [(MemoryDoc.model_validate_json(d), _from_blob(v)) for d, v in rows]

    def update_memory_confidence(self, case_id: str, slot_id: str, memory_id: str, confidence: float) -> bool:
        """기억 왜곡 시 확신도 갱신 (PRD §11.4.6)."""
        _require_ids(case_id, slot_id, "update_memory_confidence")
        with self.lock:
            row = self.conn.execute(
                "SELECT data FROM memories WHERE case_id=? AND slot_id=? AND id=?", (case_id, slot_id, memory_id)
            ).fetchone()
            if row is None:
                return False
            doc = MemoryDoc.model_validate_json(row[0]).model_copy(update={"confidence": confidence})
            self.conn.execute(
                "UPDATE memories SET data=? WHERE slot_id=? AND id=?", (doc.model_dump_json(), slot_id, memory_id)
            )
            self.conn.commit()
            self._bump()
        return True

    # ------------------------------------------------------------------ 청크
    def add_chunk(self, chunk: Chunk) -> None:
        self.add_chunks([chunk])

    def add_chunks(self, chunks: Sequence[Chunk]) -> None:
        for c in chunks:
            if c.collection in KB_COLLECTIONS:
                continue  # 지식 베이스는 판 사이에 공유되는 참고 지식이라 예외
            _require_ids(c.case_id, c.slot_id, f"chunk {c.chunk_id}")
        vecs = self._embed([chunk_index_text(c) for c in chunks])
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO chunks (slot_id, collection, chunk_id, case_id, parent_id, data, vec)"
                " VALUES (?,?,?,?,?,?,?)",
                [
                    (
                        c.slot_id or "",
                        c.collection,
                        c.chunk_id,
                        c.case_id or "",
                        c.parent_id,
                        c.model_dump_json(),
                        _to_blob(v),
                    )
                    for c, v in zip(chunks, vecs)
                ],
            )
            self.conn.commit()
            self._bump()

    def load_chunks(
        self, case_id: str | None, slot_id: str | None, collection: str = "case"
    ) -> list[tuple[Chunk, np.ndarray | None]]:
        if collection in KB_COLLECTIONS:
            where, args = "collection=? AND slot_id=''", (collection,)
        else:
            _require_ids(case_id, slot_id, "load_chunks")
            where, args = "collection=? AND case_id=? AND slot_id=?", (collection, case_id, slot_id)
        with self.lock:
            rows = self.conn.execute(f"SELECT data, vec FROM chunks WHERE {where}", args).fetchall()
        return [(Chunk.model_validate_json(d), _from_blob(v)) for d, v in rows]

    def get_chunk(self, case_id: str, slot_id: str, chunk_id: str) -> Chunk | None:
        _require_ids(case_id, slot_id, "get_chunk")
        with self.lock:
            row = self.conn.execute(
                "SELECT data FROM chunks WHERE case_id=? AND slot_id=? AND chunk_id=? AND collection='case'",
                (case_id, slot_id, chunk_id),
            ).fetchone()
        return Chunk.model_validate_json(row[0]) if row else None

    # ------------------------------------------------------------------ 정형 기록
    def add_records(self, case_id: str, slot_id: str, rows: Iterable[RecordRow]) -> int:
        _require_ids(case_id, slot_id, "records")
        data = [
            (
                slot_id, r.id, case_id, r.system, r.time, r.person_id, r.location_id, r.detail,
                json.dumps(r.visibility, ensure_ascii=False), r.evidence_id,
            )
            for r in rows
        ]
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO records (slot_id, id, case_id, system, time, person_id, location_id,"
                " detail, visibility, evidence_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                data,
            )
            self.conn.commit()
            self._bump()
        return len(data)

    def query_records(
        self,
        case_id: str,
        slot_id: str,
        system: str,
        time_from: int,
        time_to: int,
        person_id: str | None = None,
        location_id: str | None = None,
    ) -> list[RecordRow]:
        """매개변수화된 SQL 조회. 권한 필터는 호출한 쪽(records.py)이 적용한다."""
        _require_ids(case_id, slot_id, "query_records")
        sql = (
            "SELECT id, system, time, person_id, location_id, detail, visibility, evidence_id FROM records"
            " WHERE case_id=? AND slot_id=? AND system=? AND time BETWEEN ? AND ?"
        )
        args: list = [case_id, slot_id, system, time_from, time_to]
        if person_id is not None:
            sql += " AND person_id=?"
            args.append(person_id)
        if location_id is not None:
            sql += " AND location_id=?"
            args.append(location_id)
        sql += " ORDER BY time, id"
        with self.lock:
            rows = self.conn.execute(sql, args).fetchall()
        return [
            RecordRow(
                id=r[0], system=r[1], time=r[2], person_id=r[3], location_id=r[4], detail=r[5],
                visibility=json.loads(r[6]), evidence_id=r[7],
            )
            for r in rows
        ]

    def load_all_records(self, case_id: str, slot_id: str) -> list[RecordRow]:
        _require_ids(case_id, slot_id, "load_all_records")
        with self.lock:
            rows = self.conn.execute(
                "SELECT id, system, time, person_id, location_id, detail, visibility, evidence_id FROM records"
                " WHERE case_id=? AND slot_id=? ORDER BY time, id",
                (case_id, slot_id),
            ).fetchall()
        return [
            RecordRow(
                id=r[0], system=r[1], time=r[2], person_id=r[3], location_id=r[4], detail=r[5],
                visibility=json.loads(r[6]), evidence_id=r[7],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------ 슬롯 관리
    def count_slot(self, slot_id: str) -> int:
        """슬롯에 남은 행 수 (삭제 검증용). 모든 슬롯 테이블 합계."""
        with self.lock:
            return sum(
                self.conn.execute(f"SELECT COUNT(*) FROM {t} WHERE slot_id=?", (slot_id,)).fetchone()[0]
                for t in SLOT_TABLES
            )

    def list_slots(self) -> list[str]:
        with self.lock:
            found: set[str] = set()
            for t in SLOT_TABLES:
                found.update(r[0] for r in self.conn.execute(f"SELECT DISTINCT slot_id FROM {t}"))
        found.discard("")
        return sorted(found)

    def delete_slot(self, slot_id: str) -> dict[str, int]:
        """슬롯의 모든 사건 데이터를 지운다 (클리어·슬롯 삭제). 지식 베이스는 건드리지 않는다."""
        if not slot_id or not slot_id.strip():
            raise MissingSlotError("delete_slot: slot_id가 필요하다")
        counts: dict[str, int] = {}
        with self.lock:
            for t in SLOT_TABLES:
                counts[t] = self.conn.execute(f"DELETE FROM {t} WHERE slot_id=?", (slot_id,)).rowcount
            self.conn.commit()
            self._bump()
        return counts

    def copy_slot(self, src_slot: str, dst_slot: str, *, overwrite: bool = True) -> dict[str, int]:
        """슬롯 전체 복사 (세이브·불러오기·게임 시작 시 템플릿 복사).

        dst에 이미 데이터가 있으면 overwrite=True일 때 먼저 지우고(덮어쓰기 저장) 복사한다.
        기억 문서 안의 slot_id도 dst로 바꿔 쓴다.
        """
        for s in (src_slot, dst_slot):
            if not s or not s.strip():
                raise MissingSlotError("copy_slot: src/dst slot_id가 필요하다")
        if src_slot == dst_slot:
            raise ValueError("src와 dst 슬롯이 같다")
        with self.lock:
            if self.count_slot(dst_slot):
                if not overwrite:
                    raise ValueError(f"슬롯 {dst_slot!r}에 이미 데이터가 있다")
                self.delete_slot(dst_slot)
            counts: dict[str, int] = {}
            for t in SLOT_TABLES:
                cols = [r[1] for r in self.conn.execute(f"PRAGMA table_info({t})") if r[1] != "rid"]
                select = ", ".join("?" if c == "slot_id" else c for c in cols)
                cur = self.conn.execute(
                    f"INSERT INTO {t} ({', '.join(cols)}) SELECT {select} FROM {t} WHERE slot_id=?",
                    (dst_slot, src_slot),
                )
                counts[t] = cur.rowcount
            # JSON 본문 안의 slot_id 갱신
            for doc_id, data in self.conn.execute("SELECT id, data FROM memories WHERE slot_id=?", (dst_slot,)).fetchall():
                obj = json.loads(data)
                obj["slot_id"] = dst_slot
                self.conn.execute(
                    "UPDATE memories SET data=? WHERE slot_id=? AND id=?",
                    (json.dumps(obj, ensure_ascii=False), dst_slot, doc_id),
                )
            for cid, coll, data in self.conn.execute(
                "SELECT chunk_id, collection, data FROM chunks WHERE slot_id=?", (dst_slot,)
            ).fetchall():
                obj = json.loads(data)
                obj["slot_id"] = dst_slot
                self.conn.execute(
                    "UPDATE chunks SET data=? WHERE slot_id=? AND collection=? AND chunk_id=?",
                    (json.dumps(obj, ensure_ascii=False), dst_slot, coll, cid),
                )
            self.conn.commit()
            self._bump()
        return counts
