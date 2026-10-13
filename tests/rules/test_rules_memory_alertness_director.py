import pytest

from server.rules import alertness as al
from server.rules import director as dr
from server.rules import memory as mem
from server.schemas import MemoryDoc


def doc(**kw):
    base = dict(id="m1", case_id="c", slot_id="s", owner="b", visibility=["npc:b"], doc_type="observation",
                content="검은 옷을 입은 사람을 봤다", game_time=100, confidence=0.5)
    base.update(kw)
    return MemoryDoc(**base)


# ---------------------------------------------------------------- 기억
def test_initial(cfg):
    assert mem.initial_confidence(cfg, "direct") == 0.9
    assert mem.initial_confidence(cfg, "heard") == 0.6
    assert mem.initial_confidence(cfg, "guess") == 0.3


def test_decay(cfg):
    assert mem.daily_decay(cfg, 0.9, "detail") == pytest.approx(0.837)
    assert mem.daily_decay(cfg, 0.9, "core") == pytest.approx(0.873)
    assert mem.daily_decay(cfg, 0.9, "detail", days=2) == pytest.approx(0.9 * 0.93**2, abs=1e-6)
    assert mem.daily_decay(cfg, 0.21, "detail") == 0.2  # 바닥
    assert mem.daily_decay(cfg, 0.2, "core") == 0.2
    assert mem.daily_decay(cfg, 0.1, "core") == 0.1  # 이미 바닥 아래면 올리지 않음
    assert mem.daily_decay(cfg, 0.9, "core") == mem.daily_decay(cfg, 0.9, "core")


def test_should_contaminate_boundaries(cfg):
    assert mem.should_contaminate(cfg, 0.59, 0.5, True)
    assert not mem.should_contaminate(cfg, 0.6, 0.5, True)
    assert not mem.should_contaminate(cfg, 0.59, 0.49, True)
    assert not mem.should_contaminate(cfg, 0.59, 0.9, False)


def test_contaminate(cfg):
    d = doc(confidence=0.4)
    r = mem.contaminate(cfg, d, "흰 옷이었던 것 같다", "c")
    assert r.contaminated
    assert r.updated.content == "흰 옷이었던 것 같다" and r.updated.confidence == 0.5
    assert r.updated.contaminated_by == ["c"]
    assert r.preserved_original.content == d.content and r.preserved_original.visibility == []
    assert r.preserved_original.id != d.id
    assert d.content == "검은 옷을 입은 사람을 봤다"  # 원본 객체 불변
    r2 = mem.contaminate(cfg, r.updated, "또 다른 소문", "d")
    assert r2.updated.contaminated_by == ["c", "d"]


def test_first_testimony_not_contaminated(cfg):
    d = doc(is_first_testimony=True)
    r = mem.contaminate(cfg, d, "소문", "c")
    assert not r.contaminated and r.updated == d and r.preserved_original is None


@pytest.mark.parametrize(
    "conf,band", [(1.0, "assertive"), (0.75, "assertive"), (0.7499, "hedged"), (0.5, "hedged"), (0.4999, "uncertain"), (0.2, "uncertain")]
)
def test_speech_bands(cfg, conf, band):
    assert mem.speech_band(cfg, conf).band == band


def test_speech_prefix(cfg):
    assert mem.speech_band(cfg, 0.6).prefix == "아마…"
    assert mem.speech_band(cfg, 0.3).prefix == "확실하진 않은데…"


# ---------------------------------------------------------------- 경계 수준
def test_columbo(cfg):
    assert al.columbo_adjustment(cfg, -50) == -10  # 부록 F.10 예시
    assert al.columbo_adjustment(cfg, -100) == -20
    assert al.columbo_adjustment(cfg, -4) == 0
    assert al.columbo_adjustment(cfg, -5) == -1
    assert al.columbo_adjustment(cfg, 0) == 0
    assert al.columbo_adjustment(cfg, 50) == 0


def test_effective_alertness(cfg):
    assert al.effective_alertness(cfg, 30, -50) == 20
    assert al.effective_alertness(cfg, 5, -100) == 0  # 하한
    assert al.effective_alertness(cfg, 99, 0) == 99


def test_alert_events(cfg):
    assert al.apply_event(cfg, 30, "heard_suspicion") == 40
    assert al.apply_event(cfg, 30, "bluff_fail") == 50
    assert al.apply_event(cfg, 30, "repeat_visit") == 45
    assert al.apply_event(cfg, 95, "bluff_fail") == 100
    with pytest.raises(KeyError):
        al.apply_event(cfg, 30, "x")
    assert not al.repeat_visit_triggered(cfg, 1)
    assert al.repeat_visit_triggered(cfg, 2)


def test_night_candidates(cfg):
    assert al.night_action_candidates(cfg, 59, 0, 0.0) == ["keep_routine"]
    assert al.night_action_candidates(cfg, 60, 0, 0.0) == ["hide_evidence"]
    assert al.night_action_candidates(cfg, 79, 0, 0.0) == ["hide_evidence"]
    assert al.night_action_candidates(cfg, 80, 0, 0.0) == ["hide_evidence", "contact", "anonymous_tip"]
    # 콜롬보: 평판 -50 이면 70 -> 유효 60
    assert "hide_evidence" in al.night_action_candidates(cfg, 70, -50, 0.0)
    assert "hide_evidence" not in al.night_action_candidates(cfg, 69, -50, 0.0)
    assert al.night_action_candidates(cfg, 30, 0, 0.5) == ["threat_message"]
    assert al.night_action_candidates(cfg, 30, 0, 0.49) == ["keep_routine"]


# ---------------------------------------------------------------- 연출 감독
def M(**kw):
    return dr.DirectorMetrics(**kw)


def test_no_clue_triggers(cfg):
    assert dr.decide(cfg, M(actions_since_clue=5)) is None
    assert dr.decide(cfg, M(actions_since_clue=6)) == "partner_hint"
    assert dr.decide(cfg, M(actions_since_clue=9)) == "partner_hint"
    assert dr.decide(cfg, M(actions_since_clue=10)) == "event"
    assert dr.decide(cfg, M(actions_since_clue=9, hint_given_in_streak=True)) is None
    assert dr.decide(cfg, M(actions_since_clue=12, event_given_in_streak=True, hint_given_in_streak=True)) is None


def test_same_place(cfg):
    assert dr.decide(cfg, M(consecutive_same_place=3)) is None
    assert dr.decide(cfg, M(consecutive_same_place=4)) == "call_elsewhere"


def test_early_progress(cfg):
    assert dr.decide(cfg, M(day=1, max_sufficiency=0.6)) == "escalate_crisis"
    assert dr.decide(cfg, M(day=1, max_sufficiency=0.59)) is None
    assert dr.decide(cfg, M(day=2, max_sufficiency=0.9)) is None
    assert dr.decide(cfg, M(day=1, max_sufficiency=0.9, fired=["early_progress"])) is None


def test_late_struggle(cfg):
    assert dr.decide(cfg, M(day=3, is_last_day=True, max_sufficiency=0.39)) == "report_nudge"
    assert dr.decide(cfg, M(day=3, is_last_day=True, max_sufficiency=0.4)) is None
    assert dr.decide(cfg, M(day=2, is_last_day=False, max_sufficiency=0.0)) is None
    assert dr.decide(cfg, M(is_last_day=True, max_sufficiency=0.0, fired=["late_struggle"])) is None


def test_cooldown_and_daily_cap(cfg):
    assert dr.decide(cfg, M(actions_since_clue=10, actions_since_last_event=4)) is None
    assert dr.decide(cfg, M(actions_since_clue=10, actions_since_last_event=5)) == "event"
    assert dr.decide(cfg, M(actions_since_clue=10, events_today=2)) == "event"
    assert dr.decide(cfg, M(actions_since_clue=10, events_today=3)) is None


def test_priority(cfg):
    m = M(day=3, is_last_day=True, max_sufficiency=0.1, actions_since_clue=10, consecutive_same_place=5)
    assert dr.decide(cfg, m) == "report_nudge"
    m2 = M(actions_since_clue=10, consecutive_same_place=5)
    assert dr.decide(cfg, m2) == "call_elsewhere"
    assert dr.decide(cfg, m2) == dr.decide(cfg, m2)
