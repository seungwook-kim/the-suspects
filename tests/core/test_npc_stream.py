"""첫 문장부터 보여 주기: 문장마다 게임 마스터 코드 검사를 통과한 것만 내보낸다 (가짜 실시간 모델로)."""

import re

from server.agents.npc import NPCContext, StreamHooks, answer_stream
from server.llm.client import LLMClient
from server.llm.tracing import Tracer
from server.schemas import GMVerdict, NPCReply, NPCState, RetrievalHit


class StreamStub:
    """조각을 차례로 흘려보내는 가짜 실시간 모델. 다시 만들기(평소 경로)는 정해 둔 답을 낸다."""

    can_stream = True

    def __init__(self, chunks):
        self.chunks, self.tracer, self.redo = chunks, Tracer(), 0
        self.stopped_at = None

    async def structured_stream(self, *, schema, on_partial, meta=None, **_):
        raw = ""
        for i, c in enumerate(self.chunks):
            raw += c
            if (await on_partial(raw)) is False:
                self.stopped_at = i
                return None, raw
        m = re.search(r"\{.*\}", raw, re.S)
        return (schema.model_validate_json(m.group(0)) if m else None), raw

    async def structured(self, **kw):
        self.redo += 1
        return NPCReply(text="다시 만든 답이에요.", emotion="neutral"), False


def _ctx(mini_case):
    ch = next(c for c in mini_case.characters if c.id == "npc_dba")
    hits = [RetrievalHit(id="m1", kind="memory", content="11시에 퇴근했다", score=1)]
    return NPCContext(character=ch, state=NPCState(npc_id="npc_dba", location_id="loc_office"),
                      question="어젯밤 어디 계셨어요?", hits=hits, case_brief="사건: 운영 DB 삭제")


def _run(mini_case, chunks, check=lambda r: GMVerdict(ok=True), llm_check=None):
    shown, emotions = [], []
    hooks = StreamHooks(on_emotion=emotions.append, on_text=shown.append, llm_check=llm_check)
    stub = StreamStub(chunks)
    return stub, shown, emotions, answer_stream(stub, _ctx(mini_case), role="npc", gm_code_check=check,
                                                fallback_line=lambda: "모르겠어요.", hooks=hooks)


async def test_sentences_are_released_one_by_one(mini_case):
    stub, shown, emotions, run = _run(mini_case, ['{"emotion": "nervous", "text": "집에 있었어요.', " 혼자요.",
                                                  ' 진짜예요."', ', "used_ids": ["m1", "모름"]}'])
    reply, _, fb, streamed = await run
    assert emotions == ["nervous"]
    assert shown == ["집에 있었어요.", " 혼자요. 진짜예요."]  # 끝난 문장만, 닫힌 뒤 나머지
    assert reply.text == "".join(shown) and reply.used_ids == ["m1"] and streamed and not fb


async def test_violation_cuts_at_last_passing_sentence(mini_case):
    bad = lambda r: GMVerdict(ok="박정수" not in r.text, violations=["범인 이름"] if "박정수" in r.text else [])  # noqa: E731
    stub, shown, _, run = _run(mini_case, ['{"emotion": "nervous", "text": "집에 있었어요. ', "범인은 박정수예요. ",
                                           '더 할 말 없어요."}'], check=bad)
    reply, _, _, streamed = await run
    assert reply.text == "집에 있었어요." and shown == ["집에 있었어요."] and streamed
    assert stub.stopped_at == 1  # 끊은 뒤 남은 생성은 받지 않는다


async def test_first_sentence_violation_falls_back_to_normal_answer(mini_case):
    bad = lambda r: GMVerdict(ok="박정수" not in r.text, violations=["범인 이름"] if "박정수" in r.text else [])  # noqa: E731
    stub, shown, _, run = _run(mini_case, ['{"emotion": "nervous", "text": "범인은 박정수예요. ', '그렇죠."}'], check=bad)
    reply, _, _, streamed = await run
    assert shown == [] and not streamed and stub.redo == 1 and reply.text == "다시 만든 답이에요."


async def test_llm_check_sentence_is_held_until_checked(mini_case):
    need = lambda r: GMVerdict(ok="11시" not in r.text, needs_llm_check="11시" in r.text,  # noqa: E731
                               triggers=["incident_time"] if "11시" in r.text else [])  # 실제 검사처럼: 신호면 ok=False
    chunks = ['{"emotion": "neutral", "text": "퇴근했어요. ', "11시쯤이요. ", '집에 갔죠."}']

    async def yes(r, v):
        return True

    async def no(r, v):
        return False

    _, shown_ok, _, run_ok = _run(mini_case, chunks, check=need, llm_check=yes)
    reply_ok, _, _, _ = await run_ok
    assert shown_ok == ["퇴근했어요.", " 11시쯤이요. 집에 갔죠."]  # 검사가 통과한 뒤에 나머지
    assert reply_ok.text == "퇴근했어요. 11시쯤이요. 집에 갔죠."

    _, shown_no, _, run_no = _run(mini_case, chunks, check=need, llm_check=no)
    reply_no, _, _, _ = await run_no
    assert shown_no == ["퇴근했어요."] and reply_no.text == "퇴근했어요."


async def test_more_than_three_sentences_are_cut(mini_case):
    _, shown, _, run = _run(mini_case, ['{"emotion": "neutral", "text": "하나. ', "둘. ", "셋. ", "넷. ", '다섯."}'])
    reply, _, _, _ = await run
    assert reply.text == "하나. 둘. 셋."


async def test_without_streaming_it_is_the_normal_answer(mini_case):
    shown = []
    hooks = StreamHooks(on_emotion=lambda e: None, on_text=shown.append)
    reply, _, fb, streamed = await answer_stream(LLMClient(api_key=""), _ctx(mini_case), role="npc",
                                                 gm_code_check=lambda r: GMVerdict(ok=True),
                                                 fallback_line=lambda: "모르겠어요.", hooks=hooks)
    assert not streamed and shown == [] and reply.text and not fb


async def test_signal_sentence_waits_for_real_sources_like_normal_path(mini_case):
    """근거 목록을 모르는 동안은 근거 면제 없이 검사(잡아 둠), 다 쓴 뒤 실제 근거로 평소와 같은 판정."""
    from server.agents.npc import _PENDING_ID

    seen_ids = []

    def check(r):  # 실제 검사처럼: 근거로 댄 기억(m1)에 있는 시각이면 LLM 검사 면제
        seen_ids.append(list(r.used_ids))
        sig = "11시" in r.text and "m1" not in r.used_ids
        return GMVerdict(ok=not sig, needs_llm_check=sig, triggers=["incident_time"] if sig else [])

    calls = []

    async def llm_check(r, v):
        calls.append(r.text)
        return True

    chunks = ['{"emotion": "neutral", "text": "퇴근했어요. ', "11시쯤이요. ", '집에 갔죠."', ', "used_ids": ["m1"]}']
    _, shown, _, run = _run(mini_case, chunks, check=check, llm_check=llm_check)
    reply, _, _, _ = await run
    assert [_PENDING_ID] in seen_ids  # 쓰는 동안은 자리표시 근거로(면제 없음) → 시각 문장은 잡아 둠
    assert shown == ["퇴근했어요.", " 11시쯤이요. 집에 갔죠."] and calls == []  # 근거(m1)가 확인돼 LLM 검사 없이 냄
    assert reply.text == "퇴근했어요. 11시쯤이요. 집에 갔죠."

    chunks_no_src = chunks[:-1] + [', "used_ids": []}']
    calls.clear()
    _, shown2, _, run2 = _run(mini_case, chunks_no_src, check=check, llm_check=llm_check)
    await run2
    assert calls and shown2[-1].endswith("집에 갔죠.")  # 근거가 없으면 평소처럼 LLM 검사를 거친다


async def test_sentence_limit_comes_from_context(mini_case):
    from server.agents.npc import build_prompt

    ctx = _ctx(mini_case)
    ctx.sentences = (1, 2)
    assert "1~2문장" in build_prompt(ctx)[0]
    stub = StreamStub(['{"emotion": "neutral", "text": "하나. ', "둘. ", "셋. ", '넷."}'])
    hooks = StreamHooks(on_emotion=lambda e: None, on_text=lambda t: None)
    reply, _, _, _ = await answer_stream(stub, ctx, role="npc", gm_code_check=lambda r: GMVerdict(ok=True),
                                         fallback_line=lambda: "모르겠어요.", hooks=hooks)
    assert reply.text == "하나. 둘."


async def test_real_gm_check_signal_is_held_not_cut(mini_case):
    """실제 게임 마스터 코드 검사(신호면 ok=False)로: 사건 시각 문장은 끊지 않고 잡아 뒀다가 LLM 검사 뒤 낸다."""
    from server.config import load_game_config
    from server.rules import gm_rules

    cfg = load_game_config()
    t0 = mini_case.incident.time
    hhmm = f"{t0 // 60 % 24}시 {t0 % 60}분"
    checked = []

    async def llm_check(r, v):
        checked.append(v.triggers)
        return True

    chunks = ['{"emotion": "neutral", "text": "퇴근했어요. ', f"{hhmm}쯤엔 집이었어요. ", '그게 다예요."}']
    _, shown, _, run = _run(mini_case, chunks, check=lambda r: gm_rules.check_reply(cfg, mini_case, "npc_dba", r.text),
                            llm_check=llm_check)
    reply, _, _, streamed = await run
    assert streamed and shown[0] == "퇴근했어요." and "incident_time" in checked[0]
    assert reply.text == f"퇴근했어요. {hhmm}쯤엔 집이었어요. 그게 다예요."

