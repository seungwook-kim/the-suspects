"""게임 상태, 세이브 슬롯, 클리어 이력 저장소 (PRD §10).

- 개발은 SQLite. 배포 시 Postgres로 옮길 수 있게 이 모듈 밖에서는 SQL을 쓰지 않는다.
- 세이브 슬롯은 "게임 상태 + NPC 기억 + 배경 참조"의 한 묶음이다. 기억(RAG)은 rag 저장소가
  slot_id 단위로 복사·삭제하고, 이 모듈은 상태와 메타데이터를 맡는다.
- 클리어 시 남는 것은 클리어 이력(ClearHistory)뿐이다.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from server.schemas import ClearHistory, GameState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id     TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    player_id   TEXT NOT NULL,
    live_slot   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    last_seen   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS slots (
    slot_id     TEXT PRIMARY KEY,
    game_id     TEXT NOT NULL,
    case_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,          -- live | manual | auto
    state_json  TEXT NOT NULL,
    saved_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clear_history (
    id          TEXT PRIMARY KEY,
    player_id   TEXT NOT NULL,
    data_json   TEXT NOT NULL,
    cleared_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_slots_game ON slots(game_id);
CREATE INDEX IF NOT EXISTS idx_history_player ON clear_history(player_id);
"""


class StorageError(RuntimeError):
    pass


class GameStore:
    """게임 상태 저장소. 스레드 하나에서 여러 요청이 올 수 있어 잠금을 건다."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ games
    def create_game(self, state: GameState, player_id: str = "player") -> None:
        self._require_ids(state)
        now = datetime.now().isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?)",
                (state.game_id, state.case_id, player_id, state.slot_id, now, now),
            )
            self._write_slot(state, name="진행 중", kind="live")
            self._conn.commit()

    def load_live(self, game_id: str) -> GameState:
        with self._lock:
            row = self._conn.execute("SELECT live_slot FROM games WHERE game_id = ?", (game_id,)).fetchone()
            if row is None:
                raise StorageError(f"게임이 없습니다: {game_id}")
            srow = self._conn.execute("SELECT state_json FROM slots WHERE slot_id = ?", (row["live_slot"],)).fetchone()
            self._conn.execute("UPDATE games SET last_seen = ? WHERE game_id = ?", (datetime.now().isoformat(), game_id))
            self._conn.commit()
        if srow is None:
            raise StorageError(f"진행 중 슬롯이 없습니다: {game_id}")
        return GameState.model_validate_json(srow["state_json"])

    def list_games(self, player_id: str = "player") -> list[dict]:
        """진행 중인 게임 목록 (이어하기)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT g.game_id, g.case_id, g.last_seen, s.state_json FROM games g "
                "JOIN slots s ON s.slot_id = g.live_slot WHERE g.player_id = ? ORDER BY g.last_seen DESC",
                (player_id,),
            ).fetchall()
        out = []
        for r in rows:
            st = GameState.model_validate_json(r["state_json"])
            out.append({"game_id": r["game_id"], "case_id": r["case_id"], "day": st.day,
                        "phase": st.phase, "last_seen": r["last_seen"]})
        return out

    def save_live(self, state: GameState) -> None:
        self._require_ids(state)
        with self._lock:
            self._write_slot(state, name="진행 중", kind="live")
            self._conn.commit()

    # ------------------------------------------------------------------ slots
    def snapshot(self, state: GameState, name: str, kind: str = "manual") -> str:
        """세이브: 현재 상태를 새 슬롯 id로 복사한다. 반환한 slot_id로 rag 저장소도 같은 묶음을 복사해야 한다."""
        self._require_ids(state)
        new_slot = f"slot_{uuid.uuid4().hex[:12]}"
        copy = state.model_copy(update={"slot_id": new_slot})
        with self._lock:
            self._write_slot(copy, name=name, kind=kind)
            self._conn.commit()
        return new_slot

    def list_slots(self, game_id: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT slot_id, name, kind, saved_at FROM slots WHERE game_id = ? AND kind != 'live' ORDER BY saved_at DESC",
                (game_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def load_slot(self, slot_id: str) -> GameState:
        with self._lock:
            row = self._conn.execute("SELECT state_json FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
        if row is None:
            raise StorageError(f"슬롯이 없습니다: {slot_id}")
        return GameState.model_validate_json(row["state_json"])

    def activate_slot(self, game_id: str, slot_id: str, new_live_slot: str) -> GameState:
        """불러오기: 저장 슬롯의 상태를 새 live 슬롯으로 복사하고 게임의 live를 바꾼다.

        기존 live 슬롯 id를 돌려받아 rag 저장소에서도 지워야 하므로, 호출자가 먼저 old live를 조회한다.
        """
        saved = self.load_slot(slot_id)
        live = saved.model_copy(update={"slot_id": new_live_slot})
        with self._lock:
            old = self._conn.execute("SELECT live_slot FROM games WHERE game_id = ?", (game_id,)).fetchone()
            if old is not None:
                self._conn.execute("DELETE FROM slots WHERE slot_id = ?", (old["live_slot"],))
            self._write_slot(live, name="진행 중", kind="live")
            self._conn.execute("UPDATE games SET live_slot = ? WHERE game_id = ?", (new_live_slot, game_id))
            self._conn.commit()
        return live

    def live_slot_id(self, game_id: str) -> str:
        with self._lock:
            row = self._conn.execute("SELECT live_slot FROM games WHERE game_id = ?", (game_id,)).fetchone()
        if row is None:
            raise StorageError(f"게임이 없습니다: {game_id}")
        return row["live_slot"]

    def all_slot_ids(self, game_id: str) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT slot_id FROM slots WHERE game_id = ?", (game_id,)).fetchall()
        return [r["slot_id"] for r in rows]

    # ------------------------------------------------------------------ clear / delete
    def delete_game(self, game_id: str) -> list[str]:
        """게임과 모든 슬롯을 지운다. 지운 slot_id 목록을 돌려준다(rag 저장소·배경 삭제에 사용)."""
        slot_ids = self.all_slot_ids(game_id)
        with self._lock:
            self._conn.execute("DELETE FROM slots WHERE game_id = ?", (game_id,))
            self._conn.execute("DELETE FROM games WHERE game_id = ?", (game_id,))
            self._conn.commit()
        return slot_ids

    def abandoned_games(self, days: int, now: datetime | None = None) -> list[str]:
        """마지막 접속이 days일보다 오래된 게임 (방치 삭제 dry-run용, PRD §10.4)."""
        cutoff = ((now or datetime.now()) - timedelta(days=days)).isoformat()
        with self._lock:
            rows = self._conn.execute("SELECT game_id FROM games WHERE last_seen < ?", (cutoff,)).fetchall()
        return [r["game_id"] for r in rows]

    def count_case_rows(self, game_id: str) -> int:
        """삭제 검증용: 이 게임에 남은 상태 행 수."""
        with self._lock:
            n1 = self._conn.execute("SELECT COUNT(*) FROM games WHERE game_id = ?", (game_id,)).fetchone()[0]
            n2 = self._conn.execute("SELECT COUNT(*) FROM slots WHERE game_id = ?", (game_id,)).fetchone()[0]
        return int(n1) + int(n2)

    # ------------------------------------------------------------------ history
    def add_history(self, history: ClearHistory) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO clear_history VALUES (?, ?, ?, ?)",
                (history.id, history.player_id, history.model_dump_json(), history.cleared_at.isoformat()),
            )
            self._conn.commit()

    def list_history(self, player_id: str = "player", limit: int = 50) -> list[ClearHistory]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT data_json FROM clear_history WHERE player_id = ? ORDER BY cleared_at DESC LIMIT ?",
                (player_id, limit),
            ).fetchall()
        return [ClearHistory.model_validate_json(r["data_json"]) for r in rows]

    # ------------------------------------------------------------------ internal
    def _write_slot(self, state: GameState, name: str, kind: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO slots VALUES (?, ?, ?, ?, ?, ?, ?)",
            (state.slot_id, state.game_id, state.case_id, name, kind, state.model_dump_json(), datetime.now().isoformat()),
        )

    @staticmethod
    def _require_ids(state: GameState) -> None:
        if not state.case_id or not state.slot_id or not state.game_id:
            raise StorageError("case_id, slot_id, game_id 없이 저장할 수 없습니다 (AGENTS.md 규칙 9)")
