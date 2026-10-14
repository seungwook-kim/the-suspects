from server.agents.npc import NPCContext, answer, basic_checks, build_prompt
from server.llm.client import LLMClient
from server.schemas import GMVerdict, NPCReply, NPCState, RetrievalHit


def _ctx(mini_case, hits, lies=None):
    ch = next(c for c in mini_case.characters if c.id == "npc_dba")
    return NPCContext(character=ch, state=NPCState(npc_id="npc_dba", location_id="loc_office"),
                      question="어젯밤 11시쯤 어디 계셨어요?", hits=hits, case_brief="사건: 운영 DB 삭제",
                      lie_guidance=lies or [], scene="수사 1일차 10:00, 장소: 사무실")


def test_prompt_has_no_other_npc_secrets(mini_case):
    sys, user = build_prompt(_ctx(mini_case, [RetrievalHit(id="m1", kind="memory", content="11시에 퇴근했다", score=1)]))
    whole = sys + user
    assert "예전에 개발자였다" not in whole  # 청소원의 비밀
    assert "is_culprit" not in whole
    assert "반말 섞음" in sys  # 말투 규칙은 들어감
    assert sys.index("[인물]") < sys.index("[사건 공통 정보]")  # 캐싱 순서: 고정 → 변동
    assert "10:00" not in sys and user.startswith("[지금]\n수사 1일차 10:00")  # 매번 바뀌는 시각은 지시문 밖으로


def test_prompt_system_is_same_when_only_time_and_place_change(mini_case):
    a = _ctx(mini_case, [])
    b = _ctx(mini_case, [])
    b.scene = "수사 2일차 15:30, 장소: 서버실"
    assert build_prompt(a)[0] == build_prompt(b)[0]  # 지시문(캐시되는 앞부분)이 같다


async def test_fake_answer_grounded(mini_case):
    hits = [RetrievalHit(id="m1", kind="memory", content="11시에 퇴근했다", score=1, meta={"confidence": 0.9})]
    reply, verdict, fb = await answer(LLMClient(api_key=""), _ctx(mini_case, hits), role="npc",
                                      gm_code_check=lambda r: GMVerdict(ok=True), fallback_line=lambda: "모르겠어요.")
    assert not fb and reply.used_ids == ["m1"] and "퇴근" in reply.text


async def test_gm_violation_falls_back(mini_case):
    hits = [RetrievalHit(id="m1", kind="memory", content="범인은 박정수다", score=1)]
    reply, verdict, fb = await answer(
        LLMClient(api_key=""), _ctx(mini_case, hits), role="npc",
        gm_code_check=lambda r: GMVerdict(ok="박정수" not in r.text, violations=["권한 밖 인물 언급"]),
        fallback_line=lambda: "그건… 잘 모르겠네요.")
    assert fb and reply.text == "그건… 잘 모르겠네요."


def test_ungrounded_ids_rejected():
    assert basic_checks(NPCReply(text="네.", used_ids=["mX"]), {"m1"})
    assert basic_checks(NPCReply(text="하나. 둘. 셋. 넷.", used_ids=[]), set())
