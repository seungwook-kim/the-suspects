import pytest

from server.rules import sufficiency as suff
from server.rules import warrant as wr
from server.schemas import Contradiction, NotebookStatement


def _nb(state, ids, contradictions=(), statements=()):
    nb = state.notebook.model_copy(
        update={"evidence_ids": list(ids), "contradictions": list(contradictions), "statements": list(statements)}
    )
    return state.model_copy(update={"notebook": nb})


def test_sufficiency_basic(cfg, case, state):
    assert suff.suspect_sufficiency(cfg, case, state.notebook, "a") == 0.0
    s = _nb(state, ["E1"])
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "a") == pytest.approx(0.45)  # key .3 + opportunity .15
    s = _nb(state, ["E1", "E2", "E3", "E4"])
    # key .3 + opp .15 + motive .15 + means .15 + testimony .05
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "a") == pytest.approx(0.8)
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "b") == 0.0


def test_evidence_must_be_in_notebook_and_linked(cfg, case, state):
    s = _nb(state, ["E5"])
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "a") == 0.0
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "c") == pytest.approx(0.45)


def test_contradiction_and_statements(cfg, case, state):
    st = NotebookStatement(id="s1", npc_id="a", content="x", game_time=0)
    st2 = NotebookStatement(id="s2", npc_id="a", content="y", game_time=0)
    con = Contradiction(id="c1", statement_id="s1", evidence_id="E1", lie_id="L1")
    s = _nb(state, [], [con], [st, st2])
    # 모순 .2 + 모순에 안 쓴 일반 진술 s2 .05  (s1 은 모순에 쓰여 일반 진술로 안 셈)
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "a") == pytest.approx(0.25)


def test_cap_at_one(cfg, case, state):
    sts = [NotebookStatement(id=f"s{i}", npc_id="a", content="x", game_time=0) for i in range(30)]
    s = _nb(state, ["E1", "E2", "E3", "E4"], statements=sts)
    assert suff.suspect_sufficiency(cfg, case, s.notebook, "a") == 1.0


@pytest.mark.parametrize(
    "value,cells", [(0.0, 0), (0.19, 0), (0.2, 1), (0.39, 1), (0.4, 2), (0.6, 3), (0.8, 4), (0.99, 4), (1.0, 5)]
)
def test_gauge(cfg, value, cells):
    assert suff.to_gauge(cfg, value) == cells


def test_gauge_float_error(cfg):
    assert suff.to_gauge(cfg, 0.1 + 0.1 + 0.1 + 0.1 + 0.2) == 3  # 0.6000000000000001
    assert suff.to_gauge(cfg, 0.15 + 0.15 + 0.15 + 0.15) == 3


def test_all_and_gauge_map(cfg, case, state):
    s = _nb(state, ["E1", "E5"])
    allv = suff.all_sufficiency(cfg, case, s.notebook)
    assert set(allv) == {"a", "b", "c", "d"}
    assert suff.gauge_map(cfg, allv)["a"] == 2
    assert suff.covered_elements(case, s.notebook, "a") == {"opportunity"}


# ---------------------------------------------------------------- 영장


def test_warrant_weights(cfg, case, state):
    s = _nb(state, ["E1", "E2", "E3", "E4"])
    w = lambda eid: wr.evidence_weight(cfg, case, s, "a", eid)  # noqa: E731
    assert w("E1") == 0.3  # 기회 태그 + 사건 장소 + 거짓말 반박
    assert w("E2") == 0.2  # 동기
    assert w("E4") == 0.1  # 그 밖
    assert w("E5") == 0.0  # 수첩에 없음
    assert wr.evidence_weight(cfg, case, s, "b", "E2") == 0.1  # 대상과 연결 안 됨 -> 그 밖
    con = Contradiction(id="c1", statement_id="s1", evidence_id="E3", lie_id="L1")
    s2 = _nb(state, ["E3"], [con])
    assert wr.evidence_weight(cfg, case, s2, "a", "E3") == 0.3  # 진술 모순


def test_warrant_threshold_boundary_bank(cfg, case, state):
    s = _nb(state, ["E1", "E2", "E4"])
    d = wr.request_warrant(cfg, case, s, "bank", "a", ["E1", "E2"])
    assert not d.approved and d.score == pytest.approx(0.5) and d.warrant is None and d.action_cost == 2
    d = wr.request_warrant(cfg, case, s, "bank", "a", ["E1", "E2", "E4"])
    assert d.approved and d.score == pytest.approx(0.6)  # 정확히 기준이면 통과
    assert d.warrant.system == "bank" and d.warrant.target_id == "a"


def test_warrant_time_window(cfg, case, state):
    s = _nb(state, ["E1", "E2", "E4"])
    w = wr.request_warrant(cfg, case, s, "call", "a", ["E1", "E2", "E4"]).warrant
    assert w.from_time == case.incident.time - 24 * 60
    assert w.to_time == case.incident.time + 24 * 60
    ws = [w]
    assert wr.has_warrant(ws, "call", "a", w.from_time)
    assert wr.has_warrant(ws, "call", "a", w.to_time)
    assert not wr.has_warrant(ws, "call", "a", w.to_time + 1)
    assert not wr.has_warrant(ws, "call", "b", w.from_time)
    assert not wr.has_warrant(ws, "bank", "a", w.from_time)


def test_warrant_cctv(cfg, case, state):
    s = _nb(state, ["E1", "E4"])
    d = wr.request_warrant(cfg, case, s, "cctv", "a", ["E1", "E4"])
    assert d.approved and d.score == pytest.approx(0.4) and d.threshold == 0.4
    s1 = _nb(state, ["E1"])
    assert not wr.request_warrant(cfg, case, s1, "cctv", "a", ["E1"]).approved  # 0.3 < 0.4
    pub = wr.request_warrant(cfg, case, state, "cctv", "a", [], public_area=True)
    assert pub.approved and not pub.needed and pub.warrant is None


def test_duplicate_cards_counted_once_and_deterministic(cfg, case, state):
    s = _nb(state, ["E1"])
    d1 = wr.request_warrant(cfg, case, s, "cctv", "a", ["E1", "E1"])
    assert d1.score == pytest.approx(0.3)
    assert d1 == wr.request_warrant(cfg, case, s, "cctv", "a", ["E1", "E1"])


def test_unknown_system(cfg, case, state):
    with pytest.raises(ValueError):
        wr.request_warrant(cfg, case, state, "diary", "a", [])
