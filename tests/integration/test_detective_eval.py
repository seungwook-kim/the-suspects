"""탐정 자동 플레이 에이전트: 가짜 LLM으로 끝까지 도는 흐름, 보이는 정보만 쓰는지, 호출 상한 (풀이율 자체는 진짜 모델로만 잰다)."""

import inspect

from server.evals import detective
from server.evals.detective import DetectiveStep, Memory, observe, play, render
from server.game.service import GameService


async def test_fake_llm_runs_to_an_ending_without_errors(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    res = await play(svc, max_steps=60)
    # 가짜 봇은 풀이율이 아니라 흐름 점검용이라 어떤 결말이든 좋다. 판마다 인물 순서가 섞여 결과가 달라진다
    assert res.ending in ("success", "escaped", "wrong_accusation", "unfinished")
    assert res.accusations and res.detective_calls >= 2 and not res.errors, res.errors
    assert res.total_calls == len(svc.llm.tracer.records) >= res.detective_calls
    assert "판 1개" in render([res])


async def test_observation_only_contains_player_view(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    gid, view = svc.new_game("demo_db_deleted", {"difficulty": "normal"})
    text = observe(svc.view(gid), Memory())
    case = svc.cases["demo_db_deleted"]
    assert case.incident.summary in text  # 공개된 사건 요약은 보인다
    # 거짓말 장부의 진실·범인 표시는 관찰에 없다 (뷰에 없으니 에이전트에도 없다). 범인 id는 모든 인물처럼 보이는 이름표일 뿐이다
    for lie in case.lie_ledger:
        assert lie.truth not in text
    for marker in ("범인", "culprit", "공범", "is_culprit"):
        assert marker not in text, marker


def test_agent_module_never_touches_case_truth():
    src = inspect.getsource(detective)
    for forbidden in ("culprit_ids", "lie_ledger", "svc.cases", "timeline"):  # 하네스는 엔딩만 읽는다(store.load_live)
        assert forbidden not in src, forbidden


async def test_call_cap_stops_the_game(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    res = await play(svc, max_steps=60, max_calls=3)
    assert "상한" in res.stopped and res.total_calls >= 3


async def test_invalid_actions_are_counted_not_executed(tmp_path):
    svc = GameService(tmp_path, in_memory=True)
    orig = svc.llm.structured

    async def patched(**kw):  # 걸음마다 화면에 없는 장소로 이동하려 한다. 지목은 원래대로
        if kw["schema"] is DetectiveStep:
            return DetectiveStep(action="move", location_id="nowhere"), False
        return await orig(**kw)

    svc.llm.structured = patched
    res = await play(svc, max_steps=8)
    assert res.invalid_steps >= 3 and res.actions == 0  # 무효 행동은 행동을 쓰지 않는다
