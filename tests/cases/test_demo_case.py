from server.cases.loader import load_demo_case
from server.cases.verify import obtainable_evidence, verify_case

CHU = "npc_chu"


def test_demo_case_has_no_violations():
    assert [str(v) for v in verify_case(load_demo_case())] == []


def test_demo_case_shape():
    c = load_demo_case()
    assert c.case_id == "demo_db_deleted"
    mains = [x for x in c.characters if x.tier == "main"]
    assert len(mains) == 5 and 1 <= len(c.characters) - len(mains) <= 2
    assert 6 <= len(c.locations) <= 8
    assert sum(1 for x in c.locations if x.unlock_condition is None) == 3
    assert {r.system for r in c.records} >= {"access_log", "server_log", "messenger", "cctv", "call", "bank"}
    assert any("warrant:call" in r.visibility for r in c.records)
    assert 3 <= len(c.documents) <= 4
    assert 4 <= len(c.bluff_claims) <= 6
    assert all(m.slot_id == "__template__" and m.case_id == c.case_id for m in c.initial_memories)
    assert len({x.speech_style for x in c.characters}) == len(c.characters)
    assert c.culprit_ids == [CHU]
    assert {e.id for e in c.evidence if e.public_area} >= {"E7", "E9"}


def test_all_evidence_obtainable():
    c = load_demo_case()
    assert {e.id for e in c.evidence} <= obtainable_evidence(c)


def _codes(c):
    return {v.rule for v in verify_case(c)}


def test_missing_rebuttal_detected():
    c = load_demo_case()
    c.lie_ledger[0].rebuttal_evidence_ids = ["E_nope"]
    assert "R3_LIE" in _codes(c)


def test_innocent_with_all_three_detected():
    c = load_demo_case()
    c.mmo["npc_dba"].opportunity = "서버실에 있었다"
    assert "R1_MMO" in _codes(c)


def test_culprit_missing_element_detected():
    c = load_demo_case()
    c.mmo[CHU].motive = None
    assert "R1_MMO" in _codes(c)


def test_destroyable_without_trace_detected():
    c = load_demo_case()
    next(e for e in c.evidence if e.id == "E1").indirect_traces = []
    assert "R2_TRACE" in _codes(c)


def test_key_evidence_not_destroyable():
    c = load_demo_case()
    next(e for e in c.evidence if e.id == "E3").destroyable = True
    assert "R2_TRACE" in _codes(c)


def test_double_location_detected():
    c = load_demo_case()
    t = c.timeline[0]
    c.timeline.append(t.model_copy(update={"location_id": "loc_roof"}))
    assert "R4_TIMELINE" in _codes(c)


def test_culprit_not_at_scene_detected():
    c = load_demo_case()
    c.incident.time = 600
    assert "R4_TIMELINE" in _codes(c)


def test_appearance_hint_detected():
    c = load_demo_case()
    c.characters[0].appearance["hair"] = "수상한 눈빛의 머리"
    assert "R7_APPEARANCE" in _codes(c)


def test_culprit_name_in_briefing_detected():
    c = load_demo_case()
    c.storyboard["intro"] = "범인은 추성만이다"
    assert "R7_APPEARANCE" in _codes(c)


def test_unreachable_key_evidence_detected():
    c = load_demo_case()
    next(x for x in c.locations if x.id == "loc_lobby").investigate_evidence_ids.remove("E7")
    assert "S_SOLVABLE" in _codes(c)


def test_innocent_full_coverage_detected():
    c = load_demo_case()
    ev = next(e for e in c.evidence if e.id == "E22")
    ev.element_tags = ["opportunity"]  # 고태식: motive(E18) + means(E20) + opportunity
    assert "S_SOLVABLE" in _codes(c)
