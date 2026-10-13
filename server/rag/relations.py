"""시간 관계 그래프 (PRD §6.9): "사실 - 아는 사람 - 알게 된 시각 - 누구에게서".

기억 저장소와 같은 SQLite 파일의 `rel_facts`, `rel_edges` 테이블에 쌓는다(슬롯 복사·삭제 대상).
밤 대화·심문·소문 전파에서 구조화 출력으로 이미 받은 정보를 그대로 기록한다(추가 LLM 호출 없음).

- fact: 사실 하나(진실 여부 is_true 포함). 블러핑 주장은 fact_id를 주장 id로 쓴다.
- edge: 어떤 NPC가 그 사실을 알게 된 기록. from_who가 None이면 직접 겪음.
"""

from __future__ import annotations

from dataclasses import dataclass

from server.rag.store import RagStore, _require_ids
from server.schemas import BluffClaimDef, CaseBible


@dataclass(frozen=True)
class KnowledgeEdge:
    fact_id: str
    knower: str
    learned_at: int
    from_who: str | None
    via: str  # direct | heard | rumor | guess
    distortion: int
    believed: str | None  # 왜곡된 채 믿는 내용 (없으면 원문)


class RelationGraph:
    def __init__(self, store: RagStore) -> None:
        self.store = store

    # ------------------------------------------------------------------ 쓰기
    def record_fact(self, case_id: str, slot_id: str, fact_id: str, content: str, *, is_true: bool = True) -> None:
        _require_ids(case_id, slot_id, f"fact {fact_id}")
        with self.store.lock:
            self.store.conn.execute(
                "INSERT OR REPLACE INTO rel_facts (slot_id, fact_id, case_id, content, is_true) VALUES (?,?,?,?,?)",
                (slot_id, fact_id, case_id, content, int(is_true)),
            )
            self.store.conn.commit()
            self.store._bump()

    def record_knowledge(
        self,
        case_id: str,
        slot_id: str,
        fact_id: str,
        knower: str,
        learned_at: int,
        *,
        from_who: str | None = None,
        via: str = "direct",
        distortion: int = 0,
        believed: str | None = None,
    ) -> None:
        _require_ids(case_id, slot_id, f"knowledge {fact_id}")
        with self.store.lock:
            self.store.conn.execute(
                "INSERT INTO rel_edges (slot_id, case_id, fact_id, knower, learned_at, from_who, via, distortion,"
                " believed) VALUES (?,?,?,?,?,?,?,?,?)",
                (slot_id, case_id, fact_id, knower, learned_at, from_who, via, distortion, believed),
            )
            self.store.conn.commit()
            self.store._bump()

    def seed_from_case(self, case: CaseBible, slot_id: str) -> None:
        """사건 원본의 블러핑 주장 중 '거짓임을 아는 NPC'를 그래프에 심는다(게임 시작 시)."""
        for claim in case.bluff_claims:
            if claim.known_false_by:
                self.record_fact(case.case_id, slot_id, claim.id, claim.label, is_true=False)
                for npc in claim.known_false_by:
                    self.record_knowledge(case.case_id, slot_id, claim.id, npc, 0, via="direct")

    # ------------------------------------------------------------------ 읽기
    def _edges(self, case_id: str, slot_id: str, fact_id: str, knower: str | None, at_time: int | None) -> list[KnowledgeEdge]:
        _require_ids(case_id, slot_id, "relations")
        sql = (
            "SELECT fact_id, knower, learned_at, from_who, via, distortion, believed FROM rel_edges"
            " WHERE case_id=? AND slot_id=? AND fact_id=?"
        )
        args: list = [case_id, slot_id, fact_id]
        if knower is not None:
            sql += " AND knower=?"
            args.append(knower)
        if at_time is not None:
            sql += " AND learned_at<=?"
            args.append(at_time)
        sql += " ORDER BY learned_at, rid"
        with self.store.lock:
            return [KnowledgeEdge(*r) for r in self.store.conn.execute(sql, args).fetchall()]

    def who_knows(self, case_id: str, slot_id: str, fact_id: str, at_time: int | None = None) -> list[KnowledgeEdge]:
        return self._edges(case_id, slot_id, fact_id, None, at_time)

    def knows(self, case_id: str, slot_id: str, npc_id: str, fact_id: str, at_time: int | None = None) -> bool:
        return bool(self._edges(case_id, slot_id, fact_id, npc_id, at_time))

    def trace_origin(self, case_id: str, slot_id: str, fact_id: str, npc_id: str) -> list[KnowledgeEdge]:
        """npc가 이 사실을 누구에게서 어떤 경로로 들었는지 거슬러 올라간다 (소문 경로 추적)."""
        path: list[KnowledgeEdge] = []
        seen: set[str] = set()
        cur: str | None = npc_id
        while cur and cur not in seen:
            seen.add(cur)
            edges = self._edges(case_id, slot_id, fact_id, cur, None)
            if not edges:
                break
            first = edges[0]  # 가장 먼저 알게 된 경로
            path.append(first)
            cur = first.from_who
        return path

    def knows_false(
        self,
        npc_id: str,
        claim: BluffClaimDef | str,
        *,
        case_id: str,
        slot_id: str,
        at_time: int | None = None,
    ) -> bool:
        """블러핑 즉시 실패 판정: 이 NPC가 주장이 거짓임을 아는가?

        (1) 주장 정의의 known_false_by에 있거나, (2) 그래프에 '거짓 사실'을 안다고 기록돼 있으면 True.
        """
        if isinstance(claim, BluffClaimDef) and npc_id in claim.known_false_by:
            return True
        fact_id = claim.id if isinstance(claim, BluffClaimDef) else claim
        _require_ids(case_id, slot_id, "knows_false")
        with self.store.lock:
            row = self.store.conn.execute(
                "SELECT is_true FROM rel_facts WHERE slot_id=? AND fact_id=?", (slot_id, fact_id)
            ).fetchone()
        if row is None or row[0]:
            return False
        return self.knows(case_id, slot_id, npc_id, fact_id, at_time)
