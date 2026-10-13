"""권한 판정. 검색·기록 조회가 후보를 모으는 단계에서 호출한다 (AGENTS.md 규칙 5).

규칙 (기본 거부):
- scope "player": visibility에 "player" 또는 "public"이 있거나,
  "warrant:<system>"이 있고 플레이어가 그 system의 영장을 가진 경우만 보인다.
  "npc:<id>"만 있는 항목은 절대 보이지 않는다.
- scope "npc:<id>": visibility에 "public" 또는 "npc:<id>"(자기 id)가 있을 때만 보인다.
  "player"나 다른 NPC 표시, 영장 표시는 NPC에게 의미가 없다.
- 알 수 없는 scope는 오류.
"""

from __future__ import annotations

from collections.abc import Iterable

from server.schemas import RecordRow, Warrant

PLAYER = "player"


def npc_scope(npc_id: str) -> str:
    return f"npc:{npc_id}"


def validate_scope(scope: str) -> str:
    if scope == PLAYER:
        return scope
    if scope.startswith("npc:") and len(scope) > 4:
        return scope
    raise ValueError(f"알 수 없는 검색 범위(scope): {scope!r}")


def warrant_systems(warrants: Iterable[Warrant] | None) -> set[str]:
    return {w.system for w in (warrants or [])}


def can_see(visibility: list[str], scope: str, warrants: Iterable[Warrant] | None = None) -> bool:
    """메모리·청크처럼 사람/시간 대상이 없는 항목의 열람 가능 여부."""
    validate_scope(scope)
    if not visibility:
        return False
    if scope == PLAYER:
        systems = warrant_systems(warrants)
        for v in visibility:
            if v in ("player", "public"):
                return True
            if v.startswith("warrant:") and v.split(":", 1)[1] in systems:
                return True
        return False
    return "public" in visibility or scope in visibility


def warrant_covers(w: Warrant, row: RecordRow) -> bool:
    """영장이 이 기록 행을 덮는지: 같은 시스템, 시간 범위, 대상(인물 또는 장소)."""
    if w.system != row.system:
        return False
    if not (w.from_time <= row.time <= w.to_time):
        return False
    return w.target_id in (row.person_id, row.location_id)


def can_see_record(row: RecordRow, scope: str, warrants: Iterable[Warrant] | None = None) -> bool:
    validate_scope(scope)
    vis = row.visibility
    if not vis:
        return False
    if scope == PLAYER:
        warrants = list(warrants or [])
        for v in vis:
            if v in ("player", "public"):
                return True
            if v.startswith("warrant:"):
                system = v.split(":", 1)[1]
                if system == row.system and any(warrant_covers(w, row) for w in warrants):
                    return True
        return False
    return "public" in vis or scope in vis
