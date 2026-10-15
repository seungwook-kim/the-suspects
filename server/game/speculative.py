"""추측 생성: 추천 질문 답 미리 만들기 (PRD §14.1 미리 하기, 부록 F.15).

플레이어가 한 인물을 심문하는 동안(화면이 /prepare로 알림), 그 인물에게 보이는 추천 질문 칩의 답을
검색 + 인물 답 + 게임 마스터 검사까지 백그라운드로 미리 만들어 둔다. 칩을 누르면 기다리지 않고 그 답을 쓴다.

- 미리 만들 때는 게임 상태를 복사본으로만 쓴다(저장·기억 기록·증거 획득 없음). 그런 결과는 칩을 실제로 누를 때 낸다.
- 같은 상태(키)에서 누른 칩만 쓴다. 다른 행동을 하면 상태 키가 바뀌어 남은 준비분은 버린다.
- 한 번 준비(칩 표시) = (미리 만든 수, 실제로 쓴 수) 한 쌍을 쌓아 두었다가, 다음 행동 때 게임 상태의
  적중률 기록(server.rules.speculative)으로 옮긴다. 적중률이 낮으면 그 판에서 자동으로 끈다.
- 모델 호출은 node 이름 끝에 ":speculative"를 붙여 기록한다(지연 측정에서 플레이어가 기다린 호출과 구별).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from server.schemas import GameState

SPEC_TAG = "speculative"


def state_key(state: GameState) -> tuple:
    """미리 만든 답을 써도 되는 상태인지 가르는 열쇠. 이 값이 같으면 인물 답에 들어가는 입력이 같다."""
    return (state.slot_id, state.phase, state.day, state.action_no, state.clock, state.player_location,
            len(state.notebook.statements), len(state.notebook.evidence_ids))


class TaggedLLM:
    """모델 호출 기록의 node 이름에 꼬리표를 붙이는 얇은 래퍼(미리 만든 호출 구별용)."""

    def __init__(self, llm: Any, tag: str = SPEC_TAG) -> None:
        self._llm, self._tag = llm, tag

    async def structured(self, **kw: Any) -> Any:
        kw["node"] = f"{kw.get('node') or kw['role']}:{self._tag}"
        return await self._llm.structured(**kw)

    async def structured_stream(self, **kw: Any) -> Any:
        kw["node"] = f"{kw.get('node') or kw['role']}:{self._tag}"
        return await self._llm.structured_stream(**kw)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._llm, name)


@dataclass
class _Show:
    key: tuple
    npc_id: str
    tasks: dict[str, asyncio.Task] = field(default_factory=dict)  # 칩 id → 미리 만든 답(실패면 None)
    used: int = 0


class Speculator:
    def __init__(self) -> None:
        self._shows: dict[str, _Show] = {}
        self._done: dict[str, list[tuple[int, int]]] = {}  # 판 → 끝난 준비들의 (미리 만든 수, 쓴 수)

    def active(self, game_id: str) -> tuple | None:
        show = self._shows.get(game_id)
        return (show.key, show.npc_id) if show else None

    def start(self, game_id: str, key: tuple, npc_id: str, jobs: dict[str, Callable[[], Awaitable[Any]]]) -> int:
        """칩마다 답 만들기를 시작한다. 같은 상태·같은 인물로 이미 준비 중이면 그대로 둔다(0 반환)."""
        cur = self._shows.get(game_id)
        if cur and cur.key == key and cur.npc_id == npc_id:
            return 0
        self.close(game_id)
        if not jobs:
            return 0
        loop = asyncio.get_running_loop()
        show = _Show(key=key, npc_id=npc_id)
        for chip_id, job in jobs.items():
            show.tasks[chip_id] = loop.create_task(_quiet(job))
        self._shows[game_id] = show
        return len(show.tasks)

    async def take(self, game_id: str, key: tuple, chip_id: str) -> Any | None:
        """같은 상태에서 누른 칩이면 미리 만든 답(아직 만드는 중이면 끝날 때까지 기다림). 아니면 None."""
        show = self._shows.get(game_id)
        if not show or show.key != key or chip_id not in show.tasks:
            return None
        try:
            res = await asyncio.shield(show.tasks[chip_id])
        except asyncio.CancelledError:
            return None
        if res is not None:
            show.used += 1
        return res

    def close(self, game_id: str) -> None:
        """지금 준비분을 끝낸다: 덜 만든 것은 취소하고 (미리 만든 수, 쓴 수)를 쌓는다."""
        show = self._shows.pop(game_id, None)
        if not show:
            return
        for t in show.tasks.values():
            if not t.done():
                t.cancel()
        self._done.setdefault(game_id, []).append((len(show.tasks), show.used))

    def drain(self, game_id: str) -> list[tuple[int, int]]:
        """쌓인 준비 기록을 꺼낸다(게임 상태의 적중률 기록으로 옮길 때)."""
        return self._done.pop(game_id, [])

    def forget(self, game_id: str) -> None:
        """판이 끝났을 때: 준비분과 기록을 모두 버린다."""
        self.close(game_id)
        self._done.pop(game_id, None)


async def _quiet(job: Callable[[], Awaitable[Any]]) -> Any | None:
    """미리 만들기 실패는 조용히 None (칩을 누르면 평소처럼 새로 만든다)."""
    try:
        return await job()
    except asyncio.CancelledError:
        raise
    except Exception:
        return None
