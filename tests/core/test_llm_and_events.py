from server.game.events import EventBuilder, json_patch
from server.llm.client import LLMClient
from server.llm.tracing import Tracer
from server.schemas import NPCReply


async def test_fake_mode_valid():
    c = LLMClient(api_key="")
    out, fb = await c.structured(role="npc", bucket="npc", schema=NPCReply, system="s", user="u",
                                 fake=lambda: NPCReply(text="11시엔 1층에 있었어요."),
                                 fallback=lambda: NPCReply(text="기억이 잘 안 나요."))
    assert out.text.startswith("11시") and fb is False
    assert c.tracer.records[-1].bucket == "npc"


async def test_retry_cap_then_fallback():
    calls = {"n": 0}

    def fake():
        calls["n"] += 1
        return NPCReply(text="범인은 박정수예요")

    c = LLMClient(api_key="")
    out, fb = await c.structured(role="npc", bucket="npc", schema=NPCReply, system="s", user="u", fake=fake,
                                 fallback=lambda: NPCReply(text="기억이 잘 안 나요."),
                                 validate=lambda r: ["범인 이름 누출"] if "박정수" in r.text else [],
                                 max_retries=2)
    assert fb is True and out.text == "기억이 잘 안 나요."
    assert calls["n"] == 3  # 첫 시도 + 재시도 2회, 그 이상 없음
    assert c.tracer.records[-1].fallback_used


def test_prod_mode_strips_text(tmp_path):
    t = Tracer(path=tmp_path / "t.jsonl", mode="prod")
    from server.llm.tracing import CallRecord
    t.record(CallRecord(ts=0, role="npc", bucket="npc", model="m", latency_s=0.1, prompt="원문", output="원문"))
    assert "원문" not in (tmp_path / "t.jsonl").read_text(encoding="utf-8")


def test_json_patch_and_text_chunks():
    assert json_patch({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4}) == [
        {"op": "replace", "path": "/b", "value": 3}, {"op": "add", "path": "/c", "value": 4}]
    ev = EventBuilder().text("npc", "npc_dba", "가나다라마바사아자차")
    assert ev[0]["type"] == "TEXT_MESSAGE_START" and ev[-1]["type"] == "TEXT_MESSAGE_END"
    assert "".join(e["delta"] for e in ev if e["type"] == "TEXT_MESSAGE_CONTENT") == "가나다라마바사아자차"
