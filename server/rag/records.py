"""정형 기록 조회 (PRD §11.4 "정형 기록은 SQL"). 나중에 MCP 도구로 감쌀 함수.

- 자유 SQL은 받지 않는다. 시스템·시간 범위·인물·장소 매개변수만 받고, 저장소 쪽은 `?` 바인딩 쿼리를 쓴다.
- 권한: 각 행의 visibility를 scope/영장과 대조한다.
  - "player"/"public"이면 누구나, "warrant:<system>"이면 플레이어가 그 시스템의 영장을 갖고,
    영장의 시간 범위와 대상(인물 또는 장소)이 행을 덮을 때만 보인다.
  - NPC는 visibility에 "public" 또는 자기 "npc:<id>"가 있는 행만 본다.
- `source`는 CaseBible(메모리 안에서 조회) 또는 RagStore(SQL 조회, case_id/slot_id 필요).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import get_args

from server.rag.access import can_see_record, validate_scope
from server.rag.store import RagStore
from server.schemas import CaseBible, RecordRow, RecordSystem, Warrant

VALID_SYSTEMS = set(get_args(RecordSystem))


def search_records(
    source: CaseBible | RagStore,
    system: str,
    time_from: int,
    time_to: int,
    person_id: str | None = None,
    location_id: str | None = None,
    scope: str = "player",
    warrants: Iterable[Warrant] | None = None,
    *,
    case_id: str | None = None,
    slot_id: str | None = None,
    limit: int = 50,
) -> list[RecordRow]:
    """시간순으로 정렬된, 열람 권한이 있는 기록 행만 돌려준다 (최대 limit건)."""
    if system not in VALID_SYSTEMS:
        raise ValueError(f"알 수 없는 기록 시스템: {system!r}")
    if time_from > time_to:
        raise ValueError("time_from이 time_to보다 늦다")
    if limit < 1:
        raise ValueError("limit은 1 이상이어야 한다")
    validate_scope(scope)
    wlist = list(warrants or [])

    if isinstance(source, CaseBible):
        rows = [
            r
            for r in source.records
            if r.system == system
            and time_from <= r.time <= time_to
            and (person_id is None or r.person_id == person_id)
            and (location_id is None or r.location_id == location_id)
        ]
        rows.sort(key=lambda r: (r.time, r.id))
    elif isinstance(source, RagStore):
        if not case_id or not slot_id:
            raise ValueError("RagStore 조회에는 case_id와 slot_id가 필요하다")
        rows = source.query_records(case_id, slot_id, system, time_from, time_to, person_id, location_id)
    else:
        raise TypeError("source는 CaseBible 또는 RagStore여야 한다")

    return [r for r in rows if can_see_record(r, scope, wlist)][:limit]
