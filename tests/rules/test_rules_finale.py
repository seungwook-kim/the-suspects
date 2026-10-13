import pytest

from server.rules import finale as fin


def setup(cfg, case, difficulty="normal", accuse="a"):
    st = fin.start_finale(cfg, difficulty)
    return fin.accuse(cfg, case, st, accuse)


@pytest.mark.parametrize("d,lives", [("easy", 5), ("normal", 3), ("hard", 2)])
def test_lives(cfg, d, lives):
    assert fin.start_finale(cfg, d).lives == lives


def test_success_any_order(cfg, case):
    st = setup(cfg, case)
    for stage, eid in [("motive", "E2"), ("opportunity", "E1"), ("means", "E4")]:
        r = fin.present_evidence(cfg, case, st, stage, eid)
        assert r.correct and r.stage_passed and not r.rebuttal
        st = r.state
    assert st.outcome == "success" and st.lives == 3 and st.wrong == 0
    assert fin.ending_of(st) == "success"


def test_not_done_until_three(cfg, case):
    st = setup(cfg, case)
    st = fin.present_evidence(cfg, case, st, "opportunity", "E1").state
    st = fin.present_evidence(cfg, case, st, "means", "E4").state
    assert st.outcome == "ongoing" and fin.ending_of(st) == "none"


def test_wrong_evidence_costs_life(cfg, case):
    st = setup(cfg, case)
    r = fin.present_evidence(cfg, case, st, "opportunity", "E2")  # 동기 증거를 기회 단계에
    assert not r.correct and r.rebuttal and r.state.lives == 2 and r.state.wrong == 1
    r = fin.present_evidence(cfg, case, r.state, "opportunity", "E5")  # 다른 용의자의 증거
    assert r.state.lives == 1
    r = fin.present_evidence(cfg, case, r.state, "means", "nope")  # 없는 증거
    assert r.state.lives == 0 and r.state.outcome == "escaped" and r.state.wrong == 3
    assert fin.ending_of(r.state) == "escaped"
    with pytest.raises(ValueError):
        fin.present_evidence(cfg, case, r.state, "means", "E4")  # 끝난 뒤에는 불가


def test_hard_two_lives(cfg, case):
    st = setup(cfg, case, "hard")
    st = fin.present_evidence(cfg, case, st, "means", "E1").state
    assert st.outcome == "ongoing"
    st = fin.present_evidence(cfg, case, st, "means", "E1").state
    assert st.outcome == "escaped"


def test_last_life_then_correct(cfg, case):
    st = setup(cfg, case)
    st = fin.present_evidence(cfg, case, st, "means", "E1").state
    st = fin.present_evidence(cfg, case, st, "means", "E1").state
    assert st.lives == 1
    st = fin.present_evidence(cfg, case, st, "means", "E4").state
    assert st.lives == 1 and st.passed == ["means"]


def test_owned_evidence_required(cfg, case):
    st = setup(cfg, case)
    r = fin.present_evidence(cfg, case, st, "opportunity", "E1", owned_evidence_ids={"E2"})
    assert not r.correct
    assert fin.present_evidence(cfg, case, st, "opportunity", "E1", owned_evidence_ids={"E1"}).correct


def test_repeat_passed_stage_is_free(cfg, case):
    st = setup(cfg, case)
    st = fin.present_evidence(cfg, case, st, "means", "E4").state
    r = fin.present_evidence(cfg, case, st, "means", "E2")
    assert r.correct and not r.stage_passed and r.state == st


def test_innocent_accusation_flow(cfg, case):
    st = setup(cfg, case, accuse="b")
    assert st.pending_confirmation
    with pytest.raises(ValueError):
        fin.present_evidence(cfg, case, st, "means", "E4")
    wrong = fin.confirm_accusation(st)
    assert wrong.outcome == "wrong_accusation" and fin.ending_of(wrong) == "wrong_accusation" and wrong.lives == 3
    back = fin.retract_accusation(st)
    assert back.accused_id is None and not back.pending_confirmation
    assert not fin.accuse(cfg, case, back, "a").pending_confirmation


def test_confirm_without_pending(cfg, case):
    with pytest.raises(ValueError):
        fin.confirm_accusation(setup(cfg, case))


def test_present_without_accusation_and_bad_stage(cfg, case):
    with pytest.raises(ValueError):
        fin.present_evidence(cfg, case, fin.start_finale(cfg, "easy"), "means", "E4")
    with pytest.raises(ValueError):
        fin.present_evidence(cfg, case, setup(cfg, case), "alibi", "E4")


def test_bluff_disabled(cfg):
    assert fin.bluff_allowed(cfg) is False


def test_deterministic(cfg, case):
    st = setup(cfg, case)
    assert fin.present_evidence(cfg, case, st, "means", "E4") == fin.present_evidence(cfg, case, st, "means", "E4")
