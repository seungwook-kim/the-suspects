"""명령줄 모델 공급자: 가짜 명령(파이썬 스크립트)으로 입출력 규약을 확인한다."""

import json
import sys
import textwrap

from pydantic import BaseModel

from server.llm.client import LLMClient
from server.llm.tracing import Tracer


class Reply(BaseModel):
    text: str
    emotion: str


def _cfg(tmp_path, script_body: str) -> dict:
    script = tmp_path / "fake_tool.py"
    script.write_text(textwrap.dedent(script_body), encoding="utf-8")
    return {
        "active_profile": "dev",
        "profiles": {"dev": {
            "provider": "cli",
            "cli": {"command": [sys.executable, str(script), "{model}", "{system_file}", "{schema}"],
                    "cwd": str(tmp_path / "work"), "timeout_s": 30},
            "roles": {"npc": {"model": "test-model", "effort": "low"}},
        }},
    }


async def _ask(client: LLMClient):
    return await client.structured(
        role="npc", bucket="hot", schema=Reply, system="인물을 연기한다.", user="어디 계셨어요?",
        fake=lambda: Reply(text="가짜", emotion="calm"), fallback=lambda: Reply(text="대체", emotion="calm"),
    )


async def test_structured_output_is_parsed(tmp_path):
    cfg = _cfg(tmp_path, """
        import json, sys
        model, system_file, schema = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])
        user = sys.stdin.buffer.read().decode("utf-8")
        system = open(system_file, encoding="utf-8").read()
        assert model == "test-model" and "인물을 연기한다." in system and "text" in schema["properties"]
        out = {"structured_output": {"text": "사무실에 있었어요. " + user[:6], "emotion": "nervous"},
               "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 7}}
        print(json.dumps(out, ensure_ascii=False))
    """)
    client = LLMClient(tracer=Tracer(), models_config=cfg, api_key="")
    assert client.fake_mode is False  # 키가 없어도 명령줄 설정이 있으면 진짜 호출
    reply, used_fallback = await _ask(client)
    assert not used_fallback and reply.emotion == "nervous" and "어디 계셨어" in reply.text  # 표준 입력으로 전달됨
    rec = client.tracer.records[-1]
    assert rec.model == "test-model" and rec.input_tokens == 15 and rec.output_tokens == 7
    assert not list((tmp_path / "work").glob("*.txt"))  # 시스템 프롬프트 임시 파일은 지운다


async def test_tool_error_falls_back(tmp_path):
    cfg = _cfg(tmp_path, """
        import json
        print(json.dumps({"is_error": True, "result": "로그인 필요"}))
    """)
    client = LLMClient(tracer=Tracer(), models_config=cfg, api_key="")
    reply, used_fallback = await _ask(client)
    assert used_fallback and reply.text == "대체"
    assert client.tracer.records[-1].attempts == 3  # 재시도 상한 2회 후 대체 대사


async def test_plain_text_output_with_json_inside(tmp_path):
    cfg = _cfg(tmp_path, """
        print('답: {"text": "몰라요", "emotion": "calm"}')
    """)
    reply, used_fallback = await _ask(LLMClient(tracer=Tracer(), models_config=cfg, api_key=""))
    assert not used_fallback and reply.text == "몰라요"


def test_placeholder_model_stays_fake(tmp_path):
    cfg = _cfg(tmp_path, "print('{}')")
    cfg["profiles"]["dev"]["roles"]["npc"]["model"] = "<cheap-fast-model>"
    assert LLMClient(models_config=cfg, api_key="").fake_mode is True
    assert json.dumps(cfg)  # 설정 자체는 직렬화 가능


async def test_thinking_off_env_reaches_the_tool(tmp_path):
    cfg = _cfg(tmp_path, """
        import json, os, sys
        sys.stdin.buffer.read()
        print(json.dumps({"structured_output": {"text": os.environ.get("TEST_THINK_OFF", "없음"), "emotion": "calm"}}))
    """)
    cfg["profiles"]["dev"]["thinking_off"] = {"env": {"TEST_THINK_OFF": "0"}}
    plain, _ = await _ask(LLMClient(tracer=Tracer(), models_config=cfg, api_key=""))
    assert plain.text == "없음"  # 역할이 생각을 끄지 않으면 환경 변수도 그대로
    cfg["profiles"]["dev"]["roles"]["npc"]["thinking"] = "off"
    off, _ = await _ask(LLMClient(tracer=Tracer(), models_config=cfg, api_key=""))
    assert off.text == "0"


async def test_stream_output_and_kill_on_cancel(tmp_path):
    """명령줄 실시간 출력: 조각마다 받고, 받는 쪽이 취소하면 프로그램을 끝낸다(남은 생성을 버림)."""
    import asyncio
    import time

    done_flag = tmp_path / "finished.txt"
    script = tmp_path / "stream_tool.py"
    script.write_text(textwrap.dedent(f"""
        import json, sys, time
        sys.stdin.buffer.read()
        def ev(t):
            print(json.dumps({{"type": "stream_event", "event": {{"type": "content_block_delta",
                  "delta": {{"type": "text_delta", "text": t}}}}}}), flush=True)
        ev('{{"emotion": "neutral", "text": "집에')
        ev(' 있었어요."}}')
        if "--slow" in sys.argv:
            time.sleep(20)
            open(r"{done_flag}", "w").write("끝까지 돎")
        print(json.dumps({{"type": "result", "usage": {{"input_tokens": 3, "output_tokens": 4}}}}), flush=True)
    """), encoding="utf-8")
    cli = {"command": [sys.executable, str(script)], "stream_command": [sys.executable, str(script)],
           "cwd": str(tmp_path / "work"), "timeout_s": 30}
    cfg = {"active_profile": "dev", "profiles": {"dev": {"provider": "cli", "cli": cli,
                                                         "roles": {"npc": {"model": "m"}}}}}
    client = LLMClient(tracer=Tracer(), models_config=cfg, api_key="")
    assert client.can_stream
    seen = []

    async def on_partial(raw):
        seen.append(raw)

    result, _ = await client.structured_stream(role="npc", bucket="npc", schema=_Emo, system="s", user="u",
                                               on_partial=on_partial)
    assert result.text == "집에 있었어요." and len(seen) == 2
    assert client.tracer.records[-1].output_tokens == 4

    cli["stream_command"] = [sys.executable, str(script), "--slow"]
    t0 = time.perf_counter()
    task = asyncio.ensure_future(client.structured_stream(role="npc", bucket="npc", schema=_Emo, system="s", user="u",
                                                          on_partial=on_partial))
    while len(seen) < 4:
        await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.sleep(0.5)
    assert time.perf_counter() - t0 < 15 and not done_flag.exists()  # 20초 생성을 기다리지 않고 끊었다


class _Emo(BaseModel):
    emotion: str
    text: str
