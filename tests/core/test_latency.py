import json

from server.llm.client import LLMClient
from server.llm.latency import (load_records, percentile, questions, render_markdown, render_replay, replay,
                                split_prompt, summarize)


def _rec(role, lat, game="g1", ts=0.0, out=0, model="m", prompt=None, bucket="npc", fb=False, node=None, extra=None):
    return {"ts": ts, "role": role, "bucket": bucket, "model": model, "latency_s": lat, "output_tokens": out,
            "game_id": game, "prompt": prompt, "fallback_used": fb, "node": node, "extra": extra or {}}


def test_percentile_nearest_rank():
    v = [3.7, 4.1, 4.2, 4.3, 5.4, 5.6, 7.3, 8.1, 8.3, 14.3]
    assert percentile(v, 50) == 5.4 and percentile(v, 95) == 14.3
    assert percentile([], 50) == 0.0


def test_questions_group_router_retrieval_answer_and_gm_check():
    recs = [_rec("router", 9.1), _rec("retrieval", 0.1, bucket="retrieval"), _rec("npc", 5.2),
            _rec("gm_check", 1.0, bucket="gm"), _rec("retrieval", 0.0, bucket="retrieval"), _rec("npc_minor", 7.3)]
    qs = questions(recs)
    assert [round(q["total"], 1) for q in qs] == [15.4, 7.3]
    assert qs[0]["routed"] and not qs[1]["routed"]


def test_questions_drop_pending_steps_from_another_game():
    qs = questions([_rec("router", 9.0, game="old"), _rec("npc", 2.0, game="new")])
    assert qs[0]["total"] == 2.0 and not qs[0]["routed"]


def test_summarize_and_markdown_against_target():
    recs = [_rec("npc", t, out=200) for t in (2.0, 4.0, 7.0)] + [_rec("night", 6.0, bucket="night")]
    s = summarize(recs)
    assert s["questions"]["n"] == 3 and s["questions"]["over_target"] == 1
    assert s["roles"]["npc"]["p50"] == 4.0 and s["roles"]["night"]["n"] == 1
    md = render_markdown(s)
    assert "p50 4.0초" in md and "| npc | 3 |" in md


def test_load_records_skips_fake_image_broken_and_out_of_range(tmp_path):
    p = tmp_path / "t.jsonl"
    lines = [json.dumps(_rec("npc", 1.0, ts=10)), json.dumps(_rec("npc", 1.0, ts=10, model="fake")),
             json.dumps(_rec("portrait", 8.0, ts=10, bucket="image")), "{끊긴 줄", json.dumps(_rec("npc", 1.0, ts=99))]
    p.write_text("\n".join(lines), encoding="utf-8")
    assert len(load_records(p, until=50)) == 1
    assert len(load_records(p, include_fake=True, until=50)) == 2
    assert load_records(tmp_path / "없음.jsonl") == []


def test_split_prompt():
    assert split_prompt("[system]\n규칙\n[user]\n질문") == ("규칙", "질문")


async def test_replay_resends_recorded_prompts_with_current_client():
    recs = [_rec("npc", 5.0, out=300, prompt="[system]\n규칙\n[user]\n어디 계셨어요?"),
            _rec("npc", 6.0, prompt=None),  # 원문 없는 기록(배포 모드)은 건너뜀
            _rec("router", 9.0, prompt="[system]\n분류\n[user]\n음…"),
            _rec("night", 6.0, prompt="[system]\n밤\n[user]\n…")]  # 다시 보낼 수 없는 역할
    rows = await replay(LLMClient(api_key=""), recs, roles=("npc", "router", "night"), limit=10)
    assert [r["role"] for r in rows] == ["npc", "router"]
    assert rows[0]["before_s"] == 5.0 and rows[0]["out_before"] == 300 and not rows[0]["fallback"]
    assert rows[0]["text"]  # 다시 받은 답 글도 남긴다(속도와 함께 품질을 보려고)
    assert "| npc | 5.0초 |" in render_replay(rows)


def test_speculative_calls_are_not_waited_questions_and_hit_rate_is_reported():
    recs = [_rec("npc", 4.0, node="npc:speculative"), _rec("npc", 4.2, node="npc:speculative"),
            _rec("npc", 0.3, model="prepared", node="npc_prepared"),
            _rec("speculative", 0.0, model="code", node="speculative", extra={"prepared": 2, "used": 1}),
            _rec("npc", 5.0)]
    qs = questions(recs)
    assert [q["total"] for q in qs] == [0.3, 5.0] and qs[0]["prepared"] and not qs[1]["prepared"]
    s = summarize(recs)
    assert s["speculative"] == {"shows": 1, "prepared": 2, "used": 1, "hit_rate": 1.0, "discard_rate": 0.5}
    assert s["roles"]["npc (미리 만듦)"]["n"] == 2 and s["roles"]["npc (미리 만든 답 사용)"]["n"] == 1
    assert "speculative" not in s["roles"]
    assert "적중률 100%" in render_markdown(s) and "버린 비율 50%" in render_markdown(s)


async def test_measure_speculative_with_fake_llm(tmp_path):
    from server.game.service import GameService
    from server.llm.latency import measure_speculative, render_speculative

    svc = GameService(tmp_path, in_memory=True)
    rows = await measure_speculative(svc, rounds=1, read_s=0.0, settle_s=0.0)
    assert [r["mode"] for r in rows] == ["A", "B", "C"] and not any(r["error"] for r in rows)
    assert sum(1 for r in svc.llm.tracer.records if r.model == "prepared") == 2  # B·C는 미리 만든 답을 쓴다
    assert "| C. 0초 읽고 누름 | 1 |" in render_speculative(rows, 0.0)

