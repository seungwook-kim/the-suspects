import pytest

from server.rules import reputation as rep


def test_event_values(cfg, state):
    assert rep.apply_event(cfg, state, "rude").reputation == -10
    assert rep.apply_event(cfg, state, "meta").reputation == -3
    assert rep.apply_event(cfg, state, "bluff_fail").reputation == -4
    assert rep.apply_event(cfg, state, "stakeout_caught").reputation == -8
    assert rep.apply_event(cfg, state, "deal_exposed").reputation == -10
    assert rep.apply_event(cfg, state, "subquest").reputation == 8
    assert rep.apply_event(cfg, state, "offtopic_turnaway").reputation == -3
    assert rep.apply_event(cfg, state, "offtopic_rumor").reputation == -5


def test_unknown_event(cfg, state):
    with pytest.raises(KeyError):
        rep.apply_event(cfg, state, "nope")


def test_clue_daily_cap(cfg, state):
    s = state
    for _ in range(5):
        s = rep.apply_event(cfg, s, "clue_found")
    assert s.reputation == 5 and s.reputation_gain_today == 5
    s2 = rep.apply_event(cfg, s, "clue_found")
    assert s2.reputation == 5  # 상한
    # 상한 바로 아래(4)에서는 +1 허용
    s4 = state.model_copy(update={"reputation_gain_today": 4})
    assert rep.apply_event(cfg, s4, "clue_found").reputation == 1


def test_negative_sets_flag_and_clamps(cfg, state):
    s = state.model_copy(update={"reputation": -95})
    s = rep.apply_event(cfg, s, "rude")
    assert s.reputation == -100 and s.had_negative_today
    s = state.model_copy(update={"reputation": 98})
    assert rep.apply_event(cfg, s, "subquest").reputation == 100
    assert not rep.apply_event(cfg, state, "subquest").had_negative_today


def test_end_of_day_recovery(cfg, state):
    s = rep.end_of_day(cfg, state)
    assert s.reputation == 3
    bad = rep.apply_event(cfg, state, "rude")
    after = rep.end_of_day(cfg, bad)
    assert after.reputation == -10 and not after.had_negative_today and after.reputation_gain_today == 0
    top = state.model_copy(update={"reputation": 99})
    assert rep.end_of_day(cfg, top).reputation == 100


@pytest.mark.parametrize("value,count", [(0, 0), (-19, 0), (-20, 1), (-49, 1), (-50, 2), (-100, 2)])
def test_rumor_count(cfg, value, count):
    assert rep.rumor_count(cfg, value) == count


@pytest.mark.parametrize(
    "value,title",
    [(100, "믿음직한 형사"), (40, "믿음직한 형사"), (39, None), (0, None), (-19, None), (-20, "동네 괴짜 형사"),
     (-49, "동네 괴짜 형사"), (-50, "말썽꾼 형사"), (-100, "말썽꾼 형사")],
)
def test_titles(cfg, value, title):
    assert rep.title_for(cfg, value) == title


def test_apology_once_per_npc_per_day(cfg, state):
    s = rep.apply_event(cfg, state, "apology", npc_id="a")
    assert s.reputation == 5 and s.npc_states["a"].apologized_day == 1
    s2 = rep.apply_event(cfg, s, "apology", npc_id="a")
    assert s2.reputation == 5
    s3 = rep.apply_event(cfg, s, "apology", npc_id="b")
    assert s3.reputation == 10
    s_next_day = s.model_copy(update={"day": 2})
    assert rep.apply_event(cfg, s_next_day, "apology", npc_id="a").reputation == 10


def test_bluff_rumor_candidate(cfg):
    assert not rep.bluff_rumor_candidate(cfg, 1)
    assert rep.bluff_rumor_candidate(cfg, 2)
