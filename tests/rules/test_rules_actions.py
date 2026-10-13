import pytest

from server.rules import actions


@pytest.mark.parametrize(
    "kind,cost",
    [("move", 1), ("ask", 1), ("bluff", 1), ("warrant", 2), ("confrontation", 3), ("report", 1), ("stakeout", 0), ("hint", 0)],
)
def test_costs(cfg, kind, cost):
    assert actions.action_cost(cfg, kind) == cost


def test_unknown_kind(cfg):
    with pytest.raises(KeyError):
        actions.action_cost(cfg, "fly")


def test_spend_warrant(cfg, state):
    s = actions.spend(cfg, state, "warrant")
    assert s.actions_left == 10 and s.action_no == 2
    assert state.actions_left == 12  # 원본 불변


def test_spend_is_deterministic(cfg, state):
    assert actions.spend(cfg, state, "ask") == actions.spend(cfg, state, "ask")


def test_not_enough_actions(cfg, state):
    s = state.model_copy(update={"actions_left": 2})
    assert actions.can_perform(cfg, s, "confrontation") == (False, "no_actions_left")
    s3 = state.model_copy(update={"actions_left": 3})
    assert actions.can_perform(cfg, s3, "confrontation")[0]
    with pytest.raises(ValueError):
        actions.spend(cfg, s, "confrontation")


def test_zero_cost_actions_with_no_actions_left(cfg, state):
    s = state.model_copy(update={"actions_left": 0})
    h = actions.spend(cfg, s, "hint")
    assert h.hints_used == 1 and h.actions_left == 0 and h.action_no == 0


def test_confrontation_and_stakeout_limits(cfg, state):
    s = state.model_copy(update={"confrontations_used": 1})
    assert actions.can_perform(cfg, s, "confrontation")[0]
    s = actions.spend(cfg, s, "confrontation")
    assert s.confrontations_used == 2
    assert actions.can_perform(cfg, s, "confrontation") == (False, "confrontation_limit")
    st = state.model_copy(update={"stakeouts_used": 2})
    assert actions.can_perform(cfg, st, "stakeout") == (False, "stakeout_limit")
    assert actions.spend(cfg, state, "stakeout").stakeouts_used == 1


def test_days(cfg):
    assert actions.investigation_days(cfg, "hard") == 2
    assert actions.new_day_actions(cfg) == 12
