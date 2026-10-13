"""클라이언트 뷰에 비밀이 새지 않는지 (AGENTS.md 규칙 7) — 가장 중요한 테스트."""

from server.game.masking import IdMasker
from server.game.view import build_view
from server.schemas import Contradiction, NotebookStatement


def _view_json(case, state):
    masker = IdMasker(case, state.id_salt)
    return build_view(case, state, masker).model_dump_json()


def test_view_has_no_culprit_or_secret_fields(mini_case, mini_state):
    s = _view_json(mini_case, mini_state)
    for forbidden in ["is_culprit", "is_accomplice", "secrets", "goals", "lie_ledger", "mmo", "timeline",
                      "예전에 개발자였다", "백업을 안 돌렸다", "해고 원한", "출입카드를 빌림", "들키지 않기",
                      "alertness", "trust"]:
        assert forbidden not in s, forbidden


def test_internal_ids_are_masked(mini_case, mini_state):
    mini_state.notebook.evidence_ids.append("ev_cleaner_card_secret")
    mini_state.notebook.statements.append(
        NotebookStatement(id="t1", npc_id="npc_cleaner", content="1층에 있었어요", game_time=600,
                          memory_id="mem_cleaner_secret", source_ids=["mem_cleaner_secret"]))
    mini_state.notebook.contradictions.append(
        Contradiction(id="c1", statement_id="t1", evidence_id="ev_cleaner_card_secret", lie_id="lie_cleaner_alibi"))
    s = _view_json(mini_case, mini_state)
    assert "ev_cleaner_card_secret" not in s
    assert "lie_cleaner_alibi" not in s
    assert "mem_cleaner_secret" not in s
    assert "claim_cleaner_cctv" not in s
    assert "출입카드 기록" in s  # 발견한 증거의 이름·내용은 보여야 함


def test_masker_roundtrip_and_forgery(mini_case, mini_state):
    m = IdMasker(mini_case, mini_state.id_salt)
    pub = m.out("evidence", "ev_cleaner_card_secret")
    assert m.inn(pub) == "ev_cleaner_card_secret"
    assert m.inn("e_deadbeef00") is None  # 위조 ID 거부
    other = IdMasker(mini_case, "othersalt")
    assert other.out("evidence", "ev_cleaner_card_secret") != pub  # 판마다 다름


def test_locked_locations_hidden(mini_case, mini_state):
    s = _view_json(mini_case, mini_state)
    assert "옥상" not in s
    assert "loc_roof" not in s


def test_exact_numbers_hidden(mini_case, mini_state):
    mini_state.reputation = -37
    mini_state.notebook.sufficiency = {"npc_cleaner": 0.73}
    view = build_view(mini_case, mini_state, IdMasker(mini_case, mini_state.id_salt))
    assert view.sufficiency_gauge == {"npc_cleaner": 3}
    assert view.notebook.sufficiency == {}
    assert view.reputation_band == "동네 괴짜 형사"
    assert "-37" not in view.model_dump_json()
