import pytest

from server.rules import offtopic, trust


def test_start_trust(cfg, case):
    ch = {c.id: c for c in case.characters}
    assert trust.start_trust(cfg, ch["b"]) == 60  # main + chatty
    assert trust.start_trust(cfg, ch["a"]) == 40  # main + blunt
    assert trust.start_trust(cfg, ch["c"]) == 40  # minor + normal


def test_events(cfg, state):
    npc = state.npc_states["a"]
    assert trust.apply_event(cfg, npc, "lie_exposed").trust == 35
    assert trust.apply_event(cfg, npc, "cleared").trust == 55
    assert trust.apply_event(cfg, npc, "rude").trust == 35
    assert trust.apply_event(cfg, npc, "bluff_fail").trust == 40
    assert trust.apply_event(cfg, npc, "apology").trust == 55
    assert trust.apply_small_talk(cfg, npc, "chatty").trust == 53
    assert trust.apply_small_talk(cfg, npc, "blunt").trust == 49
    assert trust.apply_small_talk(cfg, npc, "normal").trust == 50
    with pytest.raises(KeyError):
        trust.apply_event(cfg, npc, "x")


def test_clamp(cfg, state):
    low = state.npc_states["a"].model_copy(update={"trust": 5})
    assert trust.apply_event(cfg, low, "rude").trust == 0
    high = state.npc_states["a"].model_copy(update={"trust": 98})
    assert trust.apply_event(cfg, high, "cleared").trust == 100


def test_disclosure_boundary(cfg, case):
    ch = {c.id: c for c in case.characters}
    assert trust.disclosure_policy(cfg, ch["a"], 20) == "normal"
    assert trust.disclosure_policy(cfg, ch["a"], 19) == "terse"
    assert trust.disclosure_policy(cfg, ch["b"], 19) == "key_fact_only"  # 핵심 증인
    assert trust.disclosure_policy(cfg, ch["b"], 20) == "normal"
    off = cfg.model_copy(update={"trust": cfg.trust.model_copy(update={"min_disclosure": False})})
    assert trust.disclosure_policy(off, ch["b"], 0) == "terse"


def test_turn_away_two_actions(cfg, state):
    npc = trust.turn_away(cfg, state.npc_states["a"], 10)
    assert npc.turned_away_until == 12
    assert trust.is_turned_away(npc, 10)
    assert trust.is_turned_away(npc, 11)
    assert not trust.is_turned_away(npc, 12)
    assert not trust.is_turned_away(state.npc_states["a"], 0)


@pytest.mark.parametrize(
    "streak,stage",
    [(0, "none"), (1, "in_character"), (2, "in_character"), (3, "chips_again"), (4, "turn_away"), (5, "turn_away"),
     (6, "rumor"), (9, "rumor")],
)
def test_stage_for(cfg, streak, stage):
    assert offtopic.stage_for(cfg, streak) == stage


def test_register_sequence(cfg):
    streak = 0
    seen = []
    for _ in range(6):
        out = offtopic.register_offtopic(cfg, streak)
        streak = out.streak
        seen.append(out)
    assert [o.stage for o in seen] == ["in_character", "in_character", "chips_again", "turn_away", "turn_away", "rumor"]
    assert [o.reputation_event for o in seen] == [None, None, None, "offtopic_turnaway", "offtopic_turnaway", "offtopic_rumor"]
    assert [o.show_chips for o in seen] == [False, False, True, True, True, True]
    assert [o.turn_away for o in seen] == [False, False, False, True, True, True]
    assert [o.partner_interject for o in seen] == [False, False, False, False, True, True]
    assert seen[5].rumor_candidate and not seen[4].rumor_candidate


def test_decay_and_floor(cfg):
    assert offtopic.register_normal(cfg, 5) == 4
    assert offtopic.register_normal(cfg, 0) == 0
    s = 4
    s = offtopic.register_normal(cfg, s)  # 3
    assert offtopic.register_offtopic(cfg, s).stage == "turn_away"  # 4 번째로 다시


def test_deterministic(cfg):
    assert offtopic.register_offtopic(cfg, 3) == offtopic.register_offtopic(cfg, 3)
