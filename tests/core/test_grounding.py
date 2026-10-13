"""근거 있는 발언 면제 (PRD 부록 F.11 v1.7).

이번 턴에 검색된 근거나 제시된 증거에 이미 있는 시각·장소·증거 이름은 게임 마스터 LLM 검사에서 뺀다.
면제가 없으면 사건 시각을 묻는 핵심 질문마다 LLM이 한 번 더 불려 핫 패스 1회 원칙이 깨진다.
"""

import pytest

from server.cases import load_demo_case
from server.config import load_game_config
from server.game.service import ground_verdict
from server.rules import gm_rules


@pytest.fixture(scope="module")
def cfg():
    return load_game_config()


@pytest.fixture(scope="module")
def case():
    return load_demo_case()


def _innocent(case):
    return next(c.id for c in case.characters if c.id not in case.culprit_ids and not c.is_accomplice)


def test_incident_time_grounded_in_own_memory_is_exempt(cfg, case):
    npc = _innocent(case)
    text = "그날 밤 11시 10분쯤 퇴근했어요."
    v = gm_rules.check_reply(cfg, case, npc, text)
    assert "incident_time" in v.triggers
    g = ground_verdict(cfg, case, v, text, "23:05쯤 로비를 지나 퇴근했다")  # ±15분 안
    assert "incident_time" not in g.triggers
    assert g.needs_llm_check is bool(g.triggers)


def test_incident_time_without_grounding_still_checked(cfg, case):
    npc = _innocent(case)
    text = "그날 밤 11시 10분쯤 퇴근했어요."
    v = gm_rules.check_reply(cfg, case, npc, text)
    g = ground_verdict(cfg, case, v, text, "오후 6시에 회의가 끝났다")
    assert "incident_time" in g.triggers and g.needs_llm_check


def test_far_time_in_grounding_does_not_exempt(cfg, case):
    npc = _innocent(case)
    text = "그날 밤 11시 10분쯤 퇴근했어요."
    v = gm_rules.check_reply(cfg, case, npc, text)
    g = ground_verdict(cfg, case, v, text, "22:30에 야식을 먹었다")  # 40분 차이
    assert "incident_time" in g.triggers


def test_presented_key_evidence_is_exempt(cfg, case):
    npc = _innocent(case)
    key = next(e for e in case.evidence if e.is_key)
    text = f"{key.name}요? 처음 보는데요."
    v = gm_rules.check_reply(cfg, case, npc, text)
    assert "key_evidence" in v.triggers
    assert "key_evidence" in ground_verdict(cfg, case, v, text, "").triggers
    assert "key_evidence" not in ground_verdict(cfg, case, v, text, "", presented=key.name).triggers


def test_violations_are_never_exempt(cfg, case):
    npc = _innocent(case)
    text = "11시 5분. " * 10  # 문장 수 초과
    v = gm_rules.check_reply(cfg, case, npc, text)
    assert v.violations
    g = ground_verdict(cfg, case, v, text, "23:05")
    assert g.violations == v.violations and not g.ok
