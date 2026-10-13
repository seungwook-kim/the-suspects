from server.graphs.night import NightDeps, NightLine, NightTalk, run_night
from server.llm.client import LLMClient
from server.schemas import NPCAction, Rumor


def _deps(applied, bad_rumor=False):
    def fake_talk(case, game, a, b):
        r = Rumor(content="형사가 청소원을 의심한대", origin_npc=a, told_by=a, told_to=b,
                  distortion_level=3 if bad_rumor else 1, game_time=game.clock)
        return NightTalk(lines=[NightLine(speaker_id=a, text="들었어요?"), NightLine(speaker_id=b, text="뭘요?")],
                         rumors=[r])

    def validate_rumor(case, r):
        return ["왜곡 단계 초과"] if r.distortion_level > 2 else []

    def end(case, game):
        game.day += 1
        return [{"type": "CUSTOM", "name": "feed", "value": {"text": "아침"}}]

    return NightDeps(
        llm=LLMClient(api_key=""),
        decide_actions=lambda case, game: [NPCAction(npc_id="npc_cleaner", action="hide_evidence")],
        pick_encounters=lambda case, game, acts: [("npc_dba", "npc_cleaner")],
        talk_prompt=lambda case, game, a, b: ("sys", "user"),
        fake_talk=fake_talk, validate_rumor=validate_rumor,
        apply_talk=lambda game, a, b, t: applied.append((a, b, len(t.rumors))),
        apply_actions=lambda case, game, acts: [],
        end_of_night=end,
    )


async def test_night_runs_and_records(mini_case, mini_state):
    applied = []
    game, events = await run_night(mini_case, mini_state, _deps(applied))
    assert applied == [("npc_dba", "npc_cleaner", 1)]
    assert game.day == 2
    assert [e["value"]["step"] for e in events if e.get("name") == "night_progress"] == [1, 2, 3, 4]
    assert game.events_log[-1]["type"] == "night"  # 진실 리플레이용 기록


async def test_invalid_rumor_skips_encounter(mini_case, mini_state):
    applied = []
    deps = _deps(applied, bad_rumor=True)
    await run_night(mini_case, mini_state, deps)
    assert applied == []  # 재시도 후에도 위반 → 그 만남은 건너뜀
    assert deps.llm.tracer.records[-1].fallback_used and deps.llm.tracer.records[-1].attempts == 3
