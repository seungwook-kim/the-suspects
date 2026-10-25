"""상황 목록·다음 사건 만들기 (오프라인, 가짜 LLM만 쓴다)."""

import asyncio
import copy
import json

import pytest

from server.cases import generate_next as GN
from server.cases import situations as S
from server.cases.generate.plan import draw
from server.cases.generate.writer import cast_prompt, fake_concept


@pytest.fixture(scope="module")
def data():
    return S.load_situations()


def test_catalog_is_valid(data):
    assert S.validate(data) == []
    assert len(data["situations"]) >= 24
    assert all(8 <= len(s["roles"]) <= 12 for s in data["situations"])


def test_validate_catches_problems(data):
    bad = copy.deepcopy(data)
    bad["situations"][1]["id"] = bad["situations"][0]["id"]
    bad["situations"][2]["roles"][0]["group"] = "nope"
    bad["situations"][3]["roles"] = bad["situations"][3]["roles"][:3]
    bad["situations"][5]["roles"][0]["needs_new_group"] = "education"  # group과 함께 쓰면 안 된다
    text = " | ".join(S.validate(bad))
    assert "중복" in text and "모르는 직업군" in text and "3명" in text and "하나만" in text


def test_setting_of_and_counts(data, tmp_path):
    assert S.setting_of("demo_db_deleted", data) == "office_it"
    assert S.setting_of("sit_nursing_home_20261030", data) == "nursing_home"
    assert S.setting_of("gen_abc", data) is None
    for name in ("sit_school_20261026", "sit_school_20261027", "demo_db_deleted"):
        (tmp_path / f"{name}.json").write_text("{}", encoding="utf-8")
    c = S.case_counts(data, tmp_path)
    assert c["school"] == 2 and c["office_it"] == 1


def test_next_situation_is_least_recently_evaluated(data, tmp_path):
    runs = tmp_path / "runs.jsonl"
    first = data["situations"][0]["id"]
    assert S.next_situation(str(runs), data)["id"] == first  # 기록 없음
    rows = [{"theme": "demo_db_deleted"}, {"theme": f"sit_{first}_20261026"}]
    runs.write_text("\n".join(json.dumps(r) for r in rows) + "\n{깨짐\n", encoding="utf-8")
    nxt = S.next_situation(str(runs), data)["id"]
    assert nxt not in {first, "office_it"}
    # 사건이 있는 상황만
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "demo_db_deleted.json").write_text("{}", encoding="utf-8")
    assert S.next_situation(str(runs), data, only_with_cases=True, case_dir=tmp_path / "cases")["id"] == "office_it"


def test_rotation_keeps_demo_when_only_demo(data, tmp_path):
    assert S.rotation_case(["demo_db_deleted"], None, data) == "demo_db_deleted"
    runs = tmp_path / "r.jsonl"
    presets = ["demo_db_deleted", "sit_school_20261026", "sit_hospital_20261026"]
    assert S.rotation_case(presets, str(runs), data) == "demo_db_deleted"
    runs.write_text("\n".join(json.dumps({"theme": t}) for t in ["demo_db_deleted", "sit_school_20261026"]) + "\n", encoding="utf-8")
    assert S.rotation_case(presets, str(runs), data) == "sit_hospital_20261026"
    runs.write_text(runs.read_text(encoding="utf-8") + json.dumps({"theme": "sit_hospital_20261026"}) + "\n", encoding="utf-8")
    assert S.rotation_case(presets, str(runs), data) == "demo_db_deleted"
    with pytest.raises(LookupError):
        S.rotation_case([], None, data)


def test_report_and_gaps(data, tmp_path):
    lib = tmp_path / "lib"
    (lib / "cleaning" / "M" / "50s").mkdir(parents=True)
    (lib / "cleaning" / "M" / "50s" / "a.webp").write_bytes(b"x")
    gp = S.gaps(data, lib)
    assert ("cleaning", "F", ) == gp["missing"][[m[:2] for m in gp["missing"]].index(("cleaning", "F"))][:2]
    assert {n for n, _, _ in gp["new"]} == set(data["proposed_groups"])
    text = S.report(data, lib, tmp_path / "nocases")
    assert "상황 27개" in text or f"상황 {len(data['situations'])}개" in text
    assert "새 상자 제안" in text and "school" in text


def test_cast_hint_reaches_cast_prompt(data):
    sit = S.by_id(data)["school"]
    plan = draw("sit_school_x", S.theme_text(sit), {"cast_hint": S.cast_hint(sit)}, seed=1)
    _, user = cast_prompt(plan, fake_concept(plan))
    assert "급식실 조리원" in user and "outfit=chef" in user
    plain = draw("x", "주제", None, seed=1)
    assert "등장 후보 직업" not in cast_prompt(plain, fake_concept(plain))[1]


def test_dry_run_calls_no_model(monkeypatch, capsys, tmp_path):
    import server.llm.client as C

    def boom(*a, **k):
        raise AssertionError("모델 연결을 만들면 안 된다")

    monkeypatch.setattr(C, "LLMClient", boom)
    GN.main(["--dry-run"])
    out = capsys.readouterr().out
    assert "다음에 만들 상황" in out and "만들려면 --confirm" in out
    GN.main([])  # --confirm 없이는 기본이 미리보기
    assert "모델을 부르지 않았다" in capsys.readouterr().out


def test_confirm_refuses_fake_llm_and_second_try_same_day(monkeypatch, tmp_path):
    from server.llm.client import LLMClient

    state = tmp_path / "state.json"
    monkeypatch.setattr(GN, "STATE_PATH", state)
    monkeypatch.setattr(GN, "DEFAULT_CASE_DIR", tmp_path / "cases")
    with pytest.raises(SystemExit) as e:  # 테스트 환경은 가짜 LLM이다
        GN.main(["--confirm"])
    assert "가짜" in str(e.value)
    # 가짜 LLM을 직접 넣어 흐름만 확인
    p = GN.make_plan("library", today="20261026", seed=3)
    llm = LLMClient()
    assert llm.fake_mode
    msg = asyncio.run(GN.generate(p, llm, case_dir=tmp_path / "cases", state_path=state, today="20261026"))
    assert "저장했다" in msg and (tmp_path / "cases" / "sit_library_20261026.json").is_file()
    assert GN.attempts_today(state, "20261026") == 1
    msg2 = asyncio.run(GN.generate(p, llm, case_dir=tmp_path / "cases", state_path=state, today="20261026"))
    assert "이미" in msg2
    with pytest.raises(SystemExit) as e2:
        monkeypatch.setattr("server.cases.generate_next._today", lambda: "20261026")
        GN.main(["--confirm", "--situation", "library"])
    assert "이미" in str(e2.value)


def test_usage_limit_failure_is_refunded_and_retried(monkeypatch, tmp_path):
    """사용량 부족으로 못 만들면 오늘 시도로 치지 않아 풀린 뒤 바로 다시 할 수 있다. 사건 내용이 틀린 실패는 시도로 남는다."""
    from types import SimpleNamespace as NS

    assert GN.is_usage_limit("You've hit your usage limit. resets at 3pm")
    assert GN.is_usage_limit("HTTP 429 Too Many Requests")
    assert not GN.is_usage_limit("검수 실패: 인물이 부족하다")

    state = tmp_path / "state.json"
    plan = {"case_id": "sit_x_20261026", "theme_text": "t", "options": {}, "seed": 1, "situation": {"id": "x"}}

    async def limited(*a, **k):
        return NS(outcome="failed", case=None, message="usage limit reached", problems=[])

    async def invalid(*a, **k):
        return NS(outcome="failed", case=None, message="검수 실패", problems=["인물 부족"])

    import server.cases.generate as G

    monkeypatch.setattr(G, "generate_case", limited)
    out = asyncio.run(GN.generate(plan, None, case_dir=tmp_path, state_path=state, today="20261026"))
    assert out.startswith(GN.RETRY_MARK) and GN.attempts_today(state, "20261026") == 0

    monkeypatch.setattr(G, "generate_case", invalid)
    out = asyncio.run(GN.generate(plan, None, case_dir=tmp_path, state_path=state, today="20261026"))
    assert not out.startswith(GN.RETRY_MARK) and GN.attempts_today(state, "20261026") == 1


def test_portrait_job_continues_same_group_after_quota_stop():
    from server.jobs import daily_portraits as D

    class Lib:
        def records(self):
            return []

    runs = [{"group": "medical", "made": 2, "ts": 1.0, "stopped": "quota", "carry": True}]
    assert D.pick_group(runs, Lib()) == "medical"
    runs = [{"group": "medical", "made": 2, "ts": 1.0, "stopped": "", "carry": False}]
    assert D.pick_group(runs, Lib()) != "medical"
