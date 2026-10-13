import pytest

from server.rules import gm_rules as gm

CLEAN = "그냥 평소처럼 퇴근했어요."


def check(cfg, case, npc, text, **kw):
    return gm.check_reply(cfg, case, npc, text, **kw)


def test_clean(cfg, case):
    v = check(cfg, case, "b", CLEAN)
    assert v.ok and not v.needs_llm_check and v.triggers == [] and v.violations == []


def test_culprit_name(cfg, case):
    v = check(cfg, case, "b", "김철수 씨가 그랬어요.")
    assert "culprit_name" in v.triggers and v.needs_llm_check and not v.ok
    assert "culprit_name" in check(cfg, case, "b", "철수 씨 말이에요?").triggers  # 이름만
    # 범인 본인은 자기 이름을 말해도 권한 안
    assert "culprit_name" not in check(cfg, case, "a", "제 이름은 김철수입니다.").triggers
    # 권한 정보로 범인을 아는 NPC
    kn = gm.NPCKnowledge(npc_id="b", known_character_ids={"a", "b"}, knows_culprit=True)
    assert "culprit_name" not in check(cfg, case, "b", "김철수 씨가 그랬어요.", knowledge=kn).triggers


def test_key_evidence_name_and_id(cfg, case):
    assert "key_evidence" in check(cfg, case, "b", "출입 기록지 봤어요.").triggers
    assert "key_evidence" in check(cfg, case, "b", "E1 이라고 적혀 있던데요.").triggers
    assert "key_evidence" not in check(cfg, case, "b", "약병이 있었나?").triggers  # 비핵심


@pytest.mark.parametrize(
    "text,hit",
    [
        ("밤 열한 시쯤 봤어요.", True),
        ("23:05에 나갔어요.", True),
        ("11시쯤이었나.", True),  # 오전·오후 불명 -> 둘 다 후보
        ("오후 11시 30분이요.", True),
        ("밤 11시 반쯤요.", True),
        ("오후 9시였어요.", True),  # 정확히 -2시간 (경계 포함)
        ("오후 8시 59분이었어요.", False),  # 2시간 1분 전
        ("새벽 1시였어요.", True),  # +2시간 (경계 포함)
        ("새벽 1시 5분이었어요.", False),
        ("오후 3시 반에 만났어요.", False),
        ("3시쯤 갔어요.", False),
        ("세 시 반이요.", False),
        ("밤 열두 시쯤이요.", True),  # 자정
        ("저녁 아홉 시에요.", True),
        ("22시 10분이요.", True),
        ("12:30에 먹었어요.", False),
        ("아침 일찍 갔어요.", False),
    ],
)
def test_time_expressions(cfg, case, text, hit):
    assert ("incident_time" in check(cfg, case, "c", text).triggers) is hit


def test_time_window_configurable(cfg, case):
    narrow = cfg.model_copy(update={"gm": cfg.gm.model_copy(update={"time_window_hours": 1})})
    assert "incident_time" not in check(narrow, case, "c", "오후 9시였어요.").triggers
    assert "incident_time" in check(narrow, case, "c", "오후 10시였어요.").triggers


def test_extract_time_candidates():
    assert gm.extract_time_candidates("오후 3시 반") == [[15 * 60 + 30]]
    assert gm.extract_time_candidates("23:05") == [[23 * 60 + 5]]
    assert gm.extract_time_candidates("밤 열한 시") == [[23 * 60]]
    assert gm.extract_time_candidates("11시") == [[11 * 60, 23 * 60]]
    assert gm.extract_time_candidates("시간이 없어요") == []


def test_incident_location(cfg, case):
    assert "incident_location" in check(cfg, case, "c", "경리팀 사무실에 갔어요.").triggers
    assert "incident_location" not in check(cfg, case, "c", "로비에 있었어요.").triggers


def test_out_of_scope_entities(cfg, case):
    assert "out_of_scope_entity" in check(cfg, case, "c", "정수진 씨랑 얘기했어요.").triggers  # d 는 모르는 인물
    assert "out_of_scope_entity" not in check(cfg, case, "a", "이영희 씨랑 얘기했어요.").triggers  # 관계 있음
    assert "out_of_scope_entity" in check(cfg, case, "a", "차용증을 봤어요.").triggers  # 사물, a 권한 밖
    assert "out_of_scope_entity" not in check(cfg, case, "b", "차용증을 봤어요.").triggers  # npc:b 가시
    assert "out_of_scope_entity" in check(cfg, case, "c", "약병이요.").triggers


def test_sentence_count(cfg, case):
    assert gm.count_sentences("하나. 둘! 셋?") == 3
    assert gm.count_sentences("글쎄요... 잘 모르겠어요.") == 1
    v = check(cfg, case, "c", "하나. 둘. 셋. 넷.")
    assert "sentence_count" in v.violations and not v.ok
    assert check(cfg, case, "c", "하나. 둘. 셋.").violations == []
    assert "empty_reply" in check(cfg, case, "c", "  ").violations


def test_llm_check_modes(cfg, case):
    always = cfg.model_copy(update={"gm": cfg.gm.model_copy(update={"llm_check": "always"})})
    never = cfg.model_copy(update={"gm": cfg.gm.model_copy(update={"llm_check": "never"})})
    assert check(always, case, "c", CLEAN).needs_llm_check
    assert not check(never, case, "b", "김철수 씨가 그랬어요.").needs_llm_check


def test_deterministic(cfg, case):
    t = "김철수 씨가 밤 11시에 경리팀 사무실에서 출입 기록지를 봤어요."
    assert check(cfg, case, "c", t) == check(cfg, case, "c", t)
    assert set(check(cfg, case, "c", t).triggers) >= {"culprit_name", "incident_time", "incident_location", "key_evidence"}


def test_knowledge_for(case):
    kn = gm.knowledge_for(case, "b")
    assert kn.known_character_ids >= {"a", "b", "c"} and "d" not in kn.known_character_ids
    assert kn.known_evidence_ids == {"E2"} and not kn.knows_culprit
    assert gm.knowledge_for(case, "a").knows_culprit


def test_fallback_lines(cfg, case):
    ch = {c.id: c for c in case.characters}
    assert gm.fallback_line(cfg, ch["b"]) == "그, 그건… 잘 모르겠어요."  # timid
    assert gm.fallback_line(cfg, ch["a"]) == "그 질문엔 답하지 않겠습니다."  # cold
    chatty = ch["c"].model_copy(update={"small_talk_style": "chatty"})
    blunt = ch["c"].model_copy(update={"small_talk_style": "blunt"})
    assert gm.fallback_line(cfg, chatty) == "어머, 그 얘긴 나중에 해요~"
    assert gm.fallback_line(cfg, blunt) == "기억 안 납니다."
    assert gm.fallback_line(cfg, ch["c"]) == cfg.gm.fallback_lines["default"]
