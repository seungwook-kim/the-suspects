from datetime import date

import pytest

from server.rules import citation, dedup, grade, limits, reversal, skill_learning, speculative
from server.schemas import Evidence


# ---------------------------------------------------------------- 등급
def test_grade_perfect(cfg):
    assert grade.grade_score(cfg, "normal", 20, 0, 0, 1) == 100


def test_grade_penalties(cfg):
    assert grade.grade_score(cfg, "normal", 40, 0, 0, 2) == 100  # 기준선은 감점 없음
    assert grade.grade_score(cfg, "normal", 41, 0, 0, 2) == 99
    assert grade.grade_score(cfg, "normal", 40, 2, 0, 2) == 84
    assert grade.grade_score(cfg, "normal", 40, 0, 2, 2) == 80
    assert grade.grade_score(cfg, "normal", 40, 0, 0, 4) == 90
    assert grade.grade_score(cfg, "normal", 60, 1, 1, 3, True) == 100 - 20 - 8 - 10 - 5 + 5
    assert grade.grade_score(cfg, "hard", 40, 0, 0, 2) == 90  # 어려움 기준 30
    assert grade.grade_score(cfg, "easy", 50, 0, 0, 2) == 100


@pytest.mark.parametrize(
    "score,g", [(100, "S"), (90, "S"), (89, "A"), (75, "A"), (74, "B"), (60, "B"), (59, "C"), (-10, "C")]
)
def test_grade_bands(cfg, score, g):
    assert grade.grade_for(cfg, score) == g


def test_grade_game(cfg, state):
    s = state.model_copy(update={"question_count": 45, "hints_used": 1, "finale_wrong": 0, "day": 3})
    assert grade.grade_game(cfg, s, "normal") == (100 - 5 - 8 - 5, "A")


# ---------------------------------------------------------------- 역할 반전
def _ev(*tags, key=False):
    return Evidence(id="e" + "".join(tags), name="n", kind="record", content="x", element_tags=list(tags), is_key=key)


def test_reversal_arrest(cfg):
    evs = [_ev("motive"), _ev("means"), _ev("opportunity", key=True)]
    s = reversal.player_sufficiency(cfg, evs, 0)
    assert s == pytest.approx(0.15 * 3 + 0.3)  # 0.75
    assert not reversal.is_arrest(cfg, s, evs)
    s2 = reversal.player_sufficiency(cfg, evs, 1)
    assert s2 == pytest.approx(0.95)
    assert reversal.is_arrest(cfg, s2, evs)
    assert not reversal.is_arrest(cfg, s2, evs[:2])  # 세 단계를 다 못 채움


def test_reversal_arrest_threshold_boundary(cfg):
    evs = [_ev("motive"), _ev("means"), _ev("opportunity")]
    assert reversal.is_arrest(cfg, 0.85, evs)
    assert not reversal.is_arrest(cfg, 0.8499, evs)


def test_reversal_win(cfg):
    assert reversal.player_wins(cfg, deadline_reached=True, sufficiency=0.84)
    assert not reversal.player_wins(cfg, deadline_reached=True, sufficiency=0.85)
    assert not reversal.player_wins(cfg, deadline_reached=False, sufficiency=0.1)
    assert reversal.player_wins(cfg, deadline_reached=False, sufficiency=0.9, ai_accused_other=True, sufficiency_on_other=0.6)
    assert not reversal.player_wins(cfg, deadline_reached=False, sufficiency=0.9, ai_accused_other=True, sufficiency_on_other=0.59)
    assert reversal.add_contradictions(cfg, 0.5, 2) == pytest.approx(0.9)
    assert reversal.add_contradictions(cfg, 0.9, 2) == 1.0


# ---------------------------------------------------------------- 추측 생성
def test_speculative_auto_off(cfg):
    st = speculative.SpeculativeStats()
    for _ in range(19):
        st = speculative.record_show(cfg, st, 3, 0)
    assert not st.disabled and speculative.is_enabled(cfg, st)  # 20회 미만은 끄지 않음
    st = speculative.record_show(cfg, st, 3, 0)
    assert st.disabled and not speculative.is_enabled(cfg, st)


def test_speculative_threshold_boundary(cfg):
    ok = speculative.SpeculativeStats()
    bad = speculative.SpeculativeStats()
    for i in range(20):
        ok = speculative.record_show(cfg, ok, 2, 1 if i % 2 else 0)  # 준비 20번 중 10번 씀 = 정확히 0.5
        bad = speculative.record_show(cfg, bad, 2, 1 if i % 2 and i > 1 else 0)  # 9번 = 0.45
    assert speculative.hit_rate(ok) == 0.5 and not ok.disabled
    assert speculative.hit_rate(bad) == 0.45 and bad.disabled


def test_speculative_hit_rate_counts_shows_not_answers(cfg):
    st = speculative.SpeculativeStats()
    for _ in range(20):
        st = speculative.record_show(cfg, st, 2, 1)  # 매번 2개 만들고 1개 씀 (하나 누르면 상태가 바뀜)
    assert speculative.hit_rate(st) == 1.0 and not st.disabled
    assert speculative.discard_rate(st) == 0.5
    assert speculative.discard_rate(speculative.SpeculativeStats()) is None
    empty = speculative.record_show(cfg, speculative.SpeculativeStats(), 0, 0)  # 만든 게 없는 준비는 적중률에서 뺀다
    assert speculative.hit_rate(empty) is None


def test_speculative_window_slides(cfg):
    st = speculative.SpeculativeStats()
    for _ in range(20):
        st = speculative.record_show(cfg, st, 3, 3)
    assert speculative.hit_rate(st) == 1.0
    for _ in range(5):
        st = speculative.record_show(cfg, st, 3, 0)
    assert len(st.shows) == 20 and speculative.hit_rate(st) == pytest.approx(0.75)
    assert speculative.hit_rate(speculative.SpeculativeStats()) is None


def test_speculative_config_off(cfg):
    off = cfg.model_copy(update={"speed": cfg.speed.model_copy(update={"speculative_chips": False})})
    assert not speculative.is_enabled(off, speculative.SpeculativeStats())


# ---------------------------------------------------------------- 상한
@pytest.mark.parametrize(
    "used,v", [(0, "normal"), (2_000_000, "normal"), (2_000_001, "cheap"), (4_000_000, "cheap"), (4_000_001, "blocked")]
)
def test_input_tokens(cfg, used, v):
    assert limits.check_limit(cfg, "input_tokens_per_day", used) == v


def test_other_limits(cfg):
    assert limits.check_limit(cfg, "output_tokens_per_day", 150_001) == "cheap"
    assert limits.check_limit(cfg, "output_tokens_per_day", 300_001) == "blocked"
    assert limits.check_limit(cfg, "case_gen_default_per_day", 5) == "normal"
    assert limits.check_limit(cfg, "case_gen_default_per_day", 6) == "cheap"
    assert limits.check_limit(cfg, "case_gen_default_per_day", 11) == "blocked"
    assert limits.check_limit(cfg, "case_gen_free_per_day", 3) == "normal"
    assert limits.check_limit(cfg, "case_gen_free_per_day", 4) == "cheap"
    assert limits.check_limit(cfg, "case_gen_free_per_day", 7) == "blocked"
    assert limits.check_limit(cfg, "mcp_calls_per_token_per_day", 200) == "normal"
    assert limits.check_limit(cfg, "mcp_calls_per_token_per_day", 401) == "blocked"
    with pytest.raises(KeyError):
        limits.check_limit(cfg, "nope", 1)


def test_per_game_limits(cfg):
    assert limits.can_use_per_game(cfg, "confrontation_per_game", 1)
    assert not limits.can_use_per_game(cfg, "confrontation_per_game", 2)
    assert not limits.can_use_per_game(cfg, "stakeout_per_game", 2)
    assert limits.can_start_game(cfg, 2) and not limits.can_start_game(cfg, 3)
    assert limits.worst("normal", "cheap") == "cheap" and limits.worst("cheap", "blocked", "normal") == "blocked"
    assert limits.worst() == "normal"


# ---------------------------------------------------------------- 반복 방지
FP = {"motive_type": "빚", "trick_type": "밀실", "culprit_role": "경리"}


def test_dedup_fingerprint_priority(cfg):
    hist = [{**FP, "culprit_role": "경비"}, dict(FP)]
    r = dedup.check_duplicate(cfg, dict(FP), hist, [1.0, 0.0], [[0.0, 1.0], [0.0, 1.0]])
    assert r.duplicate and r.reason == "fingerprint" and r.matched_index == 1  # 임베딩이 달라도 지문 우선


def test_dedup_fingerprint_partial_or_empty_not_matched(cfg):
    assert not dedup.check_duplicate(cfg, dict(FP), [{**FP, "trick_type": "독극물"}]).duplicate
    empty = {"motive_type": "", "trick_type": "", "culprit_role": ""}
    assert not dedup.check_duplicate(cfg, empty, [dict(empty)]).duplicate
    assert not dedup.check_duplicate(cfg, {}, [{}]).duplicate


def test_dedup_similarity_boundary(cfg):
    a, b = [1.0, 0.0], [0.85, 0.5]
    s = dedup.cosine(a, b)
    lo = cfg.model_copy(deep=True)
    lo.case_gen.dedup.similarity_threshold = s
    hi = cfg.model_copy(deep=True)
    hi.case_gen.dedup.similarity_threshold = s + 1e-6
    other = {**FP, "trick_type": "다름"}
    r = dedup.check_duplicate(lo, other, [FP], a, [b])
    assert r.duplicate and r.reason == "similarity" and r.similarity == pytest.approx(s)
    assert not dedup.check_duplicate(hi, other, [FP], a, [b]).duplicate


def test_dedup_similarity_default_threshold(cfg):
    other = {**FP, "trick_type": "다름"}
    assert dedup.check_duplicate(cfg, other, [FP], [1.0, 0.0], [[1.0, 0.0]]).reason == "similarity"
    r = dedup.check_duplicate(cfg, other, [FP], [1.0, 0.0], [[0.0, 1.0]])
    assert not r.duplicate and r.similarity == 0.0
    assert not dedup.check_duplicate(cfg, other, [FP]).duplicate  # 임베딩 없으면 건너뜀


def test_dedup_history_window(cfg):
    other = {**FP, "trick_type": "다름"}
    hist = [dict(FP)] + [{"motive_type": f"m{i}", "trick_type": "t", "culprit_role": "r"} for i in range(50)]
    assert not dedup.check_duplicate(cfg, dict(FP), hist).duplicate  # 51번째 이전 것은 비교 안 함
    assert dedup.check_duplicate(cfg, dict(FP), hist[1:] + [dict(FP)]).duplicate
    assert dedup.cosine([0, 0], [1, 0]) == 0.0
    with pytest.raises(ValueError):
        dedup.cosine([1], [1, 2])
    assert other


# ---------------------------------------------------------------- 스킬 학습
M = skill_learning.EvalMetrics


def test_adoption_rate_boundary(cfg):
    assert skill_learning.decide_adoption(cfg, M(success_rate=0.75, cost=10), M(success_rate=0.73, cost=10)).decision == "adopt"
    r = skill_learning.decide_adoption(cfg, M(success_rate=0.75, cost=10), M(success_rate=0.729, cost=10))
    assert r.decision == "keep_previous" and r.reasons == ["success_rate_dropped"]
    assert skill_learning.decide_adoption(cfg, M(success_rate=0.5, cost=10), M(success_rate=0.9, cost=10)).decision == "adopt"


def test_adoption_cost_boundary(cfg):
    assert skill_learning.decide_adoption(cfg, M(success_rate=0.5, cost=10), M(success_rate=0.5, cost=11)).decision == "adopt"
    r = skill_learning.decide_adoption(cfg, M(success_rate=0.5, cost=10), M(success_rate=0.5, cost=11.01))
    assert r.decision == "keep_previous" and r.reasons == ["cost_increased"]
    r = skill_learning.decide_adoption(cfg, M(success_rate=0.9, cost=10), M(success_rate=0.5, cost=20))
    assert set(r.reasons) == {"success_rate_dropped", "cost_increased"}
    assert skill_learning.decide_adoption(cfg, M(success_rate=0.5, cost=10), M(success_rate=0.5, cost=5)).decision == "adopt"


def test_adoption_rollback_off(cfg):
    off = cfg.model_copy(deep=True)
    off.skills_learning.rollback_on_regression = False
    r = skill_learning.decide_adoption(off, M(success_rate=0.9, cost=10), M(success_rate=0.1, cost=10))
    assert r.decision == "adopt" and r.reasons


def test_update_cadence_and_length(cfg):
    assert not skill_learning.can_update(cfg, 9)
    assert skill_learning.can_update(cfg, 10)
    assert not skill_learning.needs_summary(cfg, 1500)
    assert skill_learning.needs_summary(cfg, 1501)


# ---------------------------------------------------------------- 법 조문 인용
ART_TEXT = "제8조 (직장 내 괴롭힘의  금지)\n사용자 또는 근로자는 직장에서의 지위 또는 관계 등의 우위를 이용하여 업무상 적정범위를 넘어 다른 근로자에게 신체적·정신적 고통을 주면 안 된다."
KB = {
    "76조의2": citation.KBArticle(article_no="76조의2", text=ART_TEXT, effective_from=date(2019, 7, 16), effective_to=date(2030, 1, 1)),
    "10조": citation.KBArticle(article_no="10조", text=ART_TEXT, effective_from=date(2020, 1, 1)),
}
QUOTE = "직장에서의 지위 또는 관계 등의 우위를 이용하여"


def test_citation_ok(cfg):
    assert citation.verify_citation(cfg, KB, "76조의2", QUOTE, date(2024, 5, 1)).ok


def test_citation_whitespace_normalized(cfg):
    q = "직장에서의   지위  또는\n관계 등의 우위를 이용하여"
    assert citation.verify_citation(cfg, KB, "76조의2", q, date(2024, 5, 1)).ok
    assert citation.verify_citation(cfg, KB, "76조의2", "괴롭힘의 금지) 사용자 또는 근로자는 직장에서의", date(2024, 5, 1)).ok


def test_citation_failures(cfg):
    d = date(2024, 5, 1)
    assert citation.verify_citation(cfg, KB, "99조", QUOTE, d).failures == ["article_not_found"]
    assert citation.verify_citation(cfg, KB, "76조의2", "직장에서의 지위를 마음대로 이용하여 괴롭힘을 한다면", d).failures == ["quote_not_found"]
    assert citation.verify_citation(cfg, KB, "76조의2", "직장에서의 지위", d).failures == ["quote_too_short"]


def test_citation_quote_length_boundary(cfg):
    q19 = ART_TEXT.replace("  ", " ").replace("\n", " ")[8:27]
    q20 = ART_TEXT.replace("  ", " ").replace("\n", " ")[8:28]
    assert len(q19) == 19 and len(q20) == 20
    assert citation.verify_citation(cfg, KB, "76조의2", q19, date(2024, 1, 1)).failures == ["quote_too_short"]
    assert citation.verify_citation(cfg, KB, "76조의2", q20, date(2024, 1, 1)).ok


def test_citation_effective_dates(cfg):
    assert citation.verify_citation(cfg, KB, "76조의2", QUOTE, date(2019, 7, 16)).ok  # 시행일 당일
    assert citation.verify_citation(cfg, KB, "76조의2", QUOTE, date(2019, 7, 15)).failures == ["not_effective"]
    assert citation.verify_citation(cfg, KB, "76조의2", QUOTE, date(2030, 1, 1)).ok
    assert citation.verify_citation(cfg, KB, "76조의2", QUOTE, date(2030, 1, 2)).failures == ["not_effective"]
    assert citation.verify_citation(cfg, KB, "10조", QUOTE, date(2099, 1, 1)).ok  # 종료일 없음


def test_citation_multiple_failures(cfg):
    r = citation.verify_citation(cfg, KB, "76조의2", "전혀 다른 문장이 길게 이어져서 스무 자를 넘긴다", date(2000, 1, 1))
    assert r.failures == ["quote_not_found", "not_effective"]


def test_citation_blank_after_rewrites(cfg):
    bad = citation.CitationResult(ok=False, failures=["quote_not_found"])
    good = citation.CitationResult(ok=True, failures=[])
    assert not citation.should_leave_blank(cfg, 1, bad)
    assert citation.should_leave_blank(cfg, 2, bad)
    assert not citation.should_leave_blank(cfg, 5, good)
    assert citation.REVIEW_NEEDED == "검토 필요"


def test_citation_sampling_deterministic(cfg):
    assert citation.sampled_for_relevance(cfg, "r1", "76조의2") == citation.sampled_for_relevance(cfg, "r1", "76조의2")
    hits = sum(citation.sampled_for_relevance(cfg, f"r{i}", "10조") for i in range(2000))
    assert 0.15 * 2000 < hits < 0.25 * 2000


# ---------------------------------------------------------------- 엉뚱한 입력 대사
def test_offtopic_lines_vary_by_character_and_turn(cfg):
    from server.rules import offtopic
    from server.schemas import Character

    timid = Character(id="a", name="가", role="r", age=30, face_seed=1, personality="p", speech_style="s", temperament="timid")
    cold = Character(id="b", name="나", role="r", age=30, face_seed=1, personality="p", speech_style="s", temperament="cold")
    assert offtopic.line(cfg, "meta", timid, 0) != offtopic.line(cfg, "meta", cold, 0)  # 성격마다 다르게
    seq = [offtopic.line(cfg, "meta", cold, i) for i in range(3)]
    assert len(set(seq)) == 3  # 연달아 같은 말을 하지 않는다
    assert offtopic.line(cfg, "turn_away", cold, 0) == "더 할 말 없습니다."
    assert offtopic.line(cfg, "없는종류", cold, 0) == "네?"
