import pytest

from server.rules import bluff
from server.rules._util import stable_unit
from server.schemas import BluffAction, NPCState


def act(target="a", claim="accomplice_confessed", basis=(), subject=None):
    return BluffAction(target_npc=target, claim_id=claim, basis_evidence_ids=list(basis), claim_subject=subject)


def test_formula_example(cfg, case, with_evidence):
    s = with_evidence("E1", "E4")
    r = bluff.resolve_bluff(cfg, case, s, act(basis=["E1", "E4"]))
    f = r.factors
    assert f["E"] == pytest.approx(0.6) and f["P"] == 1.0 and f["V"] == 0.2
    assert f["R"] == 0.5 and f["F"] == 0.0
    assert r.score == pytest.approx(0.45 * 0.6 + 0.2 + 0.15 * 0.2 + 0.1 * 0.5 + 0.1)
    assert r.outcome == "shaken"


def test_E_weights_and_filters(cfg, case, with_evidence):
    s = with_evidence("E1", "E2", "E3", "E4", "E5")
    base = act(basis=["E1"])
    assert bluff.evidence_strength(cfg, case, s, base) == pytest.approx(0.4)
    assert bluff.evidence_strength(cfg, case, s, act(basis=["E3"])) == pytest.approx(0.1)  # 진술
    assert bluff.evidence_strength(cfg, case, s, act(basis=["E2"])) == pytest.approx(0.2)  # 보조
    assert bluff.evidence_strength(cfg, case, s, act(basis=["E5"])) == 0.0  # 다른 대상 증거
    assert bluff.evidence_strength(cfg, case, s, act(basis=["E1", "E1"])) == pytest.approx(0.4)  # 중복 한 번
    assert bluff.evidence_strength(cfg, case, s, act(basis=["E1", "E2", "E3", "E4"])) == pytest.approx(0.9)
    s0 = with_evidence()  # 수첩에 없으면 무효
    assert bluff.evidence_strength(cfg, case, s0, base) == 0.0


def test_E_cap_at_one(cfg, case, with_evidence):
    c = case.model_copy(deep=True)
    for e in c.evidence:
        e.is_key = True
        e.linked_suspects = ["a"]
    s = with_evidence("E1", "E2", "E3", "E4", "E5")
    assert bluff.evidence_strength(cfg, c, s, act(basis=["E1", "E2", "E3"])) == 1.0


def test_claim_subject_used_for_E_and_P(cfg, case, with_evidence):
    s = with_evidence("E1")
    # b 에게 "a 에 대한" 주장을 한다
    r = bluff.resolve_bluff(cfg, case, s, act(target="b", subject="a", basis=["E1"]))
    assert r.factors["E"] == pytest.approx(0.4) and r.factors["P"] == 1.0 and r.factors["V"] == 0.8


def test_partial_truth_P(cfg, case, with_evidence):
    r = bluff.resolve_bluff(cfg, case, with_evidence(), act(claim="half_claim"))
    assert r.factors["P"] == 0.5


def test_confession(cfg, case, with_evidence):
    s = with_evidence("E1", "E2", "E3", "E4")
    r = bluff.resolve_bluff(cfg, case, s, act(basis=["E1", "E2", "E3", "E4"]))
    assert r.outcome == "confession"
    assert r.score == pytest.approx(0.785)


def test_confession_needs_sufficiency(cfg, case, with_evidence):
    s = with_evidence("E1", "E2", "E3", "E4")
    a = act(basis=["E1", "E2", "E3", "E4"])
    assert bluff.resolve_bluff(cfg, case, s, a, sufficiency=0.69).outcome == "shaken"
    assert bluff.resolve_bluff(cfg, case, s, a, sufficiency=0.7).outcome == "confession"


def test_confession_score_boundary(cfg, case, with_evidence):
    s = with_evidence("E1", "E2", "E3", "E4")
    a = act(basis=["E1", "E2", "E3", "E4"])
    exact = bluff.resolve_bluff(cfg, case, s, a).score
    lo = cfg.model_copy(update={"bluff": cfg.bluff.model_copy(update={"confession_score": exact})})
    hi = cfg.model_copy(update={"bluff": cfg.bluff.model_copy(update={"confession_score": exact + 0.001})})
    assert bluff.resolve_bluff(lo, case, s, a).outcome == "confession"
    assert bluff.resolve_bluff(hi, case, s, a).outcome == "shaken"


def test_innocent_never_confesses(cfg, case, with_evidence):
    s = with_evidence("E1", "E2", "E3", "E4")
    r = bluff.resolve_bluff(cfg, case, s, act(target="b", subject="a", basis=["E1", "E2", "E3", "E4"]), sufficiency=1.0)
    assert r.outcome != "confession"


def test_shaken_boundary(cfg, case, with_evidence):
    s = with_evidence("E1", "E4")
    a = act(basis=["E1", "E4"])
    exact = bluff.resolve_bluff(cfg, case, s, a).score
    lo = cfg.model_copy(update={"bluff": cfg.bluff.model_copy(update={"shaken_score": exact})})
    hi = cfg.model_copy(update={"bluff": cfg.bluff.model_copy(update={"shaken_score": exact + 0.001})})
    assert bluff.resolve_bluff(lo, case, s, a).outcome == "shaken"
    assert bluff.resolve_bluff(hi, case, s, a).outcome == "rebutted"


def test_shaken_leaks_hint(cfg, case, with_evidence):
    s = with_evidence("E4", "E2", "E3")
    r = bluff.resolve_bluff(cfg, case, s, act(basis=["E4", "E2", "E3"]))
    assert r.outcome == "shaken" and r.leaked_hint_id == "E1"  # 장부 L1 의 반박 증거, 수첩에 없는 것
    s2 = with_evidence("E1", "E4")
    assert bluff.resolve_bluff(cfg, case, s2, act(basis=["E1", "E4"])).leaked_hint_id is None


def test_instant_fail(cfg, case, with_evidence):
    s = with_evidence("E1", "E2", "E3", "E4")
    r = bluff.resolve_bluff(cfg, case, s, act(target="c", subject="a", basis=["E1", "E2", "E3", "E4"]))
    assert r.outcome == "instant_fail" and r.score == 0.0  # c 는 known_false_by
    r2 = bluff.resolve_bluff(cfg, case, s, act(basis=["E1"]), npc_knows_false=True)
    assert r2.outcome == "instant_fail"


def test_prior_failures_lower_score(cfg, case, with_evidence, state):
    s = with_evidence("E1", "E4")
    s2 = s.model_copy(update={"npc_states": {**s.npc_states, "a": NPCState(npc_id="a", location_id="x", bluff_failures=2)}})
    r0 = bluff.resolve_bluff(cfg, case, s, act(basis=["E1", "E4"]))
    r2 = bluff.resolve_bluff(cfg, case, s2, act(basis=["E1", "E4"]))
    assert r2.factors["F"] == 0.5
    assert r0.score - r2.score == pytest.approx(0.1 * 0.5)
    s4 = s.model_copy(update={"npc_states": {**s.npc_states, "a": NPCState(npc_id="a", location_id="x", bluff_failures=9)}})
    assert bluff.resolve_bluff(cfg, case, s4, act(basis=["E1"])).factors["F"] == 1.0


def test_reputation_factor(cfg, case, with_evidence):
    lo = with_evidence(reputation=-100)
    hi = with_evidence(reputation=100)
    assert bluff.resolve_bluff(cfg, case, lo, act()).factors["R"] == 0.0
    assert bluff.resolve_bluff(cfg, case, hi, act()).factors["R"] == 1.0
    assert bluff.resolve_bluff(cfg, case, with_evidence(reputation=-50), act()).factors["R"] == 0.25


def test_temperament(cfg, case, with_evidence):
    s = with_evidence()
    assert bluff.resolve_bluff(cfg, case, s, act(target="b", subject="b")).factors["V"] == 0.8
    assert bluff.resolve_bluff(cfg, case, s, act(target="c", subject="b", claim="false_claim")).factors["V"] == 0.5


def test_failure_effects_culprit(cfg, case, with_evidence):
    s = with_evidence()
    a = act(claim="false_claim")
    r = bluff.resolve_bluff(cfg, case, s, a)
    assert r.outcome == "rebutted"
    eff = bluff.failure_effects(cfg, case, a, r)
    assert eff.failed and eff.alertness_delta == 20 and eff.trust_event == "bluff_fail"
    s2 = bluff.apply_failure(cfg, case, s, a, r)
    a_state = s2.npc_states["a"]
    assert a_state.trust == 40 and a_state.alertness == 50 and a_state.bluff_failures == 1
    assert s2.reputation == -4 and s2.bluff_failures_today == 1 and s2.had_negative_today
    assert s.npc_states["a"].trust == 50  # 원본 불변


def test_failure_effects_innocent_and_success(cfg, case, with_evidence):
    s = with_evidence()
    a = act(target="b", claim="false_claim")
    r = bluff.resolve_bluff(cfg, case, s, a)
    assert bluff.failure_effects(cfg, case, a, r).alertness_delta == 0
    ok = bluff.resolve_bluff(cfg, case, with_evidence("E1", "E2", "E3", "E4"), act(basis=["E1", "E2", "E3", "E4"]))
    assert not bluff.failure_effects(cfg, case, act(), ok).failed
    assert bluff.apply_failure(cfg, case, s, act(), ok) is s


def test_alertness_clamped(cfg, case, with_evidence, state):
    s = with_evidence()
    s = s.model_copy(update={"npc_states": {**s.npc_states, "a": s.npc_states["a"].model_copy(update={"alertness": 95})}})
    a = act(claim="false_claim")
    r = bluff.resolve_bluff(cfg, case, s, a)
    assert bluff.apply_failure(cfg, case, s, a, r).npc_states["a"].alertness == 100


def test_witness_contamination(cfg, case, with_evidence):
    s = with_evidence()
    a = act(target="b", claim="accomplice_confessed", subject="b")  # P = 0 (truth_by_target b: 0)
    expected = stable_unit(case.case_id, s.slot_id, "b", "accomplice_confessed", 0) < 0.5
    r = bluff.resolve_bluff(cfg, case, s, a, memory_confidence=0.4)
    assert r.contaminates_witness is expected
    assert r == bluff.resolve_bluff(cfg, case, s, a, memory_confidence=0.4)  # 결정적
    # 확률 100% / 0%
    always = cfg.model_copy(update={"bluff": cfg.bluff.model_copy(update={"contaminate_probability": 1.0})})
    never = cfg.model_copy(update={"bluff": cfg.bluff.model_copy(update={"contaminate_probability": 0.0})})
    assert bluff.resolve_bluff(always, case, s, a, memory_confidence=0.49).contaminates_witness
    assert not bluff.resolve_bluff(never, case, s, a, memory_confidence=0.49).contaminates_witness
    # 확신도 경계: 0.5 는 오염 안 됨
    assert not bluff.resolve_bluff(always, case, s, a, memory_confidence=0.5).contaminates_witness
    # 기억 없음 / P != 0 / 범인
    assert not bluff.resolve_bluff(always, case, s, a).contaminates_witness
    assert not bluff.resolve_bluff(always, case, s, act(target="b", subject="a"), memory_confidence=0.1).contaminates_witness
    assert not bluff.resolve_bluff(always, case, s, act(target="a", claim="false_claim"), memory_confidence=0.1).contaminates_witness


def test_contamination_varies_by_claim(cfg, case, with_evidence):
    vals = {stable_unit("c", "s", "b", f"claim{i}", 0) < 0.5 for i in range(20)}
    assert vals == {True, False}  # 50% 확률이 실제로 갈린다


def test_unknown_claim(cfg, case, with_evidence):
    with pytest.raises(KeyError):
        bluff.resolve_bluff(cfg, case, with_evidence(), act(claim="nope"))
