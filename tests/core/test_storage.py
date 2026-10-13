from datetime import datetime, timedelta

import pytest

from server.schemas import ClearHistory
from server.storage.db import GameStore, StorageError


def test_requires_ids(mini_state):
    store = GameStore()
    bad = mini_state.model_copy(update={"slot_id": ""})
    with pytest.raises(StorageError):
        store.create_game(bad)


def test_save_load_activate(mini_state):
    store = GameStore()
    store.create_game(mini_state)
    mini_state.reputation = 5
    store.save_live(mini_state)
    slot = store.snapshot(mini_state, name="수동 저장")
    mini_state.reputation = -40
    store.save_live(mini_state)
    assert store.load_live("g1").reputation == -40
    restored = store.activate_slot("g1", slot, new_live_slot="slot_live2")
    assert restored.reputation == 5
    assert store.load_live("g1").slot_id == "slot_live2"
    assert [s["slot_id"] for s in store.list_slots("g1")] == [slot]


def test_delete_game_leaves_nothing(mini_state):
    store = GameStore()
    store.create_game(mini_state)
    store.snapshot(mini_state, name="a")
    deleted = store.delete_game("g1")
    assert len(deleted) == 2
    assert store.count_case_rows("g1") == 0
    with pytest.raises(StorageError):
        store.load_live("g1")


def test_history_survives_delete(mini_state):
    store = GameStore()
    store.create_game(mini_state)
    store.add_history(ClearHistory(id="h1", player_id="player", case_title="t", theme="x", cleared_at=datetime.now(),
                                   success=True, real_minutes=30, game_days=2, question_count=20))
    store.delete_game("g1")
    assert [h.id for h in store.list_history()] == ["h1"]


def test_abandoned_dry_run(mini_state):
    store = GameStore()
    store.create_game(mini_state)
    assert store.abandoned_games(days=30) == []
    assert store.abandoned_games(days=30, now=datetime.now() + timedelta(days=31)) == ["g1"]
