"""출시용 API 연결(OpenAI 호환 주소)을 가짜 HTTP 서버로 확인한다 — 진짜 라이브러리 경로 그대로, 요금 없이.

명령줄 연결(개발용)과 달리 API 연결은 개발 PC에서 키 없이 돌려 볼 수 없어서, 요청 모양과 응답 해석을 여기서 지킨다.
"""

import json

import httpx

from server.llm.client import LLMClient
from server.llm.tracing import Tracer
from server.schemas import NPCReply

CFG = {"active_profile": "dev", "profiles": {"dev": {
    "provider": "api", "base_url": "https://llm.example/v1", "send_effort": False,
    "thinking_off": {"extra_body": {"thinking_mode": "off"}},
    "roles": {"npc": {"model": "m-fast", "max_tokens": 300, "thinking": "off"}},
}}}

ANSWER = '{"emotion": "nervous", "text": "그날은 집에 있었어요. 혼자서요.", "used_ids": ["m1"]}'


def _chunk(content=None, usage=None):
    d = {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m-fast",
         "choices": [] if content is None else [{"index": 0, "delta": {"content": content}, "finish_reason": None}]}
    if usage:
        d["usage"] = usage
    return f"data: {json.dumps(d, ensure_ascii=False)}\n\n"


def _client(handler, seen):
    def wrap(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrap))
    return LLMClient(tracer=Tracer(), models_config=CFG, api_key="k-test", http_async_client=http)


async def test_streamed_answer_arrives_in_pieces_with_usage():
    pieces = [ANSWER[:30], ANSWER[30:45], ANSWER[45:]]
    body = "".join(_chunk(p) for p in pieces)
    body += _chunk(usage={"prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160}) + "data: [DONE]\n\n"
    seen: list[dict] = []
    client = _client(lambda r: httpx.Response(200, text=body, headers={"content-type": "text/event-stream"}), seen)
    assert client.can_stream
    partials: list[str] = []

    async def on_partial(raw):
        partials.append(raw)

    result, raw = await client.structured_stream(role="npc", bucket="npc", schema=NPCReply, system="인물", user="질문",
                                                 on_partial=on_partial)
    assert result is not None and result.text == "그날은 집에 있었어요. 혼자서요." and result.emotion == "nervous"
    assert len(partials) >= 3 and partials[-1] == ANSWER  # 조각마다 지금까지의 원문이 온다
    req = seen[0]
    assert req["stream"] is True and req["model"] == "m-fast" and req["thinking_mode"] == "off"  # 생각 끄기 값 전달
    assert req["messages"][0]["role"] == "system" and "JSON 스키마" in req["messages"][0]["content"]
    rec = client.tracer.records[-1]
    assert rec.ok and rec.extra["stream"] and rec.input_tokens == 120 and rec.output_tokens == 40


async def test_plain_answer_through_api():
    resp = {"id": "c2", "object": "chat.completion", "created": 0, "model": "m-fast",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": ANSWER}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130}}
    seen: list[dict] = []
    client = _client(lambda r: httpx.Response(200, json=resp), seen)
    out, fb = await client.structured(role="npc", bucket="npc", schema=NPCReply, system="인물", user="질문",
                                      fake=lambda: NPCReply(text="가짜"), fallback=lambda: NPCReply(text="대체"))
    assert not fb and out.used_ids == ["m1"] and not seen[0].get("stream")
    assert client.tracer.records[-1].output_tokens == 30


async def test_api_error_is_reported_not_raised():
    seen: list[dict] = []
    client = _client(lambda r: httpx.Response(500, json={"error": {"message": "boom"}}), seen)

    async def on_partial(raw):
        return None

    result, _ = await client.structured_stream(role="npc", bucket="npc", schema=NPCReply, system="s", user="u",
                                               on_partial=on_partial)
    assert result is None and "호출 오류" in client.tracer.records[-1].extra["errors"][0]
