"""질문 처리 그래프의 갈래별 동작 (가짜 의존성)."""

import pytest

from server.agents.router import SemanticRouter
from server.graphs.turn import TurnDeps, run_turn
from server.llm.client import LLMClient
from server.schemas import GMVerdict, RetrievalHit


@pytest.fixture(scope="module")
def router():
    return SemanticRouter()


def _deps(router, calls):
    def retrieve(game, npc_id, q):
        calls.append("retrieve")
        return [RetrievalHit(id="m1", kind="memory", content="11시에 퇴근했다", score=1.0, meta={"confidence": 0.9})]

    def offtopic(game, npc_id, route):
        calls.append(f"offtopic:{route.kind}")
        game.offtopic_streak += 1
        return {"line": "네?", "events": []}

    def after(game, npc_id, q, reply, hits):
        calls.append("after")
        return {"evidence_ids": [], "contradictions": []}

    return TurnDeps(
        llm=LLMClient(api_key=""), router=router, retrieve=retrieve,
        gm_code_check=lambda case, game, npc, r: GMVerdict(ok=True),
        fallback_line=lambda ch: "모르겠어요.", handle_offtopic=offtopic,
        on_small_talk=lambda game, ch: calls.append("small_talk"),
        after_answer=after, lie_guidance=lambda case, npc, q: [],
        case_brief=lambda case, game: "1일차",
    )


async def test_investigate_path(mini_case, mini_state, router):
    calls = []
    game, events, _ = await run_turn(mini_case, mini_state, "npc_dba", "어젯밤 11시쯤 어디 계셨어요?", _deps(router, calls))
    assert calls == ["retrieve", "after"]
    text = "".join(e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert "퇴근" in text
    assert game.question_count == 1 and len(game.notebook.statements) == 1
    llm_calls = [r for r in _deps(router, []).llm.tracer.records]
    assert llm_calls == []  # 새 클라이언트엔 기록 없음 (기록은 실행한 클라이언트에만)


async def test_one_llm_call_on_hot_path(mini_case, mini_state, router):
    calls = []
    deps = _deps(router, calls)
    await run_turn(mini_case, mini_state, "npc_dba", "서버실 들어간 적 있으세요?", deps)
    llm = [r for r in deps.llm.tracer.records if r.model != "code"]
    assert len(llm) == 1 and llm[0].role == "npc"  # 핫 패스 LLM 1회 원칙


async def test_offtopic_path(mini_case, mini_state, router):
    calls = []
    game, events, _ = await run_turn(mini_case, mini_state, "npc_dba", "ㅁㄴㅇㄹ", _deps(router, calls))
    assert calls == ["offtopic:gibberish"] and game.offtopic_streak == 1


async def test_small_talk_skips_retrieval(mini_case, mini_state, router):
    calls = []
    await run_turn(mini_case, mini_state, "npc_dba", "오늘 점심 뭐 드셨어요?", _deps(router, calls))
    assert calls == ["small_talk"]


async def test_bluff_text_redirects(mini_case, mini_state, router):
    calls = []
    _, events, _ = await run_turn(mini_case, mini_state, "npc_dba", "CCTV에 다 찍혔다니까요", _deps(router, calls))
    assert calls == ["retrieve", "after"]
    starts = [e for e in events if e["type"] == "TEXT_MESSAGE_START"]
    assert starts[0]["role"] == "partner"  # 블러핑 버튼 안내


@pytest.mark.parametrize(
    "verdict, expect_llm_check",
    [
        (GMVerdict(ok=False, needs_llm_check=True, triggers=["incident_time"]), True),  # 근거 없는 핵심 정보
        (GMVerdict(ok=True), False),  # 깨끗한 답
    ],
)
async def test_gm_llm_check_only_when_triggers_remain(mini_case, mini_state, router, verdict, expect_llm_check):
    calls = []
    deps = _deps(router, calls)
    deps.gm_code_check = lambda case, game, npc, r: verdict

    async def gm_llm(case, game, npc, reply, v):
        calls.append("gm_llm")
        return True

    deps.gm_llm_check = gm_llm
    await run_turn(mini_case, mini_state, "npc_dba", "어젯밤 11시쯤 어디 계셨어요?", deps)
    assert ("gm_llm" in calls) is expect_llm_check
    assert calls[-1] == "after"


async def test_gm_llm_rejects_reply_with_fallback_line(mini_case, mini_state, router):
    calls = []
    deps = _deps(router, calls)
    deps.gm_code_check = lambda case, game, npc, r: GMVerdict(ok=False, needs_llm_check=True, triggers=["culprit_name"])

    async def gm_llm(case, game, npc, reply, v):
        return False  # 그 인물이 알 수 없는 정보를 말함

    deps.gm_llm_check = gm_llm
    _, events, _ = await run_turn(mini_case, mini_state, "npc_dba", "어젯밤 11시쯤 어디 계셨어요?", deps)
    text = "".join(e.get("delta", "") for e in events if e["type"] == "TEXT_MESSAGE_CONTENT")
    assert "모르겠어요." in text and "퇴근" not in text  # 걸린 답은 안전한 대체 대사로


async def test_notebook_event_sends_public_statement(mini_case, mini_state, router):
    _, events, _ = await run_turn(mini_case, mini_state, "npc_dba", "어젯밤 11시쯤 어디 계셨어요?", _deps(router, []))
    nb = next(e for e in events if e.get("name") == "notebook")["value"]["added"]
    stmt = nb["statements"][0]
    assert isinstance(stmt, dict) and stmt["content"]  # 계약: 진술은 객체
    assert "m1" not in stmt["source_ids"] and stmt["memory_id"] is None  # 근거 기억 ID는 가림


async def test_turned_away_npc(mini_case, mini_state, router):
    calls = []
    mini_state.npc_states["npc_dba"].turned_away_until = mini_state.action_no + 2
    _, events, _ = await run_turn(mini_case, mini_state, "npc_dba", "어디 계셨어요?", _deps(router, calls))
    assert calls == []
    assert any(e.get("name") == "turn_away" for e in events)
